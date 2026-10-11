"""ETL：Snailclimb/JavaGuide（docs/ 下 MySQL/Redis/网络/操作系统 教程与面试题）
→ data/jsonl/cs_javaguide.jsonl

收录范围（稀疏克隆只含 database/ 与 cs-basics/）：
- database/mysql/、database/redis/、database/sql/（含 basis.md、character-set.md）
- cs-basics/network/、cs-basics/operating-system/
跳过：mongodb/、elasticsearch/、nosql.md（非 MySQL/Redis 范畴）、
algorithms/、data-structure/（非目标域）、README.md 导航页，
以及文件名/路径含 jvm/jdk/java/collection 等 Java 专属内容（兜底防御）。

拆分规则（与 github_csbase.py 一致）：按 ##/### 标题切节（跳过 ``` 围栏内部），
<500 字符的相邻节贪心合并，>4000 按 ####/段落边界再拆，<200 碎块丢弃；
图片 ![alt](url) 仅保留 alt 文本；YAML frontmatter 剥离，title 作文件标题。

QA 抽取：面试题合集文件（问题式标题 ≥3 个且占比 ≥50%，如 *-questions-*.md、
other-network-questions.md 的 #### 问题）按 qa_pair 抽取——question=问题标题，
answer=到下一同级/更高级标题之间的正文（≥80 字符）；## 大类容器标题跳过。
其余文件按 knowledge 短文处理，question = 文件标题 - 节标题。

domain 统一 cs_basic，difficulty 统一 2。
"""
import re
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data_pipeline.schema import QAItem

ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = ROOT / "data" / "raw" / "JavaGuide" / "docs"
OUT_FILE = ROOT / "data" / "jsonl" / "cs_javaguide.jsonl"
SOURCE = "github:Snailclimb/JavaGuide"
BLOB = "https://github.com/Snailclimb/JavaGuide/blob/main/docs"

MIN_LEN = 500     # 低于此与相邻节合并
HARD_FLOOR = 200  # 合并后仍低于此的碎块丢弃
MAX_LEN = 4000
QA_MIN_ANSWER = 80   # QA 答案下限
QA_MIN_COUNT = 3     # 判定 QA 文件的问题标题下限
QA_MIN_RATIO = 0.5   # 问题式标题占比下限

# 收录的 (一级目录, 二级目录)，以及额外收录的散文件
INCLUDE_DIRS = {
    ("database", "mysql"), ("database", "redis"), ("database", "sql"),
    ("cs-basics", "network"), ("cs-basics", "operating-system"),
}
EXTRA_FILES = {"database/basis.md", "database/character-set.md"}
SKIP_NAMES = {"readme.md", "home.md"}
JAVA_HINT = re.compile(r"jvm|jdk|java|collection|hashmap", re.IGNORECASE)

HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
LINK_LINE = re.compile(r"^\s*(?:[-*]|\d+\.)\s*\[.*?\]\(")
FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
Q_PREFIX = ("为什么", "如何", "怎么", "什么是", "哪些", "是否", "有没有",
            "能否", "能不能", "说一下", "说说", "谈谈", "谈一下", "讲一讲", "啥")


def clean_heading(t: str) -> str:
    """去掉 ⭐️👍 等前后装饰符号"""
    t = t.strip()
    t = re.sub(r"^[^\w一-鿿（(「《“]+", "", t)
    t = re.sub(r"[☀-➿\U0001f000-\U0001faff⭕﻿]+$", "", t)
    return t.strip()


def is_question(t: str) -> bool:
    return t.endswith(("？", "?")) or t.startswith(Q_PREFIX)


def clean_body(text: str) -> str:
    """图片保留 alt 文本，去 HTML 注释 / img 标签 / VuePress 容器标记"""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", lambda m: m.group(1), text)
    text = re.sub(r"<img[^>]*>", "", text)
    text = re.sub(r"(?m)^:::.*$", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"(?:\n\s*-{3,}\s*)+$", "", text)
    return text.strip()


def is_link_dump(text: str) -> bool:
    """链接导航页判定：链接行占比 >40% 且正文不长"""
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if not lines or len(text) >= 3000:
        return False
    ratio = sum(1 for ln in lines if LINK_LINE.match(ln)) / len(lines)
    return ratio > 0.4


def strip_frontmatter(text: str) -> tuple[str, str]:
    """剥离 YAML frontmatter，返回 (title, 正文)"""
    m = FRONTMATTER.match(text)
    if not m:
        return "", text
    title = ""
    tm = re.search(r"(?m)^title:\s*(.+?)\s*$", m.group(1))
    if tm:
        title = tm.group(1).strip("\"'")
    return title, text[m.end():]


def scan_headings(text: str) -> list[tuple[int, str, int, int]]:
    """全部标题 [(level, 标题, 行起点, 行末点)]，跳过 ``` 围栏内部"""
    heads = []
    in_fence = False
    pos = 0
    for line in text.split("\n"):
        line_start = pos
        pos += len(line) + 1
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = HEADING.match(line)
        if m:
            heads.append((len(m.group(1)), clean_heading(m.group(2)), line_start, pos))
    return heads


def file_title(fm_title: str, text: str, stem: str) -> str:
    """frontmatter title 优先，其次第一个 H1，最后文件名"""
    if fm_title:
        return fm_title
    for lv, title, _, _ in scan_headings(text):
        if lv == 1 and title:
            return title
    return stem


def extract_qa(text: str, url: str, top_title: str = "") -> list[QAItem] | None:
    """QA 文件判定 + 抽取；非 QA 文件返回 None。

    问题式标题（##/###/####，以？/? 结尾或疑问词开头）≥3 且占比 ≥50% 判为 QA 文件；
    答案区间 = 问题标题行末 → 下一个同级或更高级标题（更深标题留在答案内）。
    """
    heads = [(lv, t, ls, le) for lv, t, ls, le in scan_headings(text)
             if 2 <= lv <= 4 and t]
    q_heads = [h for h in heads if is_question(h[1])]
    if len(q_heads) < QA_MIN_COUNT or len(q_heads) / max(len(heads), 1) < QA_MIN_RATIO:
        return None

    items = []
    parents: dict[int, str] = {1: top_title} if top_title else {}
    # 各层级最近出现的标题（含文件标题作兜底），用于给短问题补上下文
    for i, (lv, title, _, line_end) in enumerate(heads):
        question = title
        if is_question(title):
            if len(title) <= 10:
                # 「有哪些解决办法？」类泛化短问题，带上父级标题作上下文
                parent = next((parents[l] for l in sorted(parents, reverse=True)
                               if l < lv and parents[l]), "")
                if parent:
                    question = f"{parent}：{title}"
        else:
            parents[lv] = title
            parents = {l: t for l, t in parents.items() if l <= lv}
            continue
        parents[lv] = title
        parents = {l: t for l, t in parents.items() if l <= lv}
        end = len(text)
        for lv2, _, ls2, _ in heads[i + 1:]:
            if lv2 <= lv:
                end = ls2
                break
        answer = clean_body(text[line_end:end])
        if len(answer) < QA_MIN_ANSWER or len(question) < 5:
            continue
        items.append(QAItem(
            q_type="qa_pair",
            question=question,
            answer=answer,
            domain="cs_basic",
            difficulty=2,
            source=SOURCE,
            url=url,
            generated=False,
        ))
    return items


def split_sections(text: str) -> list[tuple[str, str]]:
    """按 ##/### 标题切分，返回 [(节标题, 含标题行的节文本)]；H1 标题行丢弃。
    ### 节标题带上当前 ## 父标题作前缀，避免「应用场景」等跨节重名。"""
    lines = text.split("\n")
    sections: list[tuple[str, list[str]]] = []
    cur_title = ""
    cur: list[str] = []
    h2 = ""       # 当前 ## 父标题
    in_fence = False
    for line in lines:
        if line.strip().startswith("```"):
            in_fence = not in_fence
        if not in_fence:
            m = HEADING.match(line)
            if m:
                if len(m.group(1)) == 1:
                    continue  # 文件级 H1 不入正文
                if len(m.group(1)) <= 3:
                    if cur or cur_title:
                        sections.append((cur_title, cur))
                    t = clean_heading(m.group(2))
                    if len(m.group(1)) == 2:
                        h2 = t
                        cur_title = t
                    else:
                        cur_title = f"{h2} - {t}" if h2 else t
                    cur = [line]
                    continue
        cur.append(line)
    if cur or cur_title:
        sections.append((cur_title, cur))

    out = []
    for title, body_lines in sections:
        body = clean_body("\n".join(body_lines))
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


def extract_knowledge(text: str, url: str, f_title: str) -> tuple[list[QAItem], int]:
    items: list[QAItem] = []
    dropped = 0
    for title, body in merge_small(split_sections(text)):
        for sub_title, chunk in split_large(title, body):
            if len(chunk) < HARD_FLOOR or is_link_dump(chunk):
                dropped += 1
                continue
            q = f"{f_title} - {sub_title}" if sub_title else f_title
            try:
                items.append(QAItem(
                    q_type="knowledge",
                    question=q,
                    answer=chunk,
                    domain="cs_basic",
                    difficulty=2,
                    source=SOURCE,
                    url=url,
                    generated=False,
                ))
            except Exception:
                dropped += 1
    return items, dropped


def in_scope(path: Path) -> bool:
    rel = str(path.relative_to(DOCS_DIR)).replace("\\", "/")
    if JAVA_HINT.search(rel):
        return False
    if tuple(path.relative_to(DOCS_DIR).parts[:2]) in INCLUDE_DIRS:
        return True
    return rel in EXTRA_FILES


def main():
    md_files = sorted(
        f for f in DOCS_DIR.rglob("*.md")
        if f.name.lower() not in SKIP_NAMES and in_scope(f)
    )

    items: list[QAItem] = []
    dropped = skipped = qa_files = 0
    for path in md_files:
        rel = str(path.relative_to(DOCS_DIR)).replace("\\", "/")
        url = f"{BLOB}/{quote(rel)}"
        fm_title, text = strip_frontmatter(path.read_text(encoding="utf-8"))
        if is_link_dump(text):
            skipped += 1
            continue

        f_title = file_title(fm_title, text, path.stem)
        qa = extract_qa(text, url, f_title)
        if qa is not None:
            qa_files += 1
            items.extend(qa)
        else:
            kn, dr = extract_knowledge(text, url, f_title)
            items.extend(kn)
            dropped += dr

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUT_FILE.open("w", encoding="utf-8") as fp:
        for it in items:
            fp.write(it.to_jsonl() + "\n")

    n_qa = sum(1 for it in items if it.q_type == "qa_pair")
    len_buckets = {"<500": 0, "500-4000": 0, ">4000": 0}
    for it in items:
        n = len(it.answer)
        len_buckets["<500" if n < 500 else "500-4000" if n <= 4000 else ">4000"] += 1
    print(f"源文件 {len(md_files)} 个（QA 文件 {qa_files} 个，导航页跳过 {skipped} 个）")
    print(f"产出 {len(items)} 条：qa_pair {n_qa} 条 / knowledge {len(items) - n_qa} 条"
          f"（碎块丢弃 {dropped}）")
    print(f"长度分布 {len_buckets}")
    print(f"输出：{OUT_FILE}")


if __name__ == "__main__":
    main()
