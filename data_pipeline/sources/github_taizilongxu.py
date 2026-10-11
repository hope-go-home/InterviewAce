"""ETL：taizilongxu/interview_python → data/jsonl/qa_taizilongxu.jsonl

仓库结构：Readme.md 单文件即全部题库。markdown-toc 目录之后：
    # Python语言特性            ← h1 章节（操作系统/数据库/网络/*NIX/数据结构/编程题）
    ## 1 Python的函数参数传递    ← h2 题目
    ### 1 引用计数              ← h3 属于答案内容
    ```python 代码块内的 `# xxx` 是注释而非标题（如 # mysingleton.py）→ fence 感知解析
    ```

domain 一律 python_backend；难度：编程题章节=3（实战），「什么是/区别」类概念题=1，
其余默认 2。答案 <80 字符（多为纯外链指路）的条目写入 seeds_taizilongxu.jsonl。
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data_pipeline.schema import QAItem

ROOT = Path(__file__).resolve().parents[2]
RAW_FILE = ROOT / "data" / "raw" / "interview_python" / "Readme.md"
QA_FILE = ROOT / "data" / "jsonl" / "qa_taizilongxu.jsonl"
SEEDS_FILE = ROOT / "data" / "jsonl" / "seeds_taizilongxu.jsonl"
SOURCE = "github:taizilongxu/interview_python"
URL = "https://github.com/taizilongxu/interview_python/blob/master/Readme.md"

QUESTION_MIN = 8    # 题干预文最少字符
ANSWER_MIN = 80     # 正式答案最少字符，不足转 seeds

TOC_END = "<!-- markdown-toc end -->"
HEADING_RE = re.compile(r"^(#{1,6})\s*(.*?)\s*$")
Q_NUM_RE = re.compile(r"^\d+\s+")  # 题干前导编号 `1 ` / `21 `


def iter_sections(text: str):
    """fence 感知扫描 h1/h2：yield (level, title, line_start, line_end)"""
    in_fence = False
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
        elif not in_fence:
            m = HEADING_RE.match(stripped)
            if m and m.group(2) and len(m.group(1)) <= 2:
                yield len(m.group(1)), m.group(2), offset, offset + len(line)
        offset += len(line)


def clean_answer(block: str) -> str:
    block = re.sub(r"<img[^>]*/?>", "", block)
    block = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", block)
    block = re.sub(r"\n{3,}", "\n\n", block)
    block = re.sub(r"\n?-{3,}\s*$", "", block)
    return block.strip()


def effective_len(answer: str) -> int:
    """有效内容长度：去掉 URL（纯外链指路的答案不算合格答案）"""
    return len(re.sub(r"https?://\S+", "", answer).strip())


def guess_difficulty(question: str, chapter: str) -> int:
    if chapter == "编程题":
        return 3  # 手写代码实战
    if re.search(r"什么是|是什么|区别", question):
        return 1
    return 2


def main() -> None:
    text = RAW_FILE.read_text(encoding="utf-8").replace("\r\n", "\n")
    # 跳过 markdown-toc 目录
    toc_pos = text.find(TOC_END)
    if toc_pos >= 0:
        text = text[toc_pos + len(TOC_END):]

    heads = list(iter_sections(text))
    qa_items: list[QAItem] = []
    seed_items: list[QAItem] = []
    chapter = ""
    # h2 题目区间：当前 h2 到下一个 h1/h2
    for i, (lvl, title, start, end) in enumerate(heads):
        if lvl == 1:
            chapter = title.strip().lstrip("*").strip()  # `*NIX` → `NIX`
            continue
        question = Q_NUM_RE.sub("", title).strip()
        # 题干过短则补章节前缀兜底（如「协程」→「Python语言特性：协程」）
        if len(question) < QUESTION_MIN and chapter:
            question = f"{chapter}：{question}"
        if len(question) < QUESTION_MIN:
            continue
        blk_end = heads[i + 1][2] if i + 1 < len(heads) else len(text)
        answer = clean_answer(text[end:blk_end])
        try:
            item = QAItem(
                q_type="qa_pair",
                question=question,
                answer=answer,
                domain="python_backend",
                position="ai_app_dev",
                company="",
                difficulty=guess_difficulty(question, chapter),
                source=SOURCE,
                url=URL,
                generated=False,
            )
        except Exception:
            continue
        (qa_items if effective_len(answer) >= ANSWER_MIN else seed_items).append(item)

    QA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with QA_FILE.open("w", encoding="utf-8") as fp:
        for it in qa_items:
            fp.write(it.to_jsonl() + "\n")
    if seed_items:
        with SEEDS_FILE.open("w", encoding="utf-8") as fp:
            for it in seed_items:
                fp.write(it.to_jsonl() + "\n")

    diff_dist: dict[int, int] = {}
    for it in qa_items:
        diff_dist[it.difficulty] = diff_dist.get(it.difficulty, 0) + 1
    print(f"QA {len(qa_items)} 条（难度分布 {diff_dist}）→ {QA_FILE.name}")
    print(f"seeds {len(seed_items)} 条（答案<{ANSWER_MIN}字符）→ {SEEDS_FILE.name if seed_items else '无'}")
    print(f"输出：{QA_FILE}")


if __name__ == "__main__":
    main()
