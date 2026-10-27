"""题库入库

- qa_pair（QA 对）：原子单元，**绝不切碎**
  text（子块，参与检索）= 题干；parent_text（喂给 LLM）= 题干 + 完整参考答案
- knowledge（知识短文）：父子块分块（子块 350 检索 / 父块 1000 作答，标题前缀）

幂等：入库前按 source 先删旧块（delete_by_sources），脚本可反复跑。
"""
from data_pipeline.schema import QAItem
from interviewace.backend.database.milvus import delete_by_sources, insert_documents
from interviewace.backend.logger import get_logger
from interviewace.rag.embedding import embed_documents, embed_documents_sparse
from interviewace.rag.ingest import child_splitter, parent_splitter, _titled

logger = get_logger(__name__)


def qa_to_chunks(item: QAItem) -> tuple[str, str]:
    """QAItem → (子块, 父块)。子块=题干，父块=题干+答案"""
    child = item.question.strip()
    parent = f"【问题】{item.question.strip()}\n\n【参考答案】\n{item.answer.strip()}"
    return child, parent


def ingest_qa_items(items: list[QAItem], collection_name: str | None = None,
                    batch_size: int = 64) -> int:
    """题库批量入库（幂等：按 source 先删后插）。

    分批嵌入摊薄 API/模型开销；全部插入后统一 flush 一次。
    """
    if not items:
        return 0

    # 幂等清理：同源旧块先删
    sources = sorted({it.source for it in items if it.source})
    if sources:
        delete_by_sources(sources, collection_name=collection_name)

    insert_kwargs = {"collection_name": collection_name} if collection_name else {}
    total = 0
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        children, parents = [], []
        for it in batch:
            child, parent = qa_to_chunks(it)
            children.append(child)
            parents.append(parent)

        dense_vectors = embed_documents(children)
        sparse_vectors = embed_documents_sparse(children)

        is_last = i + batch_size >= len(items)
        insert_documents(
            children, parents, dense_vectors, sparse_vectors,
            partition_name="qa_pair", q_type="qa_pair",
            source=[it.source for it in batch],  # 逐条来源（幂等清理的键）
            domains=[it.domain for it in batch],
            companies=[it.company for it in batch],
            difficulties=[it.difficulty for it in batch],
            position=batch[0].position,
            titles=[it.question[:80] for it in batch],
            urls=[it.url for it in batch],
            flush=is_last,  # 仅最后一批 flush
            **insert_kwargs,
        )
        total += len(batch)
        logger.info("ingest_qa_items progress %d/%d", total, len(items))

    return total


def _knowledge_to_chunks(item: QAItem) -> tuple[list[str], list[str]]:
    """知识短文 → (子块列表, 父块列表)：父块 1000 字带标题前缀，子块 350 字"""
    title = item.question.strip()
    body = item.answer.strip()
    children, parents = [], []
    for parent in parent_splitter.split_text(body):
        titled_parent = _titled(title, parent)
        for child in child_splitter.split_text(parent):
            children.append(child)
            parents.append(titled_parent)
    return children, parents


def ingest_knowledge_items(items: list[QAItem], collection_name: str | None = None,
                           batch_size: int = 32) -> int:
    """知识短文批量入库（父子块分块；幂等：按 source 先删后插）"""
    if not items:
        return 0

    sources = sorted({it.source for it in items if it.source})
    if sources:
        delete_by_sources(sources, collection_name=collection_name)

    insert_kwargs = {"collection_name": collection_name} if collection_name else {}
    total_chunks = 0
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        children, parents = [], []
        domains, companies, difficulties, sources_l, titles, urls = [], [], [], [], [], []
        for it in batch:
            c, p = _knowledge_to_chunks(it)
            children.extend(c)
            parents.extend(p)
            domains.extend([it.domain] * len(c))
            companies.extend([it.company] * len(c))
            difficulties.extend([it.difficulty] * len(c))
            sources_l.extend([it.source] * len(c))
            titles.extend([it.question[:80]] * len(c))
            urls.extend([it.url] * len(c))
        if not children:
            continue

        dense_vectors = embed_documents(children)
        sparse_vectors = embed_documents_sparse(children)

        is_last = i + batch_size >= len(items)
        insert_documents(
            children, parents, dense_vectors, sparse_vectors,
            partition_name="knowledge", q_type="knowledge",
            source=sources_l, domains=domains, companies=companies,
            difficulties=difficulties, position=items[0].position,
            titles=titles, urls=urls,
            flush=is_last,
            **insert_kwargs,
        )
        total_chunks += len(children)
        logger.info("ingest_knowledge_items progress 条目 %d/%d，块 %d",
                    min(i + batch_size, len(items)), len(items), total_chunks)

    return total_chunks
