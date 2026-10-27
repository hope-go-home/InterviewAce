"""CI 评测回归门禁

对比最新评测报告与基线 baseline.json：核心指标跌幅超过阈值（默认 3%）就以非零码退出，阻断合并。
骨架参考 SmartQuery/scripts/eval_gate.py，指标口径按本项目调整。

用法：
  python scripts/eval_gate.py                  # 校验（CI 用，跌超阈值则退出码 1）
  python scripts/eval_gate.py --update-baseline  # 把当前报告快照为新基线
  python scripts/eval_gate.py --threshold 0.05   # 自定义阈值
  python scripts/eval_gate.py --tier B           # 只校验 Tier B
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Windows 控制台默认 GBK，emoji/特殊字符会崩；统一切到 UTF-8
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "interviewace" / "evaluation" / "report"
BASELINE = ROOT / "interviewace" / "evaluation" / "baseline.json"

# 需要守住的关键指标：路径 → 方向（higher 表示越高越好）
WATCH = [
    ("retrieval.hybrid_rerank.recall@10", "higher", "检索 Recall@10（重排链路）"),
    ("retrieval.hybrid_rerank.mrr@10", "higher", "检索 MRR@10（首位排序）"),
    ("retrieval.hybrid_rerank.ndcg@10", "higher", "检索 nDCG@10"),
    ("answer.correctness", "higher", "生成正确性"),
    ("answer.faithfulness", "higher", "生成忠实度"),
    ("answer.hallucination_rate", "lower", "幻觉率"),
    ("scoring.spearman", "higher", "评分一致性 Spearman"),
]


def _load_reports(tier: str) -> dict:
    """把三份报告拍平成 {retrieval: {...}, answer: {...}, scoring: {...}}"""
    out = {}
    rp = REPORT_DIR / "retrieval_eval.json"
    if rp.exists():
        d = json.loads(rp.read_text(encoding="utf-8"))
        out["retrieval"] = (d.get("tiers") or {}).get(tier, {})
    ap_ = REPORT_DIR / "answer_eval.json"
    if ap_.exists():
        out["answer"] = json.loads(ap_.read_text(encoding="utf-8"))
    sp = REPORT_DIR / "scoring_eval.json"
    if sp.exists():
        out["scoring"] = json.loads(sp.read_text(encoding="utf-8"))
    return out


def _dig(d: dict, path: str):
    cur = d
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0.03, help="允许的相对跌幅（默认 3%）")
    ap.add_argument("--tier", default="B", help="检索评测用哪一层（A/B）")
    ap.add_argument("--update-baseline", action="store_true")
    args = ap.parse_args()

    current = _load_reports(args.tier)
    if not current:
        print("没有找到评测报告。先跑：")
        print("  python -m interviewace.evaluation.eval_retrieval")
        print("  python -m interviewace.evaluation.eval_answer --n 30")
        print("  python -m interviewace.evaluation.eval_scoring --n 12")
        sys.exit(1)

    if args.update_baseline:
        BASELINE.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✅ 基线已更新：{BASELINE}")
        return

    if not BASELINE.exists():
        print(f"基线不存在：{BASELINE}\n先运行 python scripts/eval_gate.py --update-baseline")
        sys.exit(1)

    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    failures, checked = [], 0

    print(f"{'指标':<34} {'基线':>9} {'当前':>9} {'变化':>9}  判定")
    print("-" * 78)
    for path, direction, label in WATCH:
        base_v, cur_v = _dig(baseline, path), _dig(current, path)
        if base_v is None or cur_v is None:
            print(f"{label:<34} {'—':>9} {'—':>9} {'':>9}  跳过（数据缺失）")
            continue
        checked += 1
        delta = cur_v - base_v
        rel = delta / abs(base_v) if base_v else 0.0
        # 越低越好的指标（如幻觉率）反向判断
        worse = (rel < -args.threshold) if direction == "higher" else (rel > args.threshold)
        flag = "❌ 回归" if worse else "✅"
        print(f"{label:<34} {base_v:>9.4f} {cur_v:>9.4f} {delta:>+9.4f}  {flag}")
        if worse:
            failures.append((label, base_v, cur_v, rel))

    print("-" * 78)
    if not checked:
        print("⚠️ 没有可比对的指标（报告与基线口径不一致？）")
        sys.exit(1)
    if failures:
        print(f"\n❌ 检测到 {len(failures)} 项指标回归（阈值 {args.threshold * 100:.0f}%）：")
        for label, b, c, rel in failures:
            print(f"   - {label}: {b:.4f} → {c:.4f}（{rel * 100:+.1f}%）")
        print("\n若确认是预期变化，运行 --update-baseline 更新基线。")
        sys.exit(1)

    print(f"\n✅ 全部 {checked} 项指标通过（阈值 {args.threshold * 100:.0f}%）")


if __name__ == "__main__":
    main()
