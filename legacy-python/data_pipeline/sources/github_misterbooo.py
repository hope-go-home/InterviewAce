"""ETL：MisterBooo/llm-interview-questions → data/jsonl/seeds_misterbooo.jsonl（种子，不入库）

仓库结构：modules/{domain}.md，每文件约 8-20 题：
    ### 01. ReAct vs Plan-and-Execute 怎么选?
    > **30 秒回答：** ...（简答，作为生成提示）
    > **继续追问：** ...
    **复核：** ... **参考资料：** ...

题目设计精良且中文，但答案只有「30 秒简答」→ 作为种子，
简答内容作为生成提示（hint），由 llm_generate.py seeds 模式扩写完整答案。
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data_pipeline.schema import QAItem

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "llm-interview-questions" / "modules"
OUT_FILE = Path(__file__).resolve().parents[2] / "data" / "jsonl" / "seeds_misterbooo.jsonl"
SOURCE = "github:MisterBooo/llm-interview-questions"
BLOB_URL = "https://github.com/MisterBooo/llm-interview-questions/blob/main/modules"

MODULE_DOMAIN = {
    "agent.md": "agent",
    "prompt-engineering.md": "prompt",
    "rag-foundations.md": "rag",
    "reranking.md": "rag",
    "document-processing.md": "rag",
    "vector-search.md": "vectordb",
    "model-architecture.md": "llm_basics",
    "model-training.md": "llm_basics",
    "fine-tuning.md": "llm_basics",
    "rlhf-alignment.md": "llm_basics",
    "inference-optimization.md": "llm_basics",
    "multimodal.md": "llm_basics",
    "knowledge-graph.md": "llm_basics",
    "evaluation-monitoring.md": "llm_basics",
}

Q_HEADING = re.compile(r"^###\s+\d+[.、]\s*(.+?)\s*$", re.MULTILINE)
BRIEF_ANSWER = re.compile(r"30\s*秒回答[：:]\*\*\s*(.+?)(?:\n\s*>|\n\n)", re.DOTALL)


def parse_file(path: Path, domain: str) -> list[QAItem]:
    text = path.read_text(encoding="utf-8")
    items = []
    headings = list(Q_HEADING.finditer(text))
    for i, m in enumerate(headings):
        question = m.group(1).strip().rstrip("？?")
        start = m.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        block = text[start:end]
        am = BRIEF_ANSWER.search(block)
        hint = re.sub(r"\s+", " ", am.group(1)).strip() if am else ""
        try:
            items.append(QAItem(
                q_type="qa_pair",
                question=question + "？",
                answer=hint,        # 简答作为生成提示（不入库，seeds_ 前缀会被跳过）
                domain=domain,
                difficulty=2,
                source=SOURCE,
                url=f"{BLOB_URL}/{path.name}",
                generated=False,
            ))
        except Exception:
            continue
    return items


def main():
    all_items: list[QAItem] = []
    for fname, domain in MODULE_DOMAIN.items():
        path = RAW_DIR / fname
        if not path.exists():
            print(f"跳过缺失文件 {fname}")
            continue
        all_items.extend(parse_file(path, domain))

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUT_FILE.open("w", encoding="utf-8") as fp:
        for it in all_items:
            fp.write(it.to_jsonl() + "\n")
    print(f"提取种子 {len(all_items)} 条 → {OUT_FILE.name}")


if __name__ == "__main__":
    main()
