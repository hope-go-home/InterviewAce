"""题库中间格式 QAItem 校验 + qa_ingest 切块单测"""
import pytest
from pydantic import ValidationError

from data_pipeline.schema import QAItem
from interviewace.rag.qa_ingest import qa_to_chunks


def _item(**kwargs) -> QAItem:
    base = {"question": "RAG 中重排的作用是什么？", "answer": "提升首位排序精度……",
            "domain": "rag", "source": "test"}
    return QAItem(**(base | kwargs))


def test_valid_item():
    item = _item()
    assert item.q_type == "qa_pair"
    assert item.difficulty == 2
    assert item.generated is False


def test_bad_domain_rejected():
    with pytest.raises(ValidationError):
        _item(domain="不存在的域")


def test_bad_difficulty_rejected():
    with pytest.raises(ValidationError):
        _item(difficulty=5)


def test_short_question_rejected():
    with pytest.raises(ValidationError):
        _item(question="嗯？")


def test_content_hash_stable_and_sensitive():
    a = _item()
    b = _item()
    c = _item(answer="另一个答案……")
    assert a.content_hash == b.content_hash
    assert a.content_hash != c.content_hash


def test_jsonl_roundtrip():
    item = _item(company="字节跳动", url="https://example.com/1")
    restored = QAItem.from_jsonl(item.to_jsonl())
    assert restored == item


def test_qa_to_chunks_never_splits():
    child, parent = qa_to_chunks(_item())
    assert child == "RAG 中重排的作用是什么？"
    assert "【问题】" in parent and "【参考答案】" in parent
    assert "提升首位排序精度" in parent
