"""ETL：Lau-Jonathan/LLM-Agent-Interview-Guide（Apache-2.0）→ data/jsonl/qa_laujonathan.jsonl

仓库结构（中文大模型+Agent 面试八股指南）：
- 01~07、09 模块文件：### Q: 题干 [⭐…]（⭐ 为面试频率，非难度），答案到下一个
  ### Q: / ## / # 标题或 --- 分隔线为止；非 Q 的 ### 子标题视为答案的一部分。
- 08-Coding：## N. 标题 [⭐…] 节，内容为手写实现代码 → 转成「手写 X」QA，难度 3。
  仅保留含代码块的节（末节 LeetCode 清单只是题目表，跳过）。
- 10-RealQuestions：字节跳动面经编号题（无答案）→ seeds_laujonathan.jsonl，
  company="字节跳动"；同题在多个面经中重复出现，按题干去重。

domain：04→rag、05→agent，其余默认 llm_basics；通用模块按题干关键词细分为
prompt/agent/rag。难度无标注，按内容深度启发式判断（默认 2）。
答案 <80 字符的模块题也降级为种子。
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data_pipeline.schema import QAItem

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "LLM-Agent-Interview-Guide"
OUT_FILE = Path(__file__).resolve().parents[2] / "data" / "jsonl" / "qa_laujonathan.jsonl"
SEEDS_FILE = Path(__file__).resolve().parents[2] / "data" / "jsonl" / "seeds_laujonathan.jsonl"
SOURCE = "github:Lau-Jonathan/LLM-Agent-Interview-Guide"
BLOB_URL = "https://github.com/Lau-Jonathan/LLM-Agent-Interview-Guide/blob/main"

FOLDER_DOMAIN = {
    "01-Foundation": "llm_basics",
    "02-Inference": "llm_basics",
    "03-FineTuning": "llm_basics",
    "04-RAG": "rag",
    "05-Agent": "agent",
    "06-Safety-Evaluation": "llm_basics",
    "07-HotTopics": "llm_basics",
    "08-Coding": "llm_basics",
    "09-SystemDesign": "llm_basics",
}

# 题干关键词细分（仅当文件夹默认 llm_basics 时启用，优先级 prompt > agent > rag）
PROMPT_KW = re.compile(r"prompt|提示词|提示工程|提示注入", re.IGNORECASE)
AGENT_KW = re.compile(r"agent|智能体|react|function calling|\bmcp\b|工具调用", re.IGNORECASE)
RAG_KW = re.compile(r"\brag\b|检索|向量|embedding|chunk|分块|重排序|rerank|查询改写|余弦相似度", re.IGNORECASE)

ADV_PAT = re.compile(r"手写|推导|设计|估算|FLOPs|优化方案")
BASIC_PAT = re.compile(r"^什么是|^是什么|有哪些|的概念")

Q_HEAD = re.compile(r"^###\s*Q[：:]\s*(.+?)\s*$")
SECTION_HEAD = re.compile(r"^##\s+(.+?)\s*$")
TOP_HEAD = re.compile(r"^#{1,2}\s")
HR = re.compile(r"^---+\s*$")
STAR_TAIL = re.compile(r"\s*⭐+\s*$")
CODING_SEC = re.compile(r"^##\s+(\d+)[.、]\s*(.+?)\s*$")
NUM_ITEM = re.compile(r"^\d+[.、]\s*(.+?)\s*$")


def guess_difficulty(question: str) -> int:
    if ADV_PAT.search(question):
        return 3
    if BASIC_PAT.search(question):
        return 1
    return 2


def refine_domain(question: str, folder_domain: str) -> str:
    if folder_domain != "llm_basics":
        return folder_domain
    if PROMPT_KW.search(question):
        return "prompt"
    if AGENT_KW.search(question):
        return "agent"
    if RAG_KW.search(question):
        return "rag"
    return "llm_basics"


def make_item(question: str, answer: str, domain: str, difficulty: int,
              url: str, company: str = "") -> QAItem | None:
    try:
        return QAItem(
            q_type="qa_pair",
            question=question,
            answer=answer,
            domain=domain,
            difficulty=difficulty,
            source=SOURCE,
            url=url,
            company=company,
            generated=False,
        )
    except Exception:
        return None


def parse_module_file(path: Path, folder_domain: str) -> tuple[list[QAItem], list[QAItem]]:
    """解析 ### Q: 格式模块文件；返回 (正式QA, 答案过短的种子)"""
    url = f"{BLOB_URL}/{path.relative_to(RAW_DIR).as_posix()}"
    qa_items, seed_items = [], []
    cur_q: str | None = None
    cur_section = ""
    buf: list[str] = []
    in_fence = False

    def flush():
        nonlocal cur_q, buf
        if cur_q is None:
            return
        question = cur_q
        if len(question) < 8 and cur_section:
            question = f"{cur_section}：{question}"
        answer = "\n".join(buf).strip()
        domain = refine_domain(question, folder_domain)
        if len(question) >= 8 and answer:
            item = make_item(question, answer, domain, guess_difficulty(question), url)
            if item:
                (qa_items if len(answer) >= 80 else seed_items).append(item)
        cur_q, buf = None, []

    for line in path.read_text(encoding="utf-8").split("\n"):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            if cur_q is not None:
                buf.append(line)
            continue
        if not in_fence:
            m = Q_HEAD.match(line)
            if m:
                flush()
                cur_q = STAR_TAIL.sub("", m.group(1)).strip()
                buf = []
                continue
            sm = SECTION_HEAD.match(line)
            if sm:
                flush()
                cur_section = re.sub(r"^\d+\.\s*", "", sm.group(1))
                continue
            if TOP_HEAD.match(line) or HR.match(line):
                flush()
                continue
        if cur_q is not None:
            buf.append(line)
    flush()
    return qa_items, seed_items


def parse_coding_file(path: Path) -> list[QAItem]:
    """08-Coding：## N. 标题 [⭐…] 节 → 手写 QA（仅保留含代码块的节）"""
    url = f"{BLOB_URL}/{path.relative_to(RAW_DIR).as_posix()}"
    items = []
    cur_title: str | None = None
    buf: list[str] = []
    in_fence = False

    def flush():
        nonlocal cur_title, buf
        if cur_title is None:
            return
        body = "\n".join(buf).strip()
        if "```" in body:  # 无代码块的节（如 LeetCode 清单）跳过
            question = f"手写 {cur_title}"
            domain = refine_domain(question, "llm_basics")
            item = make_item(question, body, domain, 3, url)
            if item:
                items.append(item)
        cur_title, buf = None, []

    for line in path.read_text(encoding="utf-8").split("\n"):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            if cur_title is not None:
                buf.append(line)
            continue
        if not in_fence:
            m = CODING_SEC.match(line)
            if m:
                flush()
                cur_title = STAR_TAIL.sub("", m.group(2)).strip()
                buf = []
                continue
        if cur_title is not None:
            buf.append(line)
    flush()
    return items


def parse_real_questions(path: Path) -> list[QAItem]:
    """10-RealQuestions：字节面经编号题（无答案）→ 种子，company=字节跳动，按题干去重"""
    url = f"{BLOB_URL}/{path.relative_to(RAW_DIR).as_posix()}"
    seeds, seen = [], set()
    in_fence = False
    in_exp = False  # 是否处于面经小节内
    for line in path.read_text(encoding="utf-8").split("\n"):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.startswith("## "):
            in_exp = line.startswith("## 面经")
            continue
        if not in_exp:
            continue
        m = NUM_ITEM.match(line.strip())
        if not m:
            continue
        question = m.group(1).strip().rstrip("？?")
        key = re.sub(r"\s+", "", question).lower()
        if key in seen or len(question) < 8:
            continue
        seen.add(key)
        domain = refine_domain(question, "llm_basics")
        item = make_item(question + "？", "", domain, guess_difficulty(question), url,
                         company="字节跳动")
        if item:
            seeds.append(item)
    return seeds


def main():
    all_qa: list[QAItem] = []
    all_seeds: list[QAItem] = []

    for folder, domain in FOLDER_DOMAIN.items():
        if folder == "08-Coding":
            continue
        for path in sorted((RAW_DIR / folder).glob("*.md")):
            qa, seeds = parse_module_file(path, domain)
            all_qa.extend(qa)
            all_seeds.extend(seeds)

    coding_path = RAW_DIR / "08-Coding" / "01-Coding-Problems.md"
    if coding_path.exists():
        all_qa.extend(parse_coding_file(coding_path))

    rq_path = RAW_DIR / "10-RealQuestions" / "01-ByteDance-Questions.md"
    if rq_path.exists():
        all_seeds.extend(parse_real_questions(rq_path))

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUT_FILE.open("w", encoding="utf-8") as fp:
        for it in all_qa:
            fp.write(it.to_jsonl() + "\n")
    if all_seeds:
        with SEEDS_FILE.open("w", encoding="utf-8") as fp:
            for it in all_seeds:
                fp.write(it.to_jsonl() + "\n")

    diff_dist, dom_dist = {}, {}
    for it in all_qa:
        diff_dist[it.difficulty] = diff_dist.get(it.difficulty, 0) + 1
        dom_dist[it.domain] = dom_dist.get(it.domain, 0) + 1
    print(f"QA {len(all_qa)} 条，难度分布 {diff_dist}，domain 分布 {dom_dist}")
    print(f"种子 {len(all_seeds)} 条 → {SEEDS_FILE.name}")
    print(f"输出：{OUT_FILE}")


if __name__ == "__main__":
    main()
