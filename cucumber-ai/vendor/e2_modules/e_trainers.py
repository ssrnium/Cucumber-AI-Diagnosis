"""Chapter5 E0/E1/E2 trainers (08_experiments/scripts/e_trainers.py).

- E0: vanilla DetectionTrainer on the isolated runtime (baseline, no fusion).
- E1: FusionDetectionTrainer — attaches TextGuidedFusion to the authoritative
  model (base weights from best.pt, fusion params trainable, zero-gate init).
- E2: same as E1 + RegionTextCriterion (v8DetectionLoss + lambda_rt * L_RT).

Full-load guarantee: get_model asserts EVERY checkpoint tensor is transferred
(intersect == checkpoint keys), not just partially matched.
"""

from __future__ import annotations

import sys
from pathlib import Path

import torch

WS = Path("D:/chines-clip-nnn/chapter5_multimodal")
sys.path.insert(0, str(WS / "02_visual_runtime/ultralytics_isolated"))
sys.path.insert(0, str(WS / "06_multiscale_fusion"))
sys.path.insert(0, str(WS / "07_region_alignment"))

from ultralytics.models.yolo.detect import DetectionTrainer  # noqa: E402
from ultralytics.nn.tasks import DetectionModel  # noqa: E402
from ultralytics.utils.loss import v8DetectionLoss  # noqa: E402
from ultralytics.utils.torch_utils import intersect_dicts  # noqa: E402

from region_text_loss import RegionTextLoss  # noqa: E402
from text_guided_fusion import TextGuidedFusion, attach_fusion  # noqa: E402


def full_load(model: torch.nn.Module, weights: str) -> None:
    """Load checkpoint and assert 100% of checkpoint tensors are transferred."""
    ckpt = torch.load(weights, map_location="cpu", weights_only=False)
    csd = ckpt["model"].float().state_dict()
    updated = intersect_dicts(csd, model.state_dict())
    assert len(updated) == len(csd), (
        f"partial load: {len(updated)}/{len(csd)} checkpoint tensors matched"
    )
    model.load_state_dict(updated, strict=False)


class RegionTextCriterion:
    """v8DetectionLoss + lambda_rt * L_RT (L_RT added into the cls item).

    Keeps the 3-item loss vector so trainer logging is unchanged; gradient of
    L_RT flows to h_l via fusion.cached_r. Documented in 08_experiments/README.
    """

    def __init__(self, model: DetectionModel, fusion: TextGuidedFusion,
                 lambda_rt: float, tau: float, sampling: str = "center"):
        self.base = v8DetectionLoss(model)
        self.rt = RegionTextLoss(fusion.t_bar, tau=tau, img_size=640, sampling=sampling)
        self.fusion = fusion
        self.lambda_rt = lambda_rt

    def __call__(self, preds, batch):
        det_loss, det_items = self.base(preds, batch)
        raw = preds[1] if isinstance(preds, tuple) else preds  # mirror v8DetectionLoss.parse_output
        b = int(raw["boxes"].shape[0])
        cls = batch["cls"].view(-1).long()
        boxes = batch["bboxes"] * 640.0
        bidx = batch["batch_idx"].view(-1).long()
        targets = []
        for i in range(b):
            m = bidx == i
            targets.append({"cls": cls[m], "boxes": boxes[m]})
        l_rt = self.rt(self.fusion.cached_r, targets)
        total = det_loss.clone()
        total[1] = total[1] + self.lambda_rt * l_rt  # into cls item (documented)
        return total, det_items


class FusionDetectionModel(DetectionModel):
    """DetectionModel + attached TextGuidedFusion (as submodule)."""

    def setup_fusion(self, t_bar: torch.Tensor, lambda_rt: float, tau: float,
                     sampling: str = "center") -> None:
        self.fusion = TextGuidedFusion(t_bar, proto_dim=5)
        self._fusion_handles = attach_fusion(self, self.fusion)
        self.lambda_rt = lambda_rt
        self.tau = tau
        self.sampling = sampling

    def init_criterion(self):
        if getattr(self, "lambda_rt", 0.0) > 0:
            return RegionTextCriterion(self, self.fusion, self.lambda_rt, self.tau,
                                       getattr(self, "sampling", "center"))
        return v8DetectionLoss(self)


class BaseETrainer(DetectionTrainer):
    """E0: baseline with full-load assertion."""

    t_bar = None
    lambda_rt = 0.0
    tau = 0.07
    sampling = "center"

    def get_model(self, cfg=None, weights=None, verbose=True):
        model = DetectionModel(cfg, nc=self.data["nc"], ch=self.data["channels"], verbose=False)
        if weights:
            full_load(model, weights)
        return model


class FusionDetectionTrainer(BaseETrainer):
    """E1 (lambda_rt=0) / E2 (lambda_rt>0): fusion-attached trainer."""

    def get_model(self, cfg=None, weights=None, verbose=True):
        model = FusionDetectionModel(cfg, nc=self.data["nc"], ch=self.data["channels"], verbose=False)
        if weights:
            full_load(model, weights)
        model.setup_fusion(self.t_bar, self.lambda_rt, self.tau, self.sampling)
        return model


# ---------------------------------------------------------------------------
# TCDH arms (prereg file 19): TCDetect head + partial checkpoint migration.
# ---------------------------------------------------------------------------


def partial_load(model: torch.nn.Module, weights: str, report_path=None) -> dict:
    """Load the chapter-4 checkpoint into a TCDetect model.

    All backbone/neck/cv2/cv3-tower tensors transfer 1:1; only the six final
    cls-conv tensors (cv3.{i}.2.{weight,bias}, nc=5 -> embed=512) are dropped by
    shape mismatch and re-initialized. Writes a migration report and asserts
    that nothing outside those six tensors is missing.
    """
    ckpt = torch.load(weights, map_location="cpu", weights_only=False)
    csd = ckpt["model"].float().state_dict()
    updated = intersect_dicts(csd, model.state_dict())
    unmatched = sorted(k for k in csd if k not in updated)
    new_keys = sorted(k for k in model.state_dict() if k not in csd)
    expected = {f"model.24.cv3.{i}.2.{s}" for i in range(3) for s in ("weight", "bias")}
    assert set(unmatched) <= expected, f"unexpected unmatched keys: {set(unmatched) - expected}"
    model.load_state_dict(updated, strict=False)
    report = {
        "source": weights,
        "matched_tensors": len(updated),
        "dropped_shape_mismatch": unmatched,
        "newly_initialized": new_keys,
        "unexpected_unmatched": sorted(set(unmatched) - expected),
    }
    if report_path:
        import json
        from pathlib import Path
        Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


class TCDetectTrainer(BaseETrainer):
    """TCDH arms S1/S2/S3: TCDetect head + partial_load + text prototypes."""

    text_pt = None          # path to prototype .pt
    text_key = "T_cap"      # key inside the .pt
    text_trainable = False  # S3 arm: True

    def get_model(self, cfg=None, weights=None, verbose=True):
        model = DetectionModel(cfg, nc=self.data["nc"], ch=self.data["channels"], verbose=False)
        if weights:
            name = getattr(self.args, "name", "tcdh")
            report_path = WS / f"08_experiments/runs/{name}_migration_report.json"
            partial_load(model, weights, report_path=report_path)
        proto = torch.load(self.text_pt, map_location="cpu", weights_only=False)[self.text_key].float()
        model.model[-1].set_text(proto, trainable=self.text_trainable)
        return model
