"""平台 HTTP 客户端：cucumber-admin（业务后端）与 cucumber-ai（AI 服务）。

定位：
  - 这些客户端是 MCP 工具（MCPToolManager 注册的 Tool）背后的真实 handler 依赖，
    Agent 不直接持有 HTTP 客户端，仍然走 ToolManager 的缓存/熔断/超时治理。
  - cucumber-admin 侧使用 svc-agent 服务账号登录获取 JWT，401 时自动重新登录刷新。

环境变量：
  CUCUMBER_ADMIN_URL      业务后端地址，默认 http://localhost:8080
  CUCUMBER_AI_URL         AI 服务地址，默认 http://localhost:8000
  AGENT_SERVICE_USERNAME  服务账号用户名，默认 svc-agent
  AGENT_SERVICE_PASSWORD  服务账号密码（必填，未配置时 admin 工具降级为不可用）
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class CucumberAIClient:
    """cucumber-ai 检测/受控诊断报告链路。"""

    def __init__(self, base_url: Optional[str] = None, timeout_s: float = 30.0):
        self._base_url = (base_url or os.getenv("CUCUMBER_AI_URL", "http://localhost:8000")).rstrip("/")
        self._timeout = timeout_s

    async def diagnose_image(self, image_bytes: bytes, filename: str = "leaf.jpg",
                             symptoms: Optional[List[str]] = None) -> Dict[str, Any]:
        """图片字节 → 病斑框检测 → 受控诊断报告（含 source_ids 来源追溯）。"""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            detect_resp = await client.post(
                f"{self._base_url}/api/v1/detect",
                files={"file": (filename, image_bytes, "image/jpeg")},
            )
            detect_resp.raise_for_status()
            detections = detect_resp.json().get("detections", [])

            diagnose_resp = await client.post(
                f"{self._base_url}/api/v1/diagnose",
                json={"detections": detections, "symptoms": symptoms or []},
            )
            diagnose_resp.raise_for_status()
            report = diagnose_resp.json()

        return {"detections": detections, "report": report}


class CucumberAdminClient:
    """cucumber-admin 业务后端客户端（svc-agent 服务账号，JWT 自动刷新）。"""

    def __init__(
        self,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout_s: float = 15.0,
    ):
        self._base_url = (base_url or os.getenv("CUCUMBER_ADMIN_URL", "http://localhost:8080")).rstrip("/")
        self._username = username or os.getenv("AGENT_SERVICE_USERNAME", "svc-agent")
        self._password = password if password is not None else os.getenv("AGENT_SERVICE_PASSWORD", "")
        self._timeout = timeout_s
        self._token: Optional[str] = None

    @property
    def configured(self) -> bool:
        """未配置服务账号密码时，admin 侧工具直接降级，不阻塞服务启动。"""
        return bool(self._password)

    async def _login(self, client: httpx.AsyncClient) -> str:
        resp = await client.post(
            f"{self._base_url}/api/v1/auth/login",
            json={"username": self._username, "password": self._password},
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != 200:
            raise RuntimeError(f"svc-agent 登录失败: {payload.get('message')}")
        token = (payload.get("data") or {}).get("token")
        if not token:
            raise RuntimeError("svc-agent 登录响应缺少 token")
        self._token = token
        logger.info("svc-agent 已登录 cucumber-admin")
        return token

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """带 JWT 的请求；401 时重新登录并重试一次（自动刷新）。"""
        if not self.configured:
            raise RuntimeError("未配置 AGENT_SERVICE_PASSWORD，admin 工具不可用")
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            if not self._token:
                await self._login(client)
            for attempt in range(2):
                headers = {"Authorization": f"Bearer {self._token}"}
                resp = await client.request(method, f"{self._base_url}{path}", headers=headers, **kwargs)
                if resp.status_code == 401 and attempt == 0:
                    logger.info("svc-agent token 过期，重新登录刷新")
                    await self._login(client)
                    continue
                resp.raise_for_status()
                payload = resp.json()
                if payload.get("code") != 200:
                    raise RuntimeError(f"admin 接口返回错误: {payload.get('message')}")
                return payload.get("data")
        raise RuntimeError("admin 请求失败")

    async def list_diagnosis_records(self, page: int = 1, size: int = 5,
                                     status: Optional[str] = None) -> Dict[str, Any]:
        """分页查询诊断记录（svc-agent 具备 diagnosis:list:all 时返回全部）。"""
        params: Dict[str, Any] = {"page": page, "size": size}
        if status:
            params["status"] = status
        return await self._request("GET", "/api/v1/diagnosis", params=params)

    async def get_diagnosis_record(self, record_id: int) -> Dict[str, Any]:
        """诊断记录详情（含病斑框与报告全文）。"""
        return await self._request("GET", f"/api/v1/diagnosis/{record_id}")

    async def create_diagnosis_feedback(self, record_id: int, corrected_disease_type: str,
                                        comment: str) -> None:
        """创建专家复核反馈（诊断有误/人工升级交接时调用）。"""
        await self._request(
            "POST", f"/api/v1/diagnosis/{record_id}/feedback",
            json={"verdict": "WRONG", "correctedDiseaseType": corrected_disease_type,
                  "comment": comment},
        )

    async def fetch_image(self, image_url: str) -> bytes:
        """按 /files/xxx 形式的图片地址从 admin 拉取图片字节。"""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._base_url}{image_url}")
            resp.raise_for_status()
            return resp.content
