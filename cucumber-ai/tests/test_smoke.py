import os

os.environ.setdefault("LLM_PROVIDER", "mock")

from fastapi.testclient import TestClient

from app.main import app
from app.services.retriever import load_knowledge

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "UP"


def test_diagnose_mock_returns_valid_report():
    payload = {
        "detections": [
            {"x1": 120.0, "y1": 85.0, "x2": 260.0, "y2": 210.0,
             "confidence": 0.87, "label": "霜霉病"}
        ],
        "symptoms": ["多角形病斑"],
    }
    response = client.post("/api/v1/diagnose", json=payload)
    assert response.status_code == 200
    data = response.json()
    for field in ("disease_type", "confidence", "basis", "agronomy",
                  "chemical", "safety", "source_ids"):
        assert field in data, f"报告缺少字段 {field}"
    valid_ids = {entry["source_id"] for entry in load_knowledge()}
    assert set(data["source_ids"]).issubset(valid_ids), "source_id 必须在知识库内"
