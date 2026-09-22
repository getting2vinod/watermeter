import os
from datetime import date
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models import MeterReading, Meter, Tenant


def calculate_meter_reading_stats(db: Session, reading: MeterReading) -> Dict[str, Any]:
    # 1. If the current reading is marked as a reset, consumption for this entry is 0.0 (starts baseline)
    if reading.is_reset:
        return {
            "id": reading.id,
            "meter_number": reading.meter.meter_number,
            "tenant_code": reading.meter.tenant.code,
            "area": reading.meter.area,
            "current_date": reading.capture_date,
            "current_reading": reading.reading_value,
            "previous_date": None,
            "previous_reading": None,
            "consumption": 0.0,
            "days": None,
            "avg_per_day": None,
            "is_reset": True,
            "image_path": reading.image_path,
            "review": getattr(reading, "review", None)
        }

    # 2. Look for the most recent reading marked with is_reset = True prior to this reading
    reset_reading = (
        db.query(MeterReading)
        .filter(
            MeterReading.meter_id == reading.meter_id,
            MeterReading.capture_date < reading.capture_date,
            MeterReading.is_reset == True
        )
        .order_by(MeterReading.capture_date.desc())
        .first()
    )

    if reset_reading:
        # If an is_reset flag is found: consumption = current_reading - reset_reading
        consumption = round(max(0.0, reading.reading_value - reset_reading.reading_value), 2)
        days = (reading.capture_date - reset_reading.capture_date).days
        avg_per_day = round(consumption / days, 3) if days and days > 0 else 0.0
        prev_date = reset_reading.capture_date
        prev_val = reset_reading.reading_value
    else:
        # If NO is_reset flag exists for the meter: consumption = current reading value
        consumption = round(reading.reading_value, 2)
        days = None
        avg_per_day = None
        prev_date = None
        prev_val = None

    return {
        "id": reading.id,
        "meter_number": reading.meter.meter_number,
        "tenant_code": reading.meter.tenant.code,
        "area": reading.meter.area,
        "current_date": reading.capture_date,
        "current_reading": reading.reading_value,
        "previous_date": prev_date,
        "previous_reading": prev_val,
        "consumption": consumption,
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

    for meter in tenant.meters:
        stat = get_latest_meter_stat(db, meter.id)
        if stat:
            meter_stats.append(stat)
            if stat.get("consumption") is not None:
                total_consumption += stat["consumption"]
        else:
            meter_stats.append({
                "meter_number": meter.meter_number,
                "area": meter.area,
                "current_date": None,
                "current_reading": None,
                "previous_date": None,
                "previous_reading": None,
                "consumption": 0.0,
                "days": None,
                "is_reset": False
            })

    return {
        "tenant": tenant,
        "meter_stats": meter_stats,
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