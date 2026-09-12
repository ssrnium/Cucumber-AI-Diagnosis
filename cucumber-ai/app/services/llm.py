"""LLM 提供方抽象。

LLM_PROVIDER 配置切换：
- mock  ：MockProvider，离线返回固定合法 JSON（本地开发 / CI 冒烟默认）
- kimi  ：KimiProvider，OpenAI 兼容 SDK，base_url=https://api.moonshot.cn/v1
- openai：复用 KimiProvider，仅需把 LLM_BASE_URL / LLM_MODEL 指向 OpenAI
"""

import abc
import json
import logging
import re
from typing import List

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMProvider(abc.ABC):
    @abc.abstractmethod
    def generate(self, prompt: str) -> str:
        """输入提示词，输出 JSON 字符串（诊断报告）。"""


class MockProvider(LLMProvider):
    """离线 Mock：从提示词中解析候选 source_id 与疑似病害，拼装合法报告 JSON。"""

    def generate(self, prompt: str) -> str:
        source_ids: List[str] = re.findall(r"KB-[A-Z]{2}-\d{3}", prompt)
        disease_match = re.search(r"疑似病害[:：]\s*(\S+)", prompt)
        disease_type = disease_match.group(1) if disease_match else "霜霉病"
        report = {
            "disease_type": disease_type,
            "confidence": 0.85,
            "basis": [
                "病斑形态、颜色与分布特征与该病害典型症状一致（mock 生成）。",
                "检测框置信度较高，病斑数量与病害发展阶段相符。",
            ],
            "agronomy": [
                "及时摘除病叶并带出棚外销毁，降低菌源基数。",
                "加强通风降湿，避免叶面长时间结露。",
            ],
            "chemical": [
                "发病初期按标签剂量选用登记药剂喷雾，注意轮换用药（mock 生成）。",
            ],
            "safety": [
                "配药施药佩戴口罩手套，遵守安全间隔期。",
            ],
            "source_ids": source_ids[:2],
        }
        return json.dumps(report, ensure_ascii=False)


class KimiProvider(LLMProvider):
    """Kimi（Moonshot）/ OpenAI 兼容提供方。"""

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._model = model

    def generate(self, prompt: str) -> str:
        from openai import OpenAI

        client = OpenAI(api_key=self._api_key, base_url=self._base_url)
        response = client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": "你是黄瓜病害诊断助手，只输出符合要求的 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        return response.choices[0].message.content or ""


def get_provider() -> LLMProvider:
    provider = settings.LLM_PROVIDER.lower()
    if provider in ("kimi", "openai"):
        logger.info("使用 LLM 提供方: %s (%s)", provider, settings.LLM_BASE_URL)
        return KimiProvider(settings.KIMI_API_KEY, settings.LLM_BASE_URL, settings.LLM_MODEL)
    return MockProvider()
