"""
Cold-chain IoT simulator.

Bulk mode (default): writes a full shipment history for a batch in one go.
Live mode (--push): appends one reading every --seconds, the way a real
sensor gateway would — nice for a live demo of the cold-chain chart.

Examples:
  python -m app.simulate_cold_chain --batch BQ-2026-12345 --hours 48
  python -m app.simulate_cold_chain --batch BQ-2026-12345 --breach
  python -m app.simulate_cold_chain --batch BQ-2026-12345 --push --seconds 3
  python -m app.simulate_cold_chain --all --hours 24
"""
import argparse
import random
import time
from datetime import datetime

from app.database import SessionLocal
from app import models
from app.routers.cold_chain import build_stats, generate_readings, SAFE_MIN_C, SAFE_MAX_C


def find_batches(db, code: str, all_batches: bool):
    if all_batches:
        return db.query(models.Batch).all()
    batch = db.query(models.Batch).filter(models.Batch.batch_code == code).first()
    if not batch:
        known = [b.batch_code for b in db.query(models.Batch).limit(10)]
        raise SystemExit(f"No batch with code '{code}'. Known codes: {', '.join(known)}")
    return [batch]


def push_live(db, batch, seconds: float, breach: bool):
    """Append a single reading every `seconds` until Ctrl+C."""
    print(f"Pushing live readings for {batch.batch_code} every {seconds}s — Ctrl+C to stop.")
    temp = 4.0
    try:
        while True:
            if breach and random.random() < 0.3:
                temp += random.uniform(0.5, 2.0)          # fridge struggling
            else:
                temp += (4.2 - temp) * 0.2 + random.uniform(-0.4, 0.4)
            temp = max(-1.0, min(18.0, temp))

            reading = models.TemperatureReading(
                batch_id=batch.id,
                temperature_c=round(temp, 2),
                location="Live simulator",
                device_id="sim-gateway-live",
                recorded_at=models.utcnow(),
            )
            state = "BREACH" if not (SAFE_MIN_C <= temp <= SAFE_MAX_C) else "ok"
            print(f"  {reading.recorded_at:%H:%M:%S}  {temp:5.2f}°C  {state}")

            db.add(reading)
            db.commit()
            time.sleep(seconds)
    except KeyboardInterrupt:
        print("\nStopped.")


def main():
    parser = argparse.ArgumentParser(description="Simulate cold-chain temperature readings")
    parser.add_argument("--batch", help="Batch code, e.g. BQ-2026-12345")
    parser.add_argument("--all", action="store_true", help="Simulate for every batch")
    parser.add_argument("--hours", type=int, default=24, help="History length in hours (default 24)")
    parser.add_argument("--interval", type=int, default=30, help="Minutes between readings (default 30)")
    parser.add_argument("--breach", action="store_true", help="Induce a refrigeration failure")
    parser.add_argument("--push", action="store_true", help="Live mode: keep pushing readings")
    parser.add_argument("--seconds", type=float, default=5, help="Seconds between live readings")
    args = parser.parse_args()

    if not args.batch and not args.all:
        parser.error("--batch CODE or --all is required")

    db = SessionLocal()
    try:
        batches = find_batches(db, args.batch, args.all)

        if args.push:
            for batch in batches:
                push_live(db, batch, args.seconds, args.breach)
            return

        for batch in batches:
            readings = generate_readings(
                batch, hours=args.hours, interval_minutes=args.interval,
                induce_breach=args.breach,
            )
            for r in readings:
                db.add(r)
            db.commit()

            stats = build_stats(readings)
            print(f"{batch.batch_code}: {stats.readings} readings "
                  f"(min {stats.min_c}°C / avg {stats.avg_c}°C / max {stats.max_c}°C), "
                  f"{stats.breaches} breaches of the {SAFE_MIN_C}-{SAFE_MAX_C}°C safe range")
    finally:
        db.close()


if __name__ == "__main__":
    main()
