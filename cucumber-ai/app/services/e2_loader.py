"""E2_gfix 论文冻结权重的运行时加载器。

E2_gfix 是带"零门控残差融合"的改进 YOLO11n，其 checkpoint 依赖训练侧的
自定义 ultralytics 运行时与融合模块定义（见 detect_one.py 的加载方式）。
因此 vendor/ 目录内置了同版本运行时副本（ultralytics 8.4.90）与融合模块：

    vendor/ultralytics/     训练侧隔离运行时（与服务器 ultralytics_ch4 同源）
    vendor/e2_modules/      text_guided_fusion.py / region_text_loss.py / e_trainers.py

加载顺序必须是：vendor 路径注入 -> import e_trainers（注册融合模块，
ckpt 反序列化时会回调这些定义）-> from ultralytics import YOLO。
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
VENDOR_DIR = ROOT_DIR / "vendor"

_READY = False


def ensure_runtime() -> None:
    """幂等注入 vendor 路径并注册融合模块。"""
    global _READY
    if _READY:
        return
    if str(VENDOR_DIR) not in sys.path:
        sys.path.insert(0, str(VENDOR_DIR))
    import ultralytics  # noqa: F401 来自 vendor/（8.4.90，而非 pip 版）

    e2m = str(VENDOR_DIR / "e2_modules")
    if e2m not in sys.path:
        sys.path.insert(0, e2m)
    import e_trainers  # noqa: F401 注册融合模块（SHBC/SCCA/零门控残差等定义）
    _READY = True


def load_yolo(weights_path: str):
    ensure_runtime()
    from ultralytics import YOLO

    return YOLO(weights_path)
