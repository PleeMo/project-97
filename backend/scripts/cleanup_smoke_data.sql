-- Removes rows created by scripts/smoke_test.py so the demo DB stays pristine.
-- Safe to run repeatedly.  Usage:  python -c "import sqlite3; sqlite3.connect('traceability.db').executescript(open('scripts/cleanup_smoke_data.sql').read())"

CREATE TEMP TABLE _smoke_batches AS SELECT id FROM batches
    WHERE product_name LIKE 'Smoke Test Juice%' OR product_name = 'Lifecycle Test Juice';
DELETE FROM quality_tests          WHERE batch_id IN (SELECT id FROM _smoke_batches);
DELETE FROM supply_chain_events    WHERE batch_id IN (SELECT id FROM _smoke_batches);
DELETE FROM qr_scans               WHERE batch_id IN (SELECT id FROM _smoke_batches);
DELETE FROM temperature_readings   WHERE batch_id IN (SELECT id FROM _smoke_batches);
DELETE FROM qr_codes               WHERE batch_id IN (SELECT id FROM _smoke_batches);
DELETE FROM recall_logs            WHERE batch_id IN (SELECT id FROM _smoke_batches);
DELETE FROM batches                WHERE id IN (SELECT id FROM _smoke_batches);

CREATE TEMP TABLE _smoke_suppliers AS SELECT id FROM suppliers WHERE name = 'Smoke Supplies';
DELETE FROM raw_material_batches WHERE supplier_id IN (SELECT id FROM _smoke_suppliers);
DELETE FROM suppliers             WHERE id IN (SELECT id FROM _smoke_suppliers);

DELETE FROM users WHERE email LIKE 'smoke-%@demo.com';
DELETE FROM recall_logs WHERE reason = 'Smoke test recall';

-- Test runs (smoke + browser e2e) hit the public verify endpoint repeatedly,
-- which inflates scan counts and can falsely flag the "genuine" demo batch.
-- Drop everything that wasn't seeded and resync the QR counters.
DELETE FROM qr_scans WHERE ip_hash != 'seed';
UPDATE qr_codes SET scan_count = (
    SELECT COUNT(*) FROM qr_scans WHERE qr_scans.batch_id = qr_codes.batch_id
);
