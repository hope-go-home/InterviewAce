"""题库双重去重

三级判重（从便宜到贵）：
1. content_hash：question+answer 完全相同的条目（跨源转载）
2. 题干归一化精确判重：去标点/空白/大小写后相同（同题换标点）
3. 题干字符 3-gram Jaccard > 0.8 判重（同题换说法）

性能考虑：Jaccard 不做 O(n²) 全对比——先建 shingle 倒排索引，
只对共享 ≥3 个 shingle 的候选对计算 Jaccard（万级题库秒级完成）。

向量级判重（embedding cos>0.92）在 M4 用 Milvus 现成索引做（见 stats.py），
本地管线用字符级已能拦截绝大多数近重复。

用法（CLI）：python data_pipeline/dedup.py data/jsonl/xxx.jsonl
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_pipeline.schema import QAItem

JACCARD_THRESHOLD = 0.8
MIN_SHARED_SHINGLES = 3


def _normalize(text: str) -> str:
    """题干归一化：去标点/空白、小写"""
    return re.sub(r"[\s\W_]+", "", text.lower())


def _shingles(text: str, n: int = 3) -> set[str]:
    t = _normalize(text)
    if len(t) < n:
        return {t} if t else set()
    return {t[i:i + n] for i in range(len(t) - n + 1)}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


def dedup_items(items: list[QAItem], threshold: float = JACCARD_THRESHOLD,
                ) -> tuple[list[QAItem], int]:
    """三级判重，返回 (保留列表, 丢弃数)。保留先出现的条目"""
    kept: list[QAItem] = []
    dropped = 0

    seen_hash: set[str] = set()
    seen_norm_q: dict[str, int] = {}
    shingle_index: dict[str, list[int]] = defaultdict(list)
    kept_shingles: list[set[str]] = []

    for item in items:
        # 第 1 级：内容哈希
        h = item.content_hash
        if h in seen_hash:
            dropped += 1
            continue
        # 第 2 级：归一化题干精确判重
        norm_q = _normalize(item.question)
        if norm_q in seen_norm_q:
            dropped += 1
            continue
        # 第 3 级：Jaccard 近重复（只查候选对）
        shingles = _shingles(item.question)
        candidate_counts: dict[int, int] = defaultdict(int)
        for sh in shingles:
            for idx in shingle_index.get(sh, []):
                candidate_counts[idx] += 1
        is_dup = False
        for idx, shared in candidate_counts.items():
            if shared >= MIN_SHARED_SHINGLES and _jaccard(shingles, kept_shingles[idx]) > threshold:
                is_dup = True
                break
        if is_dup:
            dropped += 1
            continue

        idx = len(kept)
        kept.append(item)
        seen_hash.add(h)
        seen_norm_q[norm_q] = idx
        kept_shingles.append(shingles)
        for sh in shingles:
            shingle_index[sh].append(idx)

    return kept, dropped


def main():
    if len(sys.argv) < 2:
        print("用法：python data_pipeline/dedup.py <file.jsonl>")
        sys.exit(1)
    path = Path(sys.argv[1])
    items = [QAItem.from_jsonl(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    kept, dropped = dedup_items(items)
    out = path.with_suffix(".dedup.jsonl")
    with out.open("w", encoding="utf-8") as fp:
        for it in kept:
            fp.write(it.to_jsonl() + "\n")
    print(f"{path.name}: {len(items)} → {len(kept)}（去重丢弃 {dropped}）→ {out.name}")


if __name__ == "__main__":
    main()
