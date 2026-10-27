"""ETL：KalyanKS-NLP/RAG-Interview-Questions-and-Answers-Hub（MIT License）→ data/jsonl/qa_kalyanks.jsonl

仓库结构：Interview_QA/QA_{n}-{m}.md，每个文件 3 道英文 QA（共 35 文件 / 105 题）：
    ## 📌 Q1: Explain why RAG is required ...?
    ### ✅ Answer
    ...markdown 答案...
    （文件尾部有推广页脚：## **👨🏻‍💻 LLM Engineer Toolkit** 或 **☕ Support the Author**）

README.md 只是 105 题的索引表（链接指向同一批文件），无额外内容，不解析。
仓库无难度标注，按内容深度启发式判断（默认 2）。全部归 rag 域。
答案过短（<80 字符）的条目写入 seeds_kalyanks.jsonl，不进正式 qa 文件。
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data_pipeline.schema import QAItem

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "RAG-Interview-Questions-and-Answers-Hub" / "Interview_QA"
OUT_FILE = Path(__file__).resolve().parents[2] / "data" / "jsonl" / "qa_kalyanks.jsonl"
SEEDS_FILE = Path(__file__).resolve().parents[2] / "data" / "jsonl" / "seeds_kalyanks.jsonl"
SOURCE = "github:KalyanKS-NLP/RAG-Interview-Questions-and-Answers-Hub"
BLOB_URL = "https://github.com/KalyanKS-NLP/RAG-Interview-Questions-and-Answers-Hub/blob/main/Interview_QA"

# ## 📌 Q1: 题干（冒号后可能有多个空格）
Q_HEADING = re.compile(r"^##\s*📌\s*Q(\d+):\s*(.+?)\s*$", re.MULTILINE)
# 答案右边界：文件内所有 ## 标题非题即推广页脚（👨🏻‍💻/☕/Newsletter/Survey 等），
# 纯粗体行（**☕ Support the Author** 等）与长分隔线同理；正文无 ** 开头的行
BOUNDARY = re.compile(r"^##\s|^\*\*|^-{5,}\s*$", re.MULTILINE)

BASIC_PAT = re.compile(r"^(what is|what are|define|what does|explain r, a, and g)", re.IGNORECASE)
ADV_PAT = re.compile(
    r"\b(optimiz|production|latency|scalab|design|deploy|monitor|debug|diagnos|trade-?offs?|cost[- ]eff)", re.IGNORECASE)


def guess_difficulty(question: str) -> int:
    if ADV_PAT.search(question):
        return 3
    if BASIC_PAT.match(question):
        return 1
    return 2


def parse_file(path: Path) -> tuple[list[QAItem], list[QAItem]]:
    text = path.read_text(encoding="utf-8")
    qa_items, seed_items = [], []
    headings = list(Q_HEADING.finditer(text))
    for i, m in enumerate(headings):
        question = re.sub(r"\s+", " ", m.group(2)).strip()
        # 答案区间：当前题标题到下一题标题（或文件尾）
        start = m.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        block = text[start:end]

        ans_match = re.search(r"###\s*✅\s*Answer\s*\n(.*?)$", block, re.DOTALL)
        if not ans_match:
            continue
        answer = ans_match.group(1)
        # 截掉推广页脚与分隔线（任意 ## 标题或长分隔线即边界）
        boundary = BOUNDARY.search(answer)
        if boundary:
            answer = answer[:boundary.start()]
        answer = answer.strip()
        if not answer:
            continue

        item = QAItem(
            q_type="qa_pair",
            question=question,
            answer=answer,
            domain="rag",
            difficulty=guess_difficulty(question),
            source=SOURCE,
            url=f"{BLOB_URL}/{path.name}",
            generated=False,
        )
        if len(answer) >= 80:
            qa_items.append(item)
        else:
            seed_items.append(item)  # 答案过短 → 种子
    return qa_items, seed_items


def main():
    files = sorted(RAW_DIR.glob("QA_*.md"))
    all_qa: list[QAItem] = []
    all_seeds: list[QAItem] = []
    for f in files:
        qa, seeds = parse_file(f)
        all_qa.extend(qa)
        all_seeds.extend(seeds)

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUT_FILE.open("w", encoding="utf-8") as fp:
        for it in all_qa:
            fp.write(it.to_jsonl() + "\n")
    if all_seeds:
        with SEEDS_FILE.open("w", encoding="utf-8") as fp:
            for it in all_seeds:
                fp.write(it.to_jsonl() + "\n")

    diff_dist = {}
    for it in all_qa:
        diff_dist[it.difficulty] = diff_dist.get(it.difficulty, 0) + 1
    print(f"解析文件 {len(files)} 个 → QA {len(all_qa)} 条（种子 {len(all_seeds)} 条），难度分布 {diff_dist}")
    print(f"输出：{OUT_FILE}")


if __name__ == "__main__":
    main()
