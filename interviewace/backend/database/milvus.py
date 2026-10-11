"""Milvus 数据层：interview_kb 集合的 schema / 增删搜

与 SmartQuery 的差异：
- 新增 4 个标量字段：q_type / domain / position / company(VARCHAR 倒排索引)、difficulty(INT8)
- 分区按 q_type：qa_pair（题库，整块不切）/ experience（面经） / knowledge（知识短文）
- 提供 build_filter_expr 构造标量过滤表达式（domain 过滤 + 跨域 fallback 由 retriever 编排）
"""
from interviewace.backend.config import MILVUS_HOST, MILVUS_PORT, RAG_COLLECTION, RAG_DIM
from interviewace.backend.logger import get_logger
from pymilvus import connections, Collection, CollectionSchema, FieldSchema, DataType, utility

logger = get_logger(__name__)

COLLECTION_NAME = RAG_COLLECTION
DIMENSION = RAG_DIM             # qwen dense = 2048
PARTITIONS = ["qa_pair", "experience", "knowledge"]

Q_TYPES = PARTITIONS            # 合法 q_type 枚举
DOMAINS = [
    "llm_basics", "prompt", "rag", "agent", "vectordb",
    "framework", "python_backend", "ml_dl", "cs_basic",
]

# search_dense / search_sparse 返回元组的字段顺序（10 元组）：
# (text, parent_text, score, q_type, domain, difficulty, company, source, title, url)
SEARCH_OUTPUT_FIELDS = ["text", "parent_text", "q_type", "domain", "difficulty",
                        "company", "source", "title", "url"]


def connect_milvus():
    connections.connect(
        alias="default",
        host=MILVUS_HOST,
        port=MILVUS_PORT,
    )
    logger.info("milvus connected %s:%s", MILVUS_HOST, MILVUS_PORT)


def create_collection(collection_name: str | None = None):
    collection_name = collection_name or COLLECTION_NAME
    if utility.has_collection(collection_name):
        collection = Collection(name=collection_name)
        existing = {p.name for p in collection.partitions}
        for partition in PARTITIONS:
            if partition not in existing:
                collection.create_partition(partition)
        return

    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
        FieldSchema(name="parent_text", dtype=DataType.VARCHAR, max_length=65535),
        FieldSchema(name="dense_vector", dtype=DataType.FLOAT_VECTOR, dim=DIMENSION),
        FieldSchema(name="sparse_vector", dtype=DataType.SPARSE_FLOAT_VECTOR),
        FieldSchema(name="q_type", dtype=DataType.VARCHAR, max_length=32),
        FieldSchema(name="domain", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="position", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="company", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="difficulty", dtype=DataType.INT8),
        FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=256),
        FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=512),
        FieldSchema(name="url", dtype=DataType.VARCHAR, max_length=512),
    ]

    schema = CollectionSchema(fields, description="InterviewAce interview KB embeddings")
    collection = Collection(name=collection_name, schema=schema)

    for partition in PARTITIONS:
        collection.create_partition(partition)

    index_params = {"metric_type": "IP", "index_type": "IVF_FLAT", "params": {"nlist": 128}}
    collection.create_index(field_name="dense_vector", index_params=index_params)
    collection.create_index(field_name="sparse_vector",
                            index_params={"index_type": "SPARSE_INVERTED_INDEX", "metric_type": "IP"})
    # 标量字段倒排索引：加速按知识域/题型过滤（否则为暴力扫描）
    collection.create_index(field_name="q_type", index_params={"index_type": "INVERTED"})
    collection.create_index(field_name="domain", index_params={"index_type": "INVERTED"})
    collection.load()
    logger.info("created collection %s", collection_name)


def drop_collection(collection_name: str | None = None):
    """删除集合（用于 schema 变更或消融实验重建）"""
    collection_name = collection_name or COLLECTION_NAME
    if utility.has_collection(collection_name):
        utility.drop_collection(collection_name)
        logger.info("dropped collection %s", collection_name)


def _escape(value: str) -> str:
    """Milvus 表达式字符串转义"""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def build_filter_expr(domain: str | None = None, q_type: str | None = None,
                      difficulty: int | None = None, company: str | None = None,
                      position: str | None = None) -> str | None:
    """构造标量过滤表达式（AND 组合）；无过滤条件返回 None"""
    clauses = []
    if domain:
        clauses.append(f'domain == "{_escape(domain)}"')
    if q_type:
        clauses.append(f'q_type == "{_escape(q_type)}"')
    if difficulty is not None:
        clauses.append(f"difficulty == {int(difficulty)}")
    if company:
        clauses.append(f'company == "{_escape(company)}"')
    if position:
        clauses.append(f'position == "{_escape(position)}"')
    return " and ".join(clauses) if clauses else None


def delete_by_source(source: str, collection_name: str | None = None) -> int:
    """按来源删除该来源的所有块（用于增量更新 / 删除文档）"""
    collection = Collection(name=collection_name or COLLECTION_NAME)
    collection.load()
    expr = f'source == "{_escape(source)}"'
    try:
        rows = collection.query(expr=expr, output_fields=["id"], limit=16384)
        count = len(rows)
    except Exception as e:
        logger.warning("delete_by_source query failed: %s", e)
        count = 0
    if count:
        collection.delete(expr=expr)
        collection.flush()
    logger.info("delete_by_source source=%s deleted=%d", source, count)
    return count


def delete_by_sources(sources: list[str], collection_name: str | None = None) -> int:
    """按来源批量删除（一次 delete 完成，避免逐文件 flush）。

    用于批量入库前按 source 幂等清理：先删同源旧块，再重新插入，
    从而保证同一份语料重复入库时不会产生重复块。
    """
    sources = [s for s in sources if s]
    if not sources:
        return 0
    collection = Collection(name=collection_name or COLLECTION_NAME)
    collection.load()
    escaped = ", ".join('"' + _escape(s) + '"' for s in sources)
    expr = f"source in [{escaped}]"
    try:
        rows = collection.query(expr=expr, output_fields=["id"], limit=16384)
        count = len(rows)
    except Exception as e:
        logger.warning("delete_by_sources query failed: %s", e)
        count = 0
    if count:
        collection.delete(expr=expr)
        collection.flush()
    logger.info("delete_by_sources sources=%d deleted=%d", len(sources), count)
    return count


def _broadcast(value, n: int, default):
    """标量广播为长度为 n 的列表；已是列表则原样返回"""
    if isinstance(value, list):
        return value
    return [value if value is not None else default] * n


def insert_documents(
    texts: list[str],
    parent_texts: list[str],
    dense_vectors: list[list[float]],
    sparse_vectors: list[dict[int, float]],
    partition_name: str = "knowledge",
    q_type: str = "knowledge",
    source: str = "",
    domains=None,
    companies=None,
    difficulties=None,
    position: str = "ai_app_dev",
    titles: list[str] | None = None,
    urls: list[str] | None = None,
    collection_name: str | None = None,
    flush: bool = True,
):
    """批量插入块。source/domains/companies/difficulties 可为标量（广播）或与 texts 等长的列表"""
    n = len(texts)
    titles = titles if titles is not None else [""] * n
    urls = urls if urls is not None else [""] * n
    sources = _broadcast(source, n, "")
    domains = _broadcast(domains, n, "")
    companies = _broadcast(companies, n, "")
    difficulties = _broadcast(difficulties, n, 1)
    collection = Collection(name=collection_name or COLLECTION_NAME)
    entities = [texts, parent_texts, dense_vectors, sparse_vectors,
                [q_type] * n, domains, [position] * n, companies, difficulties,
                sources, titles, urls]
    collection.insert(entities, partition_name=partition_name)
    # 批量入库时逐文件 flush 极慢，改为全部插入后统一 flush 一次
    if flush:
        collection.flush()


def _search(field: str, data, param: dict, top_k: int,
            partition_name: str | None, expr: str | None,
            collection_name: str | None) -> list[tuple]:
    collection = Collection(name=collection_name or COLLECTION_NAME)
    collection.load()

    kwargs = {
        "data": data,
        "anns_field": field,
        "param": param,
        "limit": top_k,
        "output_fields": SEARCH_OUTPUT_FIELDS,
    }
    if partition_name:
        kwargs["partition_names"] = [partition_name]
    if expr:
        kwargs["expr"] = expr

    results = collection.search(**kwargs)
    return [
        (
            hit.entity.get("text"), hit.entity.get("parent_text"), hit.score,
            hit.entity.get("q_type"), hit.entity.get("domain"),
            hit.entity.get("difficulty"), hit.entity.get("company"),
            hit.entity.get("source"), hit.entity.get("title"), hit.entity.get("url"),
        )
        for hit in results[0]
    ]


def search_dense(
    query_vector: list[float],
    top_k: int = 5,
    partition_name: str | None = None,
    expr: str | None = None,
    collection_name: str | None = None,
) -> list[tuple]:
    """稠密检索，返回 10 元组列表（字段顺序见 SEARCH_OUTPUT_FIELDS 注释）"""
    return _search("dense_vector", [query_vector],
                   {"metric_type": "IP", "params": {"nprobe": 10}},
                   top_k, partition_name, expr, collection_name)


def search_sparse(
    query_vector: dict[int, float],
    top_k: int = 5,
    partition_name: str | None = None,
    expr: str | None = None,
    collection_name: str | None = None,
) -> list[tuple]:
    """稀疏检索，返回 10 元组列表（字段顺序见 SEARCH_OUTPUT_FIELDS 注释）"""
    return _search("sparse_vector", [query_vector], {"metric_type": "IP"},
                   top_k, partition_name, expr, collection_name)
