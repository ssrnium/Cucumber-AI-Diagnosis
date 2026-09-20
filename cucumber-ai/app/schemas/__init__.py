import logging
import re
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

SYMPTOM_MAX_COUNT = 10
SYMPTOM_MAX_LENGTH = 50

# 明显指令注入样式：命中即整条剔除并记录日志（症状只是辅助证据，绝不允许指挥模型）
_INJECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"忽略.{0,10}(指令|要求|规则|约束)",
        r"ignore\s+(all\s+|any\s+)?(previous\s+|prior\s+)?instructions?",
        r"你(现在|是|将作为|扮演)",
        r"(必须|务必|直接|一律|应当)?诊断为",
        r"(system|assistant|user)\s*[::]",
    )
]


def _looks_like_injection(text: str) -> bool:
    return any(p.search(text) for p in _INJECTION_PATTERNS)


class Detection(BaseModel):
    """单个病斑框，坐标为原图像素坐标。"""

    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float = Field(ge=0.0, le=1.0)
    label: str = Field(description="病害候选类别，如 霜霉病")


class DetectResponse(BaseModel):
    detections: List[Detection]
    inference_ms: float = Field(default=0.0, description="推理耗时（毫秒），Mock 路径为 0")
    model_version: str = Field(default="mock-detector", description="实际参与推理的模型版本标识")


class DiagnoseRequest(BaseModel):
    """诊断请求：检测框证据 + 可选症状描述关键词。

    symptoms 为辅助证据：清洗（去空白/去重/剔除注入样式）后进入报告"症状线索"，
    永远不参与 protected 字段（类别/置信度）的判定。
    """

    detections: List[Detection] = Field(default_factory=list)
    symptoms: List[str] = Field(default_factory=list)

    @field_validator("symptoms", mode="before")
    @classmethod
    def _clean_symptoms(cls, raw: object) -> List[str]:
        if raw is None:
            return []
        if not isinstance(raw, (list, tuple)):
            raise ValueError("symptoms 必须是字符串列表")
        if len(raw) > SYMPTOM_MAX_COUNT:
            raise ValueError(f"症状描述最多 {SYMPTOM_MAX_COUNT} 条")
        cleaned: List[str] = []
        for item in raw:
            if not isinstance(item, str):
                raise ValueError("症状描述必须是字符串")
            text = re.sub(r"\s+", " ", item).strip()
            if not text:
                continue
            if _looks_like_injection(text):
                logger.warning("剔除疑似指令注入的症状描述: %s", text[:30])
                continue
            if len(text) > SYMPTOM_MAX_LENGTH:
                raise ValueError(f"单条症状描述最长 {SYMPTOM_MAX_LENGTH} 字")
            if text not in cleaned:
                cleaned.append(text)
        return cleaned


class Evidence(BaseModel):
    """检索到的知识证据条目。"""

    source_id: str
    disease_type: str
    title: str
    content: str
    level: str
    category: str


class DiagnosisReport(BaseModel):
    """受控生成的诊断报告（五段式 + 来源追溯 + 不确定性与状态）。

    diagnosis_status 语义：DIAGNOSED（达到阈值）/ UNCERTAIN（有候选但置信不足或类别冲突）
    / INCONCLUSIVE（无检测框，信息不足；此时 disease_type 与 confidence 为 null）。
    服务异常不落报告，FAILED 体现在业务侧诊断记录状态上。
    """

    disease_type: Optional[str] = Field(default=None, description="诊断结论病害类型（INCONCLUSIVE 时为 null）")
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0,
                                        description="结论置信度（INCONCLUSIVE 时为 null）")
    basis: List[str] = Field(description="诊断依据")
    agronomy: List[str] = Field(description="农艺措施")
    chemical: List[str] = Field(description="化学防治")
    safety: List[str] = Field(description="安全注意事项")
    source_ids: List[str] = Field(description="引用的知识来源编号，必须来自检索结果")
    uncertainty_note: Optional[str] = Field(default=None, description="低置信/类别冲突/无检出时的不确定性说明")
    report_status: Optional[str] = Field(default=None, description="polished=LLM 润色通过 / fallback_to_skeleton=骨架回退 / inconclusive=无检出")
    diagnosis_status: str = Field(default="DIAGNOSED", description="DIAGNOSED / UNCERTAIN / INCONCLUSIVE")
    requires_review: bool = Field(default=False, description="是否建议人工复核（UNCERTAIN/INCONCLUSIVE 为 true）")
