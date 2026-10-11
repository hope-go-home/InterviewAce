"""FastAPI 应用入口（M0 地基版）

挂载：健康检查 / Prometheus 指标 / 认证（登录注册）/ 知识域统计
M1+ 陆续挂载：/qa/stream（题库问答）、/interview/*（模拟面试）、/resume/*（简历备考）

启动韧性：依赖（Milvus/MySQL）连接失败只记警告不崩溃——
保证 /health 存活探针永远可用，依赖状态由 /ready 就绪探针报告。
"""
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from interviewace.backend import metrics
from interviewace.backend.auth import (
    create_access_token, get_current_user, verify_password,
)
from interviewace.backend.config import (
    ALLOW_REGISTRATION, DAILY_TOKEN_BUDGET,
)
from interviewace.backend.database import mysql as db
from interviewace.backend.health import health_router
from interviewace.backend.logger import get_logger
from interviewace.backend.ratelimit import (
    chat_limiter, client_ip, interview_limiter, login_limiter, upload_limiter,
)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动初始化：失败只警告不崩溃（/health 存活探针必须永远可用）
    try:
        from interviewace.backend.database.milvus import connect_milvus, create_collection
        connect_milvus()
        create_collection()
    except Exception as e:
        logger.warning("milvus init failed (degraded): %s", e)
    try:
        db.init_db()
    except Exception as e:
        logger.warning("mysql init failed (degraded): %s", e)
    yield


app = FastAPI(title="InterviewAce", version="0.1.0", lifespan=lifespan)

# CORS：前端 Vite 开发服务器端口
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)


@app.middleware("http")
async def http_metrics_middleware(request: Request, call_next):
    """HTTP 层 Prometheus 打点（方法/路径/状态/耗时）"""
    t0 = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - t0
    path = request.url.path
    metrics.HTTP_REQUESTS.labels(request.method, path, response.status_code).inc()
    metrics.HTTP_LATENCY.labels(request.method, path).observe(elapsed)
    return response


@app.get("/metrics", include_in_schema=False)
def prometheus_metrics():
    content, content_type = metrics.metrics_response()
    return Response(content=content, media_type=content_type)


# ---------------- 认证 ---------------- #

class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/auth/login", tags=["auth"])
def login(req: LoginRequest, request: Request):
    ip = client_ip(request)
    if not login_limiter.allow(ip):
        raise HTTPException(status_code=429, detail="尝试过于频繁，请稍后再试")
    user = db.get_user_by_username(req.username)
    if not user or not verify_password(req.password, user["password_hash"]):
        db.write_audit(None, req.username, "login", detail="failed", ip=ip)
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="账号已禁用")
    token = create_access_token(user)
    db.write_audit(user["id"], user["username"], "login", detail="success", ip=ip)
    return {"token": token, "username": user["username"], "role": user["role"]}


@app.post("/auth/register", tags=["auth"])
def register(req: LoginRequest, request: Request):
    if not ALLOW_REGISTRATION:
        raise HTTPException(status_code=403, detail="未开放注册，请联系管理员创建账号")
    ip = client_ip(request)
    if not login_limiter.allow(ip):
        raise HTTPException(status_code=429, detail="尝试过于频繁，请稍后再试")
    if db.get_user_by_username(req.username):
        raise HTTPException(status_code=409, detail="用户名已存在")
    uid = db.create_user(req.username, req.password)
    db.write_audit(uid, req.username, "register", ip=ip)
    return {"id": uid, "username": req.username}


@app.get("/auth/me", tags=["auth"])
def me(user: dict = Depends(get_current_user)):
    return user


# ---------------- 知识域统计（题库分布，前端筛选器/配置页用） ---------------- #

@app.get("/domains", tags=["qa"])
def domain_stats(user: dict = Depends(get_current_user)):
    """各 domain 题量统计"""
    from pymilvus import Collection
    from interviewace.backend.database.milvus import COLLECTION_NAME, DOMAINS

    stats = {d: 0 for d in DOMAINS}
    total = 0
    try:
        collection = Collection(name=COLLECTION_NAME)
        collection.load()
        total = collection.num_entities
        for d in DOMAINS:
            rows = collection.query(expr=f'domain == "{d}"', output_fields=["count(*)"])
            stats[d] = rows[0].get("count(*)") if rows else 0
    except Exception as e:
        logger.warning("domain stats failed: %s", e)
    return {"total": total, "domains": stats}


# ---------------- 题库浏览 / 统计 ---------------- #

DOMAIN_NAMES = {
    "llm_basics": "LLM 原理", "prompt": "Prompt 工程", "rag": "RAG",
    "agent": "Agent", "vectordb": "向量数据库", "framework": "框架",
    "python_backend": "Python 后端", "ml_dl": "ML/DL", "cs_basic": "CS 基础",
}


@app.get("/bank/stats", tags=["bank"])
def bank_stats(user: dict = Depends(get_current_user)):
    """题库总览统计：总量、域分布、难度分布、来源构成、类型构成"""
    from collections import Counter
    from pymilvus import Collection
    from interviewace.backend.database.milvus import COLLECTION_NAME

    try:
        col = Collection(name=COLLECTION_NAME)
        col.load()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"题库暂不可用：{e}")

    total = col.num_entities
    domain_counter, diff_counter, qtype_counter, generated_counter = Counter(), Counter(), Counter(), Counter()
    try:
        # 全量拉取标量字段做聚合（万级规模可承受）
        rows = col.query(expr="id >= 0",
                         output_fields=["domain", "difficulty", "q_type", "source"],
                         limit=16384)
        for r in rows:
            domain_counter[r.get("domain") or "未标注"] += 1
            diff_counter[r.get("difficulty", 0)] += 1
            qtype_counter[r.get("q_type") or "?"] += 1
            src = (r.get("source") or "")
            generated_counter["LLM 生成" if src.startswith("llm_generate") else "开源真题"] += 1
    except Exception as e:
        logger.warning("bank stats query failed: %s", e)

    return {
        "total": total,
        "domains": [{"key": k, "name": DOMAIN_NAMES.get(k, k), "count": v}
                    for k, v in domain_counter.most_common()],
        "difficulty": [{"level": k, "count": diff_counter[k]} for k in (1, 2, 3)],
        "q_type": dict(qtype_counter),
        "origin": dict(generated_counter),
    }


@app.get("/bank/questions", tags=["bank"])
def bank_questions(domain: str | None = None, difficulty: int | None = None,
                   q: str | None = None, page: int = 1, page_size: int = 20,
                   user: dict = Depends(get_current_user)):
    """题库浏览：分页 + 域/难度过滤 + 标题关键词搜索（qa_pair 条目）"""
    from pymilvus import Collection
    from interviewace.backend.database.milvus import COLLECTION_NAME, build_filter_expr

    try:
        col = Collection(name=COLLECTION_NAME)
        col.load()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"题库暂不可用：{e}")

    expr = build_filter_expr(domain=domain, difficulty=difficulty)
    base = 'q_type == "qa_pair"'
    expr = f"{base} and {expr}" if expr else base

    page = max(1, page)
    page_size = min(50, max(1, page_size))
    try:
        total_rows = col.query(expr=expr, output_fields=["count(*)"])
        total = total_rows[0].get("count(*)") if total_rows else 0
        rows = col.query(expr=expr,
                         output_fields=["title", "domain", "difficulty", "company", "url", "parent_text"],
                         limit=page_size, offset=(page - 1) * page_size)
    except Exception as e:
        logger.warning("bank questions query failed: %s", e)
        raise HTTPException(status_code=500, detail="查询失败")

    items = [{
        "title": r.get("title", ""),
        "domain": r.get("domain", ""),
        "domain_name": DOMAIN_NAMES.get(r.get("domain", ""), r.get("domain", "")),
        "difficulty": r.get("difficulty", 0),
        "company": r.get("company", ""),
        "url": r.get("url", ""),
        "answer": (r.get("parent_text", "") or ""),
    } for r in rows]

    # 关键词搜索（标题包含，不区分大小写）
    if q and q.strip():
        kw = q.strip().lower()
        items = [it for it in items if kw in it["title"].lower()]

    return {"total": total, "page": page, "page_size": page_size, "items": items}


# ---------------- 手动入库 ---------------- #

class BankAddRequest(BaseModel):
    question: str
    answer: str
    domain: str = "llm_basics"
    difficulty: int = 2
    company: str = ""
    url: str = ""


@app.post("/bank/add", tags=["bank"])
def bank_add(req: BankAddRequest, user: dict = Depends(get_current_user)):
    """手动录入一条 QA 到题库（实时嵌入 + 入库 qa_pair 分区）"""
    from data_pipeline.schema import QAItem, DOMAINS
    from interviewace.rag.qa_ingest import ingest_qa_items

    question = req.question.strip()
    answer = req.answer.strip()
    if len(question) < 5:
        raise HTTPException(status_code=400, detail="题干至少 5 个字符")
    if len(answer) < 20:
        raise HTTPException(status_code=400, detail="答案至少 20 个字符")
    if req.domain not in DOMAINS:
        raise HTTPException(status_code=400, detail=f"domain 必须是 {sorted(DOMAINS)} 之一")

    item = QAItem(
        q_type="qa_pair", question=question, answer=answer,
        domain=req.domain, difficulty=req.difficulty,
        company=req.company, url=req.url,
        source=f"manual:{user['username']}:{uuid.uuid4().hex[:8]}",
        generated=False,
    )
    try:
        n = ingest_qa_items([item])
    except Exception as e:
        logger.exception("bank_add failed: %s", e)
        raise HTTPException(status_code=500, detail=f"入库失败：{e}")
    db.write_audit(user["id"], user["username"], "upload", resource="bank_add",
                   detail=question[:100], ip="")
    return {"inserted": n, "question": question}


# ---------------- 题库问答（SSE 流式） ---------------- #

class QARequest(BaseModel):
    question: str
    session_id: str | None = None
    image_base64: str | None = None   # 图片题目（base64，无 data URI 前缀）
    position: str = "ai_app_dev"      # 岗位
    level: str = "campus"             # 级别


def _sse(event: str, data) -> str:
    """SSE 帧封装"""
    import json as _json
    return f"event: {event}\ndata: {_json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/qa/stream", tags=["qa"])
async def qa_stream(req: QARequest, request: Request, user: dict = Depends(get_current_user)):
    """题库问答 SSE 流式接口：thinking → sources → stats → token* → answer → done"""
    question = req.question.strip()
    if not question and not (req.image_base64 or "").strip():
        raise HTTPException(status_code=400, detail="问题或图片不能为空")
    if not question:
        question = "（图片题目）"

    if not chat_limiter.allow(str(user["id"])):
        raise HTTPException(status_code=429, detail="提问过于频繁，请稍后再试")
    if DAILY_TOKEN_BUDGET and db.get_tokens_today(user["id"]) >= DAILY_TOKEN_BUDGET:
        raise HTTPException(status_code=429, detail="今日额度已用完，明天再来")

    from interviewace.services.qa_service import app as qa_app, build_initial_state

    session_id = req.session_id or uuid.uuid4().hex[:16]
    history = db.get_history(session_id, user_id=user["id"])
    initial = build_initial_state(question, history, image_base64=req.image_base64 or "",
                                  position=req.position, level=req.level)

    async def event_gen():
        final_answer = ""
        sources = []
        stats = {}
        similar = []
        is_fallback = False
        try:
            yield _sse("session", {"session_id": session_id})
            async for event in qa_app.astream_events(initial, version="v2"):
                kind = event["event"]
                node = event.get("metadata", {}).get("langgraph_node", "")

                # 节点完成 → thinking / sources / stats
                if kind == "on_chain_end" and node in ("query_analysis", "retrieve", "rewrite", "generate_fallback"):
                    output = event.get("data", {}).get("output", {})
                    if not isinstance(output, dict):
                        continue
                    steps = output.get("thinking_steps", [])
                    if steps:
                        yield _sse("thinking", steps[-1])
                    if node == "retrieve":
                        sources = output.get("retrieval_sources", [])
                        stats = output.get("retrieval_stats", {})
                        similar = output.get("similar_questions", [])
                        is_fallback = output.get("is_fallback", False)
                        yield _sse("sources", sources)
                        yield _sse("stats", stats)
                    if node == "generate_fallback":
                        # 联网兜底：来源是网页
                        fsources = output.get("retrieval_sources", [])
                        if fsources:
                            yield _sse("sources", fsources)
                        yield _sse("fallback", {"online": True})

                # LLM token 流（generate / direct_answer 节点）
                elif kind == "on_chat_model_stream" and node in ("generate", "direct_answer"):
                    chunk = event.get("data", {}).get("chunk")
                    content = getattr(chunk, "content", "") if chunk else ""
                    if content:
                        yield _sse("token", {"content": content})

                # 图结束 → answer + done
                elif kind == "on_chain_end" and event.get("name") == "LangGraph":
                    output = event.get("data", {}).get("output", {})
                    if isinstance(output, dict):
                        final_answer = output.get("answer", "")
                        if output.get("is_fallback"):
                            is_fallback = True
                        yield _sse("answer", {"answer": final_answer,
                                              "similar_questions": similar,
                                              "is_fallback": is_fallback})

            yield _sse("done", {})
        except Exception as e:
            logger.exception("qa_stream failed: %s", e)
            yield _sse("error", {"message": "服务内部错误，请稍后重试"})
        finally:
            if final_answer:
                try:
                    db.save_record(session_id, question, final_answer, user_id=user["id"])
                    db.write_audit(user["id"], user["username"], "chat",
                                   resource=session_id, detail=question[:200],
                                   ip=client_ip(request))
                except Exception as e:
                    logger.warning("qa_stream persist failed: %s", e)

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.get("/sessions", tags=["qa"])
def list_qa_sessions(user: dict = Depends(get_current_user)):
    return {"sessions": db.list_sessions(user_id=user["id"])}


@app.get("/history/{session_id}", tags=["qa"])
def qa_history(session_id: str, user: dict = Depends(get_current_user)):
    return {"history": db.get_history(session_id, user_id=user["id"])}


@app.delete("/sessions/{session_id}", tags=["qa"])
def delete_qa_session(session_id: str, user: dict = Depends(get_current_user)):
    n = db.delete_session(session_id, user_id=user["id"])
    return {"deleted": n}


# ---------------- 简历出题（上传简历 → 生成针对性面试题） ---------------- #

@app.post("/resume/upload", tags=["resume"])
async def resume_upload(file: UploadFile = File(...),
                        user: dict = Depends(get_current_user)):
    """上传简历（PDF/DOCX/TXT/MD），解析并生成针对性面试题"""
    from interviewace.services import resume_service

    if not upload_limiter.allow(str(user["id"])):
        raise HTTPException(status_code=429, detail="上传过于频繁，请稍后再试")

    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件不能超过 10MB")
    try:
        text = resume_service.extract_resume_text(data, file.filename)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"文件解析失败：{e}")
    if len(text.strip()) < 30:
        raise HTTPException(status_code=400, detail="简历内容太少，无法解析")

    try:
        result = resume_service.parse_resume_and_generate(text)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # 存入简历历史
    resume_id = db.save_resume(user["id"], file.filename, result)
    result["resume_id"] = resume_id

    db.write_audit(user["id"], user["username"], "upload", resource="resume",
                   detail=file.filename)
    return result


@app.get("/resume/list", tags=["resume"])
def resume_list(user: dict = Depends(get_current_user)):
    """历史简历列表"""
    return {"items": db.list_resumes(user["id"])}


@app.get("/resume/{resume_id}", tags=["resume"])
def resume_detail(resume_id: int, user: dict = Depends(get_current_user)):
    """取一份简历的完整备考内容（含已生成的话术/预演）"""
    r = db.get_resume(resume_id, user["id"])
    if not r:
        raise HTTPException(status_code=404, detail="简历不存在")
    return r


# ---------------- 语音识别（豆包流式 ASR） ---------------- #

@app.post("/stt", tags=["stt"])
async def speech_to_text(file: UploadFile = File(...),
                         user: dict = Depends(get_current_user)):
    """语音转文字：接收 WAV（16k mono 16bit）→ 豆包流式 ASR → 返回文本"""
    from interviewace.services import stt_service

    data = await file.read()
    if len(data) < 100:
        raise HTTPException(status_code=400, detail="音频太短")
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="音频不能超过 25MB")
    try:
        text = await stt_service.transcribe_wav(data)
    except Exception as e:
        logger.warning("stt failed: %s", e)
        raise HTTPException(status_code=502, detail=f"语音识别失败：{e}")
    return {"text": text}


# ---------------- 实时语音识别（WebSocket 流式） ---------------- #

@app.websocket("/ws/stt")
async def ws_stt(websocket: WebSocket, token: str = ""):
    """实时语音识别：浏览器发 PCM 二进制流 → 豆包边识别边回文字

    协议：
      浏览器 → 服务端：二进制帧 = 16k/16bit/单声道 PCM；文本帧 "END" = 结束
      服务端 → 浏览器：JSON {type: "partial"|"final"|"error", text}
    """
    import asyncio as _asyncio
    from interviewace.services.stt_service import DoubaoStreamSession
    from interviewace.backend.auth import decode_token

    # 鉴权（WebSocket 无法带自定义 header，用 query 参数传 token）
    try:
        payload = decode_token(token)
        user_id = int(payload["sub"])
    except Exception:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    try:
        async with DoubaoStreamSession() as sess:
            stop = _asyncio.Event()

            async def pump_audio():
                """浏览器音频 → 豆包"""
                try:
                    while not stop.is_set():
                        msg = await websocket.receive()
                        if msg.get("type") == "websocket.disconnect":
                            break
                        data = msg.get("bytes")
                        if data:
                            await sess.send_audio(data, is_last=False)
                        elif msg.get("text") == "END":
                            break
                except Exception as e:
                    logger.warning("ws_stt pump_audio ended: %s", e)
                finally:
                    await sess.finish()
                    stop.set()

            async def pump_results():
                """豆包识别结果 → 浏览器（发累计全文，前端直接显示）"""
                try:
                    async for r in sess.recv_results():
                        text = r.get("text", "")
                        if not text:
                            continue
                        await websocket.send_json({
                            "type": "final" if r.get("is_final_text") else "partial",
                            "text": text,
                        })
                    await websocket.send_json({"type": "done", "text": ""})
                except Exception as e:
                    logger.warning("ws_stt pump_results ended: %s", e)
                finally:
                    stop.set()

            await _asyncio.gather(pump_audio(), pump_results())
    except Exception as e:
        logger.warning("ws_stt failed: %s", e)
        try:
            await websocket.send_json({"type": "error", "text": str(e)[:200]})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ---------------- 简历话术 / 项目预演（M3） ---------------- #

class ResumeGenRequest(BaseModel):
    profile: dict                 # 解析出的简历结构化信息
    level: str = "campus"
    resume_id: int | None = None  # 有则把话术回存到该简历


class RehearseRequest(BaseModel):
    project: str
    skills: list[str] = []
    n: int = 5
    resume_id: int | None = None


@app.post("/resume/pitch", tags=["resume"])
def resume_pitch(req: ResumeGenRequest, user: dict = Depends(get_current_user)):
    """生成 60s/90s 自我介绍话术（有 resume_id 则回存）"""
    from interviewace.services import resume_service
    try:
        result = resume_service.generate_pitch(req.profile, req.level)
        if req.resume_id:
            db.update_resume_content(req.resume_id, pitch=result)
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/resume/rehearse", tags=["resume"])
def resume_rehearse(req: RehearseRequest, user: dict = Depends(get_current_user)):
    """对一个项目生成深挖问题 + 应答要点（有 resume_id 则回存）"""
    from interviewace.services import resume_service
    try:
        result = resume_service.rehearse_project(req.project, req.skills, req.n)
        if req.resume_id:
            db.update_resume_content(req.resume_id, rehearse=result)
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------- 待补题池（题库自增长） ---------------- #

@app.get("/pending/list", tags=["bank"])
def pending_list(status: str | None = None, user: dict = Depends(get_current_user)):
    return {"items": db.list_pending(status=status)}


@app.post("/pending/{pending_id}/adopt", tags=["bank"])
def pending_adopt(pending_id: int, user: dict = Depends(get_current_user)):
    """把待补题生成标准答案并入库（题库自增长）"""
    from data_pipeline.schema import QAItem
    from interviewace.backend.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL
    from interviewace.rag.qa_ingest import ingest_qa_items
    from openai import OpenAI

    items = db.list_pending()
    target = next((it for it in items if it["id"] == pending_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="待补题不存在")

    question = target["question"]
    answer = target.get("draft_answer") or ""
    # 没有草稿答案就现场生成
    if len(answer) < 80:
        try:
            client = OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL)
            resp = client.chat.completions.create(
                model=QWEN_MODEL,
                messages=[{"role": "user", "content":
                           f"你是技术面试专家。请为这道面试题写一份分点、专业、200-400字的参考答案。\n\n题目：{question}"}],
                temperature=0.4)
            answer = (resp.choices[0].message.content or "").strip()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"生成答案失败：{e}")

    item = QAItem(q_type="qa_pair", question=question, answer=answer,
                  domain=target.get("domain") or "llm_basics", difficulty=2,
                  source=f"pending:{pending_id}", url=target.get("source_url") or "",
                  generated=True)
    n = ingest_qa_items([item])
    db.mark_pending_adopted(pending_id)
    db.write_audit(user["id"], user["username"], "upload", resource="pending_adopt",
                   detail=question[:100])
    return {"inserted": n, "question": question, "answer_len": len(answer)}


# ---------------- 模拟面试 ---------------- #

class InterviewStartRequest(BaseModel):
    position: str = "ai_app_dev"
    level: str = "campus"
    domains: list[str] = []
    num_questions: int = 10
    difficulty_cap: int = 3


class InterviewAnswerRequest(BaseModel):
    turn_id: int
    answer: str


@app.post("/interview/start", tags=["interview"])
def interview_start(req: InterviewStartRequest, user: dict = Depends(get_current_user)):
    """开一场模拟面试，返回第一题"""
    from interviewace.services import interview_service
    if not interview_limiter.allow(str(user["id"])):
        raise HTTPException(status_code=429, detail="操作过于频繁，请稍后再试")
    try:
        return interview_service.start(user["id"], req.position, req.level,
                                       req.domains, req.num_questions, req.difficulty_cap)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/interview/{session_id}/answer", tags=["interview"])
def interview_answer(session_id: int, req: InterviewAnswerRequest,
                     user: dict = Depends(get_current_user)):
    """提交作答 → 评分 → 追问/下一题/报告"""
    from interviewace.services import interview_service
    if not interview_limiter.allow(str(user["id"])):
        raise HTTPException(status_code=429, detail="操作过于频繁，请稍后再试")
    try:
        return interview_service.submit_answer(session_id, req.turn_id, req.answer, user["id"])
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/interview/{session_id}", tags=["interview"])
def interview_snapshot(session_id: int, user: dict = Depends(get_current_user)):
    """面试快照（刷新恢复现场）"""
    from interviewace.services import interview_service
    try:
        return interview_service.get_snapshot(session_id, user["id"])
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/interview/{session_id}/end", tags=["interview"])
def interview_end(session_id: int, user: dict = Depends(get_current_user)):
    """主动结束并出报告"""
    from interviewace.services import interview_service
    try:
        return interview_service.finish(session_id, user["id"])
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/interview/{session_id}/report", tags=["interview"])
def interview_report(session_id: int, user: dict = Depends(get_current_user)):
    """取面试报告"""
    session = db.get_interview_session(session_id, user_id=user["id"])
    if not session:
        raise HTTPException(status_code=404, detail="面试不存在")
    return {"session": session, "report": session.get("report"),
            "turns": db.list_turns(session_id)}


@app.get("/interviews", tags=["interview"])
def interview_list(user: dict = Depends(get_current_user)):
    """历史面试列表"""
    return {"items": db.list_interviews(user["id"])}


# ---------------- 能力画像 ---------------- #

@app.get("/me/profile", tags=["me"])
def me_profile(user: dict = Depends(get_current_user)):
    """能力画像：各域平均分/掌握度、薄弱域、连续学习天数、学习日历"""
    return db.profile_stats(user["id"])


# ---------------- 自定义入库（上传文档 / 输入问题） ---------------- #

@app.post("/bank/upload", tags=["bank"])
async def bank_upload(file: UploadFile = File(...), domain: str = "cs_basic",
                      as_qa: bool = False, user: dict = Depends(get_current_user)):
    """上传文档入库（PDF/DOCX/TXT/MD）。as_qa=true 时由 LLM 提炼成 QA 对，否则作知识短文"""
    from interviewace.services import resume_service

    if not upload_limiter.allow(str(user["id"])):
        raise HTTPException(status_code=429, detail="上传过于频繁，请稍后再试")
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件不能超过 20MB")

    try:
        text = resume_service.extract_resume_text(data, file.filename)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"文件解析失败：{e}")
    if len(text.strip()) < 50:
        raise HTTPException(status_code=400, detail="文档内容太少，无法入库")

    import os
    import tempfile
    from interviewace.backend.database.milvus import delete_by_source
    from interviewace.rag.embedding import embed_documents, embed_documents_sparse
    from interviewace.backend.database.milvus import insert_documents
    from interviewace.rag.ingest import child_splitter, parent_splitter, _titled

    source = f"upload:{user['username']}:{file.filename}"
    delete_by_source(source)  # 幂等

    # 父子分块
    children, parents = [], []
    for parent in parent_splitter.split_text(text):
        titled = _titled(file.filename, parent)
        for child in child_splitter.split_text(parent):
            children.append(child)
            parents.append(titled)
    if not children:
        raise HTTPException(status_code=400, detail="分块后无有效内容")

    dense = embed_documents(children)
    sparse = embed_documents_sparse(children)
    insert_documents(children, parents, dense, sparse,
                     partition_name="knowledge", q_type="knowledge",
                     source=source, domains=domain, companies="",
                     difficulties=2, titles=[file.filename] * len(children),
                     urls=[""] * len(children))
    db.write_audit(user["id"], user["username"], "upload", resource="bank_upload",
                   detail=f"{file.filename} ({len(children)} 块)")
    return {"inserted_chunks": len(children), "filename": file.filename, "domain": domain}


# ---------------- 答题练习 ---------------- #

class PracticeAnswerRequest(BaseModel):
    question_title: str
    question_url: str = ""
    domain: str = ""
    difficulty: int = 0
    position: str = ""
    level: str = "campus"
    my_answer: str


@app.get("/practice/next", tags=["practice"])
def practice_next(domain: str | None = None, difficulty: int | None = None,
                  position: str | None = None, level: str = "campus",
                  user: dict = Depends(get_current_user)):
    """抽一道练习题（域/难度/岗位过滤，排除已练过的题）"""
    from interviewace.services import practice_service

    # 已练过的题目标题排除
    done = db.list_practice(user["id"], limit=500)
    exclude = [r["question_title"] for r in done]

    # 级别 → 难度倾向
    diff = difficulty
    if diff is None:
        import random as _r
        if level == "intern":
            diff = _r.choice([1, 1, 2])
        elif level == "social":
            diff = _r.choice([2, 3, 3])
        else:
            diff = _r.choice([1, 2, 3])

    q = practice_service.next_question(domain=domain, difficulty=diff,
                                       position=position, exclude_titles=exclude)
    if not q:
        raise HTTPException(status_code=404, detail="没有符合条件的题目了，换个知识域试试")
    return q


@app.get("/practice/batch", tags=["practice"])
def practice_batch(n: int = 8, domain: str | None = None, difficulty: int | None = None,
                   position: str | None = None, level: str = "campus",
                   user: dict = Depends(get_current_user)):
    """一次抽 n 道题（前端预取队列，下一题即时切换）"""
    from interviewace.services import practice_service

    done = db.list_practice(user["id"], limit=500)
    exclude = [r["question_title"] for r in done]

    diff = difficulty
    if diff is None:
        import random as _r
        if level == "intern":
            diff = _r.choice([1, 1, 2])
        elif level == "social":
            diff = _r.choice([2, 3, 3])
        else:
            diff = _r.choice([1, 2, 3])

    items = practice_service.random_questions(
        domain=domain, difficulty=diff, position=position,
        exclude_titles=exclude, n=min(20, max(1, n)))
    return {"items": items}


@app.post("/practice/answer", tags=["practice"])
def practice_answer(req: PracticeAnswerRequest, user: dict = Depends(get_current_user)):
    """提交作答 → RAG 找参考答案 → AI 评分 → 写练习记录"""
    from interviewace.services import practice_service

    if not req.my_answer.strip():
        raise HTTPException(status_code=400, detail="请先写下你的作答")
    if not interview_limiter.allow(str(user["id"])):
        raise HTTPException(status_code=429, detail="操作过于频繁，请稍后再试")

    result = practice_service.evaluate_answer(req.question_title, req.my_answer, req.level)

    is_wrong = result["score"] is not None and result["score"] < 60
    record_id = db.save_practice(
        user_id=user["id"], question_title=req.question_title,
        question_url=req.question_url, my_answer=req.my_answer,
        score=result["score"] or 0, feedback=result["feedback"],
        missing_points=result["missing_points"], dim_json=result["dimensions"],
        domain=req.domain, difficulty=req.difficulty,
        position=req.position, level=req.level,
    )
    if is_wrong:
        db.add_favorite(user["id"], req.question_title, ftype="wrong",
                        domain=req.domain, difficulty=req.difficulty,
                        question_url=req.question_url)
    db.write_audit(user["id"], user["username"], "chat", resource="practice",
                   detail=req.question_title[:100])

    return {**result, "record_id": record_id, "is_wrong": is_wrong}


@app.get("/practice/records", tags=["practice"])
def practice_records(wrong_only: bool = False, user: dict = Depends(get_current_user)):
    return {"records": db.list_practice(user["id"], wrong_only=wrong_only)}


# ---------------- 收藏 / 错题本 ---------------- #

class FavoriteRequest(BaseModel):
    question_title: str
    question_url: str = ""
    domain: str = ""
    difficulty: int = 0
    ftype: str = "fav"          # fav / wrong
    action: str = "add"         # add / remove


@app.post("/bank/favorite", tags=["bank"])
def toggle_favorite(req: FavoriteRequest, user: dict = Depends(get_current_user)):
    if req.action == "remove":
        n = db.remove_favorite(user["id"], req.question_title, req.ftype)
        return {"removed": n}
    fid = db.add_favorite(user["id"], req.question_title, req.ftype,
                          req.domain, req.difficulty, req.question_url)
    return {"id": fid}


@app.get("/bank/favorites", tags=["bank"])
def list_favorites(user: dict = Depends(get_current_user)):
    return {"items": db.list_favorites(user["id"], "fav")}


@app.get("/bank/wrong", tags=["bank"])
def list_wrong(user: dict = Depends(get_current_user)):
    return {"items": db.list_favorites(user["id"], "wrong")}


# M2+ 路由挂载点：
# /interview/*     — 模拟面试（interview_service，M2）
# /resume/*        — 简历备考（resume_service，M3）
# /evaluation      — 评测报告（M4）
