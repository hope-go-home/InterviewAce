"""ETL：ather-techie/rag-interview-system（MIT License）→ data/jsonl/rag_ather_techie.jsonl

仓库结构：02_interview_bank/*.md，每个文件约 25 道 QA：
    ## Q1. What is Naive RAG...? `[Basic]`
    <details><summary>💡 Show Answer</summary>
    **Answer:**
    ...markdown 答案...
    </details>
    ---

难度映射：Basic→1 / Intermediate→2 / Advanced→3。全部归 rag 域。
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data_pipeline.schema import QAItem

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "rag-interview-system" / "02_interview_bank"
OUT_FILE = Path(__file__).resolve().parents[2] / "data" / "jsonl" / "rag_ather_techie.jsonl"
SOURCE = "github:ather-techie/rag-interview-system"
BLOB_URL = "https://github.com/ather-techie/rag-interview-system/blob/main/02_interview_bank"

DIFFICULTY_MAP = {"Basic": 1, "Intermediate": 2, "Advanced": 3}

# ## Q1. 题干 `[Basic]`
Q_HEADING = re.compile(r"^##\s+Q(\d+)[.、]\s*(.+?)\s*`\[(\w+)\]`\s*$", re.MULTILINE)


def parse_file(path: Path) -> list[QAItem]:
    text = path.read_text(encoding="utf-8")
    items = []
    headings = list(Q_HEADING.finditer(text))
    for i, m in enumerate(headings):
        question = m.group(2).strip()
        difficulty = DIFFICULTY_MAP.get(m.group(3), 2)
        # 答案区间：当前题标题到下一题标题（或文件尾）
        start = m.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        block = text[start:end]

        # 抽取 **Answer:** 到 </details> 之间的内容
        ans_match = re.search(r"\*\*Answer:\*\*\s*(.+?)</details>", block, re.DOTALL)
        if not ans_match:
            continue
        answer = ans_match.group(1).strip()
        # 去掉尾部分隔线与多余空行
        answer = re.sub(r"\n---+\s*$", "", answer).strip()
        if len(answer) < 20:
            continue

        items.append(QAItem(
            q_type="qa_pair",
            question=question,
            answer=answer,
            domain="rag",
            difficulty=difficulty,
            source=SOURCE,
            url=f"{BLOB_URL}/{path.name}",
            generated=False,
        ))
    return items


def main():
    files = sorted(RAW_DIR.glob("*.md"))
    all_items: list[QAItem] = []
    for f in files:
        items = parse_file(f)
        all_items.extend(items)

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUT_FILE.open("w", encoding="utf-8") as fp:
        for it in all_items:
            fp.write(it.to_jsonl() + "\n")

    diff_dist = {}
    for it in all_items:
        diff_dist[it.difficulty] = diff_dist.get(it.difficulty, 0) + 1
    print(f"解析文件 {len(files)} 个 → QA {len(all_items)} 条，难度分布 {diff_dist}")
    print(f"输出：{OUT_FILE}")


if __name__ == "__main__":
    main()
