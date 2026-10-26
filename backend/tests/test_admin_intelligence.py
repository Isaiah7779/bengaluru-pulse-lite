import csv
import json

from api import admin as admin_api
from conftest import make_user


def test_intelligence_endpoints_require_admin(client, user_headers):
    for path in ("/v1/admin/intelligence/overview", "/v1/admin/intelligence/research/1d", "/v1/admin/intelligence/endpoints"):
        assert client.get(path).status_code == 401
        assert client.get(path, headers=user_headers).status_code == 403


def test_research_report_serves_generated_artifacts_without_hardcoded_metrics(client, admin_headers, tmp_path, monkeypatch):
    root = tmp_path / "v2"
    (root / "statistical").mkdir(parents=True)
    (root / "transformer").mkdir()
    (root / "ensemble" / "1d").mkdir(parents=True)
    (root / "statistical" / "summary.json").write_text(json.dumps({"source": "test artifact", "metric": 12.5, "dataset": str(tmp_path / "private" / "dataset.csv")}), encoding="utf-8")
    (root / "transformer" / "summary.json").write_text(json.dumps({"status": "evaluated"}), encoding="utf-8")
    (root / "ensemble" / "1d" / "summary.json").write_text(json.dumps({"horizons": {"1d": {"test_metrics": []}}}), encoding="utf-8")
    with (root / "ensemble" / "1d" / "test_predictions.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["target_time", "actual", "ridge_prediction"])
        writer.writeheader()
        writer.writerow({"target_time": "2024-01-01", "actual": 8, "ridge_prediction": 7})
    monkeypatch.setattr(admin_api, "RESEARCH_DIR", root)

    response = client.get("/v1/admin/intelligence/research/1d", headers=admin_headers)
    assert response.status_code == 200
    result = response.json()
    assert result["reports"]["statistical"]["metric"] == 12.5
    assert result["reports"]["statistical"]["dataset"] == "dataset.csv"
    assert result["predictions"] == [{"target_time": "2024-01-01", "actual": "8", "ridge_prediction": "7"}]
    assert result["prediction_count"] == 1
    assert result["prediction_total"] == 1 and result["predictions_truncated"] is False


def test_research_horizon_is_allowlisted(client, admin_headers):
    assert client.get("/v1/admin/intelligence/research/../secret", headers=admin_headers).status_code in (404, 422)
    assert client.get("/v1/admin/intelligence/research/3d", headers=admin_headers).status_code == 422


def test_overview_labels_runtime_and_request_instrumentation_honestly(client, admin_headers):
    response = client.get("/v1/admin/intelligence/overview", headers=admin_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["database_query"] == "ok"
    assert body["request_metrics"]["status"] == "not_instrumented"
    assert body["production_forecast_model"]["status"] == "none_active"
    assert body["collectors"]["flow"]["status"] in {"unknown", "not_configured", "fresh", "stale"}
    assert all("error" not in call for call in body["latest_provider_calls"])


def test_endpoint_inventory_comes_from_fastapi_routes(client, admin_headers):
    response = client.get("/v1/admin/intelligence/endpoints", headers=admin_headers)
    assert response.status_code == 200
    routes = response.json()["endpoints"]
    assert any(route["path"] == "/v1/admin/intelligence/endpoints" and route["method"] == "GET" for route in routes)
    assert any(route["path"].startswith("/v1/") for route in routes)
    assert any(route["path"] == "/health" for route in routes) is False
