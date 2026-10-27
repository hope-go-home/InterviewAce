"""题库自动化质检（LLM-as-Judge 抽检）

按文件抽样（默认 10%，min 20 / max 50 条），用裁判模型（JUDGE_MODEL，缺省回退 QWEN_MODEL）
对 QA 对打分：准确性 / 答案完整性 / 题目质量，1-5 分，≥4 判 pass。

输出每个文件的通过率报告；通过率 < 90% 的文件标红警告（建议整批复审或重生成）。
非破坏性：只出报告，不删数据。

用法：
  python data_pipeline/qc_judge.py                  # 抽检所有 gen_*.jsonl / qa_*.jsonl
  python data_pipeline/qc_judge.py --file data/jsonl/gen_rag.jsonl --ratio 0.2
"""
import argparse
import asyncio
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openai import AsyncOpenAI

from data_pipeline.schema import QAItem
from interviewace.backend.config import (
    JUDGE_API_KEY, JUDGE_BASE_URL, JUDGE_MODEL,
)
from interviewace.backend.logger import get_logger

logger = get_logger(__name__)

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "jsonl"

JUDGE_PROMPT = """你是技术面试题的质检专家。请评估下面这道面试题及其参考答案的质量。

【题目】{question}
【参考答案】{answer}

从三个维度评估（各 1-5 分）：
1. 题目质量：是否具体、是真实面试会问的问题
2. 答案准确性：技术内容是否正确，有无明显错误
3. 答案完整性：是否分点、有深度，能支撑面试作答

严格输出 JSON：{{"question_score": int, "accuracy": int, "completeness": int, "pass": bool, "reason": "一句话理由"}}
pass 标准：三个维度都 ≥4 且无事实性错误。"""


async def _judge_one(client: AsyncOpenAI, item: QAItem, sem: asyncio.Semaphore) -> dict | None:
    prompt = JUDGE_PROMPT.format(question=item.question, answer=item.answer[:2000])
    async with sem:
        for attempt in range(3):
            try:
                resp = await client.chat.completions.create(
                    model=JUDGE_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0,
                )
                return json.loads(resp.choices[0].message.content or "")
            except Exception as e:
                logger.warning("judge retry %d: %s", attempt + 1, str(e)[:100])
                await asyncio.sleep(2 ** attempt)
    return None


async def judge_file(path: Path, ratio: float, concurrency: int) -> dict:
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    items = []
    for l in lines:
        try:
            items.append(QAItem.from_jsonl(l))
        except Exception:
            pass
    n = max(20, min(50, int(len(items) * ratio)))
    n = min(n, len(items))
    sample = random.sample(items, n) if items else []

    client = AsyncOpenAI(api_key=JUDGE_API_KEY, base_url=JUDGE_BASE_URL)
    sem = asyncio.Semaphore(concurrency)
    results = await asyncio.gather(*[_judge_one(client, it, sem) for it in sample])
    results = [r for r in results if r]

    passed = sum(1 for r in results if r.get("pass"))
    avg = {}
    for k in ("question_score", "accuracy", "completeness"):
        vals = [r.get(k, 0) for r in results if isinstance(r.get(k), (int, float))]
        avg[k] = round(sum(vals) / len(vals), 2) if vals else 0
    pass_rate = passed / len(results) if results else 0
    return {
        "file": path.name, "total": len(items), "sampled": len(results),
        "pass_rate": round(pass_rate, 3), "avg": avg,
        "warn": pass_rate < 0.9,
        "bad_cases": [
            {"q": it.question[:50], "reason": r.get("reason", "")}
            for it, r in zip(sample, results) if not r.get("pass")
        ][:5],
    }


async def main_async(args):
    if args.file:
        files = [Path(args.file)]
    else:
        files = sorted(DATA_DIR.glob("gen_*.jsonl")) + sorted(DATA_DIR.glob("qa_*.jsonl"))
    if not files:
        print("没有可质检的文件")
        return

    reports = []
    for f in files:
        rep = await judge_file(f, args.ratio, args.concurrency)
        reports.append(rep)
        mark = "⚠️ 需复审" if rep["warn"] else "✅"
        print(f"{mark} {rep['file']}: 总量 {rep['total']}，抽检 {rep['sampled']}，"
              f"通过率 {rep['pass_rate'] * 100:.0f}%，均分 {rep['avg']}")
        for bc in rep["bad_cases"]:
            print(f"    ✗ {bc['q']} —— {bc['reason']}")

    out = DATA_DIR / "qc_report.json"
    out.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已写入 {out}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=None)
    parser.add_argument("--ratio", type=float, default=0.1)
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
