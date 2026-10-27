"""ETL：wdndev/llm_interview_note（教程式知识文本，非 QA）
→ data/jsonl/knowledge_wdndev.jsonl

仓库结构：docsify 教程，章节目录 `01.大语言模型基础/` ~ `10.大语言模型应用/`
（外加 `98.相关课程/`），每章下嵌套 `<topic>/<topic>.md`。
跳过 README.md / _navbar.md / _sidebar.md 等导航文件与根目录散文件。

拆分规则：按 `##`/`###` 标题（跳过 ``` 围栏内部）切成小节；
过短的相邻节合并至 ≥500 字符，过长的按 `####`/段落边界拆到 ≤4000 字符。
question = 短文标题（topic - 节标题），answer = markdown 正文，difficulty 统一 2。

domain 映射：章节号默认 llm_basics，08 章（检索增强 rag）→ rag；
topic 名覆盖规则：含 agent→agent，含「向量」→vectordb，
含 langchain→framework，含 prompt→prompt。
"""
import re
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data_pipeline.schema import QAItem

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw" / "llm_interview_note"
OUT_FILE = ROOT / "data" / "jsonl" / "knowledge_wdndev.jsonl"
SOURCE = "github:wdndev/llm_interview_note"
BLOB = "https://github.com/wdndev/llm_interview_note/blob/main"

MIN_LEN = 500    # 低于此与相邻节合并
HARD_FLOOR = 200  # 合并后仍低于此的碎块丢弃
MAX_LEN = 4000

CHAPTER_DOMAIN = {
    "01": "llm_basics", "02": "llm_basics", "03": "llm_basics",
    "04": "llm_basics", "05": "llm_basics", "06": "llm_basics",
    "07": "llm_basics", "08": "rag", "09": "llm_basics",
    "10": "llm_basics", "98": "llm_basics",
}
# topic 名覆盖规则（顺序优先，大小写不敏感）
TOPIC_RULES = [
    ("agent", "agent"),
    ("向量", "vectordb"),
    ("langchain", "framework"),
    ("prompt", "prompt"),
]

SKIP_NAMES = {"readme.md", "_navbar.md", "_sidebar.md", "_coverpage.md"}
HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
H4 = re.compile(r"^####\s+")
TOC_LINE = re.compile(r"^\\?\[toc\\?\]\s*$", re.IGNORECASE)
LINK_LINE = re.compile(r"^\s*(?:[-*]|\d+\.)\s*\[.*?\]\(http")


def _is_link_dump(text: str) -> bool:
    """链接导航页判定：链接行占比 >60% 且正文不长（区别于带链接的实质内容）"""
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if not lines or len(text) >= 1500:
        return False
    ratio = sum(1 for ln in lines if LINK_LINE.match(ln)) / len(lines)
    return ratio > 0.6


def _domain_of(chapter: str, topic: str) -> str:
    s = f"{chapter}/{topic}".lower()
    for kw, domain in TOPIC_RULES:
        if kw in s:
            return domain
    num = chapter.split(".", 1)[0]
    return CHAPTER_DOMAIN.get(num, "llm_basics")


def split_sections(text: str) -> list[tuple[str, str]]:
    """按 ##/### 标题切分，返回 [(节标题, 含标题行的节文本)]；H1 标题行丢弃。"""
    lines = text.split("\n")
    sections: list[tuple[str, list[str]]] = []
    cur_title = ""
    cur: list[str] = []
    in_fence = False
    for line in lines:
        if line.strip().startswith("```"):
            in_fence = not in_fence
        if not in_fence:
            m = HEADING.match(line)
            if m:
                if len(m.group(1)) == 1:
                    continue  # 文件级 H1（即 topic 名）不入正文
                if cur or cur_title:
                    sections.append((cur_title, cur))
                cur_title = m.group(2).strip()
                cur = [line]
                continue
        cur.append(line)
    if cur or cur_title:
        sections.append((cur_title, cur))

    out = []
    for title, body_lines in sections:
        body = "\n".join(ln for ln in body_lines if not TOC_LINE.match(ln.strip()))
        body = re.sub(r"\n{3,}", "\n\n", body).strip()
        if body:
            out.append((title, body))
    return out


def merge_small(sections: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """贪心合并：累计长度 <MIN_LEN 时并入下一节，标题取首节。"""
    merged: list[tuple[str, str]] = []
    buf_title, buf = "", ""
    for title, body in sections:
        if not buf:
            buf_title, buf = title, body
        else:
            buf = f"{buf}\n\n{body}"
        if len(buf) >= MIN_LEN:
            merged.append((buf_title, buf))
            buf_title, buf = "", ""
    if buf:
        if merged and len(buf) < MIN_LEN:
            t, b = merged.pop()
            merged.append((t, f"{b}\n\n{buf}"))
        else:
            merged.append((buf_title, buf))
    return merged


def split_large(title: str, body: str) -> list[tuple[str, str]]:
    """超长节按 #### 或段落边界拆到 ≤MAX_LEN，续块标题加（续）。"""
    if len(body) <= MAX_LEN:
        return [(title, body)]
    # 优先按 #### 边界，退化为空行段落边界
    cut_points = [m.start() for m in re.finditer(r"\n(?=####\s|\n)", body)]
    chunks, start = [], 0
    while len(body) - start > MAX_LEN:
        limit = start + MAX_LEN
        cands = [p for p in cut_points if start + HARD_FLOOR < p <= limit]
        cut = max(cands) if cands else limit
        chunks.append(body[start:cut].strip())
        start = cut
    chunks.append(body[start:].strip())
    return [(title if i == 0 else f"{title}（续{i}）", c)
            for i, c in enumerate(chunks) if c]


def main():
    md_files = sorted(
        f for f in RAW_DIR.rglob("*.md")
        if f.name.lower() not in SKIP_NAMES
        and re.match(r"^\d{2}\.", f.relative_to(RAW_DIR).parts[0])
    )

    items: list[QAItem] = []
    dropped = 0
    for path in md_files:
        rel = path.relative_to(RAW_DIR)
        chapter = rel.parts[0]
        topic = path.parent.name if path.parent != RAW_DIR else path.stem
        domain = _domain_of(chapter, topic)
        url = f"{BLOB}/{quote(str(rel).replace(chr(92), '/'))}"
        text = path.read_text(encoding="utf-8")

        sections = merge_small(split_sections(text))
        for title, body in sections:
            for sub_title, chunk in split_large(title, body):
                if len(chunk) < HARD_FLOOR or _is_link_dump(chunk):
                    dropped += 1
                    continue
                q = f"{topic} - {sub_title}" if sub_title else topic
                try:
                    items.append(QAItem(
                        q_type="knowledge",
                        question=q,
                        answer=chunk,
                        domain=domain,
                        difficulty=2,
                        source=SOURCE,
                        url=url,
                        generated=False,
                    ))
                except Exception:
                    dropped += 1

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUT_FILE.open("w", encoding="utf-8") as fp:
        for it in items:
            fp.write(it.to_jsonl() + "\n")

    dom_dist: dict[str, int] = {}
    len_buckets = {"<500": 0, "500-4000": 0, ">4000": 0}
    for it in items:
        dom_dist[it.domain] = dom_dist.get(it.domain, 0) + 1
        n = len(it.answer)
        len_buckets["<500" if n < 500 else "500-4000" if n <= 4000 else ">4000"] += 1
    print(f"知识短文 {len(items)} 条（丢弃碎块 {dropped}），源文件 {len(md_files)} 个")
    print(f"domain 分布 {dom_dist}")
    print(f"长度分布 {len_buckets}")
    print(f"输出：{OUT_FILE}")


if __name__ == "__main__":
    main()
