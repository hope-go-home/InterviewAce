"""题库统一中间格式：所有 ETL 脚本（GitHub 抽取 / 牛客提炼 / LLM 生成）输出此格式。

JSONL 一行一个 QAItem，入库前人工可审。校验规则即「质检门禁」的第一道
（字段完整性 / 长度区间 / 枚举合法），第二道是 LLM judge 自动质检。
"""
import hashlib
import json

from pydantic import BaseModel, Field, field_validator

# 合法枚举（与 interviewace.backend.database.milvus 保持一致）
Q_TYPES = {"qa_pair", "experience", "knowledge"}
DOMAINS = {
    "llm_basics",      # LLM 原理
    "prompt",          # Prompt 工程
    "rag",             # RAG
    "agent",           # Agent
    "vectordb",        # 向量数据库
    "framework",       # LangChain/LangGraph
    "python_backend",  # Python 后端
    "ml_dl",           # ML/DL 基础
    "cs_basic",        # SQL/Redis/OS/网络
}
POSITIONS = {"ai_app_dev", "algorithm", "backend"}


class QAItem(BaseModel):
    """一条题库条目（qa_pair）或一篇面经/知识短文（experience/knowledge）"""
    q_type: str = "qa_pair"
    question: str = Field(min_length=5)
    answer: str = ""
    domain: str
    position: str = "ai_app_dev"
    company: str = ""
    difficulty: int = Field(default=2, ge=1, le=3)
    source: str = ""          # 如 github:km1994/LLMs_interview_notes（幂等清理的键）
    url: str = ""
    generated: bool = False   # True = LLM 生成（版权与质量抽检标记）

    @field_validator("q_type")
    @classmethod
    def _check_q_type(cls, v: str) -> str:
        if v not in Q_TYPES:
            raise ValueError(f"q_type 必须是 {sorted(Q_TYPES)} 之一")
        return v

    @field_validator("domain")
    @classmethod
    def _check_domain(cls, v: str) -> str:
        if v not in DOMAINS:
            raise ValueError(f"domain 必须是 {sorted(DOMAINS)} 之一")
        return v

    @field_validator("position")
    @classmethod
    def _check_position(cls, v: str) -> str:
        if v not in POSITIONS:
            raise ValueError(f"position 必须是 {sorted(POSITIONS)} 之一")
        return v

    @property
    def content_hash(self) -> str:
        """内容哈希（question+answer）：幂等入库与跨源去重的键"""
        raw = f"{self.question.strip()}|{self.answer.strip()}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def to_jsonl(self) -> str:
        return json.dumps(self.model_dump(), ensure_ascii=False)

    @classmethod
    def from_jsonl(cls, line: str) -> "QAItem":
        return cls(**json.loads(line))
