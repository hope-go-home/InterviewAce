"""简历出题服务：上传简历 → 抽取结构化信息 → 生成针对性面试题

M3 轻量先行版：只做「上传简历 → 生成针对性面试题清单」。
完整版（自我介绍话术/项目预演）后续接。
"""
import json
import os
import tempfile

from interviewace.backend.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL
from interviewace.backend.logger import get_logger
from openai import OpenAI

logger = get_logger(__name__)

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL)
    return _client


def extract_resume_text(file_bytes: bytes, filename: str) -> str:
    """从上传文件提取纯文本（PDF/DOCX/TXT/MD，扫描件走 OCR）"""
    ext = filename.rsplit(".", 1)[-1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name
    try:
        from interviewace.rag.ingest import load_file
        docs = load_file(tmp_path, q_type="knowledge")
        text = "\n".join(d.page_content for d in docs)
        return text[:6000]  # 简历一般不长，截断防爆 token
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


PROFILE_PROMPT = """你是一位资深技术面试官。请阅读下面这份简历，抽取关键信息并生成针对性面试题。

简历内容：
{resume}

输出 JSON（不要 markdown 包裹）：
{{
  "name": "姓名或称呼",
  "target": "目标岗位（从简历推断，如 AI 应用开发 / Python 后端）",
  "skills": ["技能1", "技能2"],
  "projects": ["项目1 一句话", "项目2 一句话"],
  "questions": [
    {{"question": "面试官会问的具体问题", "domain": "知识域", "why": "为什么问这个（针对简历哪点）"}}
  ]
}}

要求：
- questions 生成 10-15 道，覆盖：项目深挖、技能原理、基础知识、行为问题
- 问题要具体针对简历里写的技能和项目，不要泛泛
- domain 从枚举选：llm_basics/prompt/rag/agent/vectordb/framework/python_backend/ml_dl/cs_basic
- 如果简历信息太少，也要尽量基于已有内容出题"""


def parse_resume_and_generate(resume_text: str) -> dict:
    """LLM 抽取 + 生成面试题"""
    prompt = PROFILE_PROMPT.format(resume=resume_text)
    try:
        resp = _get_client().chat.completions.create(
            model=QWEN_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.4,
        )
        data = json.loads(resp.choices[0].message.content or "{}")
    except Exception as e:
        logger.warning("parse_resume failed: %s", e)
        raise RuntimeError(f"简历解析失败：{e}")

    return {
        "name": data.get("name", ""),
        "target": data.get("target", ""),
        "skills": data.get("skills", []),
        "projects": data.get("projects", []),
        "questions": data.get("questions", []),
    }


# ---------------- 自我介绍话术 ---------------- #

PITCH_PROMPT = """你是资深求职教练。请根据下面的简历信息，写两版自我介绍话术：60 秒版和 90 秒版。

简历信息：
{profile}

要求：
- 60 秒版：简洁有力，突出最匹配的 1-2 个亮点（校招/实习侧重潜力与学习力，社招侧重成果）
- 90 秒版：在 60 秒基础上展开一个代表性项目的技术亮点
- 口语化、适合开口说，不要书面语
- 级别：{level}；目标岗位：{target}
- 输出 JSON：{{"pitch_60": "...", "pitch_90": "..."}}"""


def generate_pitch(profile: dict, level: str = "campus") -> dict:
    """生成 60s/90s 自我介绍话术"""
    profile_text = json.dumps(profile, ensure_ascii=False)
    prompt = PITCH_PROMPT.format(profile=profile_text, level=level,
                                 target=profile.get("target", ""))
    try:
        resp = _get_client().chat.completions.create(
            model=QWEN_MODEL, messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}, temperature=0.5)
        data = json.loads(resp.choices[0].message.content or "{}")
        return {"pitch_60": data.get("pitch_60", ""), "pitch_90": data.get("pitch_90", "")}
    except Exception as e:
        logger.warning("generate_pitch failed: %s", e)
        raise RuntimeError(f"生成话术失败：{e}")


# ---------------- 项目问答预演 ---------------- #

REHEARSE_PROMPT = """你是技术面试官。针对下面这个项目，出 {n} 个层层递进的深挖问题（技术选型→架构→难点→权衡→数据指标），并给出每个问题的应答要点（STAR 话术骨架）。

项目：{project}
求职者技能：{skills}

输出 JSON：{{"questions": [{{"question": "...", "points": ["应答要点1", "要点2"]}}]}}"""


def rehearse_project(project: str, skills: list[str], n: int = 5) -> dict:
    """对一个项目生成深挖问题 + 应答要点"""
    prompt = REHEARSE_PROMPT.format(n=n, project=project,
                                    skills=", ".join(skills))
    try:
        resp = _get_client().chat.completions.create(
            model=QWEN_MODEL, messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}, temperature=0.5)
        data = json.loads(resp.choices[0].message.content or "{}")
        return {"project": project, "questions": data.get("questions", [])}
    except Exception as e:
        logger.warning("rehearse_project failed: %s", e)
        raise RuntimeError(f"项目预演失败：{e}")
