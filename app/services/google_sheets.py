import os
import logging
import gspread
from google.oauth2.service_account import Credentials
from sqlalchemy.orm import Session
from app.models import MeterReading
from app.services.readings import calculate_meter_reading_stats

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def full_sync_to_google_sheets(db: Session) -> bool:
    """
    Clears and completely overwrites Google Sheets with all current readings from the database.
    """
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    sheet_name = os.getenv("GOOGLE_SHEET_NAME", "Water Meter Readings")

    if not creds_path or not os.path.exists(creds_path):
        logger.warning("Google Credentials not found. Skipping Google Sheets sync.")
        return False

    try:
        credentials = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
        client = gspread.authorize(credentials)
        sheet = client.open(sheet_name).sheet1

        # Fetch all readings ordered chronologically
        readings = (
            db.query(MeterReading)
            .order_by(MeterReading.capture_date.asc(), MeterReading.id.asc())
            .all()
        )

        headers = [
            "Reading ID", "Date", "Meter", "Tenant", "Area",
            "Reading", "Previous Reading", "Previous Date",
            "Consumption", "Days", "Image"
        ]

        rows = [headers]
        for r in readings:
            data = calculate_meter_reading_stats(db, r)
            rows.append([
                str(data.get("id")),
                str(data.get("current_date")),
                str(data.get("meter_number")),
                str(data.get("tenant_code")),
                str(data.get("area")),
                data.get("current_reading"),
                data.get("previous_reading") if data.get("previous_reading") is not None else "-",
                str(data.get("previous_date")) if data.get("previous_date") else "-",
                data.get("consumption") if data.get("consumption") is not None else "-",
                data.get("days") if data.get("days") is not None else "-",
                str(data.get("image_path") or "-")
            ])

        # Overwrite full sheet content
        sheet.clear()
        sheet.update("A1", rows)
        logger.info("Full sync to Google Sheets completed successfully.")
        return True
    except Exception as e:
        logger.error(f"Failed full sync with Google Sheets: {e}")
        return False

def run_full_sync_task():
    """Helper function for background tasks using an independent DB session."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        full_sync_to_google_sheets(db)
    finally:
        db.close()