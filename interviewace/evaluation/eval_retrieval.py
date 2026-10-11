"""检索策略离线评测

对 golden_interview.json 里的每个 query，跑 5 种检索策略，算 Recall/Precision/MRR/nDCG/HitRate@k。

策略：
  1. dense_only          纯稠密（qwen 2048d）
  2. sparse_only         纯稀疏（bge-m3 lexical weights）
  3. hybrid_rrf          稠密+稀疏 → 加权 RRF（不重排）
  4. hybrid_rerank       完整链路（RRF → bge-reranker 重排）
  5. hybrid_rerank_domain  完整链路 + 知识域标量过滤

按 tier 分层报告：
  Tier A（query=题干原文）→ 验证「精确匹配能否排第 1」，是链路正确性 + 上界基线
  Tier B（query=LLM 改写的口语化提问）→ 真实语义检索能力，这份数字才代表实际体验

用法：
  python -m interviewace.evaluation.eval_retrieval                # 全部
  python -m interviewace.evaluation.eval_retrieval --limit 30     # 只跑前 30 条（调试）
  python -m interviewace.evaluation.eval_retrieval --tier B       # 只跑 Tier B
"""
import argparse
import json
import math
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

EVAL_DIR = Path(__file__).resolve().parent
GOLDEN = EVAL_DIR / "golden_interview.json"
REPORT_DIR = EVAL_DIR / "report"
TOP_KS = [1, 3, 5, 10]
STRATEGIES = ["dense_only", "sparse_only", "hybrid_rrf", "hybrid_rerank", "hybrid_rerank_domain"]
CHECKPOINT = EVAL_DIR / "retrieval_eval.checkpoint.jsonl"


# ---------------- 指标 ----------------

def recall_at_k(ranked: list[str], gold: set[str], k: int) -> float:
    if not gold:
        return 0.0
    hit = sum(1 for x in ranked[:k] if x in gold)
    return hit / len(gold)


def precision_at_k(ranked: list[str], gold: set[str], k: int) -> float:
    if k == 0:
        return 0.0
    return sum(1 for x in ranked[:k] if x in gold) / k


def mrr_at_k(ranked: list[str], gold: set[str], k: int) -> float:
    for i, x in enumerate(ranked[:k], start=1):
        if x in gold:
            return 1.0 / i
    return 0.0


def ndcg_at_k(ranked: list[str], gold: set[str], k: int) -> float:
    dcg = sum((1.0 if x in gold else 0.0) / math.log2(i + 1)
              for i, x in enumerate(ranked[:k], start=1))
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(gold), k) + 1))
    return dcg / ideal if ideal > 0 else 0.0


def hitrate_at_k(ranked: list[str], gold: set[str], k: int) -> float:
    return 1.0 if any(x in gold for x in ranked[:k]) else 0.0


# ---------------- 单条 query 的 5 策略排名 ----------------

def rank_all(question: str, gold_domain: str | None, pool: int = 60) -> dict[str, list[str]]:
    """返回 {策略名: 排序后的 key 列表}（嵌入只做一次，检索复用）"""
    from interviewace.backend.database.milvus import build_filter_expr, search_dense, search_sparse
    from interviewace.rag.embedding import embed_query, embed_query_sparse
    from interviewace.rag.retriever import (RERANK_POOL, _get_reranker, _rrf_scored,
                                            preprocess_query)

    base_expr = build_filter_expr(q_type="qa_pair")

    def _rerank(question: str, fused, limit: int) -> list[str]:
        cand = [(parent or text, text) for text, parent, _ in fused][:limit]
        if not cand:
            return []
        scores = _get_reranker().predict([[question, doc] for doc, _ in cand], batch_size=16)
        ranked = sorted(zip(cand, scores), key=lambda x: x[1], reverse=True)
        return [child for (_, child), _ in ranked]

    # 嵌入只算一次
    qv = embed_query(question)
    qs = embed_query_sparse(preprocess_query(question))

    dense = search_dense(qv, top_k=pool, expr=base_expr)
    sparse = search_sparse(qs, top_k=pool, expr=base_expr)
    fused = _rrf_scored(dense, sparse)

    out: dict[str, list[str]] = {
        "dense_only": [d[0] for d in dense],
        "sparse_only": [s[0] for s in sparse],
        "hybrid_rrf": [t for t, _, _ in fused],
        "hybrid_rerank": _rerank(question, fused, RERANK_POOL),
    }

    # 带知识域过滤：另取一次候选（复用同一份 query 向量），再重排
    dom = gold_domain if gold_domain and gold_domain != "?" else None
    if dom:
        dom_expr = build_filter_expr(q_type="qa_pair", domain=dom)
        d2 = search_dense(qv, top_k=pool, expr=dom_expr)
        s2 = search_sparse(qs, top_k=pool, expr=dom_expr)
        f2 = _rrf_scored(d2, s2)
        out["hybrid_rerank_domain"] = _rerank(question, f2, RERANK_POOL)
    else:
        out["hybrid_rerank_domain"] = out["hybrid_rerank"]

    return out


# ---------------- 主流程 ----------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 条")
    ap.add_argument("--tier", default="", help="只跑某层（A/B）")
    ap.add_argument("--resume", action="store_true", help="从 checkpoint 续跑")
    args = ap.parse_args()

    if not GOLDEN.exists():
        print(f"金标集不存在：{GOLDEN}\n请先运行：python -m interviewace.evaluation.build_golden --n 100 --rewrite")
        sys.exit(1)

    from interviewace.backend.database.milvus import connect_milvus
    connect_milvus()

    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    if args.tier:
        golden = [g for g in golden if g.get("tier") == args.tier]
    if args.limit:
        golden = golden[:args.limit]

    done = {}
    if args.resume and CHECKPOINT.exists():
        for line in CHECKPOINT.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
                done[d["query"]] = d
            except Exception:
                pass
        print(f"从 checkpoint 续跑，已完成 {len(done)} 条")

    print(f"评测 {len(golden)} 条 query × {len(STRATEGIES)} 策略，k={TOP_KS}")
    ckpt_fp = CHECKPOINT.open("a", encoding="utf-8")
    t0 = time.time()
    for i, g in enumerate(golden, 1):
        if g["query"] in done:
            continue
        try:
            ranks = rank_all(g["query"], g.get("domain"))
        except Exception as e:
            print(f"  [{i}] 失败：{str(e)[:80]}")
            continue
        rec = {"query": g["query"], "gold": g["gold"], "tier": g["tier"],
               "domain": g.get("domain"), "ranks": ranks}
        ckpt_fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
        ckpt_fp.flush()
        done[g["query"]] = rec
        if i % 10 == 0 or i == len(golden):
            el = time.time() - t0
            print(f"  进度 {i}/{len(golden)}  已用 {el:.0f}s  预计剩余 {el / i * (len(golden) - i):.0f}s")
    ckpt_fp.close()

    # ---------------- 汇总 ----------------
    records = list(done.values())
    by_tier = defaultdict(list)
    for r in records:
        by_tier[r["tier"]].append(r)

    report = {"total": len(records), "tiers": {}, "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    lines = ["# 检索策略评测报告", "",
             f"样本：{len(records)} 条 query ｜ 知识库：interview_kb ｜ 生成时间：{report['generated_at']}", ""]

    for tier in sorted(by_tier):
        recs = by_tier[tier]
        tier_label = {"A": "Tier A（query = 题干原文；验证精确匹配能否排第 1）",
                      "B": "Tier B（query = LLM 改写的口语化提问；真实语义检索能力）"}.get(tier, tier)
        lines += [f"## {tier_label}", "", f"样本 {len(recs)} 条", "",
                  "| 策略 | Recall@1 | Recall@5 | Recall@10 | MRR@10 | nDCG@10 | HitRate@1 | HitRate@10 |",
                  "|---|---|---|---|---|---|---|---|"]
        tier_metrics = {}
        for st in STRATEGIES:
            agg = {f"recall@{k}": [] for k in TOP_KS}
            agg.update({f"precision@{k}": [] for k in TOP_KS})
            agg.update({f"mrr@{k}": [] for k in TOP_KS})
            agg.update({f"ndcg@{k}": [] for k in TOP_KS})
            agg.update({f"hitrate@{k}": [] for k in TOP_KS})
            for r in recs:
                ranked = r["ranks"].get(st, [])
                gold = {r["gold"]}
                for k in TOP_KS:
                    agg[f"recall@{k}"].append(recall_at_k(ranked, gold, k))
                    agg[f"precision@{k}"].append(precision_at_k(ranked, gold, k))
                    agg[f"mrr@{k}"].append(mrr_at_k(ranked, gold, k))
                    agg[f"ndcg@{k}"].append(ndcg_at_k(ranked, gold, k))
                    agg[f"hitrate@{k}"].append(hitrate_at_k(ranked, gold, k))
            avg = {m: (sum(v) / len(v) if v else 0.0) for m, v in agg.items()}
            tier_metrics[st] = avg
            lines.append(
                f"| {st} | {avg['recall@1']:.3f} | {avg['recall@5']:.3f} | {avg['recall@10']:.3f} "
                f"| {avg['mrr@10']:.3f} | {avg['ndcg@10']:.3f} | {avg['hitrate@1']:.3f} | {avg['hitrate@10']:.3f} |")
        lines.append("")
        report["tiers"][tier] = tier_metrics

        # 相对 dense_only 的提升
        base = tier_metrics["dense_only"]
        best = tier_metrics["hybrid_rerank"]
        lines += [f"**相对纯稠密基线**：hybrid_rerank 的 Recall@1 "
                  f"{base['recall@1']:.3f} → {best['recall@1']:.3f}"
                  f"（{'+' if best['recall@1'] >= base['recall@1'] else ''}"
                  f"{(best['recall@1'] - base['recall@1']) * 100:.1f}pt），"
                  f"MRR@10 {base['mrr@10']:.3f} → {best['mrr@10']:.3f}", ""]

    REPORT_DIR.mkdir(exist_ok=True)
    (REPORT_DIR / "retrieval_eval.md").write_text("\n".join(lines), encoding="utf-8")
    (REPORT_DIR / "retrieval_eval.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n" + "\n".join(lines))
    print(f"\n报告已写入 {REPORT_DIR}/retrieval_eval.md")


if __name__ == "__main__":
    main()
