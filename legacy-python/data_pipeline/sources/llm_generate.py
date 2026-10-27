"""LLM 批量生成题库（万级题库主力产能）

两种模式：
  taxonomy  知识点穷举（主力）：TAXONOMY 9 域 × 每知识点 × 3 难度 × 5 题
  seeds     给 km1994 种子题干补答案（seeds_km1994.jsonl → qa_seeds_km1994.jsonl）

工程要点：
- 异步并发（asyncio.Semaphore 限流，默认 8 路）+ 指数退避重试
- 断点续跑：每条生成结果即时追加到 data/jsonl/gen_{domain}.jsonl，
  重跑时跳过已完成的 (domain, point, difficulty) 组合
- 质检门禁：JSON 解析失败/字段缺失/答案过短即丢弃；QAItem 校验兜底
- 成本：默认 qwen-plus（GEN_MODEL 可改），万级生成约 ¥20-40
- 生成内容一律标记 generated=True（版权与质量抽检标记）

用法：
  python data_pipeline/sources/llm_generate.py --mode taxonomy
  python data_pipeline/sources/llm_generate.py --mode taxonomy --domains rag agent
  python data_pipeline/sources/llm_generate.py --mode seeds
"""
import argparse
import asyncio
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from openai import AsyncOpenAI

from data_pipeline.schema import QAItem
from data_pipeline.taxonomy import (
    DIFFICULTIES, DIFFICULTY_DESC, QUESTIONS_PER_CALL, TAXONOMY,
)
from interviewace.backend.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL
from interviewace.backend.logger import get_logger

logger = get_logger(__name__)

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "jsonl"
SEEDS_FILE = DATA_DIR / "seeds_km1994.jsonl"

import os
# 默认用账户主力模型（.env 的 QWEN_MODEL，已验证有额度且支持 JSON 模式）；
# 可用 GEN_MODEL=qwen-plus / qwen-max 等覆盖（注意账户免费额度限制）
GEN_MODEL = os.getenv("GEN_MODEL") or QWEN_MODEL

TAXONOMY_PROMPT = """你是资深技术面试官与出题专家。请针对以下知识点出 {n} 道面试题，并给出高质量参考答案。

知识域：{domain}（AI 应用开发实习岗）
知识点：{point}
难度档位：{difficulty} —— {difficulty_desc}

要求：
- 题目是面试官会问的原话，具体、不空泛，各题之间考察角度不同
- 参考答案分点作答、准确专业，{ans_len} 字左右，可含代码片段或示例
- 严格输出 JSON：{{"items": [{{"question": "...", "answer": "..."}}]}}，不要输出任何其他内容"""

SEEDS_ANSWER_PROMPT = """你是大模型领域专家。请为以下面试题逐一写出高质量参考答案（分点、专业、每题 {ans_len} 字左右，可含示例）。
若题目附带了「参考要点」，请以其为核心展开扩写，不要偏离其结论。

题目列表：
{questions}

严格输出 JSON：{{"answers": ["答案1", "答案2", ...]}}，顺序与题目一一对应，不要输出任何其他内容。"""


def _client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL)


async def _chat_json(client: AsyncOpenAI, prompt: str, model: str,
                     max_retries: int = 3) -> dict | None:
    """带重试的 JSON 输出调用；失败返回 None"""
    for attempt in range(max_retries):
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.7,
            )
            content = resp.choices[0].message.content or ""
            return json.loads(content)
        except Exception as e:
            wait = 2 ** attempt + random.random()
            logger.warning("chat_json retry %d/%d: %s", attempt + 1, max_retries, str(e)[:120])
            await asyncio.sleep(wait)
    return None


def _valid_item(question: str, answer: str, min_ans_len: int = 80) -> bool:
    """质检门禁：题干过短 / 答案过短 / 问答相同 一律丢弃"""
    if len(question.strip()) < 8 or len(answer.strip()) < min_ans_len:
        return False
    if question.strip() == answer.strip():
        return False
    return True


# ---------------- taxonomy 模式 ---------------- #

def _done_keys(path: Path) -> set[str]:
    """从已有生成文件读 checkpoint：(point|difficulty) 集合"""
    done = set()
    if not path.exists():
        return done
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
            done.add(d.get("_gen_key", ""))
        except Exception:
            continue
    return done


async def _gen_one(client: AsyncOpenAI, domain: str, point: str, difficulty: int,
                   sem: asyncio.Semaphore, out_fp, stats: dict) -> None:
    key = f"{point}|{difficulty}"
    prompt = TAXONOMY_PROMPT.format(
        n=QUESTIONS_PER_CALL, domain=domain, point=point,
        difficulty=difficulty, difficulty_desc=DIFFICULTY_DESC[difficulty],
        ans_len={1: 200, 2: 300, 3: 400}[difficulty],
    )
    async with sem:
        data = await _chat_json(client, prompt, GEN_MODEL)
    if not data or "items" not in data:
        stats["failed"] += 1
        return
    kept = 0
    for raw in data["items"]:
        # 容错：模型偶尔返回字符串而非对象
        if not isinstance(raw, dict):
            stats["filtered"] += 1
            continue
        q, a = (raw.get("question") or "").strip(), (raw.get("answer") or "").strip()
        if not _valid_item(q, a):
            stats["filtered"] += 1
            continue
        try:
            item = QAItem(q_type="qa_pair", question=q, answer=a, domain=domain,
                          difficulty=difficulty, source=f"llm_generate:{GEN_MODEL}",
                          generated=True)
        except Exception:
            stats["filtered"] += 1
            continue
        rec = item.model_dump()
        rec["_gen_key"] = key
        out_fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
        out_fp.flush()
        kept += 1
    stats["kept"] += kept
    stats["calls"] += 1
    if stats["calls"] % 20 == 0:
        logger.info("progress: calls=%d kept=%d filtered=%d failed=%d",
                    stats["calls"], stats["kept"], stats["filtered"], stats["failed"])


async def run_taxonomy(domains: list[str], concurrency: int):
    client = _client()
    sem = asyncio.Semaphore(concurrency)
    for domain in domains:
        points = TAXONOMY.get(domain)
        if not points:
            logger.warning("unknown domain %s, skip", domain)
            continue
        out_path = DATA_DIR / f"gen_{domain}.jsonl"
        done = _done_keys(out_path)
        stats = {"calls": 0, "kept": 0, "filtered": 0, "failed": 0}
        with out_path.open("a", encoding="utf-8") as fp:
            tasks = []
            for point in points:
                for difficulty in DIFFICULTIES:
                    if f"{point}|{difficulty}" in done:
                        continue
                    tasks.append(_gen_one(client, domain, point, difficulty, sem, fp, stats))
            # return_exceptions=True：单个任务异常不连累其他任务
            await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("domain=%s done: %s", domain, stats)


# ---------------- seeds 模式（给 km1994 题干补答案） ---------------- #

async def _answer_batch(client: AsyncOpenAI, seeds: list[QAItem], sem: asyncio.Semaphore,
                        out_fp, stats: dict) -> None:
    lines = []
    for i, s in enumerate(seeds):
        hint = f"（参考要点：{s.answer}）" if s.answer.strip() else ""
        lines.append(f"{i + 1}. {s.question}{hint}")
    prompt = SEEDS_ANSWER_PROMPT.format(questions="\n".join(lines), ans_len=300)
    async with sem:
        data = await _chat_json(client, prompt, GEN_MODEL)
    if not data or "answers" not in data:
        stats["failed"] += 1
        return
    answers = data["answers"]
    for seed, ans in zip(seeds, answers):
        ans = (ans or "").strip()
        if not _valid_item(seed.question, ans):
            stats["filtered"] += 1
            continue
        item = seed.model_copy(update={"answer": ans, "generated": True,
                                       "source": f"llm_generate:{GEN_MODEL}"})
        out_fp.write(item.to_jsonl() + "\n")
        stats["kept"] += 1
    out_fp.flush()


async def run_seeds(concurrency: int, batch_size: int = 5):
    # 处理所有 seeds_*.jsonl（km1994 题干、misterbooo 题干+简答提示等）
    seed_files = sorted(DATA_DIR.glob("seeds_*.jsonl"))
    if not seed_files:
        logger.error("没有种子文件（seeds_*.jsonl）")
        return
    seeds: list[QAItem] = []
    for f in seed_files:
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    seeds.append(QAItem.from_jsonl(line))
                except Exception:
                    pass
    out_path = DATA_DIR / "qa_seeds.jsonl"

    # 断点续跑：已生成的题干跳过
    done_qs = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            try:
                done_qs.add(json.loads(line)["question"])
            except Exception:
                pass
    seeds = [s for s in seeds if s.question not in done_qs]
    logger.info("seeds 待生成 %d 条（已完成 %d 条，来自 %d 个种子文件）",
                len(seeds), len(done_qs), len(seed_files))

    client = _client()
    sem = asyncio.Semaphore(concurrency)
    stats = {"kept": 0, "filtered": 0, "failed": 0}
    with out_path.open("a", encoding="utf-8") as fp:
        tasks = [_answer_batch(client, seeds[i:i + batch_size], sem, fp, stats)
                 for i in range(0, len(seeds), batch_size)]
        await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("seeds done: %s → %s", stats, out_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["taxonomy", "seeds"], default="taxonomy")
    parser.add_argument("--domains", nargs="*", default=list(TAXONOMY.keys()))
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("model=%s concurrency=%d mode=%s", GEN_MODEL, args.concurrency, args.mode)
    if args.mode == "taxonomy":
        asyncio.run(run_taxonomy(args.domains, args.concurrency))
    else:
        asyncio.run(run_seeds(args.concurrency))


if __name__ == "__main__":
    main()
