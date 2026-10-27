"""评分一致性评测 —— 回答「你的 AI 点评准不准」

做法（诚实口径，先说清楚测的是什么）：
  构造「好 / 中 / 差」三档质量的作答（LLM 按指令生成不同质量水准），
  用项目的 practice_service.evaluate_answer 给它们打分，
  再算 AI 分数与「质量档位」的 Spearman 秩相关 + ±10 分命中率。

  → 这测的是 **AI 评分能否稳定区分答案好坏（排序一致性）**，
    不是与真人评委的绝对一致性。若要后者，把真人标注写成 JSONL 传 --human 即可。

  之所以能作为有效信号：如果 AI 连「好答案 > 差答案」都排不对，那它的点评必然不可靠。
  反之排序一致 + 分档间距合理，说明评分 rubric 是灵敏的。

用法：
  python -m interviewace.evaluation.eval_scoring              # 12 题 × 3 档 = 36 次评分
  python -m interviewace.evaluation.eval_scoring --n 20
  python -m interviewace.evaluation.eval_scoring --human human_scores.jsonl
      # human_scores.jsonl 每行 {"question":..., "answer":..., "human_score": 0-100}
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

EVAL_DIR = Path(__file__).resolve().parent
GOLDEN = EVAL_DIR / "golden_interview.json"
REPORT_DIR = EVAL_DIR / "report"
CHECKPOINT = EVAL_DIR / "scoring_eval.checkpoint.jsonl"

# 三档质量的生成指令 + 对应的「预期分数」
LEVELS = [
    ("good", 90, "请写一份**高质量**的面试作答：准确、分点、覆盖原理与权衡，可带例子。"),
    ("medium", 65, "请写一份**中等质量**的作答：方向对但很浅，只提 1-2 个要点，不展开原理。"),
    ("bad", 30, "请写一份**很差**的作答：只有一句模糊的套话，或答非所问，明显不准确。"),
]

GEN_PROMPT = """你是面试作答模拟器。请针对下面的面试题，{instruction}

面试题：{question}

只输出作答正文，不要任何解释、不要标注质量档位。"""


def _gen_answer(question: str, instruction: str) -> str:
    from interviewace.backend.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL
    from openai import OpenAI
    client = OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL)
    r = client.chat.completions.create(
        model=QWEN_MODEL,
        messages=[{"role": "user", "content": GEN_PROMPT.format(instruction=instruction, question=question)}],
        temperature=0.6)
    return (r.choices[0].message.content or "").strip()


def spearman(xs: list[float], ys: list[float]) -> float:
    """Spearman 秩相关系数（无并列时等价于对秩做 Pearson）"""
    n = len(xs)
    if n < 3:
        return 0.0

    def ranks(vals):
        order = sorted(range(n), key=lambda i: vals[i])
        r = [0.0] * n
        for pos, i in enumerate(order):
            r[i] = pos + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    den = (sum((rx[i] - mx) ** 2 for i in range(n)) *
           sum((ry[i] - my) ** 2 for i in range(n))) ** 0.5
    return num / den if den else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=12, help="题目数（×3 档 = 评分次数）")
    ap.add_argument("--human", default="", help="真人标注 JSONL（可选）")
    args = ap.parse_args()

    from interviewace.backend.database.milvus import connect_milvus
    from interviewace.services.practice_service import evaluate_answer
    connect_milvus()

    pairs = []   # (question, answer, expected_score)

    if args.human and Path(args.human).exists():
        # 用真人标注
        for line in Path(args.human).read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                pairs.append((d["question"], d["answer"], d["human_score"]))
        print(f"载入真人标注 {len(pairs)} 条")
        source = "human"
    else:
        golden = [g for g in json.loads(GOLDEN.read_text(encoding="utf-8"))
                  if g.get("tier") == "B"][:args.n]
        print(f"构造 {len(golden)} 题 × {len(LEVELS)} 档 = {len(golden) * len(LEVELS)} 条待评分")
        for g in golden:
            for name, expected, instr in LEVELS:
                try:
                    ans = _gen_answer(g["query"], instr)
                except Exception as e:
                    print(f"  生成失败：{str(e)[:70]}")
                    continue
                if ans:
                    pairs.append((g["query"], ans, expected))
        source = "synthetic"

    done = {}
    if CHECKPOINT.exists():
        for line in CHECKPOINT.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
                done[(d["question"], d["answer"][:60])] = d
            except Exception:
                pass
    fp = CHECKPOINT.open("a", encoding="utf-8")

    ai_scores, expected_scores, rows = [], [], []
    t0 = time.time()
    for i, (q, a, exp) in enumerate(pairs, 1):
        key = (q, a[:60])
        if key in done:
            rec = done[key]
        else:
            try:
                r = evaluate_answer(q, a, level="campus")
            except Exception as e:
                print(f"  [{i}] 评分失败：{str(e)[:70]}")
                continue
            rec = {"question": q, "answer": a, "expected": exp, "ai_score": r.get("score"),
                   "dims": r.get("dimensions", {}), "source": source}
            fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fp.flush()
            done[key] = rec
        if rec.get("ai_score") is not None:
            ai_scores.append(rec["ai_score"])
            expected_scores.append(rec["expected"])
            rows.append(rec)
            print(f"  [{i}/{len(pairs)}] 预期 {rec['expected']} → AI 给 {rec['ai_score']}")
    fp.close()

    if len(rows) < 3:
        print("有效样本不足")
        return

    rho = spearman(expected_scores, ai_scores)
    within10 = sum(1 for r in rows if abs(r["ai_score"] - r["expected"]) <= 10) / len(rows)

    # 分档均值（看 AI 是否把三档拉开了）
    from collections import defaultdict
    by_exp = defaultdict(list)
    for r in rows:
        by_exp[r["expected"]].append(r["ai_score"])
    band = {k: round(sum(v) / len(v), 1) for k, v in sorted(by_exp.items(), reverse=True)}

    report = {
        "samples": len(rows), "source": source,
        "spearman": round(rho, 3), "within_10pt_rate": round(within10, 3),
        "band_means": band, "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    label = "与真人标注" if source == "human" else "与「好/中/差」质量档位"
    lines = ["# AI 评分一致性评测报告", "",
             f"样本 {len(rows)} 条（来源：{'真人标注' if source == 'human' else '构造的三档质量作答'}）",
             f"生成时间：{report['generated_at']}", "",
             "## 结论", "",
             f"- **Spearman 秩相关（{label}）：{rho:.3f}**",
             f"- **±10 分命中率：{within10 * 100:.1f}%**",
             f"- 各档 AI 均分：{band}", "",
             "> 口径说明：本评测衡量的是「AI 评分能否稳定区分作答质量好坏」（排序一致性），"
             "不是与真人评委的绝对分数一致。排序一致且各档拉开，说明评分 rubric 灵敏。", ""]

    # 错判样例：预期高但 AI 给低（或反之）
    mis = [r for r in rows if abs(r["ai_score"] - r["expected"]) > 25][:5]
    if mis:
        lines += ["## 分歧较大的样例（|AI 分 − 预期| > 25）", ""]
        for r in mis:
            lines.append(f"- 预期 {r['expected']} → AI {r['ai_score']}｜{r['question'][:45]}")
    REPORT_DIR.mkdir(exist_ok=True)
    (REPORT_DIR / "scoring_eval.md").write_text("\n".join(lines), encoding="utf-8")
    (REPORT_DIR / "scoring_eval.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                                  encoding="utf-8")
    print("\n" + "\n".join(lines))
    print(f"\n报告已写入 {REPORT_DIR}/scoring_eval.md（耗时 {time.time() - t0:.0f}s）")


if __name__ == "__main__":
    main()
