"""构建检索评测金标集

两层口径（写清楚各自测什么，避免自欺）：

  Tier A（免费，不问 LLM）：query = 题干原文，gold = 该题干本身
      测的是「管线能否把精确匹配排到首位」——用于验证链路正确性 + 对比各策略
  Tier B（少量 token）：query = LLM 改写成「真实用户口吻」的提问，gold = 原题干
      测的是「语义检索能力」——用户不会照着题干原文问，这才是真实场景

产出：interviewace/evaluation/golden_interview.json
  [{"query": "...", "gold": "原题干", "domain": "rag", "tier": "A"}, ...]

用法：
  python -m interviewace.evaluation.build_golden --n 100            # 只建 Tier A
  python -m interviewace.evaluation.build_golden --n 100 --rewrite  # A + B
"""
import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

OUT_FILE = Path(__file__).resolve().parent / "golden_interview.json"

REWRITE_PROMPT = """请把下面这道面试题改写成「求职者口语化提问」的形式，用于检索测试。

原题：{q}

要求：
- 保留核心技术概念（否则无法评测），但换一种说法，模拟真实用户提问
- 可以更口语、更简短、可以带一点上下文（如「我在项目里遇到…」）
- 不要照抄原题的关键词顺序
- 只输出改写后的一句话，不要解释、不要引号"""


def sample_questions(n: int) -> list[dict]:
    """从题库随机抽 n 道 qa_pair（覆盖各知识域）"""
    from collections import defaultdict

    from pymilvus import Collection

    from interviewace.backend.database.milvus import COLLECTION_NAME, connect_milvus

    connect_milvus()
    col = Collection(name=COLLECTION_NAME)
    col.load()
    rows = col.query(expr='q_type == "qa_pair"',
                     output_fields=["title", "domain", "difficulty"], limit=16384)
    by_domain = defaultdict(list)
    for r in rows:
        t = (r.get("title") or "").strip()
        if t and len(t) >= 8:
            by_domain[r.get("domain") or "?"].append({
                "title": t, "domain": r.get("domain") or "?",
                "difficulty": r.get("difficulty", 2),
            })

    # 各域等额抽样，保证覆盖面
    domains = sorted(by_domain)
    per = max(1, n // len(domains))
    picked = []
    for d in domains:
        pool = by_domain[d]
        random.shuffle(pool)
        picked.extend(pool[:per])
    random.shuffle(picked)
    return picked[:n]


def rewrite_queries(items: list[dict], concurrency: int = 8) -> list[str]:
    """用 LLM 把题干改写成口语化提问（Tier B）"""
    import asyncio

    from interviewace.backend.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL
    from interviewace.backend.logger import get_logger
    from openai import AsyncOpenAI

    logger = get_logger(__name__)
    client = AsyncOpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL)
    sem = asyncio.Semaphore(concurrency)

    async def one(q: str) -> str:
        async with sem:
            for _ in range(3):
                try:
                    r = await client.chat.completions.create(
                        model=QWEN_MODEL,
                        messages=[{"role": "user", "content": REWRITE_PROMPT.format(q=q)}],
                        temperature=0.7, max_tokens=200)
                    return (r.choices[0].message.content or "").strip().strip('"「」')
                except Exception as e:
                    logger.warning("rewrite retry: %s", str(e)[:80])
                    await asyncio.sleep(2)
            return ""

    async def run():
        return await asyncio.gather(*[one(it["title"]) for it in items])

    return asyncio.run(run())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100, help="每层样本数")
    ap.add_argument("--rewrite", action="store_true", help="同时生成 Tier B（消耗 LLM token）")
    args = ap.parse_args()

    items = sample_questions(args.n)
    print(f"抽样 {len(items)} 道题，覆盖 {len({i['domain'] for i in items})} 个知识域")

    golden = [{
        "query": it["title"], "gold": it["title"],
        "domain": it["domain"], "difficulty": it["difficulty"], "tier": "A",
    } for it in items]

    if args.rewrite:
        print(f"用 LLM 改写 {len(items)} 条为口语化提问（Tier B）…")
        rewritten = rewrite_queries(items)
        ok = 0
        for it, rq in zip(items, rewritten):
            if rq and len(rq) >= 5 and rq != it["title"]:
                golden.append({
                    "query": rq, "gold": it["title"],
                    "domain": it["domain"], "difficulty": it["difficulty"], "tier": "B",
                })
                ok += 1
        print(f"改写成功 {ok}/{len(items)} 条")

    OUT_FILE.write_text(json.dumps(golden, ensure_ascii=False, indent=2), encoding="utf-8")
    tiers = {}
    for g in golden:
        tiers[g["tier"]] = tiers.get(g["tier"], 0) + 1
    print(f"金标集已写入 {OUT_FILE}（{tiers}）")


if __name__ == "__main__":
    main()
