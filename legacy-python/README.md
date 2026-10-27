# legacy-python —— FastAPI 原型 + 数据/评测工具链

这是 InterviewAce 的**初版后端（FastAPI + LangGraph）与数据管线**。**当前运行系统不需要它**——主后端是仓库根目录的 `backend-java/`（Spring Boot 3）。

保留它的三个理由：

1. **数据工具链**：题库 13,411 条的 ETL、去重、质检、嵌入、入库脚本（`data_pipeline/` + `scripts/ingest_all.py`）。新环境首次灌题库用它（幂等，可重跑）：
   ```bash
   cd legacy-python
   pip install -r requirements.txt
   python scripts/ingest_all.py
   ```
2. **评测体系**：金标集、检索/生成/评分评测脚本与基线（`interviewace/evaluation/`），CI 的评测回归门禁（`scripts/eval_gate.py`）依赖它。
3. **迁移对照**：Java 版是这份原型的完整重写，两边 API 契约一致（JWT/BCrypt/snake_case JSON），可互相切换。

## 运行原型后端（可选，与 Java 版共用 8002 端口，不要同时启动）

```bash
cd legacy-python
python app.py    # → http://localhost:8002
```

## 目录

| 路径 | 内容 |
|---|---|
| `interviewace/` | 原版后端包（backend / rag / services）+ evaluation（评测） |
| `data_pipeline/` | 题库 ETL（schema 校验 / 三级去重 / LLM 质检 / 领域分类） |
| `scripts/` | ingest_all 入库 / eval_gate 门禁 / create_user |
| `tests/` | 24 单测 + 8 集成测试（`pytest tests/ -q`） |
| `prometheus/` | Python 侧自定义指标的告警规则（历史） |
| `EVALUATION.md` | 评测口径与完整报告说明 |
| `Dockerfile` | 原型后端镜像（由根目录 `docker-compose.app.yml` 引用） |
