from typing import List, Optional

from pydantic import BaseModel, Field


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


class DiagnoseRequest(BaseModel):
    """诊断请求：检测框证据 + 可选症状描述关键词。"""

    detections: List[Detection] = Field(default_factory=list)
    symptoms: List[str] = Field(default_factory=list)


class Evidence(BaseModel):
    """检索到的知识证据条目。"""

    source_id: str
    disease_type: str
    title: str
    content: str
    level: str
    category: str


class DiagnosisReport(BaseModel):
    """受控生成的诊断报告（五段式 + 来源追溯）。"""

    disease_type: str = Field(description="诊断结论病害类型")
    confidence: float = Field(ge=0.0, le=1.0)
    basis: List[str] = Field(description="诊断依据")
    agronomy: List[str] = Field(description="农艺措施")
    chemical: List[str] = Field(description="化学防治")
    safety: List[str] = Field(description="安全注意事项")
    source_ids: List[str] = Field(description="引用的知识来源编号，必须来自检索结果")
