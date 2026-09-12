"""Region-text alignment loss (chapter5, 07_region_alignment).

Region representation: R_l = h_l(F_l), cached inside the fusion module
PRE-injection (before residual write-back). For each GT box:
  1. scale assignment by box area (candidate rule, documented):
       area < 32^2 px  -> P3 (stride 8)
       area < 96^2 px  -> P4 (stride 16)
       else            -> P5 (stride 32)
  2. region vector = bilinear sample of R_l at the box center (no RoIAlign);
  3. logits = cosine(region_vec, T_bar) / tau; loss = cross_entropy(logits, cls).

Empty-target batches return a graph-connected zero loss (no error).
T_bar stays a frozen buffer; gradients flow to h_l only.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision.ops import roi_align

SCALE_STRIDE = {"P3": 8, "P4": 16, "P5": 32}
AREA_THRESHOLDS = (32.0 ** 2, 96.0 ** 2)  # candidate rule


def assign_scale(w_px: float, h_px: float) -> str:
    area = w_px * h_px
    if area < AREA_THRESHOLDS[0]:
        return "P3"
    if area < AREA_THRESHOLDS[1]:
        return "P4"
    return "P5"


class RegionTextLoss(nn.Module):
    def __init__(self, t_bar: torch.Tensor, tau: float = 0.07, img_size: int = 640,
                 sampling: str = "center"):
        super().__init__()
        assert sampling in ("center", "roialign")
        self.register_buffer("t_bar", t_bar.float().clone())  # frozen
        self.tau = tau
        self.img_size = img_size
        self.sampling = sampling  # 'center' (E2/E3) | 'roialign' (E4)
        self.last_region_count = 0
        self.last_scale_counts = {"P3": 0, "P4": 0, "P5": 0}

    def _regions_center(self, cached_r, targets, device):
        """E2/E3 path: bilinear sample at GT box center."""
        region_vecs, region_cls, scale_counts = [], [], {"P3": 0, "P4": 0, "P5": 0}
        for b, tgt in enumerate(targets):
            if tgt["cls"].numel() == 0:
                continue
            for cls, (cx, cy, w, h) in zip(tgt["cls"].tolist(), tgt["boxes"].tolist()):
                scale = assign_scale(w, h)
                r_map = cached_r[scale]
                gx = (cx / self.img_size) * 2.0 - 1.0
                gy = (cy / self.img_size) * 2.0 - 1.0
                grid = torch.tensor([[[[gx, gy]]]], device=device, dtype=r_map.dtype)
                vec = F.grid_sample(r_map[b : b + 1], grid, mode="bilinear", align_corners=True)[0, :, 0, 0]
                region_vecs.append(vec)
                region_cls.append(int(cls))
                scale_counts[scale] += 1
        return region_vecs, region_cls, scale_counts

    def _regions_roialign(self, cached_r, targets, device):
        """E4 path: ONE batched RoIAlign(7x7) call per scale + mean pooling.

        Vectorized 2026-07-25: per-box roi_align calls were ~4x slower/epoch.
        """
        region_vecs, region_cls, scale_counts = [], [], {"P3": 0, "P4": 0, "P5": 0}
        # group GT boxes by assigned scale
        by_scale = {"P3": [], "P4": [], "P5": []}
        for b, tgt in enumerate(targets):
            if tgt["cls"].numel() == 0:
                continue
            for cls, (cx, cy, w, h) in zip(tgt["cls"].tolist(), tgt["boxes"].tolist()):
                scale = assign_scale(w, h)
                x1 = max(0.0, cx - w / 2.0)
                y1 = max(0.0, cy - h / 2.0)
                x2 = min(float(self.img_size), cx + w / 2.0)
                y2 = min(float(self.img_size), cy + h / 2.0)
                x2 = max(x2, x1 + 1.0)
                y2 = max(y2, y1 + 1.0)
                by_scale[scale].append((b, x1, y1, x2, y2, int(cls)))
        for scale, rows in by_scale.items():
            if not rows:
                continue
            rois = torch.tensor([r[:5] for r in rows], device=device,
                                dtype=cached_r[scale].dtype)  # [N,5] one H2D per scale
            roi = roi_align(cached_r[scale], rois, output_size=(7, 7),
                            spatial_scale=1.0 / SCALE_STRIDE[scale], aligned=True)
            vecs = roi.mean(dim=(2, 3))  # [N,5]
            for vec, r in zip(vecs, rows):
                region_vecs.append(vec)
                region_cls.append(r[5])
            scale_counts[scale] = len(rows)
        return region_vecs, region_cls, scale_counts

    def forward(self, cached_r: dict, targets: list) -> torch.Tensor:
        """cached_r: {scale: [B,5,H,W]}; targets: list per image of dicts
        {"cls": [Ni], "boxes": [Ni,4] pixel xywh}. Empty targets -> zero loss."""
        device = self.t_bar.device
        zero = torch.zeros((), device=device)
        # keep graph connectivity so total-loss backward never breaks
        anchor = sum(r.sum() * 0.0 for r in cached_r.values())
        if self.sampling == "roialign":
            region_vecs, region_cls, scale_counts = self._regions_roialign(cached_r, targets, device)
        else:
            region_vecs, region_cls, scale_counts = self._regions_center(cached_r, targets, device)
        self.last_scale_counts = scale_counts
        self.last_region_count = len(region_vecs)
        if not region_vecs:
            return zero + anchor
        rv = F.normalize(torch.stack(region_vecs), dim=-1, p=2)  # [N,5]
        tn = F.normalize(self.t_bar, dim=-1, p=2)  # [5,5]
        logits = rv @ tn.T / self.tau  # [N,5]
        labels = torch.tensor(region_cls, device=device, dtype=torch.long)
        return F.cross_entropy(logits, labels) + anchor
