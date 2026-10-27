"""模拟面试服务：状态机

核心设计：状态存 MySQL，每轮请求独立执行（不用长驻 checkpointer，重启/刷新不丢状态）。
状态机：in_progress → [主问题 1..N] → finished
每题内部：提问 → 作答 → 评分 → decide_next(追问/下一题/结束)

面试时用 LLM 出/选题（RAG 提供真题参考），评分复用 practice_service.evaluate_answer。
"""
import json

from interviewace.backend.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL
from interviewace.backend.database import mysql as db
from interviewace.backend.logger import get_logger
from interviewace.rag.retriever import retrieve_with_meta
from interviewace.services import practice_service, question_selector as qs
from openai import OpenAI

logger = get_logger(__name__)

_client = None


def _llm() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL)
    return _client


# ---------------- 选题 ---------------- #

def _pick_question(session: dict, seq: int) -> dict:
    """从题库选题：域轮转 + 难度递进 + 已问排除"""
    asked = {t["question"] for t in db.list_turns(session["id"])}
    domain = qs.pick_domain(session.get("domains") or [], seq)
    difficulty = qs.target_difficulty(seq, session["num_questions"],
                                      session.get("level") or "campus",
                                      session.get("difficulty_cap", 3))
    q = practice_service.next_question(domain=domain, difficulty=difficulty,
                                       position=session.get("position"),
                                       exclude_titles=list(asked))
    if not q:  # 该域题耗尽 → 放开域重试
        q = practice_service.next_question(domain=None, difficulty=difficulty,
                                           position=session.get("position"),
                                           exclude_titles=list(asked))
    if not q:
        return None
    return {**q, "question_source": "rag"}


def _gen_followup(question: str, answer: str, missing: list[str], kind: str) -> str:
    """LLM 生成追问（澄清式 / 深挖式）"""
    style = ("针对考生答错/遗漏的点，用一个更基础的澄清式追问，引导他补上。"
             if kind == "followup_clarify" else
             "针对考生的正确回答，追问一层原理/权衡/实战踩坑，考察深度。")
    prompt = (f"你是技术面试官。题目：{question}\n考生作答：{answer}\n"
              f"遗漏点：{json.dumps(missing, ensure_ascii=False)}\n\n"
              f"{style}只输出追问的题干一句话，不要多余内容。")
    try:
        resp = _llm().chat.completions.create(
            model=QWEN_MODEL, messages=[{"role": "user", "content": prompt}], temperature=0.5)
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        logger.warning("gen_followup failed: %s", e)
        return "能再展开讲讲刚才的回答吗？"


# ---------------- 面试流程 ---------------- #

def start(user_id: int, position: str, level: str, domains: list[str],
          num_questions: int, difficulty_cap: int = 3) -> dict:
    """开一场面试：建场次 + 出第一题"""
    sid = db.create_interview_session(user_id, position, level, domains,
                                      num_questions, difficulty_cap)
    session = db.get_interview_session(sid)
    q = _pick_question(session, 1)
    if not q:
        raise RuntimeError("题库没有可用题目，请先扩充题库")
    turn_id = db.add_turn(sid, 1, q["title"], question_source=q["question_source"],
                          qa_refs=[{"title": q["title"], "url": q.get("url", "")}])
    return {"interview_id": sid, "seq": 1, "total": num_questions,
            "question": {"turn_id": turn_id, "seq": 1, "text": q["title"],
                         "domain": q.get("domain"), "difficulty": q.get("difficulty"),
                         "is_followup": False, "source": q["question_source"]}}


def submit_answer(session_id: int, turn_id: int, answer: str,
                  user_id: int) -> dict:
    """提交作答 → 评分 → 决定下一步。返回事件载荷（评分 + 追问/下一题/报告）"""
    session = db.get_interview_session(session_id, user_id=user_id)
    if not session or session["status"] != "in_progress":
        raise RuntimeError("面试不存在或已结束")

    turns = db.list_turns(session_id)
    turn = next((t for t in turns if t["id"] == turn_id), None)
    if not turn:
        raise RuntimeError("题目不存在")

    # 评分（RAG 找参考答案 + rubric）
    eval_result = practice_service.evaluate_answer(turn["question"], answer,
                                                   session.get("level") or "campus")
    score = eval_result["score"] or 0
    db.answer_turn(turn_id, answer, score, eval_result["feedback"],
                   eval_result["missing_points"], eval_result["dimensions"])

    seq = turn["seq"]
    followup_no = turn["followup_no"]
    action = qs.decide_next(score, followup_no, seq, session["num_questions"])

    out = {"feedback": {"score": score, "dimensions": eval_result["dimensions"],
                        "feedback": eval_result["feedback"],
                        "missing_points": eval_result["missing_points"],
                        "reference_url": eval_result.get("reference_url", "")},
           "action": action, "seq": seq, "total": session["num_questions"]}

    if action in ("followup_clarify", "followup_deep"):
        fq = _gen_followup(turn["question"], answer, eval_result["missing_points"], action)
        fid = db.add_turn(session_id, seq, fq, question_source="llm",
                          parent_turn_id=turn["id"], followup_no=followup_no + 1)
        out["next"] = {"turn_id": fid, "seq": seq, "text": fq, "is_followup": True,
                       "followup_no": followup_no + 1, "domain": turn.get("domain")}
    elif action == "next_question":
        nq = _pick_question(session, seq + 1)
        if not nq:
            action = "finish"
        else:
            nid = db.add_turn(session_id, seq + 1, nq["title"],
                              question_source=nq["question_source"],
                              qa_refs=[{"title": nq["title"], "url": nq.get("url", "")}])
            db.update_session_progress(session_id, current_seq=seq + 1)
            out["next"] = {"turn_id": nid, "seq": seq + 1, "text": nq["title"],
                           "domain": nq.get("domain"), "difficulty": nq.get("difficulty"),
                           "is_followup": False, "source": nq["question_source"]}

    if action == "finish":
        report = finish(session_id, user_id)
        out["action"] = "finish"
        out["report"] = report

    return out


def finish(session_id: int, user_id: int) -> dict:
    """结束面试 → 生成总评报告"""
    session = db.get_interview_session(session_id, user_id=user_id)
    turns = db.list_turns(session_id)
    main_turns = [t for t in turns if t["followup_no"] == 0 and t["score"] is not None]
    if not main_turns:
        raise RuntimeError("还没有作答记录")

    scores = [t["score"] for t in main_turns]
    avg = round(sum(scores) / len(scores), 1)

    # 四维均分
    dims = {}
    for t in main_turns:
        for k, v in (t.get("dimensions") or {}).items():
            dims.setdefault(k, []).append(v)
    dim_avg = {k: round(sum(v) / len(v), 1) for k, v in dims.items() if v}

    # 按域聚合找薄弱
    from collections import defaultdict
    by_domain = defaultdict(list)
    for t in main_turns:
        refs = t.get("qa_refs") or []
        by_domain[refs[0].get("domain", "") if refs else ""].append(t["score"])
    domain_avg = sorted(
        [{"domain": d or "综合", "avg": round(sum(s) / len(s), 1)} for d, s in by_domain.items()],
        key=lambda x: x["avg"])
    weak = domain_avg[:3]

    # LLM 总评
    summary = ""
    try:
        brief = "\n".join(f"Q{t['seq']}[{t['score']}分]: {t['question'][:40]}"
                          for t in main_turns[:10])
        prompt = (f"你是技术面试官。这是一场面试的逐题得分：\n{brief}\n\n"
                  f"请写一段 100 字左右的总评（优势 + 待提升 + 建议）。")
        resp = _llm().chat.completions.create(
            model=QWEN_MODEL, messages=[{"role": "user", "content": prompt}], temperature=0.4)
        summary = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        logger.warning("interview summary failed: %s", e)

    report = {
        "total_score": avg, "dimensions": dim_avg, "weak_domains": weak,
        "summary": summary,
        "per_question": [{"seq": t["seq"], "question": t["question"], "score": t["score"],
                          "feedback": t["feedback"], "qa_refs": t.get("qa_refs", [])}
                         for t in main_turns],
    }
    db.update_session_progress(session_id, status="finished", total_score=int(avg), report=report)
    return report


def get_snapshot(session_id: int, user_id: int) -> dict:
    """面试快照（刷新恢复现场）"""
    session = db.get_interview_session(session_id, user_id=user_id)
    if not session:
        raise RuntimeError("面试不存在")
    turns = db.list_turns(session_id)
    # 当前待答的题（最后一条未作答的）
    pending = next((t for t in reversed(turns) if t["answer"] is None), None)
    return {"session": session, "turns": turns,
            "current": {"turn_id": pending["id"], "seq": pending["seq"],
                        "text": pending["question"], "is_followup": pending["followup_no"] > 0}
            if pending else None}
