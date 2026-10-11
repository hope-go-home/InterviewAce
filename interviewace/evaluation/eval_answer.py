"""生成质量评测（LLM-as-Judge）

对一批问题跑「检索 → 生成 → 裁判打分」，评估：
  - correctness   正确性（1-5）
  - faithfulness  忠实度（答案是否 grounded 于检索到的资料，1-5）
  - hallucination 是否出现资料未支撑的编造（bool）

口径说明：裁判模型与生成模型不同（JUDGE_MODEL vs QWEN_MODEL），避免「自己判自己」。

用法：
  python -m interviewace.evaluation.eval_answer --n 30
  python -m interviewace.evaluation.eval_answer --n 30 --tier B
"""
import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

EVAL_DIR = Path(__file__).resolve().parent
GOLDEN = EVAL_DIR / "golden_interview.json"
REPORT_DIR = EVAL_DIR / "report"
CHECKPOINT = EVAL_DIR / "answer_eval.checkpoint.jsonl"

GEN_PROMPT = """你是一位技术面试官。请基于下面的参考资料回答用户问题。

<参考资料>
{context}
</参考资料>

用户问题：{question}

要求：分点作答、准确、必要时给例子。资料不足时明确说明，不要编造。"""

JUDGE_PROMPT = """你是严格的评测裁判。请评估下面这个回答的质量。

【问题】{question}
【参考资料】（回答本应基于这些资料）
{context}
【待评估回答】
{answer}

从三个维度评估：
1. correctness（1-5）：技术内容是否正确
2. faithfulness（1-5）：回答中的事实是否都能在参考资料中找到支撑（5=全部有支撑，1=大量无支撑）
3. hallucination（true/false）：是否出现参考资料未提及、且无法从常识确定的编造内容

严格输出 JSON：{{"correctness": int, "faithfulness": int, "hallucination": bool, "reason": "一句话理由"}}"""


def _generate(question: str, context: str) -> str:
    from interviewace.backend.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL
    from openai import OpenAI
    client = OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL)
    r = client.chat.completions.create(
        model=QWEN_MODEL,
        messages=[{"role": "user", "content": GEN_PROMPT.format(context=context, question=question)}],
        temperature=0.3)
    return (r.choices[0].message.content or "").strip()


def _judge(question: str, context: str, answer: str) -> dict:
    from interviewace.backend.config import JUDGE_API_KEY, JUDGE_BASE_URL, JUDGE_MODEL
    from openai import OpenAI
    client = OpenAI(api_key=JUDGE_API_KEY, base_url=JUDGE_BASE_URL)
    r = client.chat.completions.create(
        model=JUDGE_MODEL,
        messages=[{"role": "user", "content": JUDGE_PROMPT.format(
            question=question, context=context[:3000], answer=answer[:2500])}],
        response_format={"type": "json_object"}, temperature=0)
    return json.loads(r.choices[0].message.content or "{}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--tier", default="B")
    args = ap.parse_args()

    if not GOLDEN.exists():
        print("金标集不存在，先运行 build_golden")
        sys.exit(1)

    from interviewace.backend.database.milvus import connect_milvus
    from interviewace.rag.retriever import retrieve_with_meta
    connect_milvus()

    golden = [g for g in json.loads(GOLDEN.read_text(encoding="utf-8"))
              if g.get("tier") == args.tier][:args.n]
    print(f"评测 {len(golden)} 条（Tier {args.tier}）")

    done = {}
    if CHECKPOINT.exists():
        for line in CHECKPOINT.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
                done[d["query"]] = d
            except Exception:
                pass
    fp = CHECKPOINT.open("a", encoding="utf-8")

    t0 = time.time()
    for i, g in enumerate(golden, 1):
        if g["query"] in done:
            continue
        try:
            res = retrieve_with_meta(g["query"], top_k=5, allow_fallback=True)
            context = "\n\n".join(s.parent_text for s in res.sources)
            answer = _generate(g["query"], context)
            verdict = _judge(g["query"], context, answer)
        except Exception as e:
            print(f"  [{i}] 失败：{str(e)[:90]}")
            continue
        rec = {"query": g["query"], "answer": answer[:1500], **verdict}
        fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fp.flush()
        done[g["query"]] = rec
        print(f"  [{i}/{len(golden)}] correctness={verdict.get('correctness')} "
              f"faithfulness={verdict.get('faithfulness')} halluc={verdict.get('hallucination')}")
    fp.close()

    recs = [r for r in done.values() if "correctness" in r]
    if not recs:
        print("没有有效结果")
        return
    def avg(key):
        vals = [r[key] for r in recs if isinstance(r.get(key), (int, float))]
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    hallu = sum(1 for r in recs if r.get("hallucination"))
    report = {
        "samples": len(recs), "tier": args.tier,
        "correctness": avg("correctness"), "faithfulness": avg("faithfulness"),
        "hallucination_rate": round(hallu / len(recs), 3),
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    lines = ["# 生成质量评测报告（LLM-as-Judge）", "",
             f"样本 {len(recs)} 条（Tier {args.tier}）｜裁判模型：{__import__('interviewace.backend.config', fromlist=['JUDGE_MODEL']).JUDGE_MODEL}",
             f"生成时间：{report['generated_at']}", "",
             "| 指标 | 数值 | 说明 |", "|---|---|---|",
             f"| 正确性 | {report['correctness']} / 5 | 技术内容是否正确 |",
             f"| 忠实度 | {report['faithfulness']} / 5 | 答案是否 grounded 于检索资料 |",
             f"| 幻觉率 | {report['hallucination_rate'] * 100:.1f}% | 出现资料未支撑编造的占比 |", ""]
    # 低分样例
    bad = sorted(recs, key=lambda r: (r.get("faithfulness", 5), r.get("correctness", 5)))[:5]
    if bad:
        lines += ["## 待改进样例（忠实度/正确性最低的 5 条）", ""]
        for r in bad:
            lines.append(f"- **{r['query'][:50]}** — 正确性 {r.get('correctness')} / 忠实度 "
                         f"{r.get('faithfulness')}：{str(r.get('reason', ''))[:100]}")
    REPORT_DIR.mkdir(exist_ok=True)
    (REPORT_DIR / "answer_eval.md").write_text("\n".join(lines), encoding="utf-8")
    (REPORT_DIR / "answer_eval.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                                 encoding="utf-8")
    print("\n" + "\n".join(lines))
    print(f"\n报告已写入 {REPORT_DIR}/answer_eval.md  （耗时 {time.time() - t0:.0f}s）")


if __name__ == "__main__":
    main()
