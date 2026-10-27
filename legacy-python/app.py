"""后端启动入口：uvicorn 跑 interviewace.backend.main:app，端口 8002

端口约定：8000=SmartQuery 后端，8001=Attu(Milvus 可视化)，8002=InterviewAce 后端
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("interviewace.backend.main:app", host="0.0.0.0", port=8002, reload=False)

