"""ETL：315386775/DeepLearing-Interview-Awesome-2024（MIT License）
→ data/jsonl/qa_dl_awesome.jsonl（+ seeds_dl_awesome.jsonl）

仓库结构：按专题分目录，每专题一个 Reference.md，问答格式为：

    # 01. 题干
    ...markdown 答案（到下一题标题为止）...

专题取舍：
    LLMs/Reference.md        大模型专题（含多模态/AIGC）→ llm_basics
    LLMs/Agent.md            Agent 工作流（基本无答案）→ agent，多数进 seeds
    DeepLearning/Reference.md 深度学习基础与框架 → ml_dl
    CodeAnything/Reference.md 手撕代码 → ml_dl（CV 检测/分割专属题跳过）
    VisionPerception/        CV 视觉专题（目标检测/分割）→ 整目录跳过
    IndustryAlgorithm/       自动驾驶等垂域（BEV/点云/相机标定，偏视觉感知）→ 跳过
    AwesomeProjects/         开源项目推荐，非面试 QA → 跳过

解析坑点：代码围栏内有 `# 注释` 伪标题，必须跟踪 ``` 围栏状态，
且题号会重复（如两个 `# 09.`），只能靠位置切分。

答案 ≥80 字符收为 qa_pair；不足的题干进 seeds_dl_awesome.jsonl（待 LLM 生成）。
难度无标注，按标题关键词启发式：基础概念词→1，源码/分布式/显存等→3，其余→2。
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data_pipeline.schema import QAItem

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw" / "DeepLearing-Interview-Awesome-2024"
OUT_FILE = ROOT / "data" / "jsonl" / "qa_dl_awesome.jsonl"
SEEDS_FILE = ROOT / "data" / "jsonl" / "seeds_dl_awesome.jsonl"
SOURCE = "github:315386775/DeepLearing-Interview-Awesome-2024"
BLOB = "https://github.com/315386775/DeepLearing-Interview-Awesome-2024/blob/main"

MIN_ANSWER_LEN = 80

# 收录的文件 → domain
FILES = {
    "LLMs/Reference.md": "llm_basics",
    "LLMs/Agent.md": "agent",
    "DeepLearning/Reference.md": "ml_dl",
    "CodeAnything/Reference.md": "ml_dl",
}

# 标题含这些词的题属 CV 检测/分割专属，跳过（大小写不敏感）
CV_SKIP = ["目标检测", "分割", "yolo", "detr", "fcos", "centernet",
           "anchor", "nms", "bbox", "iou", "dice", "dinov2", "unet", "光流", "bev"]

BASIC_HINTS = ["什么是", "是什么", "简介", "有哪些", "含义", "介绍一下"]
ADV_HINTS = ["源码", "推导", "分布式", "显存", "并行", "加速", "底层"]

# `# 01. 题干` / `# 8. 题干` / `# 05.题干`（允许无空格）；`# 14.`（空标题，
# 源文件残缺）也视为题边界——其正文随空标题一并丢弃，避免污染上一题答案
Q_HEADING = re.compile(r"^#\s*(\d+)\s*[.、]\s*(.*?)\s*$")
# 仅供查阅的引流链接行（答案若只剩这个则视为无答案）
REF_LINE = re.compile(
    r"^(?:更详细请查阅|详细参考|参考)[:：]?\s*(?:\[.*?\]\(.*?\)|https?://\S+)\s*$")


def _difficulty(title: str) -> int:
    t = title.lower()
    if any(k in t for k in ADV_HINTS):
        return 3
    if any(k in title for k in BASIC_HINTS):
        return 1
    return 2


def split_questions(text: str) -> list[tuple[str, str]]:
    """按 `# NN.` 一级标题切分（跳过 ``` 围栏内部），返回 [(题干, 答案原文)]"""
    lines = text.split("\n")
    n = len(lines)
    heads: list[tuple[int, str]] = []  # (行号, 题干)
    in_fence = False
    i = 0
    while i < n:
        line = lines[i]
        if line.strip().startswith("```"):
            if not in_fence:
                # 杂散起始围栏修补：围栏外遇到围栏行、且下一非空行是含中文的题标题，
                # 说明它是残留杂散行（如 CodeAnything Q33 的 `# todo` 后多出的 ```），
                # 跳过不切换围栏状态。注意：答案代码块的【闭合】围栏后面也常跟下一题
                # 标题，那种情况 in_fence=True，正常闭合，绝不可跳过。
                j = i + 1
                while j < n and not lines[j].strip():
                    j += 1
                m = Q_HEADING.match(lines[j]) if j < n else None
                if m and len(m.group(2)) >= 5 and re.search(r"[一-鿿]", m.group(2)):
                    i += 1
                    continue
                in_fence = True
            else:
                in_fence = False
            i += 1
            continue
        if not in_fence:
            m = Q_HEADING.match(line)
            if m:
                heads.append((i, m.group(2).strip()))
        i += 1

    out = []
    for idx, (ln, title) in enumerate(heads):
        end = heads[idx + 1][0] if idx + 1 < len(heads) else len(lines)
        body = "\n".join(lines[ln + 1:end]).strip()
        out.append((title, body))
    return out


def clean_answer(body: str) -> str:
    """去尾部引流链接行/分隔线，压缩多余空行；返回是否达标由调用方判断"""
    lines = [ln for ln in body.split("\n") if not REF_LINE.match(ln.strip())]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    text = re.sub(r"\n?---+\s*$", "", text).strip()
    return text


def main():
    qa_items: list[QAItem] = []
    seed_items: list[QAItem] = []
    skipped_cv = 0

    for rel, domain in FILES.items():
        path = RAW_DIR / rel
        if not path.exists():
            print(f"[warn] 缺文件：{rel}")
            continue
        url = f"{BLOB}/{rel}"
        for title, body in split_questions(path.read_text(encoding="utf-8")):
            if len(title) < 5:
                continue
            t = title.lower()
            if any(k in t for k in CV_SKIP):
                skipped_cv += 1
                continue
            answer = clean_answer(body)
            # 单题覆盖：手撕代码里的 C++ 题归 cs_basic 而非 ml_dl
            q_domain = "cs_basic" if "c++" in t else domain
            try:
                item = QAItem(
                    q_type="qa_pair",
                    question=title,
                    answer=answer if len(answer) >= MIN_ANSWER_LEN else "",
                    domain=q_domain,
                    difficulty=_difficulty(title),
                    source=SOURCE,
                    url=url,
                    generated=False,
                )
            except Exception:
                continue
            (qa_items if item.answer else seed_items).append(item)

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUT_FILE.open("w", encoding="utf-8") as fp:
        for it in qa_items:
            fp.write(it.to_jsonl() + "\n")
    with SEEDS_FILE.open("w", encoding="utf-8") as fp:
        for it in seed_items:
            fp.write(it.to_jsonl() + "\n")

    diff_dist: dict[int, int] = {}
    dom_dist: dict[str, int] = {}
    for it in qa_items:
        diff_dist[it.difficulty] = diff_dist.get(it.difficulty, 0) + 1
        dom_dist[it.domain] = dom_dist.get(it.domain, 0) + 1
    print(f"QA {len(qa_items)} 条，domain 分布 {dom_dist}，难度分布 {diff_dist}")
    print(f"CV 专属题跳过 {skipped_cv} 条；答案不足进种子 {len(seed_items)} 条")
    print(f"输出：{OUT_FILE}")
    print(f"种子：{SEEDS_FILE}")


if __name__ == "__main__":
    main()
