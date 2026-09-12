"""病斑检测服务。

【E2_gfix 权重插入点】
将硕士论文中训练好的改进 YOLO11n 权重（E2_gfix.pt）放置到 WEIGHTS_PATH
（默认 weights/E2_gfix.pt），服务启动后自动加载并走真实推理；
权重不存在时回退 MockDetector，返回固定示例病斑框，保证链路可联调。
"""

import io
import logging
from pathlib import Path
from typing import List

from app.core.config import settings
from app.schemas import Detection

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[2]


class Detector:
    def __init__(self, weights_path: str = None) -> None:
        self._model = None
        raw_path = weights_path or settings.WEIGHTS_PATH
        path = Path(raw_path)
        if not path.is_absolute():
            path = ROOT_DIR / raw_path
        if path.exists():
            try:
                # 可选导入：真实权重存在时才需要 ultralytics，未安装则回退 Mock
                from ultralytics import YOLO  # noqa: WPS433

                self._model = YOLO(str(path))
                logger.info("已加载检测权重: %s", path)
            except Exception as exc:  # noqa: BLE001
                logger.warning("权重加载失败，回退 Mock 检测: %s", exc)
        else:
            logger.info("未找到检测权重 %s，使用 Mock 检测", path)

    def detect(self, image_bytes: bytes) -> List[Detection]:
        if self._model is not None:
            try:
                return self._real_detect(image_bytes)
            except Exception as exc:  # noqa: BLE001
                logger.warning("真实推理失败，回退 Mock 检测: %s", exc)
        return self._mock_detect()

    def _real_detect(self, image_bytes: bytes) -> List[Detection]:
        from PIL import Image  # 可选依赖，随 ultralytics 安装

        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        results = self._model.predict(image, verbose=False)
        detections: List[Detection] = []
        for box in results[0].boxes:
            x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())
            detections.append(
                Detection(
                    x1=x1,
                    y1=y1,
                    x2=x2,
                    y2=y2,
                    confidence=float(box.conf[0]),
                    label=self._model.names[int(box.cls[0])],
                )
            )
        return detections

    @staticmethod
    def _mock_detect() -> List[Detection]:
        return [
            Detection(x1=120.0, y1=85.0, x2=260.0, y2=210.0, confidence=0.87, label="霜霉病"),
            Detection(x1=310.0, y1=240.0, x2=390.0, y2=330.0, confidence=0.72, label="霜霉病"),
        ]


detector = Detector()
