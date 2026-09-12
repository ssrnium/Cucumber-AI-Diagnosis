from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import detect, diagnose, eval, knowledge

app = FastAPI(
    title="cucumber-ai",
    description="黄瓜叶片病害智能识别与可信辅助诊断 - AI 服务",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(detect.router, prefix="/api/v1", tags=["detect"])
app.include_router(diagnose.router, prefix="/api/v1", tags=["diagnose"])
app.include_router(knowledge.router, prefix="/api/v1", tags=["knowledge"])
app.include_router(eval.router, prefix="/api/v1", tags=["eval"])


@app.get("/health")
def health() -> dict:
    return {
        "status": "UP",
        "service": "cucumber-ai",
        "llm_provider": settings.LLM_PROVIDER,
    }
