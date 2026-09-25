#!/usr/bin/env python
"""
End-to-end smoke test for the TraceCert API (stdlib only).

Point it at a running server:
    uvicorn app.main:app --port 8000 &
    python scripts/smoke_test.py http://localhost:8000

Exits non-zero if any check fails, printing a pass/fail line per check.
"""
import json
import sys
import urllib.error
import urllib.request
import uuid

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
FAILURES = []
CHECKS = 0


def call(method, path, body=None, token=None, raw=False, data=None, content_type=None,
         out_headers=None):
    url = f"{BASE}{path}"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    payload = None
    if data is not None:
        payload = data
        if content_type:
            headers["Content-Type"] = content_type
    elif body is not None:
        payload = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as res:
            raw_body = res.read()
            status = res.status
            if out_headers is not None:
                out_headers.update(dict(res.headers))
    except urllib.error.HTTPError as e:
        raw_body = e.read()
        status = e.code
        if out_headers is not None:
            out_headers.update(dict(e.headers))

    if raw:
        return status, raw_body
    try:
        return status, json.loads(raw_body.decode() or "null")
    except Exception:
        return status, raw_body.decode(errors="replace")


def check(name, cond, detail=""):
    global CHECKS
    CHECKS += 1
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


def login(email):
    status, body = call("POST", "/auth/login", {"email": email, "password": "password123"})
    assert status == 200, f"login failed for {email}: {body}"
    return body["access_token"], body["user"]


def main():
    # --- health / root ---
    status, body = call("GET", "/health")
    check("GET /health", status == 200 and body.get("status") == "ok")
    check("GET /health readiness fields (version/db/model/uptime)",
          bool(body.get("version")) and body.get("database") == "ok"
          and body.get("model") in ("ml", "untrained")
          and isinstance(body.get("uptime_seconds"), int),
          detail=str(body))

    rid_headers = {}
    call("GET", "/health", out_headers=rid_headers)
    check("responses carry X-Request-ID",
          any(k.lower() == "x-request-id" for k in rid_headers),
          detail=str(list(rid_headers)))

    # --- auth ---
    admin_token, admin = login("admin@demo.com")
    prod_token, producer = login("producer@demo.com")
    check("login (admin/producer)", bool(admin_token and prod_token))

    status, body = call("GET", "/auth/me", token=prod_token)
    check("GET /auth/me", status == 200 and body["role"] == "producer")

    fake = f"smoke-{uuid.uuid4().hex[:8]}@demo.com"
    status, body = call("POST", "/auth/register",
                        {"name": "Smoke Test", "email": fake,
                         "password": "password123", "role": "retailer"})
    check("POST /auth/register (new user)", status == 200 and "access_token" in body)

    status, body = call("POST", "/auth/login", {"email": "nope@demo.com", "password": "x"})
    check("POST /auth/login rejects bad creds", status == 401)

    # --- suppliers / raw materials ---
    status, body = call("POST", "/suppliers",
                        {"name": "Smoke Supplies", "location": "Testville"},
                        token=admin_token)
    check("POST /suppliers", status == 200 and body.get("id"))
    supplier_id = body.get("id")

    status, body = call("POST", "/suppliers/raw-materials",
                        {"supplier_id": supplier_id, "material_type": "Test Apples",
                         "quantity_kg": 10},
                        token=admin_token)
    check("POST /suppliers/raw-materials", status == 200 and body.get("id"))
    raw_material_id = body.get("id")

    status, body = call("GET", "/suppliers")
    check("GET /suppliers", status == 200 and isinstance(body, list) and len(body) >= 1)

    # --- batches ---
    status, body = call("POST", "/batches",
                        {"product_name": "Smoke Test Juice 1L",
                         "raw_material_id": raw_material_id,
                         "volume_liters": 100},
                        token=prod_token)
    check("POST /batches", status == 200 and body.get("batch_code", "").startswith("BQ-"))
    batch = body
    batch_id, batch_code = batch["id"], batch["batch_code"]

    # second batch used to exercise the lifecycle rules
    status, body = call("POST", "/batches", {"product_name": "Lifecycle Test Juice"},
                        token=prod_token)
    check("POST /batches (lifecycle subject)", status == 200 and body.get("id"))
    lifecycle_batch = body

    status, body = call("GET", "/batches")
    check("GET /batches", status == 200 and len(body) >= 5)

    status, body = call("GET", "/batches?page=1&page_size=2")
    check("GET /batches paginated envelope",
          status == 200 and isinstance(body, dict)
          and set(body) == {"items", "total", "page", "page_size", "pages"}
          and len(body["items"]) <= 2,
          detail=str(body))

    status, body = call("GET", "/batches?sort=not_a_column")
    check("GET /batches rejects unknown sort field (400)", status == 400,
          detail=str(body))

    status, body = call("GET", f"/batches/{batch_id}")
    check("GET /batches/{id} detail", status == 200 and "quality_tests" in body)

    status, body = call("POST", "/batches",
                        {"product_name": "Should Fail"}, token="invalid-token")
    check("POST /batches rejects bad token", status == 401)

    # --- quality tests + ML ---
    status, body = call("POST", "/quality-tests",
                        {"batch_id": batch_id, "ph": 3.5, "brix": 12.0,
                         "microbial_cfu": 20, "temperature_c": 4.0},
                        token=prod_token)
    check("POST /quality-tests (good readings)", status == 200 and body.get("result") == "pass")
    good_test = body

    status, body = call("POST", "/quality-tests",
                        {"batch_id": lifecycle_batch["id"], "ph": 5.9, "brix": 3.0,
                         "microbial_cfu": 900, "temperature_c": 15.0},
                        token=prod_token)
    check("POST /quality-tests (bad readings)", status == 200 and body.get("result") == "fail")
    bad_test = body

    # --- lifecycle rules ---
    status, body = call("POST", "/supply-chain/events",
                        {"batch_id": lifecycle_batch["id"], "event_type": "shipped",
                         "location": "Should Not Ship Hub"},
                        token=prod_token)
    check("lifecycle: shipping a QC-failed batch is blocked (409)", status == 409,
          detail=f"status={status} body={body}")

    status, body = call("POST", "/quality-tests",
                        {"batch_id": lifecycle_batch["id"], "ph": 3.6, "brix": 12.0,
                         "microbial_cfu": 12, "temperature_c": 4.0},
                        token=prod_token)
    check("lifecycle: passing re-test recovers the batch", status == 200 and body.get("result") == "pass")

    status, body = call("POST", "/supply-chain/events",
                        {"batch_id": lifecycle_batch["id"], "event_type": "shipped",
                         "location": "Now Shipping Hub"},
                        token=prod_token)
    check("lifecycle: recovered batch can ship", status == 200, detail=str(body))

    status, body = call("GET", f"/quality-tests/batch/{batch_id}")
    check("GET /quality-tests/batch/{id}", status == 200 and len(body) == 1,
          detail=f"status={status} n={len(body) if isinstance(body, list) else body}")

    status, body = call("POST", "/quality-tests/predict?ph=6.0&microbial_cfu=500",
                        token=prod_token)
    check("POST /quality-tests/predict (what-if)", status == 200 and "risk_score" in body,
          detail=f"status={status} body={body}")

    status, body = call("GET", "/quality-tests/model-info", token=prod_token)
    check("GET /quality-tests/model-info",
          status == 200 and body.get("source") == "ml"
          and body.get("holdout", {}).get("accuracy", 0) > 0.8
          and bool(body.get("feature_importances")),
          detail=str(body))

    status, body = call("POST", "/quality-tests/retrain", token=prod_token)
    check("POST /quality-tests/retrain denied for non-admin", status == 403,
          detail=f"status={status} body={body}")

    status, body = call("POST", "/quality-tests/retrain", token=admin_token)
    check("POST /quality-tests/retrain (admin)",
          status == 200 and body.get("holdout", {}).get("accuracy", 0) > 0.8,
          detail=str(body))

    # --- certificates (multipart upload + download) ---
    pdf = ("%PDF-1.4\n1 0 obj<< /Type /Catalog >>endobj\ntrailer<< /Root 1 0 R >>\n%%EOF").encode()
    boundary = "----smoke" + uuid.uuid4().hex
    multipart = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="qc-certificate.pdf"\r\n'
        f"Content-Type: application/pdf\r\n\r\n"
    ).encode() + pdf + f"\r\n--{boundary}--\r\n".encode()

    status, body = call("POST", f"/quality-tests/{good_test['id']}/certificate",
                        data=multipart,
                        content_type=f"multipart/form-data; boundary={boundary}",
                        token=prod_token)
    check("POST certificate (multipart upload)", status == 200 and body.get("filename"),
          detail=f"status={status} body={body}")

    status, raw = call("GET", f"/quality-tests/{good_test['id']}/certificate",
                       token=prod_token, raw=True)
    check("GET certificate (download)", status == 200 and raw.startswith(b"%PDF"),
          detail=f"status={status} bytes={raw[:40]!r}")

    status, body = call("GET", f"/quality-tests/batch/{batch_id}")
    check("certificate filename exposed in test listing",
          status == 200 and any(t.get("certificate_filename") for t in body),
          detail=str(body)[:200])

    # --- supply chain ---
    status, body = call("POST", "/supply-chain/events",
                        {"batch_id": batch_id, "event_type": "shipped",
                         "location": "Smoke Logistics Hub"},
                        token=prod_token)
    check("POST /supply-chain/events", status == 200 and body["event_type"] == "shipped")

    status, body = call("GET", f"/supply-chain/events/batch/{batch_id}")
    check("GET /supply-chain/events/batch/{id}", status == 200 and len(body) >= 2)

    # --- QR ---
    status, body = call("GET", f"/qr/{batch_id}")
    check("GET /qr/{id}", status == 200 and body.get("image_base64", "").startswith("data:image/png"))

    # --- cold chain ---
    status, body = call("POST", "/cold-chain/readings",
                        {"batch_id": batch_id, "temperature_c": 4.2,
                         "location": "Smoke Fridge", "device_id": "t-1"},
                        token=prod_token)
    check("POST /cold-chain/readings", status == 200 and body["temperature_c"] == 4.2)

    status, body = call("POST", f"/cold-chain/simulate/{batch_id}",
                        {"hours": 12, "interval_minutes": 30, "induce_breach": True},
                        token=prod_token)
    check("POST /cold-chain/simulate", status == 200 and body["stats"]["readings"] >= 10,
          detail=str(body)[:200])

    status, body = call("GET", f"/cold-chain/batch/{batch_id}", token=prod_token)
    stats = body.get("stats", {})
    check("GET /cold-chain/batch/{id}", status == 200 and stats.get("breaches", 0) >= 1,
          detail=str(stats))

    # --- public verification + scan telemetry ---
    status, body = call("GET", f"/verify/{batch_code}?tz=Africa/Kigali")
    check("GET /verify/{code} (public, valid)", status == 200 and body.get("valid") is True)
    status, body = call("GET", "/verify/DOES-NOT-EXIST-123")
    check("GET /verify/{code} (public, unknown)", status == 200 and body.get("valid") is False)

    # --- anti-counterfeit analysis ---
    status, body = call("GET", f"/scans/batch/{batch_id}", token=admin_token)
    check("GET /scans/batch/{id}", status == 200 and "risk_level" in body, detail=str(body)[:200])

    # Flagged seeded batch: cloned-code demo must come back high risk
    status, batches = call("GET", "/batches")
    seeded = [b for b in batches if b["product_name"] == "Passion Fruit Juice 500ml"]
    if seeded:
        status, body = call("GET", f"/scans/batch/{seeded[0]['id']}", token=admin_token)
        check("seeded cloned-code batch is flagged high risk",
              status == 200 and body.get("risk_level") == "high" and body.get("scans_24h", 0) >= 5,
              detail=str(body)[:300])
        status, body = call("GET", f"/verify/{seeded[0]['batch_code']}?tz=Asia/Shanghai")
        check("verify response carries anti-counterfeit alert",
              status == 200 and bool(body.get("alert")), detail=str(body)[:300])

    # --- recalls ---
    status, body = call("POST", "/recalls",
                        {"batch_id": batch_id, "reason": "Smoke test recall"},
                        token=admin_token)
    check("POST /recalls", status == 200 and "affected_locations" in body)
    status, body = call("GET", "/recalls")
    check("GET /recalls", status == 200 and len(body) >= 1)

    status, body = call("POST", "/recalls",
                        {"batch_id": batch_id, "reason": "second recall"},
                        token=admin_token)
    check("lifecycle: double recall blocked (409)", status == 409,
          detail=f"status={status} body={body}")

    status, body = call("POST", "/supply-chain/events",
                        {"batch_id": batch_id, "event_type": "shipped",
                         "location": "Nowhere"},
                        token=prod_token)
    check("lifecycle: movement blocked after recall (409)", status == 409,
          detail=f"status={status} body={body}")

    status, body = call("POST", "/quality-tests",
                        {"batch_id": batch_id, "ph": 3.6, "brix": 12.0,
                         "microbial_cfu": 10, "temperature_c": 4.0},
                        token=prod_token)
    check("lifecycle: QC blocked after recall (409)", status == 409,
          detail=f"status={status} body={body}")

    # --- alerts feed ---
    status, body = call("GET", "/alerts", token=prod_token)
    alert_types = {a["type"] for a in body} if status == 200 else set()
    check("GET /alerts", status == 200 and isinstance(body, list) and len(body) >= 2,
          detail=f"status={status} body={str(body)[:200]}")
    check("alerts flag the seeded cloned QR code", "counterfeit" in alert_types,
          detail=str(alert_types))
    check("alerts include the QC-failed seeded batch", "qc_failed" in alert_types,
          detail=str(alert_types))
    check("alerts include our recall",
          any(a["type"] == "recalled" and a["batch_id"] == batch_id for a in body))
    check("alerts sorted critical-first",
          [a["severity"] for a in body] == sorted(
              [a["severity"] for a in body],
              key=lambda s: {"critical": 0, "warning": 1, "info": 2}[s]))

    # --- analytics ---
    status, body = call("GET", "/dashboard/analytics", token=prod_token)
    check("GET /dashboard/analytics (14-day series + risk buckets)",
          status == 200 and len(body.get("days", [])) == 14
          and len(body.get("risk_buckets", [])) == 4,
          detail=f"status={status} body={str(body)[:200]}")

    # --- dashboard ---
    status, body = call("GET", "/dashboard/summary", token=prod_token)
    check("GET /dashboard/summary", status == 200
          and body.get("total_batches", 0) >= 5
          and "total_scans" in body
          and "flagged_batches" in body
          and "cold_chain_breaches_24h" in body,
          detail=str(body)[:300])

    # --- CSV exports ---
    status, raw = call("GET", "/export/batches.csv")
    check("CSV export requires auth (401)", status == 401, detail=f"status={status}")

    for path, marker in [("/export/batches.csv", "batch_code"),
                         ("/export/quality-tests.csv", "tested_at"),
                         ("/export/scans.csv", "scanned_at"),
                         ("/export/temperatures.csv", "temperature_c"),
                         ("/export/recalls.csv", "reason")]:
        resp_headers = {}
        status, raw = call("GET", path, token=prod_token, raw=True,
                           out_headers=resp_headers)
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
        header = text.splitlines()[0] if text else ""
        disposition = next((v for k, v in resp_headers.items()
                             if k.lower() == "content-disposition"), "")
        check(f"GET {path}",
              status == 200 and marker in header and "attachment" in disposition,
              detail=f"status={status} header={header[:120]} disposition={disposition}")
        if path == "/export/batches.csv":
            check("batches.csv contains our batch code", batch_code in text,
                  detail=text[:200])
        if path == "/export/temperatures.csv":
            check("temperatures.csv flags a breach", ",no," in text,
                  detail=text[:200])

    # --- supplier scorecard ---
    status, body = call("GET", "/suppliers/stats", token=prod_token)
    smoke_row = next((s for s in body if s.get("name") == "Smoke Supplies"), None) if status == 200 else None
    check("GET /suppliers/stats", status == 200 and isinstance(body, list) and smoke_row is not None,
          detail=f"status={status} body={str(body)[:300]}")
    check("supplier scorecard counts our lot",
          bool(smoke_row) and smoke_row["lots"] >= 1,
          detail=str(smoke_row))
    musanze = next((s for s in body if s.get("name", "").startswith("Musanze")), None) if status == 200 else None
    check("seeded supplier reports QC pass rate",
          bool(musanze) and musanze["batches_linked"] >= 4
          and musanze["qc_pass_rate"] is not None,
          detail=str(musanze))

    # --- batch timeline ---
    status, body = call("GET", f"/batches/{batch_id}/timeline", token=prod_token)
    entries = body.get("entries", []) if isinstance(body, dict) else []
    kinds = {e["kind"] for e in entries}
    check("GET /batches/{id}/timeline", status == 200 and len(entries) >= 4,
          detail=f"status={status} body={str(body)[:300]}")
    check("timeline covers production + QC + breach + recall",
          {"production", "qc", "breach", "recall"} <= kinds,
          detail=str(kinds))
    ats = [e["at"] for e in entries]
    check("timeline is newest-first", ats == sorted(ats, reverse=True),
          detail=str(ats[:3]))
    check("timeline counts match entries",
          body.get("counts", {}).get("total") == len(entries),
          detail=str(body.get("counts")))
    recall_entries = [e for e in entries if e["kind"] == "recall"]
    check("timeline recall entry is critical",
          bool(recall_entries) and recall_entries[0]["severity"] == "critical"
          and "Smoke test recall" in (recall_entries[0]["detail"] or ""),
          detail=str(recall_entries))
    status, _ = call("GET", f"/batches/{batch_id}/timeline")
    check("timeline requires auth (401)", status == 401, detail=f"status={status}")

    print(f"\n{CHECKS - len(FAILURES)}/{CHECKS} checks passed")
    if FAILURES:
        print("Failed: " + "; ".join(FAILURES))
        sys.exit(1)


if __name__ == "__main__":
    main()
