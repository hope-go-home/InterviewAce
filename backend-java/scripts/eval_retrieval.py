"""Java 版检索链路评测：金标集直接打 /debug/retrieve（不调 LLM 生成，纯检索+重排）。

口径与 Python 版 eval_retrieval.py 完全一致：tier B 前 60 条、title 前 80 字符归一化比对、
指标 Recall@1/3/5/10 + MRR@10 + nDCG@10 + HitRate@10。

用法：
    python scripts/eval_retrieval.py                 # 默认 tier B limit 60
    python scripts/eval_retrieval.py --tier A --limit 99
"""
import argparse
import json
import math
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "http://localhost:8002"
GOLDEN = Path(__file__).resolve().parents[2] / "interviewace" / "evaluation" / "golden_interview.json"
BASELINE = Path(__file__).resolve().parents[2] / "interviewace" / "evaluation" / "baseline.json"


def norm_key(s: str) -> str:
    """题库 title 存题干前 80 字符，检索返回完整题干 → 一律按前 80 字符比对（与 Python 版一致）"""
    return (s or "").strip()[:80]


def login() -> str:
    req = urllib.request.Request(BASE + "/auth/login",
                                 data=json.dumps({"username": "admin", "password": "admin123"}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())["token"]


def retrieve(query: str, token: str, top_k: int = 10) -> list[str]:
    qs = urllib.parse.urlencode({"query": query, "topK": top_k, "qType": "qa_pair"})
    req = urllib.request.Request(f"{BASE}/debug/retrieve?{qs}",
                                 headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read())
    return [norm_key(s["title"]) for s in d["sources"]]


def recall_at_k(ranked, gold, k):
    return 1.0 if gold in ranked[:k] else 0.0


def mrr_at_k(ranked, gold, k):
    for i, x in enumerate(ranked[:k]):
        if x == gold:
            return 1.0 / (i + 1)
    return 0.0


def ndcg_at_k(ranked, gold, k):
    dcg = sum((1.0 if x == gold else 0.0) / math.log2(i + 1) for i, x in enumerate(ranked[:k], 1))
    return dcg / 1.0  # 单金标：IDCG=1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", default="B")
    ap.add_argument("--limit", type=int, default=60)
    args = ap.parse_args()

    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    golden = [g for g in golden if g.get("tier") == args.tier][: args.limit]
    print(f"评测 {len(golden)} 条金标 query（tier {args.tier}）→ Java 版 稠密+云端重排 链路")

    token = login()
    ks = (1, 3, 5, 10)
    agg = {f"recall@{k}": 0.0 for k in ks}
    agg.update({"mrr@10": 0.0, "ndcg@10": 0.0, "hitrate@10": 0.0})
    misses = []

    for i, g in enumerate(golden):
        gold = norm_key(g["gold"])
        try:
            ranked = retrieve(g["query"], token)
        except Exception as e:
            print(f"  [{i+1}] 检索失败: {e}")
            ranked = []
        for k in ks:
            agg[f"recall@{k}"] += recall_at_k(ranked, gold, k)
        agg["mrr@10"] += mrr_at_k(ranked, gold, 10)
        agg["ndcg@10"] += ndcg_at_k(ranked, gold, 10)
        agg["hitrate@10"] += 1.0 if gold in ranked[:10] else 0.0
        if gold not in ranked[:10]:
            misses.append(g["query"][:40])
        if (i + 1) % 10 == 0:
            print(f"  进度 {i+1}/{len(golden)}，当前 recall@1={agg['recall@1']/(i+1):.3f}")

    n = len(golden)
    print("\n=== Java 版检索指标（稠密 + qwen3.7-text-rerank）===")
    for k in ks:
        print(f"Recall@{k}:  {agg[f'recall@{k}']/n:.3f}")
    print(f"MRR@10:    {agg['mrr@10']/n:.3f}")
    print(f"nDCG@10:   {agg['ndcg@10']/n:.3f}")
    print(f"HitRate@10:{agg['hitrate@10']/n:.3f}")

    if BASELINE.exists():
        base = json.loads(BASELINE.read_text(encoding="utf-8"))["retrieval"]
        print("\n=== 与 Python 版基线对比（同金标同口径）===")
        print(f"{'指标':<12}{'Java 稠密+云重排':<18}{'Py 纯稠密':<12}{'Py 混合+本地重排':<16}")
        for m in ("recall@1", "recall@10", "mrr@10", "ndcg@10"):
            jv = agg[m] / n
            d = base["dense_only"][m]
            h = base["hybrid_rerank"][m]
            print(f"{m:<12}{jv:<18.3f}{d:<12.3f}{h:<16.3f}")

    if misses:
        print(f"\n未命中 query（{len(misses)} 条，供优化分析）:")
        for q in misses[:10]:
            print("  -", q)

    out = Path(__file__).resolve().parent / "eval_retrieval_result.json"
    out.write_text(json.dumps({k: v / n for k, v in agg.items()},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已写入 {out.name}")


if __name__ == "__main__":
    main()
