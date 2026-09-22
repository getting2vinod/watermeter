import os
from datetime import date
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models import MeterReading, Meter, Tenant


def calculate_meter_reading_stats(db: Session, reading: MeterReading) -> Dict[str, Any]:
    # 1. Get the immediately preceding captured reading for this meter
    prev_reading = (
        db.query(MeterReading)
        .filter(
            MeterReading.meter_id == reading.meter_id,
            MeterReading.capture_date < reading.capture_date
        )
        .order_by(MeterReading.capture_date.desc())
        .first()
    )

    # 2. Get the reset baseline reading (most recent reading where is_reset is True, on or prior to this reading)
    reset_reading = (
        db.query(MeterReading)
        .filter(
            MeterReading.meter_id == reading.meter_id,
            MeterReading.capture_date <= reading.capture_date,
            MeterReading.is_reset == True
        )
        .order_by(MeterReading.capture_date.desc())
        .first()
    )
    baseline = reset_reading.reading_value if reset_reading else 0.0

    prev_date = prev_reading.capture_date if prev_reading else None
    prev_val = prev_reading.reading_value if prev_reading else None

    # 3. Calculate interval consumption from immediately preceding reading
    if reading.is_reset:
        consumption = 0.0
        days = None
        avg_per_day = None
    elif prev_reading:
        consumption = round(max(0.0, reading.reading_value - prev_reading.reading_value), 2)
        days = (reading.capture_date - prev_reading.capture_date).days
        avg_per_day = round(consumption / days, 3) if days and days > 0 else 0.0
    else:
        # No previous reading captured: consumption equals the current reading
        consumption = round(reading.reading_value, 2)
        days = None
        avg_per_day = None

    # Net total consumption calculated relative to the reset baseline
    net_consumption = round(max(0.0, reading.reading_value - baseline), 2)

    return {
        "id": reading.id,
        "meter_number": reading.meter.meter_number,
        "tenant_code": reading.meter.tenant.code,
        "area": reading.meter.area,
        "current_date": reading.capture_date,
        "current_reading": reading.reading_value,
        "previous_date": prev_date,
        "previous_reading": prev_val,
        "baseline_reading": baseline,
        "consumption": consumption,
        "net_consumption": net_consumption,
        "days": days,
        "avg_per_day": avg_per_day,
        "is_reset": reading.is_reset,
        "image_path": reading.image_path,
        "review": getattr(reading, "review", None)
    }


def get_latest_meter_stat(db: Session, meter_id: int) -> Optional[Dict[str, Any]]:
    latest_reading = (
        db.query(MeterReading)
        .filter(MeterReading.meter_id == meter_id)
        .order_by(MeterReading.capture_date.desc())
        .first()
    )
    if not latest_reading:
        return None
    return calculate_meter_reading_stats(db, latest_reading)


def get_tenant_statement_data(db: Session, tenant_id: int) -> Dict[str, Any]:
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        return {}

    meter_stats = []
    total_consumption = 0.0
    total_baseline = 0.0
    total_current = 0.0

    for meter in tenant.meters:
        stat = get_latest_meter_stat(db, meter.id)
        if stat:
            meter_stats.append(stat)
            total_baseline += stat.get("baseline_reading", 0.0) or 0.0
            total_current += stat.get("current_reading", 0.0) or 0.0
            total_consumption += stat.get("net_consumption", 0.0) or 0.0
        else:
            meter_stats.append({
                "meter_number": meter.meter_number,
                "area": meter.area,
                "current_date": None,
                "current_reading": None,
                "previous_date": None,
                "previous_reading": None,
                "baseline_reading": 0.0,
                "consumption": 0.0,
                "net_consumption": 0.0,
                "days": None,
                "is_reset": False
            })

    return {
        "tenant": tenant,
        "meter_stats": meter_stats,
        "total_baseline": round(total_baseline, 2),
        "total_current": round(total_current, 2),
        "total_consumption": round(total_consumption, 2),
        "generated_date": date.today()
    }


def delete_meter_reading(db: Session, reading_id: int) -> bool:
    reading = db.query(MeterReading).filter(MeterReading.id == reading_id).first()
    if not reading:
        return False

    if reading.image_path and os.path.exists(reading.image_path):
        try:
            os.remove(reading.image_path)
        except OSError:
            pass

    db.delete(reading)
    db.commit()
    return True