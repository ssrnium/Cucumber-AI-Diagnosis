from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """AI 服务配置，均可通过同名环境变量覆盖。"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM 提供方：mock（本地固定 JSON）/ kimi / openai
    LLM_PROVIDER: str = "mock"
    KIMI_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.moonshot.cn/v1"
    LLM_MODEL: str = "moonshot-v1-8k"

    # 检测权重路径（E2_gfix 改进 YOLO11n 权重插入点，不存在时自动走 Mock 检测）
    WEIGHTS_PATH: str = "weights/E2_gfix.pt"

    # 知识库文件路径
    KNOWLEDGE_PATH: str = "data/disease_knowledge.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
