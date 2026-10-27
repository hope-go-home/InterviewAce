"""题库分布统计报表

扫描 data/jsonl/ 下所有正式数据文件（gen_*.jsonl / qa_*.jsonl / knowledge_*.jsonl，
跳过 seeds_*），输出 domain × difficulty × q_type × source 的分布，
并做两项健康检查：
- 每 domain 题量低于下限（默认 80）报警
- 难度分布失衡（某档占比 > 70%）报警

用法：python data_pipeline/stats.py
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_pipeline.schema import DOMAINS

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "jsonl"
DOMAIN_MIN = 80
DIFFICULTY_NAME = {1: "基础", 2: "应用", 3: "进阶"}


def main():
    files = [f for f in sorted(DATA_DIR.glob("*.jsonl"))
             if not f.name.startswith("seeds_") and f.name != "qc_report.jsonl"]
    if not files:
        print("没有数据文件")
        return

    by_domain: dict[str, int] = defaultdict(int)
    by_domain_diff: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    by_qtype: dict[str, int] = defaultdict(int)
    by_source: dict[str, int] = defaultdict(int)
    generated_count = 0
    total = 0
    invalid = 0

    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:
                invalid += 1
                continue
            total += 1
            dom = d.get("domain", "?")
            by_domain[dom] += 1
            by_domain_diff[dom][d.get("difficulty", 2)] += 1
            by_qtype[d.get("q_type", "?")] += 1
            by_source[d.get("source", "?")] += 1
            if d.get("generated"):
                generated_count += 1

    print("=" * 64)
    print(f"题库总量：{total} 条（其中 LLM 生成 {generated_count} 条，占 {generated_count / max(total, 1) * 100:.0f}%）")
    print(f"数据文件：{len(files)} 个；无效行：{invalid}")
    print("=" * 64)

    print("\n按知识域（domain × 难度）：")
    print(f"{'domain':<16} {'总量':>6} {'基础':>6} {'应用':>6} {'进阶':>6}  状态")
    for dom in sorted(DOMAINS):
        n = by_domain.get(dom, 0)
        diffs = by_domain_diff.get(dom, {})
        warn = ""
        if n < DOMAIN_MIN:
            warn = f"⚠️ 不足 {DOMAIN_MIN}"
        elif n > 0:
            top_ratio = max(diffs.values()) / n if diffs else 0
            if top_ratio > 0.7:
                warn = "⚠️ 难度失衡"
        ok = "✅" if not warn else ""
        print(f"{dom:<16} {n:>6} {diffs.get(1, 0):>6} {diffs.get(2, 0):>6} {diffs.get(3, 0):>6}  {warn}{ok}")

    print("\n按条目类型：")
    for qt, n in sorted(by_qtype.items(), key=lambda x: -x[1]):
        print(f"  {qt:<12} {n:>6}")
    print("\n按来源：")
    for src, n in sorted(by_source.items(), key=lambda x: -x[1]):
        print(f"  {src:<50} {n:>6}")


if __name__ == "__main__":
    main()
