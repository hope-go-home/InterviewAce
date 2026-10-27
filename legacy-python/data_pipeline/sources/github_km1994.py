"""ETL：km1994/LLMs_interview_notes → data/jsonl/seeds_km1994.jsonl（**种子**，不入库）

该仓库 main 分支只有一个巨型 README.md：按专题章节组织的中文面试**题干清单**，
答案在其付费专栏（不抓取、不复制——合规红线）。

产出的种子只有 question 没有 answer，供 llm_generate.py 生成答案后再入库。
文件以 seeds_ 开头，ingest_all.py 会跳过。

章节 → domain 映射用关键词匹配，默认 llm_basics。
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data_pipeline.schema import QAItem

README = Path(__file__).resolve().parents[2] / "data" / "raw" / "LLMs_interview_notes" / "README.md"
OUT_FILE = Path(__file__).resolve().parents[2] / "data" / "jsonl" / "seeds_km1994.jsonl"
SOURCE = "github:km1994/LLMs_interview_notes"

# 章节关键词 → domain（顺序优先，先匹配先生效）
DOMAIN_RULES = [
    (["rag", "检索增强"], "rag"),
    (["agent", "智能体"], "agent"),
    (["prompt", "提示词", "提示工程"], "prompt"),
    (["向量", "milvus", "faiss"], "vectordb"),
    (["langchain", "langgraph", "框架"], "framework"),
    (["微调", "rlhf", "lora", "sft", "训练"], "llm_basics"),
    (["推理", "部署", "量化", "加速"], "llm_basics"),
    (["机器学习", "深度学习", "神经网络", "过拟合"], "ml_dl"),
    (["mysql", "redis", "操作系统", "网络", "sql"], "cs_basic"),
    (["python", "后端"], "python_backend"),
]

SECTION_HEADING = re.compile(r"^#{2,4}\s+\[?([^\]\n]+?)\]?(?:\(.+?\))?\s*$", re.MULTILINE)
QUESTION_LINE = re.compile(r"^[-*]\s*(?:\d+\s*[.、]?)?\s*(.{5,}?)\s*$", re.MULTILINE)


def _domain_of(section: str) -> str:
    s = section.lower()
    for keywords, domain in DOMAIN_RULES:
        if any(k in s for k in keywords):
            return domain
    return "llm_basics"


def main():
    text = README.read_text(encoding="utf-8")
    sections = list(SECTION_HEADING.finditer(text))

    items: list[QAItem] = []
    for i, m in enumerate(sections):
        section = m.group(1).strip()
        start, end = m.end(), sections[i + 1].start() if i + 1 < len(sections) else len(text)
        body = text[start:end]
        domain = _domain_of(section)
        for qm in QUESTION_LINE.finditer(body):
            q = qm.group(1).strip().rstrip("？?")
            # 过滤导航/非题目行
            if len(q) < 6 or q.startswith(("http", "[", "!", "<")):
                continue
            if not re.search(r"[一-鿿]", q):  # 必须含中文（题干是中文清单）
                continue
            try:
                items.append(QAItem(
                    q_type="qa_pair",
                    question=q + "？",
                    answer="",          # 种子：答案待 llm_generate.py 生成
                    domain=domain,
                    source=SOURCE,
                    url="https://github.com/km1994/LLMs_interview_notes",
                    generated=False,
                ))
            except Exception:
                continue

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUT_FILE.open("w", encoding="utf-8") as fp:
        for it in items:
            fp.write(it.to_jsonl() + "\n")

    domain_dist = {}
    for it in items:
        domain_dist[it.domain] = domain_dist.get(it.domain, 0) + 1
    print(f"提取种子题干 {len(items)} 条，domain 分布 {domain_dist}")
    print(f"输出：{OUT_FILE}（种子文件，ingest_all.py 会跳过，待 LLM 生成答案）")


if __name__ == "__main__":
    main()
