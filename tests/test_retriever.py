"""检索器纯函数单测：RRF 融合 / 查询预处理 / 过滤表达式构造

不依赖 Milvus / 模型 / 网络（search 与 embed 均为外部调用，此处只测纯函数）。
search 元组为 10 元组：(text, parent_text, score, q_type, domain,
difficulty, company, source, title, url)
"""
from interviewace.backend.database.milvus import build_filter_expr
from interviewace.rag.retriever import (
    RRF_DENSE_WEIGHT, RRF_K, RRF_SPARSE_WEIGHT,
    _rrf_scored, preprocess_query, rrf_fusion,
)


def _hit(text: str, parent: str | None = None) -> tuple:
    return (text, parent or f"父块:{text}", 0.0, "qa_pair", "rag", 2,
            "", "test_src", "", "")


# ---------------- RRF 融合 ---------------- #

def test_rrf_dense_first_when_dense_weight_higher():
    dense = [_hit("A"), _hit("B")]
    sparse = [_hit("B"), _hit("A")]
    scored = _rrf_scored(dense, sparse)
    # A 在稠密第 1：0.8/(60+1)；B 在稀疏第 1：0.2/(60+1) → A 总分更高
    assert scored[0][0] == "A"
    assert scored[0][2] > scored[1][2]


def test_rrf_merges_same_text_across_channels():
    dense = [_hit("A")]
    sparse = [_hit("A")]
    scored = _rrf_scored(dense, sparse)
    assert len(scored) == 1
    expected = (RRF_DENSE_WEIGHT + RRF_SPARSE_WEIGHT) / (RRF_K + 1)
    assert abs(scored[0][2] - expected) < 1e-9


def test_rrf_fusion_returns_parents_in_order():
    dense = [_hit("A"), _hit("B")]
    sparse = []
    parents = rrf_fusion(dense, sparse)
    assert parents == ["父块:A", "父块:B"]


def test_rrf_fusion_falls_back_to_child_when_no_parent():
    hit = ("子块无父块", "", 0.0, "qa_pair", "rag", 2, "", "src", "", "")
    assert rrf_fusion([hit], []) == ["子块无父块"]


# ---------------- 查询预处理 ---------------- #

def test_preprocess_removes_stopwords():
    out = preprocess_query("请问 RAG 中的重排是什么")
    assert "请问" not in out
    assert "什么" not in out
    assert "RAG" in out


def test_preprocess_keeps_original_when_too_short_after_filter():
    q = "的了吗"  # 全是停用词，过滤后不足 2 词 → 保留原查询
    assert preprocess_query(q) == q


def test_preprocess_empty():
    assert preprocess_query("") == ""


# ---------------- 过滤表达式 ---------------- #

def test_build_filter_expr_none():
    assert build_filter_expr() is None


def test_build_filter_expr_single():
    assert build_filter_expr(domain="rag") == 'domain == "rag"'


def test_build_filter_expr_and_combination():
    expr = build_filter_expr(domain="rag", q_type="qa_pair", difficulty=2)
    assert 'domain == "rag"' in expr
    assert 'q_type == "qa_pair"' in expr
    assert "difficulty == 2" in expr
    assert expr.count(" and ") == 2


def test_build_filter_expr_escapes_quotes():
    expr = build_filter_expr(company='字节"跳动')
    assert '\\"' in expr
