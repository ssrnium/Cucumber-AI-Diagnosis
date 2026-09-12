"""Text-guided multi-scale fusion module (chapter5, 06_multiscale_fusion).

Minimal closed-loop design (frozen data-flow):
  F_l -> h_l (1x1 conv, C_l -> proto_dim)          # visual adaptation
      -> L2 normalize -> cosine match vs T_bar      # position-level matching  S_l [B,K,H,W]
      -> aggregate: A_l = S_l @ T_bar               # semantic aggregation    A_l [B,D,H,W]
      -> g_l (1x1 conv, proto_dim -> C_l)           # write-back mapping
      -> F'_l = F_l + gamma_l * g_l(A_l)            # zero-gated residual write-back

T_bar (TP-DSP low-dim prototypes, r=5/alpha=0.8) is a FIXED buffer: no gradient.
gamma_l is initialized to 0.5 (gate-activation fix, 2026-08-23). The earlier
zero-init let the gate random-walk around 0 for 300 epochs (AdamW + noisy
near-zero-mean detection gradient; |gamma| <= 0.11 in the ch4v22 arms), so the
fusion branch never actually engaged. A non-zero init gives g_l real gradients
from step 0 so the write-back branch learns, and gamma itself is placed in the
no-weight-decay optimizer group (scalar gate, treated like logit_scale).

Boundaries: no region-alignment loss, no formal training, no TP-DSP changes,
no text re-encoding.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

# scale name -> (layer_index, channels, spatial size at 640 input)
FUSION_SCALES = {
    "P3": {"layer": 17, "channels": 64, "size": 80},
    "P4": {"layer": 20, "channels": 128, "size": 40},
    "P5": {"layer": 23, "channels": 256, "size": 20},
}


class ScaleFusion(nn.Module):
    """Single-scale text-guided fusion block with a learnable gate (init 0.5)."""

    def __init__(self, channels: int, proto_dim: int = 5):
        super().__init__()
        self.adapt = nn.Conv2d(channels, proto_dim, kernel_size=1)      # h_l
        self.writeback = nn.Conv2d(proto_dim, channels, kernel_size=1)  # g_l
        self.gate = nn.Parameter(torch.full((1,), 0.5))                 # gamma_l (init 0.5, see module docstring)

    def forward(self, feat: torch.Tensor, t_bar: torch.Tensor) -> torch.Tensor:
        v = self.adapt(feat)                                # [B, D, H, W] = R_l (pre-injection)
        self.last_r = v  # cached region representation for region-text loss (no interface change)
        vn = F.normalize(v, dim=1, p=2)
        tn = F.normalize(t_bar, dim=-1, p=2)                # [K, D] (already normalized)
        s = torch.einsum("bdhw,kd->bkhw", vn, tn)           # position-level match [B,K,H,W]
        a = torch.einsum("bkhw,kd->bdhw", s, tn)            # aggregated semantics [B,D,H,W]
        return feat + self.gate * self.writeback(a)         # residual write-back


class TextGuidedFusion(nn.Module):
    """Multi-scale fusion container; holds T_bar as a frozen buffer."""

    def __init__(self, t_bar: torch.Tensor, proto_dim: int = 5):
        super().__init__()
        assert t_bar.shape[1] == proto_dim
        self.register_buffer("t_bar", t_bar.float().clone())  # frozen, no grad
        self.scales = nn.ModuleDict(
            {name: ScaleFusion(cfg["channels"], proto_dim) for name, cfg in FUSION_SCALES.items()}
        )
        self.cached_r: dict = {}  # scale_name -> R_l = h_l(F_l), pre-injection, from latest forward

    def fuse(self, scale_name: str, feat: torch.Tensor) -> torch.Tensor:
        out = self.scales[scale_name](feat, self.t_bar)
        self.cached_r[scale_name] = self.scales[scale_name].last_r
        return out


class FusionHook:
    """Module-level picklable forward hook (closures break torch.save pickling)."""

    def __init__(self, fusion: "TextGuidedFusion", scale_name: str):
        self.fusion = fusion
        self.scale_name = scale_name

    def __call__(self, module, inputs, output):
        return self.fusion.fuse(self.scale_name, output)


def attach_fusion(base_model: nn.Module, fusion: TextGuidedFusion) -> list:
    """Attach fusion to layers 17/20/23 via output-replacing forward hooks.

    Returns the hook handles (caller may remove them). The Detect layer (24)
    then receives the fused P3/P4/P5 features. Base model source is untouched.
    """
    handles = []
    for name, cfg in FUSION_SCALES.items():
        layer = base_model.model[cfg["layer"]]
        handles.append(layer.register_forward_hook(FusionHook(fusion, name)))
    return handles
