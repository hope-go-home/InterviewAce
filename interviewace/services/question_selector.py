"""模拟面试选题策略（纯函数，可单测）

- 知识域轮转：按 session.domains 配比轮转
- 难度递进：前 1/3 难度1 → 中 1/3 难度2 → 后 1/3 难度3
- 已问题目排除
- 级别映射：实习偏基础 / 社招偏进阶
"""
import random

LEVEL_DIFFICULTY = {
    "intern": [1, 1, 2],     # 实习偏基础
    "campus": [1, 2, 3],     # 校招均衡
    "social": [2, 3, 3],     # 社招偏进阶
}


def target_difficulty(seq: int, total: int, level: str = "campus",
                      difficulty_cap: int = 3) -> int:
    """按进度给难度：前 1/3 易、中 1/3 中、后 1/3 难，再叠加级别偏移"""
    third = max(1, total // 3)
    if seq <= third:
        base = 1
    elif seq <= third * 2:
        base = 2
    else:
        base = 3
    pool = LEVEL_DIFFICULTY.get(level, LEVEL_DIFFICULTY["campus"])
    # 级别在基础上微调：社招倾向 +1（封顶 difficulty_cap），实习倾向 -1（保底 1）
    if level == "social":
        base = min(difficulty_cap, base + random.choice([0, 1]))
    elif level == "intern":
        base = max(1, base - random.choice([0, 1]))
    return min(difficulty_cap, base)


def pick_domain(domains: list[str], seq: int) -> str | None:
    """知识域轮转：第 seq 题取第 (seq-1) % len 个域；空则 None（不过滤）"""
    if not domains:
        return None
    return domains[(seq - 1) % len(domains)]


def decide_next(score: int | None, followup_no: int, seq: int, num_questions: int,
                rng: random.Random | None = None) -> str:
    """评分后决定下一步（纯函数）。

    返回：'followup_clarify' / 'followup_deep' / 'next_question' / 'finish'
    规则：
      score < 60 且追问 < 2 层 → 澄清式追问
      60-85 且追问 < 1 层      → 50% 概率深挖式追问
      否则 seq < 题数          → 下一题
      否则                     → 结束出报告
    """
    rng = rng or random.Random()
    if score is not None:
        if score < 60 and followup_no < 2:
            return "followup_clarify"
        if 60 <= score < 85 and followup_no < 1 and rng.random() < 0.5:
            return "followup_deep"
    if seq < num_questions:
        return "next_question"
    return "finish"
