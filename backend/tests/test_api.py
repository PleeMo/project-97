"""
API tests run through FastAPI's TestClient — no live server required.

    python -m pytest

Each run starts from an empty, isolated test database (see conftest.py), so
the demo database is never touched.
"""

# ---------------------------------------------------------------- helpers
def hdr(token):
    return {"Authorization": f"Bearer {token}"}


GOOD = {"ph": 3.6, "brix": 12.5, "microbial_cfu": 15, "temperature_c": 4.0}
BAD = {"ph": 5.9, "brix": 3.0, "microbial_cfu": 900, "temperature_c": 15.0}


# ---------------------------------------------------------------- auth
class TestAuth:
    def test_health(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

    def test_login_success(self, client):
        email = "login-ok@example.com"
        client.post("/auth/register", json={"name": "Login Test", "email": email,
                                            "password": "pw-12345", "role": "retailer"})
        res = client.post("/auth/login", json={"email": email, "password": "pw-12345"})
        assert res.status_code == 200
        assert res.json()["user"]["role"] == "retailer"
        assert res.json()["access_token"]

    def test_login_wrong_password(self, client):
        res = client.post("/auth/login", json={"email": "login-ok@example.com",
                                               "password": "wrong"})
        assert res.status_code == 401

    def test_me_requires_token(self, client):
        assert client.get("/auth/me").status_code == 401

    def test_register_duplicate_email(self, client, users):
        # login-ok@example.com was registered by test_login_success above
        payload = {"name": "Dup", "email": "login-ok@example.com",
                   "password": "x-password", "role": "retailer"}
        res = client.post("/auth/register", json=payload)
        assert res.status_code == 400


# ---------------------------------------------------------------- suppliers
class TestSuppliers:
    def test_supplier_and_material_flow(self, client, users):
        res = client.post("/suppliers", json={"name": "Pytest Orchards",
                                              "location": "Testville"},
                          headers=hdr(users["admin"]))
        assert res.status_code == 200
        supplier_id = res.json()["id"]

        res = client.post("/suppliers/raw-materials",
                          json={"supplier_id": supplier_id, "material_type": "Apples",
                                "quantity_kg": 42},
                          headers=hdr(users["producer"]))
        assert res.status_code == 200
        material_id = res.json()["id"]

        materials = client.get("/suppliers/raw-materials").json()
        match = [m for m in materials if m["id"] == material_id][0]
        assert match["supplier"]["name"] == "Pytest Orchards"  # nested supplier

    def test_material_creation_forbidden_for_retailer(self, client, users):
        suppliers = client.get("/suppliers").json()
        res = client.post("/suppliers/raw-materials",
                          json={"supplier_id": suppliers[0]["id"], "material_type": "X"},
                          headers=hdr(users["retailer"]))
        assert res.status_code == 403


# ---------------------------------------------------------------- batches
class TestBatches:
    def test_create_batch_returns_code(self, batch):
        assert batch["batch_code"].startswith("BQ-")
        assert batch["status"] == "in_production"

    def test_batch_detail_structure(self, client, users, batch):
        res = client.get(f"/batches/{batch['id']}", headers=hdr(users["producer"]))
        assert res.status_code == 200
        data = res.json()
        assert data["quality_tests"] == []
        # creating a batch logs a "produced" event automatically
        assert [e["event_type"] for e in data["events"]] == ["produced"]

    def test_batch_links_to_raw_material_and_supplier(self, client, users, batch):
        sid = client.post("/suppliers", json={"name": "Lineage Co"},
                          headers=hdr(users["admin"])).json()["id"]
        mid = client.post("/suppliers/raw-materials",
                          json={"supplier_id": sid, "material_type": "Mango"},
                          headers=hdr(users["producer"])).json()["id"]
        created = client.post("/batches", json={"product_name": "Mango Juice",
                                                "raw_material_id": mid},
                              headers=hdr(users["producer"])).json()
        data = client.get(f"/batches/{created['id']}").json()
        assert data["raw_material"]["material_type"] == "Mango"
        assert data["raw_material"]["supplier"]["name"] == "Lineage Co"

    def test_create_forbidden_for_retailer(self, client, users):
        res = client.post("/batches", json={"product_name": "Nope"},
                          headers=hdr(users["retailer"]))
        assert res.status_code == 403

    def test_invalid_token_rejected(self, client):
        res = client.post("/batches", json={"product_name": "Nope"},
                          headers=hdr("not-a-real-token"))
        assert res.status_code == 401

    def test_missing_batch_404(self, client):
        assert client.get("/batches/does-not-exist").status_code == 404


# ---------------------------------------------------------------- quality + ML
class TestQuality:
    def test_passing_test_scores_pass(self, client, users, batch):
        res = client.post("/quality-tests", json={"batch_id": batch["id"], **GOOD},
                          headers=hdr(users["producer"]))
        assert res.status_code == 200
        body = res.json()
        assert body["result"] == "pass"
        assert 0 <= body["risk_score"] <= 100

        detail = client.get(f"/batches/{batch['id']}").json()
        assert detail["status"] == "passed_qc"

    def test_failing_test_scores_fail(self, client, users, batch):
        res = client.post("/quality-tests", json={"batch_id": batch["id"], **BAD},
                          headers=hdr(users["producer"]))
        assert res.json()["result"] == "fail"
        detail = client.get(f"/batches/{batch['id']}").json()
        assert detail["status"] == "failed_qc"

    def test_predict_requires_auth(self, client):
        res = client.post("/quality-tests/predict?ph=3.5")
        assert res.status_code == 401

    def test_model_info_exposes_metrics(self, client, users):
        res = client.get("/quality-tests/model-info", headers=hdr(users["producer"]))
        assert res.status_code == 200
        info = res.json()
        assert info["source"] == "ml"
        assert info["holdout"]["accuracy"] > 0.8
        assert info["cross_validation"]["folds"] == 5
        assert len(info["feature_importances"]) == 4
        assert info["feature_importances"][0]["feature"] in \
            ("ph", "brix", "microbial_cfu", "temperature_c")

    def test_retrain_admin_only(self, client, users):
        assert client.post("/quality-tests/retrain",
                           headers=hdr(users["producer"])).status_code == 403
        res = client.post("/quality-tests/retrain", headers=hdr(users["admin"]))
        assert res.status_code == 200
        assert res.json()["holdout"]["accuracy"] > 0.8


# ---------------------------------------------------------------- certificates
class TestCertificates:
    def test_upload_download_roundtrip(self, client, users, batch):
        test = client.post("/quality-tests", json={"batch_id": batch["id"], **GOOD},
                           headers=hdr(users["producer"])).json()
        pdf = b"%PDF-1.4 pytest certificate"
        res = client.post(f"/quality-tests/{test['id']}/certificate",
                          files={"file": ("cert.pdf", pdf, "application/pdf")},
                          headers=hdr(users["producer"]))
        assert res.status_code == 200
        assert res.json()["filename"] == "cert.pdf"

        res = client.get(f"/quality-tests/{test['id']}/certificate",
                         headers=hdr(users["producer"]))
        assert res.status_code == 200
        assert res.content == pdf

        listing = client.get(f"/quality-tests/batch/{batch['id']}").json()
        assert listing[0]["certificate_filename"] == "cert.pdf"

    def test_rejects_unsupported_type(self, client, users, batch):
        test = client.post("/quality-tests", json={"batch_id": batch["id"], **GOOD},
                           headers=hdr(users["producer"])).json()
        res = client.post(f"/quality-tests/{test['id']}/certificate",
                          files={"file": ("evil.exe", b"MZ", "application/octet-stream")},
                          headers=hdr(users["producer"]))
        assert res.status_code == 400

    def test_missing_certificate_404(self, client, users, batch):
        test = client.post("/quality-tests", json={"batch_id": batch["id"], **GOOD},
                           headers=hdr(users["producer"])).json()
        res = client.get(f"/quality-tests/{test['id']}/certificate",
                         headers=hdr(users["producer"]))
        assert res.status_code == 404


# ---------------------------------------------------------------- lifecycle
class TestLifecycle:
    def _ship(self, client, token, batch_id, location="Hub"):
        return client.post("/supply-chain/events",
                           json={"batch_id": batch_id, "event_type": "shipped",
                                 "location": location},
                           headers=hdr(token))

    def test_cannot_ship_untested_batch(self, client, users, batch):
        res = self._ship(client, users["producer"], batch["id"])
        assert res.status_code == 409
        assert "passed_qc" in res.json()["detail"]

    def test_cannot_ship_failed_batch(self, client, users, batch):
        client.post("/quality-tests", json={"batch_id": batch["id"], **BAD},
                    headers=hdr(users["producer"]))
        assert self._ship(client, users["producer"], batch["id"]).status_code == 409

    def test_pass_then_ship_updates_status(self, client, users, batch):
        client.post("/quality-tests", json={"batch_id": batch["id"], **GOOD},
                    headers=hdr(users["producer"]))
        assert self._ship(client, users["producer"], batch["id"]).status_code == 200
        detail = client.get(f"/batches/{batch['id']}").json()
        assert detail["status"] == "in_transit"

    def test_retest_recovers_failed_batch(self, client, users, batch):
        client.post("/quality-tests", json={"batch_id": batch["id"], **BAD},
                    headers=hdr(users["producer"]))
        assert self._ship(client, users["producer"], batch["id"]).status_code == 409
        client.post("/quality-tests", json={"batch_id": batch["id"], **GOOD},
                    headers=hdr(users["producer"]))
        assert self._ship(client, users["producer"], batch["id"]).status_code == 200

    def test_recalled_batch_is_frozen(self, client, users, batch):
        client.post("/quality-tests", json={"batch_id": batch["id"], **GOOD},
                    headers=hdr(users["producer"]))
        self._ship(client, users["producer"], batch["id"])
        res = client.post("/recalls", json={"batch_id": batch["id"],
                                            "reason": "pytest recall"},
                          headers=hdr(users["admin"]))
        assert res.status_code == 200
        assert res.json()["affected_locations"]

        assert self._ship(client, users["producer"], batch["id"]).status_code == 409
        res = client.post("/quality-tests", json={"batch_id": batch["id"], **GOOD},
                          headers=hdr(users["producer"]))
        assert res.status_code == 409
        res = client.post("/recalls", json={"batch_id": batch["id"], "reason": "again"},
                          headers=hdr(users["admin"]))
        assert res.status_code == 409

    def test_system_events_cannot_be_logged_manually(self, client, users, batch):
        res = client.post("/supply-chain/events",
                          json={"batch_id": batch["id"], "event_type": "produced"},
                          headers=hdr(users["producer"]))
        assert res.status_code == 400


# ---------------------------------------------------------------- cold chain
class TestColdChain:
    def test_reading_then_stats(self, client, users, batch):
        res = client.post("/cold-chain/readings",
                          json={"batch_id": batch["id"], "temperature_c": 5.5,
                                "location": "Pytest Fridge", "device_id": "t-1"},
                          headers=hdr(users["producer"]))
        assert res.status_code == 200

        res = client.post(f"/cold-chain/simulate/{batch['id']}",
                          json={"hours": 12, "interval_minutes": 30,
                                "induce_breach": True},
                          headers=hdr(users["producer"]))
        assert res.status_code == 200
        stats = res.json()["stats"]
        assert stats["readings"] == 24 + 1   # 12h / 30min steps + the manual reading
        assert stats["breaches"] >= 1
        assert stats["safe_max_c"] == 8.0

    def test_cold_chain_forbidden_for_retailer(self, client, users, batch):
        res = client.post("/cold-chain/readings",
                          json={"batch_id": batch["id"], "temperature_c": 5},
                          headers=hdr(users["retailer"]))
        assert res.status_code == 403


# ---------------------------------------------------------------- verify + anti-counterfeit
class TestVerifyAndAntiCounterfeit:
    def test_unknown_code_reports_invalid(self, client):
        res = client.get("/verify/BQ-0000-00000?tz=UTC")
        assert res.status_code == 200
        body = res.json()
        assert body["valid"] is False
        assert "counterfeit" in body["message"].lower()

    def test_verify_flags_a_hot_code(self, client, users, batch):
        for tz in ["Africa/Kigali", "Africa/Kigali", "Asia/Shanghai",
                   "Europe/Madrid", "America/New_York", "Africa/Nairobi"]:
            res = client.get(f"/verify/{batch['batch_code']}?tz={tz}")
            assert res.status_code == 200
            assert res.json()["valid"] is True

        body = client.get(f"/verify/{batch['batch_code']}?tz=Asia/Shanghai").json()
        assert body["scan_count"] == 7
        assert body["alert"]           # consumer-facing warning

        analysis = client.get(f"/scans/batch/{batch['id']}",
                              headers=hdr(users["admin"])).json()
        assert analysis["total_scans"] == 7
        assert analysis["risk_level"] == "high"
        assert analysis["distinct_locations_24h"] == 5
        assert analysis["flags"]

    def test_scan_analysis_hidden_from_retailer(self, client, users, batch):
        res = client.get(f"/scans/batch/{batch['id']}", headers=hdr(users["retailer"]))
        assert res.status_code == 403


# ---------------------------------------------------------------- recalls
class TestRecalls:
    def test_recall_snapshots_downstream_locations(self, client, users, batch):
        client.post("/quality-tests", json={"batch_id": batch["id"], **GOOD},
                    headers=hdr(users["producer"]))
        client.post("/supply-chain/events",
                    json={"batch_id": batch["id"], "event_type": "shipped",
                          "location": "Kigali Hub"},
                    headers=hdr(users["distributor"]))
        res = client.post("/recalls", json={"batch_id": batch["id"],
                                            "reason": "cold chain failure"},
                          headers=hdr(users["admin"]))
        assert res.status_code == 200
        assert "Kigali Hub" in res.json()["affected_locations"]

        listing = client.get("/recalls").json()
        assert any(r["batch_id"] == batch["id"] for r in listing)

        detail = client.get(f"/batches/{batch['id']}").json()
        assert detail["status"] == "recalled"


# ---------------------------------------------------------------- CSV exports
class TestCsvExports:
    def test_batches_csv(self, client, users, batch):
        res = client.get("/export/batches.csv", headers=hdr(users["producer"]))
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/csv")
        assert "attachment" in res.headers.get("content-disposition", "")
        lines = res.text.splitlines()
        assert "batch_code" in lines[0]
        assert any(batch["batch_code"] in line for line in lines[1:])

    def test_all_exports_require_auth(self, client):
        for path in ("/export/batches.csv", "/export/quality-tests.csv",
                     "/export/scans.csv", "/export/temperatures.csv",
                     "/export/recalls.csv"):
            assert client.get(path).status_code == 401, path

    def test_every_dataset_exports(self, client, users, batch):
        client.get(f"/verify/{batch['batch_code']}?tz=UTC")  # creates a scan
        client.post("/cold-chain/readings",
                    json={"batch_id": batch["id"], "temperature_c": 12.5},
                    headers=hdr(users["producer"]))
        client.post("/quality-tests", json={"batch_id": batch["id"], **GOOD},
                    headers=hdr(users["producer"]))
        expected_header_token = {
            "/export/quality-tests.csv": "tested_at",
            "/export/scans.csv": "scanned_at",
            "/export/temperatures.csv": "temperature_c",
            "/export/recalls.csv": "reason",
        }
        for path, token in expected_header_token.items():
            res = client.get(path, headers=hdr(users["producer"]))
            assert res.status_code == 200, path
            assert token in res.text.splitlines()[0], path
        # the temperature export flags out-of-range readings
        res = client.get("/export/temperatures.csv", headers=hdr(users["producer"]))
        assert ",no," in res.text   # 12.5°C is outside the safe range


# ---------------------------------------------------------------- supplier scorecard
class TestSupplierStats:
    def test_stats_require_auth(self, client):
        assert client.get("/suppliers/stats").status_code == 401

    def test_scorecard_follows_the_lot_to_the_batch(self, client, users, batch):
        sid = client.post("/suppliers", json={"name": "Scorecard Farms"},
                          headers=hdr(users["admin"])).json()["id"]
        mid = client.post("/suppliers/raw-materials",
                          json={"supplier_id": sid, "material_type": "Pineapple",
                                "quantity_kg": 75},
                          headers=hdr(users["producer"])).json()["id"]
        linked = client.post("/batches", json={"product_name": "Pineapple Juice",
                                               "raw_material_id": mid},
                             headers=hdr(users["producer"])).json()
        client.post("/quality-tests", json={"batch_id": linked["id"], **GOOD},
                    headers=hdr(users["producer"]))
        client.post("/quality-tests", json={"batch_id": linked["id"], **BAD},
                    headers=hdr(users["producer"]))

        res = client.get("/suppliers/stats", headers=hdr(users["producer"]))
        assert res.status_code == 200
        row = [s for s in res.json() if s["supplier_id"] == sid][0]
        assert row["name"] == "Scorecard Farms"
        assert row["lots"] == 1
        assert row["total_quantity_kg"] == 75
        assert row["batches_linked"] == 1
        assert row["qc_tests"] == 2
        assert row["qc_pass_rate"] == 0.5
        assert 0 <= row["avg_risk_score"] <= 100
        assert row["recalls"] == 0

    def test_untested_supplier_reports_no_rate(self, client, users):
        client.post("/suppliers", json={"name": "Quiet Farms"},
                    headers=hdr(users["admin"]))
        res = client.get("/suppliers/stats", headers=hdr(users["producer"]))
        row = [s for s in res.json() if s["name"] == "Quiet Farms"][0]
        assert row["lots"] == 0
        assert row["qc_pass_rate"] is None
        assert row["avg_risk_score"] is None


# ---------------------------------------------------------------- batch timeline
class TestBatchTimeline:
    def test_timeline_requires_auth(self, client, batch):
        assert client.get(f"/batches/{batch['id']}/timeline").status_code == 401

    def test_timeline_404_for_unknown_batch(self, client, users):
        res = client.get("/batches/nope/timeline", headers=hdr(users["producer"]))
        assert res.status_code == 404

    def test_production_event_and_newest_first(self, client, users, batch):
        client.post("/quality-tests", json={"batch_id": batch["id"], **GOOD},
                    headers=hdr(users["producer"]))
        client.post("/supply-chain/events",
                    json={"batch_id": batch["id"], "event_type": "shipped",
                          "location": "Timeline Hub"},
                    headers=hdr(users["distributor"]))

        res = client.get(f"/batches/{batch['id']}/timeline",
                         headers=hdr(users["producer"]))
        assert res.status_code == 200
        body = res.json()
        kinds = [e["kind"] for e in body["entries"]]
        assert "production" in kinds
        assert "qc" in kinds
        assert "event" in kinds
        assert body["counts"]["total"] == len(body["entries"])
        ats = [e["at"] for e in body["entries"]]
        assert ats == sorted(ats, reverse=True)   # newest first
        assert any("Timeline Hub" in (e["detail"] or "") for e in body["entries"])

    def test_failed_qc_and_recall_are_critical(self, client, users, batch):
        client.post("/quality-tests", json={"batch_id": batch["id"], **BAD},
                    headers=hdr(users["producer"]))
        client.get(f"/verify/{batch['batch_code']}?tz=UTC")
        client.post("/cold-chain/readings",
                    json={"batch_id": batch["id"], "temperature_c": 11.5,
                          "location": "Timeline Fridge"},
                    headers=hdr(users["producer"]))
        client.post("/recalls", json={"batch_id": batch["id"],
                                      "reason": "timeline recall"},
                    headers=hdr(users["admin"]))

        body = client.get(f"/batches/{batch['id']}/timeline",
                          headers=hdr(users["producer"])).json()
        by_kind = {}
        for e in body["entries"]:
            by_kind.setdefault(e["kind"], []).append(e)
        assert by_kind["qc"][0]["severity"] == "critical"
        assert by_kind["qc"][0]["title"] == "QC test failed"
        assert by_kind["scan"][0]["kind"] == "scan"
        assert by_kind["breach"][0]["severity"] == "warning"
        assert "11.5" in by_kind["breach"][0]["title"]
        assert by_kind["recall"][0]["severity"] == "critical"
        assert "timeline recall" in by_kind["recall"][0]["detail"]
        # safe readings must not appear as breaches
        client.post("/cold-chain/readings",
                    json={"batch_id": batch["id"], "temperature_c": 4.0},
                    headers=hdr(users["producer"]))
        body = client.get(f"/batches/{batch['id']}/timeline",
                          headers=hdr(users["producer"])).json()
        assert body["counts"]["breach"] == 1


# ---------------------------------------------------------------- dashboard + alerts
class TestDashboard:
    def test_summary_shape(self, client, users):
        body = client.get("/dashboard/summary", headers=hdr(users["producer"])).json()
        for key in ("total_batches", "passed_qc", "failed_qc", "recalled",
                    "in_transit", "average_risk_score", "total_scans",
                    "flagged_batches", "cold_chain_breaches_24h",
                    "status_breakdown"):
            assert key in body

    def test_analytics_shape(self, client, users):
        body = client.get("/dashboard/analytics", headers=hdr(users["producer"])).json()
        assert len(body["days"]) == 14
        assert all(set(d) == {"date", "scans", "breaches", "avg_risk"} for d in body["days"])
        assert {b["bucket"] for b in body["risk_buckets"]} == \
            {"low", "moderate", "high", "untested"}

    def test_alerts_require_auth(self, client):
        assert client.get("/alerts").status_code == 401

    def test_alerts_shape_and_ordering(self, client, users):
        res = client.get("/alerts", headers=hdr(users["producer"]))
        assert res.status_code == 200
        alerts = res.json()
        assert alerts, "earlier tests should have produced at least one alert"
        for a in alerts:
            assert set(a) >= {"id", "type", "severity", "batch_id", "message", "created_at"}
            assert a["severity"] in ("critical", "warning", "info")
        rank = {"critical": 0, "warning": 1, "info": 2}
        assert [rank[a["severity"]] for a in alerts] == sorted(
            rank[a["severity"]] for a in alerts)


# ---------------------------------------------------------------- platform
class TestPlatform:
    """Cross-cutting polish: readiness probe, request ids, pagination, rate limit."""

    def test_health_is_a_full_readiness_probe(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ok"
        assert body["version"]
        assert body["database"] == "ok"
        assert body["model"] in ("ml", "untrained")
        assert body["uptime_seconds"] >= 0
        assert body["checked_at"].endswith("Z")

    def test_root_advertises_version_and_health(self, client):
        body = client.get("/").json()
        assert body["version"] and body["health"] == "/health"

    def test_responses_carry_a_request_id(self, client):
        res = client.get("/health")
        assert res.headers.get("X-Request-ID"), "middleware should add a request id"
        # a client-supplied id is echoed back for distributed tracing
        res = client.get("/health", headers={"X-Request-ID": "trace-abc-123"})
        assert res.headers["X-Request-ID"] == "trace-abc-123"

    def test_legacy_batch_list_is_still_a_plain_array(self, client, users):
        res = client.get("/batches", headers=hdr(users["producer"]))
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_paginated_batch_envelope(self, client, users):
        res = client.get("/batches?page=1&page_size=2", headers=hdr(users["producer"]))
        assert res.status_code == 200
        body = res.json()
        assert set(body) == {"items", "total", "page", "page_size", "pages"}
        assert len(body["items"]) <= 2
        assert body["total"] >= len(body["items"])
        assert body["pages"] >= 1
        assert isinstance(body["items"][0]["batch_code"], str)

    def test_batch_sorting_asc_and_desc(self, client, users):
        def codes(order):
            res = client.get(f"/batches?sort=batch_code&order={order}",
                             headers=hdr(users["producer"]))
            assert res.status_code == 200
            payload = res.json()
            rows = payload["items"] if isinstance(payload, dict) else payload
            return [b["batch_code"] for b in rows]

        asc, desc = codes("asc"), codes("desc")
        assert asc == sorted(asc)
        assert desc == sorted(desc, reverse=True)

    def test_unknown_sort_field_is_rejected(self, client, users):
        res = client.get("/batches?sort=password", headers=hdr(users["producer"]))
        assert res.status_code == 400
        assert "Cannot sort by" in res.json()["detail"]

    def test_invalid_page_is_rejected(self, client, users):
        res = client.get("/batches?page=0", headers=hdr(users["producer"]))
        assert res.status_code == 422

    def test_verify_endpoint_is_rate_limited(self, client):
        from app.main import VERIFY_RATE_LIMIT, _verify_hits

        _verify_hits.clear()          # don't inherit hits from earlier tests
        try:
            for _ in range(VERIFY_RATE_LIMIT):
                res = client.get("/verify/BQ-RATE-LIMIT-00000?tz=UTC")
                assert res.status_code == 200
            res = client.get("/verify/BQ-RATE-LIMIT-00000?tz=UTC")
            assert res.status_code == 429
            assert res.headers.get("Retry-After")
            assert "Too many" in res.json()["detail"]
        finally:
            _verify_hits.clear()      # leave the limiter clean for later runs
