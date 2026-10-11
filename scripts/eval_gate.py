"""CI 评测回归门禁（M4 实现）

读取最新评测报告与 baseline.json 对比：核心指标（Recall@10 / MRR / 评分一致性）
跌幅超过 3% 即以非零码退出，阻断合并。骨架参考 SmartQuery/scripts/eval_gate.py。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# M4 实现
