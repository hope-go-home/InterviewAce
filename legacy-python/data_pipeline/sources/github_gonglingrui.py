"""ETL：GongLingRui/llm-agents-interview → data/jsonl/qa_gonglingrui.jsonl

仓库为中文面经/笔记混合库，只抽取有明确 QA 结构的部分：

1. 大模型原理/文言AI/大模型基础面试题/*.md —— 编号面试题系列，一题一节：
       ### 1. 简单介绍一下大语言模型【LLMs】？
       ### 一、什么是大模型幻觉问题？
   题干 = 编号标题（阿拉伯数字 `N.` 或中文数字 `一、`）且含疑问词/问号；
   答案 = 到下一题干标题为止，截断「参考资料/参考链接」尾注。
2. 大模型原理/文言AI/Agent系列/*.md、transformer篇/*.md —— 每文件一道主题题，
   题干 = 首个正文标题（优先与文件编号一致的标题，过滤 `--` 引用类垃圾标题）。
3. 大模型原理/文言AI/后训练/3.监督微调SFT.md —— 文末「快问快答」：
       1. **Q1：LoRA为什么推理时没有额外延迟？**
          A：...
   后训练/*.md 另按「疑问句式标题」扫描（如 #### 4.1 DPO针对RLHF做了哪些改进）。
4. 大模型面试题/语义表达/*.md —— 首个 # 标题即题干，余下全文为答案。
5. 大模型原理/RAG知识汇总-全量.md —— 面试指南小节：
       **Q1: 什么是文本分块？...**        *   **回答思路**：...
   难度取 `#### Level N` 标注（无标注默认 2）。

其余目录（ai-agent-notes 读书笔记、参考文章、上下文工程汇总、6.ScalingLaw
纯截图等）无 QA 结构，不抽取。答案 <80 字符的条目写入 seeds_gonglingrui.jsonl。
"""
import re
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data_pipeline.schema import QAItem

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw" / "llm-agents-interview"
QA_FILE = ROOT / "data" / "jsonl" / "qa_gonglingrui.jsonl"
SEEDS_FILE = ROOT / "data" / "jsonl" / "seeds_gonglingrui.jsonl"
SOURCE = "github:GongLingRui/llm-agents-interview"
BLOB_URL = "https://github.com/GongLingRui/llm-agents-interview/blob/main"

QUESTION_MIN = 8    # 题干预文最少字符
ANSWER_MIN = 80     # 正式答案最少字符，不足转 seeds

HEADING_RE = re.compile(r"^(#{1,6})\s*(.*?)\s*$")
# 编号题干：`1. xxx` / `4.xxx`（排除 5.1 小数小节）/ `一、xxx`
Q_NUM_RE = re.compile(r"^(?:\d+[.、](?!\d)|[一二三四五六七八九十]+、)\s*(.+?)\s*$")
INTERROGATIVE = re.compile(r"什么|如何|怎么|怎样|哪些|为什么|为啥|区别|介绍|简述|详细|评价|评估|缓解|原理|是否|能否|吗")
REF_HEAD_RE = re.compile(r"^#{1,6}\s*参考(资料|链接|文献)", re.MULTILINE)
BOLD_Q_RE = re.compile(r"\*\*Q(\d+)[：:]\s*(.+?)\*\*")
LEVEL_RE = re.compile(r"^####\s+Level\s+(\d)")


def iter_headings(text: str):
    """fence 感知的标题扫描，yield (level, title, line_start, line_end)"""
    in_fence = False
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
        elif not in_fence:
            m = HEADING_RE.match(stripped)
            if m and m.group(2):
                yield len(m.group(1)), m.group(2), offset, offset + len(line)
        offset += len(line)


def clean_answer(block: str) -> str:
    """去掉图片标签/引用、尾部分隔线，收敛空行"""
    block = re.sub(r"<img[^>]*/?>", "", block)
    block = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", block)
    block = re.sub(r"\n{3,}", "\n\n", block)
    block = re.sub(r"\n?-{3,}\s*$", "", block)
    return block.strip()


def effective_len(answer: str) -> int:
    """有效内容长度：去掉 URL（纯外链指路的答案不算合格答案）"""
    return len(re.sub(r"https?://\S+", "", answer).strip())


def guess_difficulty(question: str) -> int:
    if re.search(r"优化策略|评估|评价|缓解|改进|并行化|实战|综合", question):
        return 3
    if re.search(r"什么是|是什么|简单介绍|指什么|定义|有哪些|分类|优点|缺点|特点", question):
        return 1
    return 2


def url_for(path: Path) -> str:
    rel = path.relative_to(RAW_DIR).as_posix()
    return f"{BLOB_URL}/{quote(rel)}"


def make_item(question: str, answer: str, domain: str, path: Path,
              difficulty: int | None = None) -> QAItem | None:
    question = re.sub(r"\s+", " ", question).strip()
    if len(question) < QUESTION_MIN:
        return None
    try:
        return QAItem(
            q_type="qa_pair",
            question=question,
            answer=answer,
            domain=domain,
            position="ai_app_dev",
            company="",
            difficulty=difficulty if difficulty is not None else guess_difficulty(question),
            source=SOURCE,
            url=url_for(path),
            generated=False,
        )
    except Exception:
        return None


# ---------- 1. 大模型基础面试题：编号题干 ----------

def parse_numbered_file(path: Path, domain: str) -> list[QAItem]:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    heads = list(iter_headings(text))
    qs = []
    for _lvl, title, start, end in heads:
        m = Q_NUM_RE.match(title)
        if not m:
            continue
        qtext = m.group(1)
        if qtext.endswith(("？", "?")) or INTERROGATIVE.search(qtext):
            qs.append((qtext, start, end))
    items = []
    for i, (qtext, _s, end) in enumerate(qs):
        blk_end = qs[i + 1][1] if i + 1 < len(qs) else len(text)
        block = REF_HEAD_RE.split(text[end:blk_end])[0]  # 截断参考资料尾注
        answer = clean_answer(block)
        item = make_item(qtext, answer, domain, path)
        if item:
            items.append(item)
    return items


# ---------- 2. Agent系列 / transformer篇：一文件一主题题 ----------

def parse_topic_file(path: Path, domain: str) -> list[QAItem]:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    heads = [h for h in iter_headings(text) if h[0] <= 3]
    if not heads:
        return []
    # 优先与文件编号一致的标题（如文件 1.基础结构.md → `# 1.介绍一下...`）
    prefer = re.match(r"^(\d+)", path.name)
    chosen = None
    if prefer:
        for h in heads:
            if re.match(rf"^{prefer.group(1)}[.、]", h[1]):
                chosen = h
                break
    if chosen is None:  # 退化：首个干净标题（过滤 `--` 引用类垃圾标题）
        for h in heads:
            if "--" not in h[1] and len(h[1]) >= 4:
                chosen = h
                break
    if chosen is None:
        return []
    qtext = re.sub(r"^\d+(?:\.\d+)*[.、\-]\s*", "", chosen[1]).strip().rstrip("：:")
    answer = clean_answer(text[chosen[3]:])
    item = make_item(qtext, answer, domain, path)
    return [item] if item else []


# ---------- 3a. 后训练/监督微调SFT：快问快答 **QN：...** A：... ----------

def parse_bold_qa_file(path: Path, domain: str) -> list[QAItem]:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    matches = list(BOLD_Q_RE.finditer(text))
    items = []
    for i, m in enumerate(matches):
        qtext = m.group(2).strip()
        # 答案边界：下一个 Q 所在行的行首（Q 行形如 `3. **Q2：...**`）
        nxt = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        nxt = text.rfind("\n", 0, nxt) + 1
        block = text[m.end():nxt]
        a = re.search(r"A[：:]\s*", block)
        if not a:
            continue
        answer = re.split(r"^#{1,6}\s", block[a.end():], flags=re.MULTILINE)[0]
        answer = clean_answer(answer)
        item = make_item(qtext, answer, domain, path)
        if item:
            items.append(item)
    return items


# ---------- 3b. 后训练：疑问句式标题（如 #### 4.1 DPO针对RLHF做了哪些改进） ----------

def parse_interrogative_headings(path: Path, domain: str) -> list[QAItem]:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    heads = list(iter_headings(text))
    items = []
    for idx, (lvl, title, start, end) in enumerate(heads):
        qtext = re.sub(r"^\d+(?:\.\d+)*[.、\-]\s*|^[一二三四五六七八九十]+、\s*", "", title).strip()
        if not INTERROGATIVE.search(qtext) and not qtext.endswith(("？", "?")):
            continue
        # 答案到同级或更高级标题为止
        blk_end = len(text)
        for lvl2, _t2, s2, _e2 in heads[idx + 1:]:
            if lvl2 <= lvl:
                blk_end = s2
                break
        answer = clean_answer(text[end:blk_end])
        item = make_item(qtext, answer, domain, path)
        if item:
            items.append(item)
    return items


# ---------- 4. 大模型面试题/语义表达：首个 h1 即题干 ----------

def parse_h1_file(path: Path, domain: str) -> list[QAItem]:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    for lvl, title, _s, end in iter_headings(text):
        if lvl == 1:
            answer = clean_answer(text[end:])
            item = make_item(title, answer, domain, path)
            return [item] if item else []
    return []


# ---------- 5. RAG知识汇总-全量：面试指南 **QN: ...** + #### Level N 难度 ----------

def parse_rag_guide(path: Path, domain: str = "rag") -> list[QAItem]:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    lines = text.splitlines()
    items = []
    difficulty = 2
    i = 0
    while i < len(lines):
        line = lines[i]
        lv = LEVEL_RE.match(line.strip())
        if lv:
            difficulty = min(3, max(1, int(lv.group(1))))
        m = re.match(r"^\*\*Q(\d+)[：:]\s*(.+?)\*\*\s*$", line.strip())
        if not m:
            i += 1
            continue
        qtext = m.group(2).strip()
        # 答案 = 后续的引用/缩进行；遇到下一题（**QN）、新标题或顶格正文即停
        j = i + 1
        while j < len(lines):
            ln = lines[j]
            if re.match(r"^\s*\*\*Q\d+[：:]", ln) or HEADING_RE.match(ln.strip()):
                break
            if not ln.strip():
                j += 1
                continue
            if ln[0] in " \t" or ln.lstrip().startswith("*") or re.match(r"^\d+[A-Za-z]*[.、]", ln):
                j += 1
                continue
            break
        answer = clean_answer("\n".join(lines[i + 1:j]))
        item = make_item(qtext, answer, domain, path, difficulty=difficulty)
        if item:
            items.append(item)
        i = j
    return items


def main():
    qa_items: list[QAItem] = []
    seed_items: list[QAItem] = []

    def collect(items: list[QAItem]):
        for it in items:
            (qa_items if effective_len(it.answer) >= ANSWER_MIN else seed_items).append(it)

    # 1. 大模型基础面试题（文件名含 RAG 的归 rag 域，其余 llm_basics）
    d1 = RAW_DIR / "大模型原理" / "文言AI" / "大模型基础面试题"
    for f in sorted(d1.glob("*.md")):
        domain = "rag" if re.search(r"rag", f.name, re.IGNORECASE) else "llm_basics"
        collect(parse_numbered_file(f, domain))

    # 2. Agent系列（agent）、transformer篇（llm_basics）：一文件一题
    for f in sorted((RAW_DIR / "大模型原理" / "文言AI" / "Agent系列").glob("*.md")):
        collect(parse_topic_file(f, "agent"))
    for f in sorted((RAW_DIR / "大模型原理" / "文言AI" / "transformer篇").glob("*.md")):
        collect(parse_topic_file(f, "llm_basics"))

    # 3. 后训练（llm_basics）：快问快答 + 疑问句式标题
    d3 = RAW_DIR / "大模型原理" / "文言AI" / "后训练"
    collect(parse_bold_qa_file(d3 / "3.监督微调SFT.md", "llm_basics"))
    for f in sorted(d3.glob("*.md")):
        collect(parse_interrogative_headings(f, "llm_basics"))

    # 4. 大模型面试题（llm_basics）：首个 h1 即题干
    for f in sorted((RAW_DIR / "大模型面试题").rglob("*.md")):
        collect(parse_h1_file(f, "llm_basics"))

    # 5. RAG知识汇总-全量：面试指南 Q&A（rag）
    collect(parse_rag_guide(RAW_DIR / "大模型原理" / "RAG知识汇总-全量.md"))

    QA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with QA_FILE.open("w", encoding="utf-8") as fp:
        for it in qa_items:
            fp.write(it.to_jsonl() + "\n")
    if seed_items:
        with SEEDS_FILE.open("w", encoding="utf-8") as fp:
            for it in seed_items:
                fp.write(it.to_jsonl() + "\n")

    diff_dist: dict[int, int] = {}
    dom_dist: dict[str, int] = {}
    for it in qa_items:
        diff_dist[it.difficulty] = diff_dist.get(it.difficulty, 0) + 1
        dom_dist[it.domain] = dom_dist.get(it.domain, 0) + 1
    print(f"QA {len(qa_items)} 条（domain {dom_dist}，难度 {diff_dist}）→ {QA_FILE.name}")
    print(f"seeds {len(seed_items)} 条（答案<{ANSWER_MIN}字符）→ {SEEDS_FILE.name if seed_items else '无'}")
    print(f"输出：{QA_FILE}")


if __name__ == "__main__":
    main()
