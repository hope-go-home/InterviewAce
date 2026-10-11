"""题库批量入库：python scripts/ingest_all.py [--dir data/jsonl] [--reset] [--limit N]

流程：遍历 JSONL（跳过 seeds_* 种子文件）→ QAItem 校验
→ 三级去重（content_hash 精确 + 归一化题干 + Jaccard 近重复，见 data_pipeline/dedup.py）
→ 按 q_type 分流：qa_pair 整块入库 / knowledge 走父子分块入库
→ 幂等：按 source 先删后插，可反复跑。
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_pipeline.dedup import dedup_items
from data_pipeline.schema import QAItem
from interviewace.backend.database.milvus import (
    connect_milvus, create_collection, drop_collection,
)
from interviewace.backend.logger import get_logger
from interviewace.rag.qa_ingest import ingest_knowledge_items, ingest_qa_items

logger = get_logger(__name__)


def load_jsonl_dir(jsonl_dir: Path, limit: int | None = None) -> list[QAItem]:
    """读取目录下全部 JSONL（跳过 seeds_*），校验 + 三级去重"""
    items: list[QAItem] = []
    invalid = 0

    files = sorted(f for f in jsonl_dir.glob("*.jsonl") if not f.name.startswith("seeds_"))
    for f in files:
        for line_no, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                item = QAItem.from_jsonl(line)
            except Exception as e:
                invalid += 1
                logger.warning("校验失败 %s:%d %s", f.name, line_no, str(e)[:120])
                continue
            if not item.answer.strip():
                invalid += 1
                continue
            items.append(item)
            if limit and len(items) >= limit:
                break

    logger.info("加载：有效 %d 条，无效 %d 条（来自 %d 个文件）", len(items), invalid, len(files))

    # 三级去重（content_hash + 归一化题干 + Jaccard 近重复）
    items, dropped = dedup_items(items)
    logger.info("去重：丢弃 %d 条近重复，剩余 %d 条", dropped, len(items))
    return items


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="data/jsonl", help="JSONL 目录")
    parser.add_argument("--reset", action="store_true", help="删除重建 interview_kb 集合")
    parser.add_argument("--limit", type=int, default=None, help="只入库前 N 条（调试用）")
    args = parser.parse_args()

    jsonl_dir = Path(args.dir)
    if not jsonl_dir.is_dir():
        print(f"目录不存在：{jsonl_dir}")
        sys.exit(1)

    connect_milvus()
    if args.reset:
        drop_collection()
    create_collection()

    items = load_jsonl_dir(jsonl_dir, limit=args.limit)
    if not items:
        print("没有可入库的数据")
        return

    # 按 q_type 分流入库
    qa_items = [it for it in items if it.q_type == "qa_pair"]
    knowledge_items = [it for it in items if it.q_type == "knowledge"]
    experience_items = [it for it in items if it.q_type == "experience"]

    n_qa = ingest_qa_items(qa_items)
    n_knowledge = ingest_knowledge_items(knowledge_items)
    if experience_items:
        logger.warning("experience（面经）入库走 ingest.py 的文档管线，本次跳过 %d 条",
                       len(experience_items))
    print(f"入库完成：QA {n_qa} 条 + 知识短文 {n_knowledge} 块 → interview_kb")


if __name__ == "__main__":
    main()
