"""病斑检测服务。

权重存在（默认 weights/E2_gfix.pt）时，经 e2_loader 加载论文冻结的
E2_gfix 改进 YOLO11n 做真实推理（imgsz=640/conf=0.25/iou=0.7/CPU，
与论文评测部署口径一致），返回中文病害类别与推理耗时；
权重缺失或加载失败时回退 MockDetector（固定示例框），保证链路可联调。
"""

import io
import logging
import time
from pathlib import Path
from typing import List, Tuple

from app.core.config import settings
from app.schemas import Detection

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[2]

CLASS_NAME_ZH = {
    "Fresh_Leaf": "健康叶",
    "Anthracnose": "炭疽病",
    "Downy_Mildew": "霜霉病",
    "Gummy_Stem_Blight": "蔓枯病",
    "Powdery_Mildew": "白粉病",
}

# 部署推理参数（交接文档口径：imgsz=640/conf=0.25/iou=0.7/CPU）
PREDICT_PARAMS = {"imgsz": 640, "conf": 0.25, "iou": 0.7, "device": "cpu"}


class Detector:
    def __init__(self, weights_path: str = None) -> None:
        self._model = None
        self.model_version = "mock-detector"
        raw_path = weights_path or settings.WEIGHTS_PATH
        path = Path(raw_path)
        if not path.is_absolute():
            path = ROOT_DIR / raw_path
        if path.exists():
            try:
                from app.services import e2_loader

                self._model = e2_loader.load_yolo(str(path))
                self.model_version = path.stem
                logger.info("已加载检测权重: %s", path)
            except Exception as exc:  # noqa: BLE001
                logger.warning("权重加载失败，回退 Mock 检测: %s", exc)
        else:
            logger.info("未找到检测权重 %s，使用 Mock 检测", path)

    def detect(self, image_bytes: bytes) -> Tuple[List[Detection], float]:
        """返回 (病斑框列表, 推理耗时毫秒)。Mock 路径耗时记 0。"""
        if self._model is not None:
            try:
                return self._real_detect(image_bytes)
            except Exception as exc:  # noqa: BLE001
                logger.warning("真实推理失败，回退 Mock 检测: %s", exc)
        return self._mock_detect(), 0.0

    def _real_detect(self, image_bytes: bytes) -> Tuple[List[Detection], float]:
        from PIL import Image

        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        t0 = time.perf_counter()
        results = self._model.predict(image, verbose=False, **PREDICT_PARAMS)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        detections: List[Detection] = []
        for box in results[0].boxes:
            x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())
            name = self._model.names[int(box.cls[0])]
            detections.append(
                Detection(
                    x1=x1,
                    y1=y1,
                    x2=x2,
                    y2=y2,
                    confidence=float(box.conf[0]),
                    label=CLASS_NAME_ZH.get(name, name),
                )
            )
        return detections, elapsed_ms

    @staticmethod
    def _mock_detect() -> List[Detection]:
        return [
            Detection(x1=120.0, y1=85.0, x2=260.0, y2=210.0, confidence=0.87, label="霜霉病"),
            Detection(x1=310.0, y1=240.0, x2=390.0, y2=330.0, confidence=0.72, label="霜霉病"),
        ]


detector = Detector()
