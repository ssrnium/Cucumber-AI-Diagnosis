from fastapi import APIRouter, File, UploadFile

from app.schemas import DetectResponse
from app.services.detector import detector

router = APIRouter()


@router.post("/detect", response_model=DetectResponse)
async def detect(file: UploadFile = File(...)) -> DetectResponse:
    """叶片图片 -> 病斑框列表。权重存在走真实推理，否则返回 Mock 示例框。"""
    image_bytes = await file.read()
    return DetectResponse(detections=detector.detect(image_bytes))
