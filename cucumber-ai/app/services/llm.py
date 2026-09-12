"""LLM 提供方抽象（受控润色版）。

接口：`polish(task, correction_errors)` —— 输入受控润色任务包（prompts.build_task），
输出润色后的 JSON 文本。

提供方：
- mock     ：MockProvider，离线回显骨架（确定性，必过校验，用于开发/CI）
- kimi     ：Kimi k3（论文第六章同端点 https://api.kimi.com/coding/v1，temperature=1）
- deepseek ：DeepSeek V4.1 Flash（OpenAI 兼容，deepseek-flash）

请求级重试（与论文 llm_client.py 同口径）：401 立即抛出；429/连接错误/5xx 指数退避
（1s、2s）共 3 次；工作流级的"纠错重润"在 report.py 中另行实现。
"""

import abc
import json
import logging
import time
from typing import Dict, List, Optional

from app.core.config import settings
from app.services import prompts

logger = logging.getLogger(__name__)


class LLMProvider(abc.ABC):
    @abc.abstractmethod
    def polish(self, task: Dict, correction_errors: Optional[List[str]] = None) -> str:
        """对任务包中的 editable_fields 做语言润色，返回 JSON 文本。"""


class MockProvider(LLMProvider):
    """离线 Mock：原样回显骨架的 protected+editable 字段。

    等价于"最保守的润色"——一个字不改，必然通过 12 项校验，
    用于离线开发与 CI 冒烟（也是 LLM 完全不可用时的确定性下限）。
    """

    def polish(self, task: Dict, correction_errors: Optional[List[str]] = None) -> str:
        merged = dict(task.get("protected_fields", {}))
        merged.update(task.get("editable_fields", {}))
        return json.dumps(merged, ensure_ascii=False)


class _OpenAICompatProvider(LLMProvider):
    """OpenAI 兼容协议的润色提供方（Kimi k3 / DeepSeek 共用实现）。"""

    MAX_TOKENS = 2048
    RETRYABLE = ("RateLimit", "APIConnection", "APITimeout", "InternalServer", "ServiceUnavailable")

    def __init__(self, api_key: str, base_url: str, model: str, temperature: float = 1.0) -> None:
        if not api_key:
            raise RuntimeError(f"{self.provider_name} 的 API key 未配置")
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._temperature = temperature

    @property
    def provider_name(self) -> str:  # pragma: no cover
        return self.__class__.__name__

    def polish(self, task: Dict, correction_errors: Optional[List[str]] = None) -> str:
        import httpx
        from openai import APIError, AuthenticationError, OpenAI

        # trust_env=False：绕开系统代理（与论文 llm_client.py 一致，代理会导致间歇性 Connection error）
        http_client = httpx.Client(trust_env=False, timeout=60.0)
        client = OpenAI(api_key=self._api_key, base_url=self._base_url,
                        http_client=http_client, max_retries=0)
        user = prompts.task_to_user_content(task, correction_errors)
        last_exc: Optional[Exception] = None
        for attempt in range(1, 4):  # 请求级 3 次（与论文一致）
            try:
                resp = client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": prompts.SYSTEM_MSG},
                        {"role": "user", "content": user},
                    ],
                    temperature=self._temperature,
                    max_tokens=self.MAX_TOKENS,
                )
                usage = getattr(resp, "usage", None)
                if usage is not None:
                    logger.info("LLM tokens: model=%s attempt=%d prompt=%s completion=%s",
                                self._model, attempt,
                                getattr(usage, "prompt_tokens", "?"),
                                getattr(usage, "completion_tokens", "?"))
                return resp.choices[0].message.content or ""
            except AuthenticationError:
                raise  # 401 立即抛出，不重试（论文口径）
            except APIError as exc:
                last_exc = exc
                if not any(m in type(exc).__name__ or m in str(exc) for m in self.RETRYABLE):
                    raise
                if attempt < 3:
                    time.sleep(2 ** (attempt - 1))  # 1s、2s 指数退避
        raise last_exc  # type: ignore[misc]


class KimiProvider(_OpenAICompatProvider):
    """Kimi k3（论文第六章同端点；k3 端点 temperature 只能为 1）。"""

    def __init__(self) -> None:
        super().__init__(settings.KIMI_API_KEY, settings.KIMI_BASE_URL,
                         settings.KIMI_MODEL, temperature=1.0)


class DeepSeekProvider(_OpenAICompatProvider):
    """DeepSeek V4.1 Flash（OpenAI 兼容）。"""

    def __init__(self) -> None:
        super().__init__(settings.DEEPSEEK_API_KEY, settings.DEEPSEEK_BASE_URL,
                         settings.DEEPSEEK_MODEL, temperature=1.0)


def get_provider() -> LLMProvider:
    provider = settings.LLM_PROVIDER.lower()
    if provider == "kimi":
        logger.info("使用 LLM 提供方: kimi (%s, %s)", settings.KIMI_BASE_URL, settings.KIMI_MODEL)
        return KimiProvider()
    if provider == "deepseek":
        logger.info("使用 LLM 提供方: deepseek (%s, %s)", settings.DEEPSEEK_BASE_URL, settings.DEEPSEEK_MODEL)
        return DeepSeekProvider()
    return MockProvider()
