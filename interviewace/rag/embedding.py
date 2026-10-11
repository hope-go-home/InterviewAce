"""嵌入层：稠密用 qwen（DashScope，2048 维），稀疏用 BAAI/bge-m3。

与 SmartQuery 的差异：本地模型（bge-m3）改为**懒加载单例**——
模块 import 不再加载 2GB 模型，首次调用才加载；
测试与不需要稀疏检索的进程（如纯前端联调）启动更快。
"""
from interviewace.backend.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_EMBEDDING_MODEL
from langchain_openai import OpenAIEmbeddings

# OpenAI 兼容协议客户端是轻量对象（不下载模型），可模块级创建
embeddings = OpenAIEmbeddings(
    model=QWEN_EMBEDDING_MODEL or "qwen3.7-text-embedding",
    api_key=QWEN_API_KEY,
    base_url=QWEN_BASE_URL,
    check_embedding_ctx_length=False,
    chunk_size=20,  # qwen3.7-text-embedding 单次最多 20 条
    dimensions=2048,  # 指定输出维度
)


def embed_documents(texts: list[str]) -> list[list[float]]:
    """qwen 稠密向量（2048 维）——批量入库"""
    if not texts:
        return []
    return embeddings.embed_documents(texts)


def embed_query(text: str) -> list[float]:
    """qwen 稠密向量——单条查询"""
    return embeddings.embed_query(text)


# ---------------- BGE-M3：稀疏词汇权重（懒加载单例） ---------------- #

_sparse_model = None


def _get_sparse_model():
    """首次调用时加载 bge-m3（约 2GB，从 HF_HOME 缓存离线加载）"""
    global _sparse_model
    if _sparse_model is None:
        from FlagEmbedding import BGEM3FlagModel
        _sparse_model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)
    return _sparse_model


def embed_documents_sparse(texts: list[str]) -> list[dict[int, float]]:
    if not texts:
        return []
    out = _get_sparse_model().encode(texts, return_sparse=True, return_dense=False)
    return [{int(t): float(w) for t, w in d.items()} for d in out["lexical_weights"]]


def embed_query_sparse(text: str) -> dict[int, float]:
    out = _get_sparse_model().encode([text], return_sparse=True, return_dense=False)
    return {int(t): float(w) for t, w in out["lexical_weights"][0].items()}
