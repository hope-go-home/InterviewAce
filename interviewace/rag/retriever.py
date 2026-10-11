"""混合检索器：稠密+稀疏并行 → 加权 RRF → source 去重 → CrossEncoder 重排

与 SmartQuery 的差异（继承其评测教训）：
- **删除 Multi-Query / HyDE**（SmartQuery 实测在饱和召回场景无效或更差）
- 新增 domain / q_type / difficulty / company 标量过滤（build_filter_expr）
- domain 过滤结果不足时自动 fallback 全库检索，结果标记 cross_domain=True
- reranker 改懒加载单例（import 不再加载模型）
"""
import hashlib
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field

from interviewace.backend import metrics
from interviewace.backend.database.milvus import (
    build_filter_expr, search_dense, search_sparse,
)
from interviewace.backend.logger import get_logger
from interviewace.rag.embedding import embed_query, embed_query_sparse

logger = get_logger(__name__)


# ---------------- 数据结构 ---------------- #

@dataclass
class RetrievalSource:
    """单条检索来源的元数据"""
    text: str
    parent_text: str
    dense_rank: int
    sparse_rank: int
    rrf_score: float
    rerank_score: float
    q_type: str = ""
    domain: str = ""
    difficulty: int = 0
    company: str = ""
    source: str = ""
    title: str = ""
    url: str = ""


@dataclass
class RetrievalResult:
    """检索结果的结构化包装，携带元数据供前端展示"""
    documents: list[str]
    sources: list[RetrievalSource] = field(default_factory=list)
    dense_hit_count: int = 0
    sparse_hit_count: int = 0
    fused_count: int = 0
    cross_domain: bool = False   # True = domain 过滤结果不足，已 fallback 全库检索


# ---------------- 检索缓存（LRU + TTL，防止无上限增长） ---------------- #
_retrieval_cache: "OrderedDict[str, tuple[float, RetrievalResult]]" = OrderedDict()
_cache_lock = threading.Lock()
CACHE_TTL = 300
CACHE_MAXSIZE = 512


def _get_cache_key(question: str, top_k: int, expr: str | None,
                   collection_name: str | None = None, extra: str = "") -> str:
    """生成缓存键（含过滤条件，避免跨域/跨集合串味）"""
    raw = f"{question}:{top_k}:{expr or ''}:{collection_name or ''}:{extra}"
    return hashlib.md5(raw.encode()).hexdigest()


def _get_from_cache(key: str) -> RetrievalResult | None:
    """从缓存获取结果（命中即刷新 LRU 顺序）"""
    with _cache_lock:
        item = _retrieval_cache.get(key)
        if item is None:
            return None
        cached_time, cached_result = item
        if time.time() - cached_time >= CACHE_TTL:
            del _retrieval_cache[key]
            return None
        _retrieval_cache.move_to_end(key)
        return cached_result


def _put_to_cache(key: str, result: RetrievalResult) -> None:
    """存入缓存，超出容量时淘汰最久未使用项"""
    with _cache_lock:
        _retrieval_cache[key] = (time.time(), result)
        _retrieval_cache.move_to_end(key)
        while len(_retrieval_cache) > CACHE_MAXSIZE:
            _retrieval_cache.popitem(last=False)


# ---------------- 核心检索逻辑 ---------------- #

# 加权 RRF 参数：题库语料（中文 QA）上稠密预期仍强于稀疏，沿用 0.8:0.2；
# M1 检索评测会在金标集上验证是否需要调整
RRF_K = 60
RRF_DENSE_WEIGHT = 0.8
RRF_SPARSE_WEIGHT = 0.2

# 重排候选池大小：每个通道取回多少条参与 RRF/重排
CANDIDATE_POOL = 60
# 重排最多处理的候选数（CPU 交叉编码器较慢，限制上限以控制延迟）
RERANK_POOL = 30
# 重排输入截断长度（256 在质量与 CPU 延迟间较平衡）
RERANK_MAX_LENGTH = 256

# domain 过滤召回不足时的 fallback 阈值：融合候选少于此数则放开过滤全库重检
CROSS_DOMAIN_FALLBACK_MIN = 3


def _rrf_scored(dense_results: list[tuple], sparse_results: list[tuple],
                k: int = RRF_K, dense_weight: float = RRF_DENSE_WEIGHT,
                sparse_weight: float = RRF_SPARSE_WEIGHT) -> list[tuple[str, str, float]]:
    """加权 RRF 融合（返回带分数结果，供 rrf_fusion 和 retrieve_with_meta 共用）

    参数 k 控制排名衰减速度：k 越小，靠前排名权重越大（更激进）。
    输入为 search_dense/search_sparse 的 10 元组，这里只用 text/parent_text。
    """
    doc_scores: dict[str, dict] = {}
    for rank, item in enumerate(dense_results):
        text, parent_text = item[0], item[1]
        doc_scores[text] = {"parent_text": parent_text,
                            "score": dense_weight / (k + rank + 1)}
    for rank, item in enumerate(sparse_results):
        text, parent_text = item[0], item[1]
        contrib = sparse_weight / (k + rank + 1)
        if text in doc_scores:
            doc_scores[text]["score"] += contrib
        else:
            doc_scores[text] = {"parent_text": parent_text, "score": contrib}
    sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1]["score"], reverse=True)
    return [(text, item["parent_text"], item["score"]) for text, item in sorted_docs]


def rrf_fusion(dense_results: list[tuple], sparse_results: list[tuple], k: int = 60) -> list[str]:
    """RRF 融合，返回按融合分数降序的父块文本列表"""
    return [parent_text or text for text, parent_text, _ in _rrf_scored(dense_results, sparse_results, k)]


# ---------------- 重排器（懒加载单例） ---------------- #

_reranker = None


def _get_reranker():
    """首次调用时加载 bge-reranker-v2-m3（从 HF_HOME 缓存离线加载）"""
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder
        _reranker = CrossEncoder("BAAI/bge-reranker-v2-m3", local_files_only=True)
        _reranker.max_length = RERANK_MAX_LENGTH  # 控制 CPU 推理延迟
    return _reranker


# --------------- 查询预处理（提升稀疏召回）--------------- #

# 中文停用词（高频低语义词）
STOP_WORDS = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一", "一个",
    "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好",
    "自己", "这", "他", "她", "它", "们", "那", "个", "被", "从", "对", "但", "以",
    "而", "与", "或", "等", "之", "把", "让", "给", "用", "按", "通过", "根据",
    "什么", "怎么", "如何", "为什么", "哪些", "哪个", "哪里", "请问", "吗", "呢",
    "啊", "呀", "吧", "嗯", "哦", "哈", "呵", "嘿", "喂", "哎",
}

# 英文停用词（避免 "how / do / i / the" 之类污染稀疏检索）
STOP_WORDS |= {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "am", "do", "does", "did", "doing", "have", "has", "had", "having",
    "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them",
    "my", "your", "his", "its", "our", "their", "this", "that", "these", "those",
    "and", "or", "but", "if", "then", "else", "so", "because", "as", "of",
    "to", "in", "on", "at", "by", "for", "with", "about", "into", "from",
    "up", "down", "out", "over", "under", "again", "can", "could", "will",
    "would", "should", "shall", "may", "might", "must", "not", "no", "yes",
    "how", "what", "when", "where", "why", "which", "who", "whom", "whose",
    "there", "here", "please", "any", "some", "all", "very", "just",
}

# 中文多字停用词（按子串移除）：中文不按空格分词，"什么/怎么/请问"等
# 黏在句子里也要去掉，否则稀疏检索被高频低义词污染
CN_SUBSTR_STOPWORDS = {
    w for w in STOP_WORDS
    if len(w) > 1 and all('一' <= ch <= '鿿' for ch in w)
}


def preprocess_query(question: str) -> str:
    """查询预处理：去除停用词、标准化格式，提升稀疏检索效果"""
    if not question:
        return question

    # 1. 去除特殊字符（保留中文、英文、数字）
    question = re.sub(r'[^一-鿿a-zA-Z0-9\s]', ' ', question)

    # 2. 中文多字停用词按子串移除
    for w in CN_SUBSTR_STOPWORDS:
        question = question.replace(w, " ")

    # 3. 去除多余空格
    question = re.sub(r'\s+', ' ', question).strip()

    # 4. 分词并去除停用词（空格分词：英文逐词、中文整段）
    words = question.split()
    filtered_words = [w for w in words if w not in STOP_WORDS and len(w) > 1]

    # 5. 如果过滤后太短，保留原查询
    if len(filtered_words) < 2:
        return question

    return " ".join(filtered_words)


# --------------- 带元数据的检索（核心入口）--------------- #
# 返回 RetrievalResult，包含每条的 dense/sparse 命中排名、RRF 分数、rerank 分数
# 前端可据此展示"检索链路"：这条来自稠密第 3 名 + 稀疏第 7 名 → RRF 融合 → rerank 排第 1

def _hybrid_search(question: str, expr: str | None, pool_cfg: int,
                   partition_name: str | None, collection_name: str | None):
    """一次稠密+稀疏并行检索 + RRF 融合，返回 (scored, dense_results, sparse_results)"""
    processed_query = preprocess_query(question)
    query_vector = embed_query(question)                 # 稠密用原始问题（语义完整）
    query_sparse = embed_query_sparse(processed_query)   # 稀疏用去停用词后的关键词
    search_kwargs = {"collection_name": collection_name} if collection_name else {}
    dense_results = search_dense(query_vector, top_k=pool_cfg,
                                 partition_name=partition_name, expr=expr, **search_kwargs)
    sparse_results = search_sparse(query_sparse, top_k=pool_cfg,
                                   partition_name=partition_name, expr=expr, **search_kwargs)
    return _rrf_scored(dense_results, sparse_results), dense_results, sparse_results


def retrieve_with_meta(question: str, top_k: int = 8,
                       domain: str | None = None,
                       q_type: str | None = None,
                       difficulty: int | None = None,
                       company: str | None = None,
                       position: str | None = None,
                       partition_name: str | None = None,
                       collection_name: str | None = None,
                       candidate_pool: int | None = None,
                       rerank_pool: int | None = None,
                       allow_fallback: bool = True) -> RetrievalResult:
    """执行混合检索并返回带元数据的结果。

    domain/q_type/difficulty/company/position：标量过滤（AND 组合）。
    allow_fallback：domain 过滤下融合候选 < CROSS_DOMAIN_FALLBACK_MIN 时，
    自动放开过滤全库重检并在结果上标记 cross_domain=True（前端提示"跨域结果"）。

    candidate_pool：每个通道取回的候选数（默认 CANDIDATE_POOL）
    rerank_pool：送入重排的候选数（默认 RERANK_POOL）
    """
    pool_cfg = max(top_k * 2, candidate_pool or CANDIDATE_POOL)
    rp_cfg = rerank_pool or RERANK_POOL
    expr = build_filter_expr(domain=domain, q_type=q_type,
                             difficulty=difficulty, company=company, position=position)
    cache_key = _get_cache_key(question, top_k, expr, collection_name,
                               f"{pool_cfg}:{rp_cfg}:{partition_name or ''}")
    cached_result = _get_from_cache(cache_key)
    if cached_result:
        logger.info("retrieve_with_meta cache_hit query=%s", question[:60])
        return cached_result

    t0 = time.perf_counter()

    scored, dense_results, sparse_results = _hybrid_search(
        question, expr, pool_cfg, partition_name, collection_name)

    # domain 过滤召回不足 → 放开过滤全库重检（跨域 fallback）
    cross_domain = False
    if expr and allow_fallback and len(scored) < CROSS_DOMAIN_FALLBACK_MIN:
        logger.info("retrieve_with_meta fallback: filtered=%d < %d, retry without filter",
                    len(scored), CROSS_DOMAIN_FALLBACK_MIN)
        scored, dense_results, sparse_results = _hybrid_search(
            question, None, pool_cfg, partition_name, collection_name)
        cross_domain = True

    # 子块文本 → 排名 + 元数据（10 元组：3=q_type 4=domain 5=difficulty 6=company 7=source 8=title 9=url）
    dense_rank_map: dict[str, int] = {}
    sparse_rank_map: dict[str, int] = {}
    meta_map: dict[str, tuple] = {}
    for rank, item in enumerate(dense_results, start=1):
        dense_rank_map[item[0]] = rank
        meta_map.setdefault(item[0], item[3:])
    for rank, item in enumerate(sparse_results, start=1):
        sparse_rank_map[item[0]] = rank
        meta_map.setdefault(item[0], item[3:])

    doc_rrf_scores = {text: score for text, _, score in scored}

    # 去重再送重排：每个「文档单元」取融合分最高的子块，保证更多不同条目进入重排。
    # 去重键 = q_type|source|title：
    #   - experience/knowledge 文档：同文档多块共享该三元组 → 按文档去重（同 SmartQuery）
    #   - qa_pair 题库：title=题干前80字，每题独立 → 不按仓库 source 折叠
    #     （题库同源几千题共享一个 source，按 source 去重会只剩 1 个候选）
    seen_keys: set[str] = set()
    candidates: list[tuple[str, str]] = []   # (parent_text, child_text)
    for text, parent_text, _ in scored:
        meta = meta_map.get(text)
        key = f"{meta[0]}|{meta[4]}|{meta[5]}" if meta else (parent_text or text)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        candidates.append((parent_text or text, text))
        if len(candidates) >= rp_cfg:
            break

    # Rerank
    pairs = [[question, doc] for doc, _ in candidates]
    rerank_scores = _get_reranker().predict(pairs, batch_size=16) if candidates else []
    ranked = sorted(zip(candidates, rerank_scores), key=lambda x: x[1], reverse=True)
    top = [(doc, child_text, float(score)) for (doc, child_text), score in ranked][:top_k]

    # 组装 RetrievalSource 列表
    sources = []
    for doc, child_text, rerank_score in top:
        meta = meta_map.get(child_text, ("", "", 0, "", "", "", ""))
        qt, dom, diff, comp, src, title, url = (list(meta) + ["", "", 0, "", "", "", ""])[:7]
        sources.append(RetrievalSource(
            text=child_text,
            parent_text=doc,
            dense_rank=dense_rank_map.get(child_text),
            sparse_rank=sparse_rank_map.get(child_text),
            rrf_score=round(doc_rrf_scores.get(child_text, 0.0), 6),
            rerank_score=round(float(rerank_score), 4),
            q_type=qt or "",
            domain=dom or "",
            difficulty=diff or 0,
            company=comp or "",
            source=src or "",
            title=title or "",
            url=url or "",
        ))

    elapsed = (time.perf_counter() - t0) * 1000
    logger.info(
        "retrieve_with_meta query=%s domain=%s dense=%d sparse=%d fused=%d cand=%d top=%d cross_domain=%s (%.1fms)",
        question[:60], domain, len(dense_results), len(sparse_results), len(scored),
        len(candidates), len(top), cross_domain, elapsed,
    )

    result = RetrievalResult(
        documents=[s.parent_text for s in sources],
        sources=sources,
        dense_hit_count=len(dense_results),
        sparse_hit_count=len(sparse_results),
        fused_count=len(scored),
        cross_domain=cross_domain,
    )

    # 指标打点
    metrics.RETRIEVAL_SECONDS.observe(elapsed / 1000.0)
    metrics.RETRIEVAL_HITS.observe(len(sources))

    # 存入缓存
    _put_to_cache(cache_key, result)

    return result
