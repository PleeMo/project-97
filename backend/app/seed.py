"""
Seeds the database with demo users, suppliers, raw materials, batches
(some passing, one failing, one recalled) with quality tests, supply chain
events, cold-chain readings, QR scan telemetry and a demo lab certificate —
so every screen in the frontend has something to show immediately.

Run:  python -m app.seed
"""
import base64
from datetime import datetime, timedelta

from app.database import SessionLocal, Base, engine
from app import models, auth
from app.ml.predict import risk_score
from app.routers.batches import generate_batch_code
from app.routers.cold_chain import generate_readings

Base.metadata.create_all(bind=engine)


def _demo_pdf(lines):
    """Minimal but valid single-page PDF — stands in for a scanned lab
    certificate so the UI has something real to open."""
    def esc(s):
        return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    content = "BT /F1 14 Tf 60 740 Td 20 TL\n"
    for line in lines:
        content += f"({esc(line)}) Tj T*\n"
    content += "ET"
    stream = content.encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF").encode()
    return bytes(out)


def run():
    db = SessionLocal()
    try:
        if db.query(models.User).first():
            print("Database already has data — skipping seed. Delete traceability.db to reseed.")
            return

        # --- Users ---
        admin = models.User(name="Amina Uwase", email="admin@demo.com",
                             hashed_password=auth.hash_password("password123"),
                             role=models.RoleEnum.admin, organization="HQ")
        producer = models.User(name="Jean Producer", email="producer@demo.com",
                                hashed_password=auth.hash_password("password123"),
                                role=models.RoleEnum.producer, organization="Kivu Juice Factory")
        distributor = models.User(name="Eric Distributor", email="distributor@demo.com",
                                   hashed_password=auth.hash_password("password123"),
                                   role=models.RoleEnum.distributor, organization="Rwanda Logistics Co")
        retailer = models.User(name="Grace Retailer", email="retailer@demo.com",
                                hashed_password=auth.hash_password("password123"),
                                role=models.RoleEnum.retailer, organization="Kigali FreshMart")
        db.add_all([admin, producer, distributor, retailer])
        db.commit()

        # --- Supplier + raw material ---
        supplier = models.Supplier(name="Musanze Orchards Co-op", location="Musanze, Rwanda", contact="+250700000000")
        db.add(supplier)
        db.commit()

        raw_material = models.RawMaterialBatch(
            supplier_id=supplier.id, material_type="Passion Fruit", quantity_kg=500,
        )
        db.add(raw_material)
        db.commit()

        def make_batch(product_name, days_ago, volume, ph, brix, microbial_cfu, temperature_c, journey):
            batch = models.Batch(
                batch_code=generate_batch_code(db),
                product_name=product_name,
                raw_material_id=raw_material.id,
                production_date=models.utcnow() - timedelta(days=days_ago),
                expiry_date=models.utcnow() + timedelta(days=90 - days_ago),
                volume_liters=volume,
                created_by=producer.id,
            )
            db.add(batch)
            db.commit()
            db.refresh(batch)

            db.add(models.QRCode(batch_id=batch.id, code_value=batch.batch_code))

            scored = risk_score(ph=ph, brix=brix, microbial_cfu=microbial_cfu, temperature_c=temperature_c)
            test = models.QualityTest(
                batch_id=batch.id, ph=ph, brix=brix, microbial_cfu=microbial_cfu,
                temperature_c=temperature_c, result=scored["result"], risk_score=scored["risk_score"],
                tested_by=producer.id,
            )
            db.add(test)
            batch.status = models.BatchStatusEnum.passed_qc if scored["result"] == "pass" else models.BatchStatusEnum.failed_qc

            base_time = batch.production_date
            for i, (actor, event_type, location) in enumerate(journey, start=1):
                db.add(models.SupplyChainEvent(
                    batch_id=batch.id, actor_id=actor.id, event_type=event_type,
                    location=location, timestamp=base_time + timedelta(hours=i * 6),
                ))
                status_map = {
                    models.EventTypeEnum.shipped: models.BatchStatusEnum.in_transit,
                    models.EventTypeEnum.received: models.BatchStatusEnum.in_transit,
                    models.EventTypeEnum.sold: models.BatchStatusEnum.delivered,
                }
                if event_type in status_map:
                    batch.status = status_map[event_type]

            db.commit()
            return batch

        # Healthy batch, fully delivered
        b1 = make_batch(
            "Passion Fruit Juice 1L", days_ago=10, volume=1000,
            ph=3.6, brix=13.0, microbial_cfu=15, temperature_c=4.0,
            journey=[
                (producer, models.EventTypeEnum.produced, "Kivu Juice Factory"),
                (producer, models.EventTypeEnum.quality_check, "Kivu Juice Factory QC Lab"),
                (distributor, models.EventTypeEnum.shipped, "Rwanda Logistics Co - Kigali Hub"),
                (retailer, models.EventTypeEnum.received, "Kigali FreshMart"),
                (retailer, models.EventTypeEnum.sold, "Kigali FreshMart"),
            ],
        )

        # In-transit batch, borderline but passing
        b2 = make_batch(
            "Passion Fruit Juice 500ml", days_ago=3, volume=600,
            ph=3.9, brix=11.5, microbial_cfu=40, temperature_c=6.0,
            journey=[
                (producer, models.EventTypeEnum.produced, "Kivu Juice Factory"),
                (producer, models.EventTypeEnum.quality_check, "Kivu Juice Factory QC Lab"),
                (distributor, models.EventTypeEnum.shipped, "Rwanda Logistics Co - Kigali Hub"),
            ],
        )

        # Failed QC batch — cold chain breach + high microbial count
        b3 = make_batch(
            "Mixed Berry Juice 1L", days_ago=1, volume=400,
            ph=3.2, brix=9.0, microbial_cfu=180, temperature_c=11.0,
            journey=[
                (producer, models.EventTypeEnum.produced, "Kivu Juice Factory"),
                (producer, models.EventTypeEnum.quality_check, "Kivu Juice Factory QC Lab"),
            ],
        )

        # Recalled batch (already delivered before the issue was found — good recall demo)
        b4 = make_batch(
            "Mango Juice 1L", days_ago=15, volume=800,
            ph=3.5, brix=13.5, microbial_cfu=20, temperature_c=4.0,
            journey=[
                (producer, models.EventTypeEnum.produced, "Kivu Juice Factory"),
                (producer, models.EventTypeEnum.quality_check, "Kivu Juice Factory QC Lab"),
                (distributor, models.EventTypeEnum.shipped, "Rwanda Logistics Co - Kigali Hub"),
                (retailer, models.EventTypeEnum.received, "Huye Fresh Market"),
                (retailer, models.EventTypeEnum.sold, "Huye Fresh Market"),
            ],
        )
        events = db.query(models.SupplyChainEvent).filter(models.SupplyChainEvent.batch_id == b4.id).all()
        locations = sorted({e.location for e in events if e.location})
        db.add(models.RecallLog(
            batch_id=b4.id, reason="Post-market microbial re-test exceeded safety threshold.",
            triggered_by=admin.id, affected_locations=", ".join(locations),
        ))
        b4.status = models.BatchStatusEnum.recalled
        db.commit()

        # --- Cold-chain readings (simulated IoT history per batch) ---
        cold_chain_specs = {
            b1.id: dict(hours=48, induce_breach=False),
            b2.id: dict(hours=24, induce_breach=False),
            b3.id: dict(hours=24, induce_breach=True),   # the failed batch also broke the cold chain
            b4.id: dict(hours=72, induce_breach=False),
        }
        for b in (b1, b2, b3, b4):
            for reading in generate_readings(b, **cold_chain_specs[b.id]):
                db.add(reading)
        db.commit()

        # --- QR scan telemetry feeding the anti-counterfeit analysis ---
        MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
                     "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1")
        ANDROID_UA = ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/123.0 Mobile Safari/537.36")

        def add_scans(batch, specs):
            # specs: list of (hours_ago, timezone, user_agent)
            for hours_ago, tz, ua in specs:
                db.add(models.QRScan(
                    batch_id=batch.id, location=tz, user_agent=ua, ip_hash="seed",
                    scanned_at=models.utcnow() - timedelta(hours=hours_ago, minutes=hours_ago * 7),
                ))
            if batch.qr_code:
                batch.qr_code.scan_count = len(specs)

        # Genuine batch: a handful of scans, same place — no flags.
        add_scans(b1, [
            (50, "Africa/Kigali", MOBILE_UA),
            (31, "Africa/Kigali", ANDROID_UA),
            (6, "Africa/Kigali", MOBILE_UA),
        ])

        # Cloned-code demo: one code "used" all over the world in hours.
        add_scans(b2, [
            (0.5, "Asia/Shanghai", MOBILE_UA),
            (1.2, "Asia/Shanghai", ANDROID_UA),
            (2.0, "Europe/Madrid", MOBILE_UA),
            (2.5, "America/New_York", ANDROID_UA),
            (3.1, "Africa/Kigali", MOBILE_UA),
            (4.0, "Asia/Shanghai", MOBILE_UA),
            (5.2, "Europe/Madrid", ANDROID_UA),
            (6.5, "Africa/Nairobi", MOBILE_UA),
            (8.0, "America/New_York", MOBILE_UA),
            (11.0, "Asia/Shanghai", ANDROID_UA),
            (14.0, "Europe/Madrid", MOBILE_UA),
            (18.0, "Africa/Kigali", ANDROID_UA),
        ])

        add_scans(b4, [
            (60, "Africa/Kigali", ANDROID_UA),
            (20, "Africa/Kigali", MOBILE_UA),
        ])
        db.commit()

        # --- Demo lab certificate attached to the healthy batch's QC test ---
        test1 = db.query(models.QualityTest).filter(models.QualityTest.batch_id == b1.id).first()
        if test1:
            test1.certificate_filename = f"qc-certificate-{b1.batch_code}.pdf"
            test1.certificate_mime = "application/pdf"
            test1.certificate_data = base64.b64encode(_demo_pdf([
                "Kivu Juice Factory - Quality Control Laboratory",
                "Certificate of Analysis",
                "",
                f"Batch: {b1.batch_code}",
                f"Product: {b1.product_name}",
                f"pH: {test1.ph}    Brix: {test1.brix}",
                f"Microbial count: {test1.microbial_cfu} CFU/mL",
                f"Storage temperature: {test1.temperature_c} C",
                f"ML risk score: {test1.risk_score} / 100",
                f"Result: {test1.result.upper()}",
                "",
                "Analyst: J. Producer   Signed: (electronic)",
            ])).decode()
            db.commit()

        print("Seed complete. Demo logins (password: password123):")
        print("  admin@demo.com | producer@demo.com | distributor@demo.com | retailer@demo.com")
        print("Demo batch codes to try on the public verify page:")
        for b in (b1, b2, b3, b4):
            print(f"  {b.batch_code} -> {b.product_name} ({b.status.value})")
        print("Anti-counterfeit demo: open the first code a few times from the verify "
              f"page, and inspect {b2.batch_code} in the dashboard — its QR code was "
              "seeded with scans from 5 different countries.")

    finally:
        db.close()


if __name__ == "__main__":
    run()
