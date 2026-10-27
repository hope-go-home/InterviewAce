"""MySQL 数据层：用户 / 审计 / 会话记录 / 反馈 / token 预算

面试场次(interview_session/interview_turn)与简历(resume/resume_prediction)表
在 M2/M3 里程碑添加。表结构变更通过 _ensure_columns 做轻量迁移。
"""
from datetime import datetime

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, func
from sqlalchemy.orm import sessionmaker, declarative_base

from interviewace.backend.config import (
    MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE,
)
from interviewace.backend.logger import get_logger

logger = get_logger(__name__)

DATABASE_URL = (
    f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
    f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}?charset=utf8mb4"
)
# 连接池：pool_pre_ping 防 MySQL 8 小时断连，pool_recycle 主动回收
engine = create_engine(
    DATABASE_URL,
    pool_size=10, max_overflow=20,
    pool_pre_ping=True, pool_recycle=3600,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class ChatRecord(Base):
    __tablename__ = "chat_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), index=True, nullable=False)
    user_id = Column(Integer, index=True, nullable=True)   # 归属用户（历史会话按用户隔离）
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


def _ensure_database():
    """共享 MySQL 实例下自动建库：rag-mysql 容器首启只建了 resume_rag_db，
    interviewace_db 由这里按需创建（CREATE DATABASE IF NOT EXISTS 幂等）"""
    from sqlalchemy import text
    server_url = (
        f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
        f"@{MYSQL_HOST}:{MYSQL_PORT}/?charset=utf8mb4"
    )
    server_engine = create_engine(server_url, pool_pre_ping=True)
    try:
        with server_engine.begin() as conn:
            conn.execute(text(
                f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}` "
                "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            ))
    finally:
        server_engine.dispose()


def init_db():
    _ensure_database()
    Base.metadata.create_all(bind=engine)
    logger.info("mysql tables ready")
    seed_default_admin()


def save_record(session_id: str, question: str, answer: str, user_id: int | None = None):
    db = SessionLocal()
    try:
        db.add(ChatRecord(session_id=session_id, question=question,
                          answer=answer, user_id=user_id))
        db.commit()
    finally:
        db.close()


def get_history(session_id: str, user_id: int | None = None) -> list[dict]:
    """取某会话的问答记录；user_id 不为空时只取该用户的"""
    db = SessionLocal()
    try:
        q = db.query(ChatRecord).filter(ChatRecord.session_id == session_id)
        if user_id is not None:
            q = q.filter(ChatRecord.user_id == user_id)
        records = q.order_by(ChatRecord.created_at).all()
        return [
            {"question": r.question, "answer": r.answer, "created_at": str(r.created_at)}
            for r in records
        ]
    finally:
        db.close()


def list_sessions(user_id: int | None = None, limit: int = 50) -> list[dict]:
    """按会话聚合，返回首问、末次时间、问答条数；按用户隔离"""
    db = SessionLocal()
    try:
        q = db.query(
            ChatRecord.session_id,
            func.min(ChatRecord.id).label("first_id"),
            func.max(ChatRecord.created_at).label("last_time"),
            func.count(ChatRecord.id).label("count"),
        )
        if user_id is not None:
            q = q.filter(ChatRecord.user_id == user_id)
        rows = (q.group_by(ChatRecord.session_id)
                 .order_by(func.max(ChatRecord.created_at).desc())
                 .limit(limit).all())
        result = []
        for r in rows:
            first_question = (
                db.query(ChatRecord.question)
                .filter(ChatRecord.id == r.first_id)
                .scalar()
            )
            result.append({
                "session_id": r.session_id,
                "first_question": first_question or "",
                "last_time": str(r.last_time),
                "count": r.count,
            })
        return result
    finally:
        db.close()


def delete_session(session_id: str, user_id: int | None = None) -> int:
    """删除会话的全部问答记录，返回删除条数；user_id 不为空时校验归属"""
    db = SessionLocal()
    try:
        q = db.query(ChatRecord).filter(ChatRecord.session_id == session_id)
        if user_id is not None:
            q = q.filter(ChatRecord.user_id == user_id)
        n = q.delete(synchronize_session=False)
        db.commit()
        return n
    finally:
        db.close()


# ---------------- 用户与审计（身份权限）---------------- #

class User(Base):
    """系统用户：角色绑定在服务端，前端不可伪造"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(16), nullable=False, default="user")  # admin / user
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    """审计日志：登录、提问、上传、删除等敏感操作留痕"""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, index=True, nullable=True)
    username = Column(String(64), index=True, nullable=True)
    action = Column(String(32), nullable=False)     # login / chat / upload / delete
    resource = Column(String(255), nullable=True)
    detail = Column(Text, nullable=True)
    ip = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


def count_users() -> int:
    db = SessionLocal()
    try:
        return db.query(func.count(User.id)).scalar() or 0
    finally:
        db.close()


def create_user(username: str, password: str, role: str = "user") -> int:
    """创建用户，返回用户 id"""
    from interviewace.backend.auth import hash_password
    db = SessionLocal()
    try:
        user = User(username=username, password_hash=hash_password(password), role=role)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id
    finally:
        db.close()


def get_user_by_username(username: str) -> dict | None:
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.username == username).first()
        if u is None:
            return None
        return {
            "id": u.id, "username": u.username, "password_hash": u.password_hash,
            "role": u.role, "is_active": u.is_active,
        }
    finally:
        db.close()


def list_users(limit: int = 200) -> list[dict]:
    """用户列表（不含密码哈希）"""
    db = SessionLocal()
    try:
        rows = db.query(User).order_by(User.id).limit(limit).all()
        return [{
            "id": u.id, "username": u.username,
            "role": u.role, "is_active": u.is_active, "created_at": str(u.created_at),
        } for u in rows]
    finally:
        db.close()


def write_audit(user_id: int | None, username: str | None, action: str,
                resource: str = "", detail: str = "", ip: str = ""):
    db = SessionLocal()
    try:
        db.add(AuditLog(user_id=user_id, username=username, action=action,
                        resource=resource, detail=detail[:2000], ip=ip))
        db.commit()
    except Exception as e:
        logger.warning("write_audit failed: %s", e)
    finally:
        db.close()


def list_audit(limit: int = 100) -> list[dict]:
    db = SessionLocal()
    try:
        rows = (db.query(AuditLog).order_by(AuditLog.id.desc()).limit(limit).all())
        return [{
            "id": r.id, "username": r.username, "action": r.action,
            "resource": r.resource, "detail": r.detail, "ip": r.ip,
            "created_at": str(r.created_at),
        } for r in rows]
    finally:
        db.close()


def seed_default_admin():
    """无任何用户时，创建默认管理员（账号来自 config / .env）"""
    try:
        if count_users() > 0:
            return
        from interviewace.backend.config import DEFAULT_ADMIN_USER, DEFAULT_ADMIN_PASSWORD
        create_user(DEFAULT_ADMIN_USER, DEFAULT_ADMIN_PASSWORD, "admin")
        logger.info("seeded default admin user=%s", DEFAULT_ADMIN_USER)
    except Exception as e:
        logger.warning("seed_default_admin failed: %s", e)


# ---------------- 答案反馈（点赞 / 点踩）---------------- #

class Feedback(Base):
    """答案反馈：用户对回答点赞/点踩，用于闭环收集 badcase"""
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, index=True, nullable=True)
    session_id = Column(String(64), index=True, nullable=True)
    question = Column(Text, nullable=True)
    answer = Column(Text, nullable=True)
    rating = Column(String(8), nullable=False)   # up / down
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


def save_feedback(rating: str, user_id: int | None = None, session_id: str = "",
                  question: str = "", answer: str = "", comment: str = "") -> int:
    db = SessionLocal()
    try:
        row = Feedback(user_id=user_id, session_id=session_id, question=question,
                       answer=answer, rating=rating, comment=comment)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id
    finally:
        db.close()


def feedback_stats() -> dict:
    """反馈统计：点赞/点踩数量"""
    db = SessionLocal()
    try:
        up = db.query(func.count(Feedback.id)).filter(Feedback.rating == "up").scalar() or 0
        down = db.query(func.count(Feedback.id)).filter(Feedback.rating == "down").scalar() or 0
        return {"up": up, "down": down, "total": up + down}
    finally:
        db.close()


# ---------------- 每日 token 用量（成本预算熔断） ---------------- #

class TokenUsage(Base):
    """按用户/按天累计 LLM token 用量，用于每日预算熔断"""
    __tablename__ = "token_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, index=True, nullable=True)
    day = Column(String(10), index=True, nullable=False)   # YYYY-MM-DD
    tokens = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def _today() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def add_tokens(user_id: int | None, n: int) -> None:
    if not n:
        return
    db = SessionLocal()
    try:
        row = (db.query(TokenUsage)
               .filter(TokenUsage.user_id == user_id, TokenUsage.day == _today()).first())
        if row is None:
            db.add(TokenUsage(user_id=user_id, day=_today(), tokens=n))
        else:
            row.tokens = (row.tokens or 0) + n
        db.commit()
    except Exception as e:
        logger.warning("add_tokens failed: %s", e)
    finally:
        db.close()


def get_tokens_today(user_id: int | None) -> int:
    db = SessionLocal()
    try:
        row = (db.query(TokenUsage)
               .filter(TokenUsage.user_id == user_id, TokenUsage.day == _today()).first())
        return row.tokens if row else 0
    finally:
        db.close()


# ---------------- 练习记录 / 收藏 / 待补题 ---------------- #

class PracticeRecord(Base):
    """答题练习记录：每次作答的评分与点评"""
    __tablename__ = "practice_record"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, index=True, nullable=False)
    question_title = Column(String(512), nullable=False)   # 题干（题没有自增 id，用 title 标识）
    question_url = Column(String(512), nullable=True)
    domain = Column(String(64), index=True, nullable=True)
    difficulty = Column(Integer, nullable=True)
    position = Column(String(64), nullable=True)
    level = Column(String(16), nullable=True)              # intern / campus / social
    my_answer = Column(Text, nullable=True)
    score = Column(Integer, nullable=True)                 # 0-100
    dim_json = Column(Text, nullable=True)                 # 各维度得分 JSON
    feedback = Column(Text, nullable=True)
    missing_points = Column(Text, nullable=True)           # JSON list
    is_wrong = Column(Boolean, nullable=False, default=False)  # score<60 进错题本
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class Favorite(Base):
    """收藏 / 错题标记"""
    __tablename__ = "favorite"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, index=True, nullable=False)
    question_title = Column(String(512), nullable=False)
    question_url = Column(String(512), nullable=True)
    domain = Column(String(64), nullable=True)
    difficulty = Column(Integer, nullable=True)
    ftype = Column(String(8), nullable=False, default="fav")  # fav / wrong
    created_at = Column(DateTime, default=datetime.utcnow)


class PendingQuestion(Base):
    """待补题池：题库外被问到的问题，待生成答案入库"""
    __tablename__ = "pending_question"

    id = Column(Integer, primary_key=True, autoincrement=True)
    question = Column(String(512), index=True, nullable=False)
    domain = Column(String(64), nullable=True)
    position = Column(String(64), nullable=True)
    ask_count = Column(Integer, nullable=False, default=1)
    draft_answer = Column(Text, nullable=True)
    source_url = Column(String(512), nullable=True)
    status = Column(String(16), nullable=False, default="pending")  # pending / drafted / adopted
    created_at = Column(DateTime, default=datetime.utcnow)


def save_practice(user_id: int, question_title: str, my_answer: str, score: int,
                  feedback: str = "", missing_points=None, dim_json=None,
                  domain: str = "", difficulty: int = 0, position: str = "",
                  level: str = "", question_url: str = "") -> int:
    import json as _json
    db = SessionLocal()
    try:
        row = PracticeRecord(
            user_id=user_id, question_title=question_title, question_url=question_url,
            domain=domain, difficulty=difficulty, position=position, level=level,
            my_answer=my_answer, score=score, feedback=feedback,
            missing_points=_json.dumps(missing_points or [], ensure_ascii=False),
            dim_json=_json.dumps(dim_json or {}, ensure_ascii=False),
            is_wrong=bool(score is not None and score < 60),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id
    finally:
        db.close()


def list_practice(user_id: int, wrong_only: bool = False, limit: int = 200) -> list[dict]:
    db = SessionLocal()
    try:
        q = db.query(PracticeRecord).filter(PracticeRecord.user_id == user_id)
        if wrong_only:
            q = q.filter(PracticeRecord.is_wrong == True)  # noqa: E712
        rows = q.order_by(PracticeRecord.created_at.desc()).limit(limit).all()
        return [{
            "id": r.id, "question_title": r.question_title, "question_url": r.question_url,
            "domain": r.domain, "difficulty": r.difficulty, "score": r.score,
            "feedback": r.feedback, "is_wrong": r.is_wrong,
            "created_at": str(r.created_at),
        } for r in rows]
    finally:
        db.close()


def add_favorite(user_id: int, question_title: str, ftype: str = "fav",
                 domain: str = "", difficulty: int = 0, question_url: str = "") -> int:
    db = SessionLocal()
    try:
        exist = (db.query(Favorite)
                 .filter(Favorite.user_id == user_id,
                         Favorite.question_title == question_title,
                         Favorite.ftype == ftype).first())
        if exist:
            return exist.id
        row = Favorite(user_id=user_id, question_title=question_title, ftype=ftype,
                       domain=domain, difficulty=difficulty, question_url=question_url)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id
    finally:
        db.close()


def remove_favorite(user_id: int, question_title: str, ftype: str = "fav") -> int:
    db = SessionLocal()
    try:
        n = (db.query(Favorite)
             .filter(Favorite.user_id == user_id,
                     Favorite.question_title == question_title,
                     Favorite.ftype == ftype)
             .delete(synchronize_session=False))
        db.commit()
        return n
    finally:
        db.close()


def list_favorites(user_id: int, ftype: str = "fav", limit: int = 200) -> list[dict]:
    db = SessionLocal()
    try:
        rows = (db.query(Favorite)
                .filter(Favorite.user_id == user_id, Favorite.ftype == ftype)
                .order_by(Favorite.created_at.desc()).limit(limit).all())
        return [{
            "id": r.id, "question_title": r.question_title, "question_url": r.question_url,
            "domain": r.domain, "difficulty": r.difficulty, "created_at": str(r.created_at),
        } for r in rows]
    finally:
        db.close()


def upsert_pending_question(question: str, domain: str = "", position: str = "",
                            draft_answer: str = "", source_url: str = "") -> int:
    """题库外问题记入待补题池；已存在则 ask_count+1"""
    db = SessionLocal()
    try:
        row = db.query(PendingQuestion).filter(PendingQuestion.question == question).first()
        if row is None:
            row = PendingQuestion(question=question, domain=domain, position=position,
                                  draft_answer=draft_answer, source_url=source_url)
            db.add(row)
        else:
            row.ask_count = (row.ask_count or 1) + 1
            if draft_answer and not row.draft_answer:
                row.draft_answer = draft_answer
            if source_url and not row.source_url:
                row.source_url = source_url
        db.commit()
        db.refresh(row)
        return row.id
    finally:
        db.close()


def list_pending(status: str | None = None, limit: int = 100) -> list[dict]:
    db = SessionLocal()
    try:
        q = db.query(PendingQuestion)
        if status:
            q = q.filter(PendingQuestion.status == status)
        rows = q.order_by(PendingQuestion.ask_count.desc(),
                          PendingQuestion.created_at.desc()).limit(limit).all()
        return [{
            "id": r.id, "question": r.question, "domain": r.domain, "position": r.position,
            "ask_count": r.ask_count, "draft_answer": r.draft_answer,
            "source_url": r.source_url, "status": r.status, "created_at": str(r.created_at),
        } for r in rows]
    finally:
        db.close()


def mark_pending_adopted(pending_id: int) -> bool:
    db = SessionLocal()
    try:
        row = db.query(PendingQuestion).filter(PendingQuestion.id == pending_id).first()
        if not row:
            return False
        row.status = "adopted"
        db.commit()
        return True
    finally:
        db.close()


# ---------------- 能力画像 ---------------- #

def profile_stats(user_id: int) -> dict:
    """聚合练习记录 → 各域平均分/练习数/掌握度、薄弱域、学习日历"""
    from collections import defaultdict
    db = SessionLocal()
    try:
        rows = (db.query(PracticeRecord)
                .filter(PracticeRecord.user_id == user_id)
                .order_by(PracticeRecord.created_at).all())
        by_domain: dict[str, list[int]] = defaultdict(list)
        day_count: dict[str, int] = defaultdict(int)
        for r in rows:
            if r.score is not None:
                by_domain[r.domain or "未分类"].append(r.score)
            day = str(r.created_at)[:10]
            day_count[day] += 1

        domains = [{
            "domain": d,
            "avg_score": round(sum(scores) / len(scores), 1),
            "count": len(scores),
            "mastered": sum(1 for s in scores if s >= 85),
            "weak": sum(1 for s in scores if s < 60),
        } for d, scores in by_domain.items()]
        domains.sort(key=lambda x: x["avg_score"])

        # 连续学习天数
        days = sorted(day_count.keys())
        streak = 0
        from datetime import date, timedelta
        today = date.today()
        dset = set(days)
        cur = today
        while cur.strftime("%Y-%m-%d") in dset:
            streak += 1
            cur -= timedelta(days=1)

        return {
            "total_practiced": len(rows),
            "avg_score": round(sum(r.score for r in rows if r.score is not None) /
                               max(1, sum(1 for r in rows if r.score is not None)), 1),
            "domains": domains,
            "weak_domains": [d for d in domains if d["avg_score"] < 70][:3],
            "streak_days": streak,
            "calendar": [{"day": d, "count": c} for d, c in day_count.items()],
        }
    finally:
        db.close()


# ---------------- 模拟面试 ---------------- #

class InterviewSession(Base):
    """一场模拟面试的配置与状态"""
    __tablename__ = "interview_session"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, index=True, nullable=False)
    position = Column(String(64), nullable=True)        # 岗位
    level = Column(String(16), nullable=True)           # intern/campus/social
    domains = Column(Text, nullable=True)               # JSON 选中的知识域列表
    num_questions = Column(Integer, nullable=False, default=10)
    difficulty_cap = Column(Integer, nullable=False, default=3)
    status = Column(String(16), nullable=False, default="in_progress")  # in_progress / finished
    current_seq = Column(Integer, nullable=False, default=1)            # 当前第几题（主问题）
    total_score = Column(Integer, nullable=True)                        # 总评均分
    report_json = Column(Text, nullable=True)                           # 总评报告 JSON
    created_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)


class InterviewTurn(Base):
    """一轮问答（含追问，parent_turn_id 挂到主问题）"""
    __tablename__ = "interview_turn"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, index=True, nullable=False)
    seq = Column(Integer, nullable=False)               # 主问题序号
    parent_turn_id = Column(Integer, nullable=True)     # 追问链：指向主问题 turn id
    followup_no = Column(Integer, nullable=False, default=0)  # 0=主问题，1/2=第几层追问
    question = Column(Text, nullable=False)
    question_source = Column(String(16), nullable=False, default="rag")  # rag / resume / llm
    qa_refs = Column(Text, nullable=True)               # JSON：检索到的参考题 [{title,url,score}]
    answer = Column(Text, nullable=True)
    score = Column(Integer, nullable=True)              # 0-100
    dim_json = Column(Text, nullable=True)              # 四维得分 JSON
    feedback = Column(Text, nullable=True)
    missing_points = Column(Text, nullable=True)        # JSON list
    created_at = Column(DateTime, default=datetime.utcnow)


def create_interview_session(user_id, position, level, domains, num_questions, difficulty_cap):
    import json as _json
    db = SessionLocal()
    try:
        row = InterviewSession(user_id=user_id, position=position, level=level,
                               domains=_json.dumps(domains, ensure_ascii=False),
                               num_questions=num_questions, difficulty_cap=difficulty_cap)
        db.add(row); db.commit(); db.refresh(row)
        return row.id
    finally:
        db.close()


def get_interview_session(session_id, user_id=None):
    import json as _json
    db = SessionLocal()
    try:
        q = db.query(InterviewSession).filter(InterviewSession.id == session_id)
        if user_id is not None:
            q = q.filter(InterviewSession.user_id == user_id)
        s = q.first()
        if not s:
            return None
        return {"id": s.id, "user_id": s.user_id, "position": s.position, "level": s.level,
                "domains": _json.loads(s.domains or "[]"), "num_questions": s.num_questions,
                "difficulty_cap": s.difficulty_cap, "status": s.status,
                "current_seq": s.current_seq, "total_score": s.total_score,
                "report": _json.loads(s.report_json) if s.report_json else None,
                "created_at": str(s.created_at),
                "finished_at": str(s.finished_at) if s.finished_at else None}
    finally:
        db.close()


def update_session_progress(session_id, current_seq=None, status=None, total_score=None, report=None):
    import json as _json
    db = SessionLocal()
    try:
        s = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
        if not s:
            return
        if current_seq is not None:
            s.current_seq = current_seq
        if status is not None:
            s.status = status
        if total_score is not None:
            s.total_score = total_score
        if report is not None:
            s.report_json = _json.dumps(report, ensure_ascii=False)
        if status == "finished":
            s.finished_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()


def add_turn(session_id, seq, question, question_source="rag",
             parent_turn_id=None, followup_no=0, qa_refs=None):
    import json as _json
    db = SessionLocal()
    try:
        row = InterviewTurn(session_id=session_id, seq=seq, question=question,
                            question_source=question_source, parent_turn_id=parent_turn_id,
                            followup_no=followup_no,
                            qa_refs=_json.dumps(qa_refs or [], ensure_ascii=False))
        db.add(row); db.commit(); db.refresh(row)
        return row.id
    finally:
        db.close()


def answer_turn(turn_id, answer, score, feedback, missing_points=None, dim_json=None):
    import json as _json
    db = SessionLocal()
    try:
        t = db.query(InterviewTurn).filter(InterviewTurn.id == turn_id).first()
        if not t:
            return
        t.answer = answer; t.score = score; t.feedback = feedback
        t.missing_points = _json.dumps(missing_points or [], ensure_ascii=False)
        t.dim_json = _json.dumps(dim_json or {}, ensure_ascii=False)
        db.commit()
    finally:
        db.close()


def list_turns(session_id):
    import json as _json
    db = SessionLocal()
    try:
        rows = (db.query(InterviewTurn).filter(InterviewTurn.session_id == session_id)
                .order_by(InterviewTurn.seq, InterviewTurn.followup_no).all())
        return [{"id": r.id, "seq": r.seq, "parent_turn_id": r.parent_turn_id,
                 "followup_no": r.followup_no, "question": r.question,
                 "question_source": r.question_source, "answer": r.answer,
                 "score": r.score, "feedback": r.feedback,
                 "missing_points": _json.loads(r.missing_points or "[]"),
                 "dimensions": _json.loads(r.dim_json or "{}"),
                 "qa_refs": _json.loads(r.qa_refs or "[]"),
                 "created_at": str(r.created_at)} for r in rows]
    finally:
        db.close()


def list_interviews(user_id, limit=50):
    db = SessionLocal()
    try:
        rows = (db.query(InterviewSession).filter(InterviewSession.user_id == user_id)
                .order_by(InterviewSession.created_at.desc()).limit(limit).all())
        return [{"id": s.id, "position": s.position, "level": s.level,
                 "num_questions": s.num_questions, "status": s.status,
                 "total_score": s.total_score, "created_at": str(s.created_at)} for s in rows]
    finally:
        db.close()


# ---------------- 简历备考历史 ---------------- #

class Resume(Base):
    """上传的简历及其生成的备考内容（面试题/话术/预演）"""
    __tablename__ = "resume"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, index=True, nullable=False)
    filename = Column(String(255), nullable=False)
    target = Column(String(128), nullable=True)          # 目标岗位
    name = Column(String(64), nullable=True)             # 姓名
    profile_json = Column(Text, nullable=True)           # 结构化简历（skills/projects/...）
    questions_json = Column(Text, nullable=True)         # 生成的面试题
    pitch_json = Column(Text, nullable=True)             # 自我介绍话术
    rehearse_json = Column(Text, nullable=True)          # 项目预演（按项目缓存）
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def save_resume(user_id, filename, result: dict) -> int:
    """保存一份简历解析结果，返回 id"""
    import json as _json
    db = SessionLocal()
    try:
        row = Resume(
            user_id=user_id, filename=filename,
            name=result.get("name", ""), target=result.get("target", ""),
            profile_json=_json.dumps({
                "name": result.get("name", ""), "target": result.get("target", ""),
                "skills": result.get("skills", []), "projects": result.get("projects", []),
            }, ensure_ascii=False),
            questions_json=_json.dumps(result.get("questions", []), ensure_ascii=False),
        )
        db.add(row)
        db.commit(); db.refresh(row)
        return row.id
    finally:
        db.close()


def list_resumes(user_id: int, limit: int = 50) -> list[dict]:
    db = SessionLocal()
    try:
        rows = (db.query(Resume).filter(Resume.user_id == user_id)
                .order_by(Resume.created_at.desc()).limit(limit).all())
        return [{"id": r.id, "filename": r.filename, "name": r.name, "target": r.target,
                 "created_at": str(r.created_at)} for r in rows]
    finally:
        db.close()


def get_resume(resume_id: int, user_id: int) -> dict | None:
    import json as _json
    db = SessionLocal()
    try:
        r = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == user_id).first()
        if not r:
            return None
        profile = _json.loads(r.profile_json or "{}")
        return {
            "id": r.id, "filename": r.filename,
            "name": profile.get("name", ""), "target": profile.get("target", ""),
            "skills": profile.get("skills", []), "projects": profile.get("projects", []),
            "questions": _json.loads(r.questions_json or "[]"),
            "pitch": _json.loads(r.pitch_json) if r.pitch_json else None,
            "rehearse": _json.loads(r.rehearse_json) if r.rehearse_json else None,
            "created_at": str(r.created_at),
        }
    finally:
        db.close()


def update_resume_content(resume_id: int, pitch: dict = None, rehearse: dict = None):
    """把生成的话术/预演结果回存到简历记录"""
    import json as _json
    db = SessionLocal()
    try:
        r = db.query(Resume).filter(Resume.id == resume_id).first()
        if not r:
            return
        if pitch is not None:
            r.pitch_json = _json.dumps(pitch, ensure_ascii=False)
        if rehearse is not None:
            r.rehearse_json = _json.dumps(rehearse, ensure_ascii=False)
        db.commit()
    finally:
        db.close()


# ---------------- 长期记忆（学习画像 → 注入生成 prompt） ---------------- #

DOMAIN_CN = {
    "llm_basics": "LLM 原理", "prompt": "Prompt 工程", "rag": "RAG",
    "agent": "Agent", "vectordb": "向量数据库", "framework": "框架",
    "python_backend": "Python 后端", "ml_dl": "ML/DL", "cs_basic": "CS 基础",
}


def get_learning_profile(user_id: int) -> dict:
    """聚合练习记录 → 学习画像（薄弱域 / 强项 / 练习量）"""
    from collections import defaultdict
    db = SessionLocal()
    try:
        rows = (db.query(PracticeRecord)
                .filter(PracticeRecord.user_id == user_id)
                .order_by(PracticeRecord.created_at.desc()).limit(500).all())
        by_domain: dict[str, list[int]] = defaultdict(list)
        for r in rows:
            if r.domain and r.score is not None:
                by_domain[r.domain].append(r.score)
        domains = [{
            "domain": d, "name": DOMAIN_CN.get(d, d),
            "avg": round(sum(s) / len(s), 1), "count": len(s),
        } for d, s in by_domain.items()]
        domains.sort(key=lambda x: x["avg"])
        return {
            "total": len(rows),
            "weak": [d for d in domains if d["avg"] < 70][:3],
            "strong": [d for d in domains if d["avg"] >= 85][:2],
            "domains": domains,
        }
    finally:
        db.close()


def get_top_topics(user_id: int, limit: int = 5) -> list[str]:
    """跨会话高频关注主题（从历史提问里按知识域聚合）"""
    from collections import Counter
    db = SessionLocal()
    try:
        rows = (db.query(ChatRecord).filter(ChatRecord.user_id == user_id)
                .order_by(ChatRecord.created_at.desc()).limit(300).all())
        # 问题里出现的关键词（粗粒度，够用）
        keywords = ["RAG", "Transformer", "Agent", "注意力", "微调", "向量", "索引",
                    "Redis", "MySQL", "LangChain", "LangGraph", "重排", "分块", "Prompt",
                    "GIL", "协程", "缓存", "事务", "并发"]
        c = Counter()
        for r in rows:
            q = r.question or ""
            for k in keywords:
                if k.lower() in q.lower():
                    c[k] += 1
        return [k for k, _ in c.most_common(limit)]
    finally:
        db.close()


def build_memory_context(user_id: int) -> str:
    """把长期记忆压成一段短文本，供注入 prompt（控制在 ~120 token 内）"""
    prof = get_learning_profile(user_id)
    topics = get_top_topics(user_id)
    if not prof["total"] and not topics:
        return ""
    parts = []
    if prof["total"]:
        parts.append(f"该用户已练习 {prof['total']} 题，平均 {round(sum(d['avg'] for d in prof['domains']) / max(1, len(prof['domains'])), 1)} 分")
    if prof["weak"]:
        parts.append("薄弱知识域：" + "、".join(f"{d['name']}({d['avg']}分)" for d in prof["weak"]))
    if prof["strong"]:
        parts.append("较强：" + "、".join(d["name"] for d in prof["strong"]))
    if topics:
        parts.append("近期常问：" + "、".join(topics))
    return "；".join(parts)
