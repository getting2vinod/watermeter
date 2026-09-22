import os
from datetime import date
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models import MeterReading, Meter, Tenant

def calculate_meter_reading_stats(db: Session, reading: MeterReading) -> Dict[str, Any]:
    # If the reading itself is a reset marker, it starts a new cycle (no prior baseline for this tenant)
    if reading.is_reset:
        reset_reading = None
    else:
        # Find the most recent reset marker before this reading
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
        
        # If no explicit reset marker exists, fall back to the very first reading for this meter
        if not reset_reading:
            reset_reading = (
                db.query(MeterReading)
                .filter(
                    MeterReading.meter_id == reading.meter_id,
                    MeterReading.capture_date < reading.capture_date
                )
                .order_by(MeterReading.capture_date.asc())
                .first()
            )

    if not reset_reading:
        # Requirement 1: If no previous reading exists (or it's the reset marker), use current reading
        consumption = round(reading.reading_value, 2)
        days = None
        avg_per_day = None
        prev_date = None
        prev_val = None
    else:
        # Requirement 3: Total consumption is calculated from the reset marker baseline
        consumption = round(reading.reading_value - reset_reading.reading_value, 2)
        days = (reading.capture_date - reset_reading.capture_date).days
        avg_per_day = round(consumption / days, 3) if days and days > 0 else 0.0
        prev_date = reset_reading.capture_date
        prev_val = reset_reading.reading_value

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
            if stat["consumption"] is not None:
                total_consumption += stat["consumption"]
        else:
            meter_stats.append({
                "meter_number": meter.meter_number,
                "area": meter.area,
                "current_date": None,
                "current_reading": None,
                "previous_date": None,
                "previous_reading": None,
                "consumption": None,
                "days": None
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