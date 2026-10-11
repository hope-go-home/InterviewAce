"""答题练习服务：抽题 + AI 评分（RAG 提供参考答案依据）

评分稳定性：rubric 结构化 JSON 输出 + temperature=0 + 参考答案必须进裁判上下文。
"""
import json
import random

from interviewace.backend.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL
from interviewace.backend.logger import get_logger
from interviewace.rag.retriever import retrieve_with_meta
from openai import OpenAI

logger = get_logger(__name__)

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL)
    return _client


# ---------------- 抽题 ---------------- #

def next_question(domain: str | None = None, difficulty: int | None = None,
                  position: str | None = None,
                  exclude_titles: list[str] | None = None) -> dict | None:
    """从题库快速抽一道 qa_pair（标量过滤直查，不走向量检索/重排——抽题不需要语义匹配）"""
    batch = random_questions(domain=domain, difficulty=difficulty, position=position,
                             exclude_titles=exclude_titles, n=1)
    return batch[0] if batch else None


def random_questions(domain: str | None = None, difficulty: int | None = None,
                     position: str | None = None, exclude_titles: list[str] | None = None,
                     n: int = 1) -> list[dict]:
    """直接从 Milvus 标量过滤随机抽 n 道 qa_pair（毫秒级，无嵌入/重排）"""
    from pymilvus import Collection
    from interviewace.backend.database.milvus import COLLECTION_NAME, build_filter_expr

    try:
        col = Collection(name=COLLECTION_NAME)
        col.load()
    except Exception as e:
        logger.warning("random_questions load failed: %s", e)
        return []

    expr = build_filter_expr(domain=domain, difficulty=difficulty, position=position)
    base = 'q_type == "qa_pair"'
    expr = f"{base} and {expr}" if expr else base

    try:
        total_rows = col.query(expr=expr, output_fields=["count(*)"])
        total = total_rows[0].get("count(*)") if total_rows else 0
    except Exception as e:
        logger.warning("random_questions count failed: %s", e)
        return []
    if total == 0:
        return []

    exclude = set(exclude_titles or [])
    picked = []
    seen = set()
    # 多试几个随机偏移，凑够 n 条不重复且不在排除集里
    max_offset = max(0, total - 1)
    for _ in range(min(total, 40)):
        if len(picked) >= n:
            break
        off = random.randint(0, max_offset)
        try:
            rows = col.query(expr=expr,
                             output_fields=["title", "domain", "difficulty", "company", "url"],
                             limit=1, offset=off)
        except Exception:
            continue
        if not rows:
            continue
        r = rows[0]
        title = r.get("title", "")
        if not title or title in seen or title in exclude:
            continue
        seen.add(title)
        picked.append({
            "title": title, "domain": r.get("domain", ""),
            "difficulty": r.get("difficulty", 0), "company": r.get("company", ""),
            "url": r.get("url", ""),
        })
    return picked


# ---------------- 评分 ---------------- #

JUDGE_PROMPT = """你是一位严格且专业的技术面试官。请根据【参考答案】评估【考生的作答】。

【题目】{question}
【参考答案】{reference}
【考生作答】{answer}

请输出 JSON（不要 markdown 包裹）：
{{
  "score": 0-100 的整数总分,
  "dimensions": {{"准确性": 0-100, "深度": 0-100, "表达": 0-100}},
  "feedback": "一两句总体点评，指出亮点与不足",
  "missing_points": ["考生遗漏或答错的关键点1", "关键点2"]
}}

评分标准：
- 准确性：作答与参考答案的技术事实是否一致，有无错误
- 深度：是否覆盖要点、有无原理/权衡层面的理解
- 表达：是否条理清晰、分点作答
作答明显偏离题意或几乎为空时 score 应 ≤40。{level_note}"""

_LEVEL_NOTE = {
    "intern": "这是实习级问题，作答抓住核心概念即可，不必苛求深度。",
    "campus": "这是校招级问题，要求概念准确 + 一定的原理理解。",
    "social": "这是社招级问题，要求原理 + 权衡 + 实战深度，评分从严。",
}


def evaluate_answer(question: str, answer: str, level: str = "campus") -> dict:
    """检索参考答案 → LLM 评分。返回结构化评分结果。

    带缓存：同一 (题目, 作答, 级别) 重复提交直接命中（评分是 temperature=0 的确定性调用）
    """
    from interviewace.backend.cache import hash_key, llm_cache
    ck = hash_key("eval", question, answer, level)
    cached = llm_cache.get(ck)
    if cached is not None:
        logger.info("evaluate_answer cache_hit q=%s", question[:40])
        return cached

    # 1. 检索该题的参考答案（RAG 提供评分依据）
    reference = ""
    ref_url = ""
    try:
        result = retrieve_with_meta(question, top_k=3, allow_fallback=True)
        if result.sources:
            best = result.sources[0]
            reference = best.parent_text
            ref_url = best.url
    except Exception as e:
        logger.warning("evaluate_answer retrieve failed: %s", e)

    if not reference:
        reference = "（题库未收录该题参考答案，请基于你的专业判断评分）"

    # 2. LLM 评分（temperature=0，rubric JSON）
    prompt = JUDGE_PROMPT.format(
        question=question, reference=reference[:2500], answer=answer[:2500],
        level_note=_LEVEL_NOTE.get(level, _LEVEL_NOTE["campus"]),
    )
    try:
        resp = _get_client().chat.completions.create(
            model=QWEN_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0,
        )
        data = json.loads(resp.choices[0].message.content or "{}")
    except Exception as e:
        logger.warning("evaluate_answer llm failed: %s", e)
        data = {}

    score = data.get("score")
    try:
        score = max(0, min(100, int(score)))
    except (TypeError, ValueError):
        score = None

    out = {
        "score": score,
        "dimensions": data.get("dimensions", {}),
        "feedback": data.get("feedback", ""),
        "missing_points": data.get("missing_points", []),
        "reference_answer": reference,
        "reference_url": ref_url,
    }
    llm_cache.put(ck, out)
    return out
