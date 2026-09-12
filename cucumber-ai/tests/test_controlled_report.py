# -*- coding: utf-8 -*-
"""受控生成迁移版测试：论文口径部件（12 项校验/骨架/三级检索）+ 流水线行为。

全部确定性路径，不调用真实 LLM API。
"""
import json
import os

os.environ.setdefault("LLM_PROVIDER", "mock")

import pytest

from app.schemas import Detection, DiagnoseRequest
from app.services import prompts, report, skeleton, validators
from app.services.knowledge_store import K_STORE


def _det(label="霜霉病", conf=0.93, x1=10.0):
    return Detection(x1=x1, y1=10.0, x2=x1 + 100, y2=120.0, confidence=conf, label=label)


def _request(labels_confs=(("霜霉病", 0.93),)):
    return DiagnoseRequest(detections=[_det(l, c) for l, c in labels_confs], symptoms=[])


def _skeleton_for(cls="Downy_Mildew", conf=0.93, low=False, conflict=False):
    ev = {
        "image_id": "t-0001",
        "suspected_disease_class": cls,
        "prediction_confidence": conf,
        "detection_count": 1,
        "regions": [{"region_id": "t-0001_region_0", "class_id": 1,
                     "class_name": cls, "confidence": conf, "bbox_xyxy": [1, 2, 3, 4]}],
        "low_confidence_flag": low,
        "class_conflict_flag": conflict,
    }
    entry, _, _ = K_STORE.lookup(cls)
    return skeleton.build_skeleton(ev, entry or {}), entry


# ── 知识检索（论文 tools/knowledge_lookup 口径）──
@pytest.mark.parametrize("cls", ["Fresh_Leaf", "Anthracnose", "Downy_Mildew",
                                 "Gummy_Stem_Blight", "Powdery_Mildew"])
def test_lookup_exact_all_classes(cls):
    entry, sids, method = K_STORE.lookup(cls)
    assert entry is not None and method == "exact" and sids


def test_lookup_miss():
    entry, sids, method = K_STORE.lookup("Not_A_Disease")
    assert entry is None and sids == [] and method == "miss"


def test_all_source_ids_count_28():
    assert len(K_STORE.all_source_ids()) == 28


# ── 骨架（确定性模板口径）──
def test_skeleton_fields_and_fresh_leaf_no_chemical():
    sk, _ = _skeleton_for(cls="Fresh_Leaf")
    # name_cn 以知识库 healthy_leaf 条目为准（"健康叶片"，论文同名）
    assert sk["diagnosis_summary"].startswith("检测模型预测该叶片为健康叶片")
    assert not any(s.startswith("化学防治") for s in sk["management_suggestions"])
    for k in prompts.PROTECTED + prompts.EDITABLE:
        assert k in sk


def test_skeleton_low_confidence_note():
    sk, _ = _skeleton_for(conf=0.5, low=True)
    assert "低于 0.75" in sk["uncertainty_note"] and "建议人工复核" in sk["uncertainty_note"]


# ── 12 项校验（论文 validate_kimi_polish 口径）──
def _echo_polish(sk):
    return {**{k: sk[k] for k in prompts.PROTECTED},
            **{k: sk[k] for k in prompts.EDITABLE}}


def test_check_one_identical_passes():
    sk, _ = _skeleton_for()
    assert validators.check_one(sk, _echo_polish(sk), K_STORE.all_source_ids()) == []


def test_check_one_missing_field():
    sk, _ = _skeleton_for()
    pol = _echo_polish(sk)
    del pol["uncertainty_note"]
    assert "missing_field:uncertainty_note" in validators.check_one(sk, pol, K_STORE.all_source_ids())


def test_check_one_protected_changed():
    sk, _ = _skeleton_for()
    pol = _echo_polish(sk)
    pol["prediction_confidence"] = 0.9999
    assert "protected_field_changed:prediction_confidence" in validators.check_one(sk, pol, K_STORE.all_source_ids())


def test_check_one_unknown_source_id():
    sk, _ = _skeleton_for()
    pol = _echo_polish(sk)
    pol["source_ids"] = ["KB-XXX-999"]
    assert "unknown_source_id:KB-XXX-999" in validators.check_one(sk, pol, K_STORE.all_source_ids())


def test_check_one_unsupported_segment():
    sk, _ = _skeleton_for()
    pol = _echo_polish(sk)
    # 与骨架无任何 3-gram 重合的编造句（"该叶片"等共用三元组会误判为支撑）
    pol["diagnosis_summary"] = "建议立即焚烧并深埋全部植株处理"
    errs = validators.check_one(sk, pol, K_STORE.all_source_ids())
    assert any(e.startswith("unsupported_segment:") for e in errs)


def test_check_one_markdown_wrapper():
    sk, _ = _skeleton_for()
    pol = _echo_polish(sk)
    pol["knowledge_explanation"] = "```json\n" + pol["knowledge_explanation"]
    assert "markdown_wrapper_found" in validators.check_one(sk, pol, K_STORE.all_source_ids())


def test_check_one_fresh_leaf_chemical():
    sk, _ = _skeleton_for(cls="Fresh_Leaf")
    pol = _echo_polish(sk)
    pol["management_suggestions"] = sk["management_suggestions"] + ["化学防治：喷施农药喷雾"]
    errs = validators.check_one(sk, pol, K_STORE.all_source_ids())
    assert any(e.startswith("fresh_leaf_disease_control:") for e in errs)


def test_check_one_low_confidence_note_missing():
    sk, _ = _skeleton_for(conf=0.5, low=True)
    pol = _echo_polish(sk)
    pol["uncertainty_note"] = ""
    assert "low_confidence_note_missing" in validators.check_one(sk, pol, K_STORE.all_source_ids())


def test_check_one_visual_overclaim():
    sk, _ = _skeleton_for()
    pol = _echo_polish(sk)
    pol["diagnosis_summary"] = "图中可见明显病斑扩展。"
    assert "visual_overclaim_in_summary" in validators.check_one(sk, pol, K_STORE.all_source_ids())


# ── 流水线（mock provider 全确定性）──
def test_pipeline_mock_polished_pass():
    rep = report.generate_report(_request())
    assert rep.report_status == "polished"
    assert rep.disease_type == "黄瓜霜霉病"
    assert rep.basis and rep.source_ids
    assert set(rep.source_ids).issubset(K_STORE.all_source_ids())


def test_pipeline_low_confidence_note():
    rep = report.generate_report(_request((("霜霉病", 0.5),)))
    assert rep.confidence == 0.5
    assert rep.uncertainty_note and "低于 0.75" in rep.uncertainty_note
    assert any("人工复核" in s for s in rep.safety)


def test_pipeline_class_conflict_note():
    rep = report.generate_report(_request((("霜霉病", 0.9), ("白粉病", 0.6))))
    assert rep.uncertainty_note and "冲突" in rep.uncertainty_note


def test_pipeline_empty_detections_fresh_leaf():
    rep = report.generate_report(DiagnoseRequest(detections=[], symptoms=[]))
    assert rep.disease_type == "健康叶片"  # name_cn 以知识库条目为准
    assert rep.uncertainty_note  # 空检测 -> 低置信


class _BrokenProvider:
    def polish(self, task, correction_errors=None):
        raise RuntimeError("simulated llm outage")


class _GarbageThenEchoProvider:
    def __init__(self):
        self.calls = 0

    def polish(self, task, correction_errors=None):
        self.calls += 1
        if self.calls == 1:
            return "这不是 JSON"
        return json.dumps({**task["protected_fields"], **task["editable_fields"]},
                          ensure_ascii=False)


def test_pipeline_fallback_on_llm_outage(monkeypatch):
    monkeypatch.setattr("app.services.report.llm.get_provider", lambda: _BrokenProvider())
    rep = report.generate_report(_request())
    assert rep.report_status == "fallback_to_skeleton"
    assert rep.basis and rep.source_ids  # 骨架本身必然合规


def test_pipeline_repairs_once_on_garbage(monkeypatch):
    provider = _GarbageThenEchoProvider()
    monkeypatch.setattr("app.services.report.llm.get_provider", lambda: provider)
    rep = report.generate_report(_request())
    assert rep.report_status == "polished"
    assert provider.calls == 2  # 首润失败 -> 仅 1 次纠错重润
