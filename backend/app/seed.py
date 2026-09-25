"""
Seeds the database with demo users, 5 suppliers, raw-material lots, 16
batches covering every lifecycle status (delivered, in transit, in
production, passed/failed QC, recalled), quality tests, supply-chain
events, cold-chain readings, QR scan telemetry, 3 recalls and a demo
lab certificate — so every screen in the frontend has something to show
immediately.

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

        # --- Suppliers + raw-material lots (roots of every traceability chain) ---
        suppliers = {
            "musanze": models.Supplier(name="Musanze Orchards Co-op",
                                       location="Musanze, Rwanda", contact="+250700000000"),
            "kivu": models.Supplier(name="Kivu Bay Citrus",
                                    location="Gisenyi, Rwanda", contact="+250700111111"),
            "nyungwe": models.Supplier(name="Nyungwe Plantations",
                                       location="Nyamasheke, Rwanda", contact="+250700222222"),
            "gitenge": models.Supplier(name="Gitenge Tea Estates",
                                       location="Ruhengeri, Rwanda", contact="+250700333333"),
            "akagera": models.Supplier(name="Akagera Springs Water",
                                       location="Kirehe, Rwanda", contact="+250700444444"),
        }
        db.add_all(suppliers.values())
        db.commit()

        lots = {}

        def add_lot(key, supplier, material, kg):
            lot = models.RawMaterialBatch(
                supplier_id=supplier.id, material_type=material, quantity_kg=kg,
            )
            db.add(lot)
            db.commit()
            db.refresh(lot)
            lots[key] = lot

        add_lot("passion1", suppliers["musanze"], "Passion Fruit", 500)
        add_lot("passion2", suppliers["musanze"], "Passion Fruit", 300)
        add_lot("oranges", suppliers["kivu"], "Oranges", 800)
        add_lot("pineapple", suppliers["kivu"], "Pineapples", 450)
        add_lot("mango", suppliers["nyungwe"], "Mangoes", 600)
        add_lot("soursop", suppliers["nyungwe"], "Soursop", 200)
        add_lot("tea", suppliers["gitenge"], "Green Tea Leaves", 250)
        add_lot("hibiscus", suppliers["gitenge"], "Hibiscus Flowers", 150)
        add_lot("water", suppliers["akagera"], "Purified Water", 1500)
        add_lot("lemons", suppliers["akagera"], "Lemons", 300)

        def make_batch(product_name, lot_key, days_ago, volume, qc=None, journey=(),
                       expiry_days=None):
            """Create a batch with QR code, optional QC test and a supply-chain
            journey. `qc=None` leaves the batch in production (no test yet)."""
            batch = models.Batch(
                batch_code=generate_batch_code(db),
                product_name=product_name,
                raw_material_id=lots[lot_key].id,
                production_date=models.utcnow() - timedelta(days=days_ago),
                expiry_date=models.utcnow() + timedelta(
                    days=expiry_days if expiry_days is not None else 90 - days_ago),
                volume_liters=volume,
                created_by=producer.id,
            )
            if qc is None:
                batch.status = models.BatchStatusEnum.in_production
            db.add(batch)
            db.commit()
            db.refresh(batch)

            db.add(models.QRCode(batch_id=batch.id, code_value=batch.batch_code))

            if qc:
                scored = risk_score(**qc)
                test = models.QualityTest(
                    batch_id=batch.id, **qc,
                    result=scored["result"], risk_score=scored["risk_score"],
                    tested_by=producer.id,
                )
                db.add(test)
                batch.status = (models.BatchStatusEnum.passed_qc
                                if scored["result"] == "pass"
                                else models.BatchStatusEnum.failed_qc)

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

        # Reusable journey legs
        PRODUCED = (producer, models.EventTypeEnum.produced, "Kivu Juice Factory")
        QC_LAB = (producer, models.EventTypeEnum.quality_check, "Kivu Juice Factory QC Lab")
        SHIP_HUB = (distributor, models.EventTypeEnum.shipped, "Rwanda Logistics Co - Kigali Hub")

        def delivered_journey(receive_at, sell_at):
            return [PRODUCED, QC_LAB, SHIP_HUB,
                    (retailer, models.EventTypeEnum.received, receive_at),
                    (retailer, models.EventTypeEnum.sold, sell_at)]

        # ---- flagship demo batches (codes printed at the end of the seed) ----

        # Healthy batch, fully delivered
        b1 = make_batch(
            "Passion Fruit Juice 1L", "passion1", days_ago=10, volume=1000,
            qc=dict(ph=3.6, brix=13.0, microbial_cfu=15, temperature_c=4.0),
            journey=delivered_journey("Kigali FreshMart", "Kigali FreshMart"),
        )

        # In-transit batch, borderline but passing — the cloned-QR demo
        b2 = make_batch(
            "Passion Fruit Juice 500ml", "passion1", days_ago=3, volume=600,
            qc=dict(ph=3.9, brix=11.5, microbial_cfu=40, temperature_c=6.0),
            journey=[PRODUCED, QC_LAB, SHIP_HUB],
        )

        # Failed QC batch — cold chain breach + high microbial count
        b3 = make_batch(
            "Mixed Berry Juice 1L", "passion1", days_ago=1, volume=400,
            qc=dict(ph=3.2, brix=9.0, microbial_cfu=180, temperature_c=11.0),
            journey=[PRODUCED, QC_LAB],
        )

        # Recalled batch (already delivered before the issue was found)
        b4 = make_batch(
            "Mango Juice 1L", "mango", days_ago=15, volume=800,
            qc=dict(ph=3.5, brix=13.5, microbial_cfu=20, temperature_c=4.0),
            journey=delivered_journey("Huye Fresh Market", "Huye Fresh Market"),
        )

        # ---- still on the production line (no QC test yet → "untested" risk) ----
        lemonade = make_batch(
            "Cold-Pressed Lemonade 1L", "lemons", days_ago=2, volume=500,
            qc=None, journey=[PRODUCED], expiry_days=60,
        )
        soursop = make_batch(
            "Soursop Smoothie 1L", "soursop", days_ago=1, volume=300,
            qc=None, journey=[PRODUCED], expiry_days=45,
        )

        # ---- passed QC, waiting in stock ----
        nectar = make_batch(
            "Passion Fruit Nectar 1L", "passion1", days_ago=7, volume=900,
            qc=dict(ph=3.7, brix=12.8, microbial_cfu=18, temperature_c=4.2),
            journey=[PRODUCED, QC_LAB],
        )
        orange = make_batch(
            "Orange Juice 1L", "oranges", days_ago=6, volume=1200,
            qc=dict(ph=4.0, brix=11.8, microbial_cfu=22, temperature_c=3.8),
            journey=[PRODUCED, QC_LAB],
        )

        # ---- second QC failure (a different failure mode: too sweet, too warm) ----
        blend = make_batch(
            "Carrot & Mango Blend 1L", "mango", days_ago=2, volume=350,
            qc=dict(ph=5.6, brix=4.0, microbial_cfu=640, temperature_c=9.5),
            journey=[PRODUCED, QC_LAB],
        )

        # ---- in transit ----
        bissap = make_batch(
            "Bissap Hibiscus Drink 1L", "hibiscus", days_ago=4, volume=700,
            qc=dict(ph=3.4, brix=10.5, microbial_cfu=30, temperature_c=5.5),
            journey=[PRODUCED, QC_LAB, SHIP_HUB],
        )
        ginger = make_batch(
            "Ginger Lemonade 750ml", "lemons", days_ago=5, volume=550,
            qc=dict(ph=3.8, brix=10.0, microbial_cfu=25, temperature_c=4.5),
            journey=[PRODUCED, QC_LAB, SHIP_HUB],
        )

        # ---- two more recalls, different reasons and routes ----
        tea = make_batch(
            "Iced Green Tea 1L", "tea", days_ago=20, volume=650,
            qc=dict(ph=4.2, brix=8.5, microbial_cfu=35, temperature_c=5.0),
            journey=delivered_journey("Musanze Supermarket", "Musanze Supermarket"),
        )
        concentrate = make_batch(
            "Passion Fruit Concentrate 2L", "passion2", days_ago=25, volume=450,
            qc=dict(ph=3.3, brix=16.0, microbial_cfu=12, temperature_c=4.0),
            journey=delivered_journey("Gisenyi Corner Store", "Gisenyi Corner Store"),
        )

        # ---- stock that is past / approaching its expiry date ----
        fizz = make_batch(
            "Pineapple Fizz 1L", "pineapple", days_ago=85, volume=750,
            qc=dict(ph=3.9, brix=12.0, microbial_cfu=28, temperature_c=4.4),
            journey=delivered_journey("Kigali FreshMart", "Kigali FreshMart"),
            expiry_days=5,                       # expires within the 7-day warning window
        )
        mango_nectar = make_batch(
            "Mango Nectar 250ml", "mango", days_ago=100, volume=300,
            qc=dict(ph=4.1, brix=13.2, microbial_cfu=45, temperature_c=4.8),
            journey=delivered_journey("Huye Fresh Market", "Huye Fresh Market"),
            expiry_days=-10,                     # already expired — critical alert demo
        )

        # ---- newest batch: a fresh, fully traced delivery (listed first in the UI) ----
        tropical = make_batch(
            "Tropical Mix Juice 1L", "mango", days_ago=3, volume=1000,
            qc=dict(ph=3.6, brix=12.6, microbial_cfu=16, temperature_c=4.1),
            journey=delivered_journey("Kigali FreshMart", "Kigali FreshMart"),
        )

        # --- Recalls (3 examples: microbial, labelling, seal integrity) ---
        def add_recall(batch, reason):
            events = db.query(models.SupplyChainEvent).filter(
                models.SupplyChainEvent.batch_id == batch.id).all()
            locations = sorted({e.location for e in events if e.location})
            db.add(models.RecallLog(
                batch_id=batch.id, reason=reason, triggered_by=admin.id,
                affected_locations=", ".join(locations),
            ))
            batch.status = models.BatchStatusEnum.recalled
            db.commit()

        add_recall(b4, "Post-market microbial re-test exceeded safety threshold.")
        add_recall(tea, "Label declared incorrect caffeine content — labelling "
                        "non-compliance found during market surveillance.")
        add_recall(concentrate, "Seal integrity failure reported by retailers — "
                                "leakage creates a secondary contamination risk.")

        # --- Cold-chain readings (simulated IoT history per tested batch) ---
        cold_chain_specs = {
            b1.id: dict(hours=48, induce_breach=False),
            b2.id: dict(hours=24, induce_breach=False),
            b3.id: dict(hours=24, induce_breach=True),    # failed batch also broke the cold chain
            b4.id: dict(hours=72, induce_breach=False),
            bissap.id: dict(hours=12, induce_breach=True),  # a second, milder incident
        }
        tested = db.query(models.Batch).join(models.QualityTest).all()
        for b in tested:
            spec = cold_chain_specs.get(b.id, dict(hours=12, induce_breach=False))
            for reading in generate_readings(b, **spec):
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

        # Genuine batches: a handful of scans, same place — no flags.
        add_scans(b1, [
            (50, "Africa/Kigali", MOBILE_UA),
            (31, "Africa/Kigali", ANDROID_UA),
            (6, "Africa/Kigali", MOBILE_UA),
        ])
        add_scans(tropical, [
            (30, "Africa/Kigali", MOBILE_UA),
            (9, "Africa/Kigali", ANDROID_UA),
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

        n_batches = db.query(models.Batch).count()
        n_suppliers = db.query(models.Supplier).count()
        n_recalls = db.query(models.RecallLog).count()
        n_readings = db.query(models.TemperatureReading).count()
        n_scans = db.query(models.QRScan).count()

        print("Seed complete. Demo logins (password: password123):")
        print("  admin@demo.com | producer@demo.com | distributor@demo.com | retailer@demo.com")
        print(f"Demo data: {n_batches} batches · {n_suppliers} suppliers · "
              f"{n_recalls} recalls · {n_readings} temperature readings · {n_scans} scans")
        print("Batch codes to try on the public verify page:")
        for b in (b1, b2, b3, b4, tropical, tea):
            print(f"  {b.batch_code} -> {b.product_name} ({b.status.value})")
        print("Anti-counterfeit demo: inspect " + b2.batch_code + " in the dashboard — its "
              "QR code was seeded with scans from 5 different countries.")
        print("Recall demo: the Recalls page lists all "
              f"{n_recalls} recalls with their affected locations.")

    finally:
        db.close()


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):   # Windows cp1252 consoles: keep ✓/· intact
        sys.stdout.reconfigure(encoding="utf-8")
    run()
