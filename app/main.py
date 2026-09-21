import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Depends, Form, UploadFile, File, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import engine, Base, get_db
from app.models import Tenant, Meter, MeterReading
from app.services.readings import calculate_meter_reading_stats, get_tenant_statement_data, delete_meter_reading
from app.services.google_sheets import run_full_sync_task
import os
import re

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Water Meter Management System")

class RemoveDoubleSlashesMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            # Clean up the routing path
            scope["path"] = re.sub(r"/{2,}", "/", scope["path"])
        await self.app(scope, receive, send)

# Wrap your FastAPI app with the ASGI middleware
app.add_middleware(RemoveDoubleSlashesMiddleware)

ROUTE_PATH = os.getenv("ROUTE_PATH", "")

if ROUTE_PATH != "":
    ROUTE_PATH = "/" + ROUTE_PATH

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

UPLOAD_DIR = PROJECT_ROOT / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.on_event("startup")
def seed_initial_data():
    db = next(get_db())
    if db.query(Tenant).count() == 0:
        tenants_data = [
            ("A1", "Tenant A1"), ("B1", "Tenant B1"),
            ("A2", "Tenant A2"), ("B2", "Tenant B2"),
            ("A3", "Tenant A3"), ("B3", "Tenant B3")
        ]
        meters_data = [
            ("A1", "A11", "Wash"), ("A1", "A12", "Kitchen"),
            ("B1", "B11", "Wash"), ("B1", "B12", "Kitchen"),
            ("A2", "A21", "Wash"), ("A2", "A22", "Kitchen"),
            ("B2", "B21", "Wash"), ("B2", "B22", "Kitchen"),
            ("A3", "A31", "Wash"), ("A3", "A32", "Kitchen"),
            ("B3", "B31", "Wash"), ("B3", "B32", "Kitchen")
        ]
        
        tenant_map = {}
        for code, name in tenants_data:
            t = Tenant(code=code, name=name)
            db.add(t)
            db.commit()
            db.refresh(t)
            tenant_map[code] = t.id

        for t_code, meter_num, area in meters_data:
            m = Meter(tenant_id=tenant_map[t_code], meter_number=meter_num, area=area)
            db.add(m)
        db.commit()


@app.get("/", response_class=HTMLResponse)
@app.get("/capture", response_class=HTMLResponse)
def capture_form(request: Request, db: Session = Depends(get_db)):
    meters = db.query(Meter).all()
    today = datetime.now().strftime("%Y-%m-%d")
    return templates.TemplateResponse(
        request=request,
        name="capture.html",
        context={"meters": meters, "today": today,"ROUTE_PATH":ROUTE_PATH}
    )


@app.post("/capture")
async def save_reading(
    background_tasks: BackgroundTasks,
    meter_id: int = Form(...),
    capture_date: str = Form(...),
    reading_value: float = Form(...),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    meter = db.query(Meter).filter(Meter.id == meter_id).first()
    date_obj = datetime.strptime(capture_date, "%Y-%m-%d").date()

    file_path = None
    if image and image.filename:
        meter_folder = UPLOAD_DIR / "water" / meter.meter_number
        meter_folder.mkdir(parents=True, exist_ok=True)
        filename = f"{capture_date}_{image.filename}"
        saved_file = meter_folder / filename

        with open(saved_file, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        file_path = str(saved_file)

    reading = MeterReading(
        meter_id=meter_id,
        capture_date=date_obj,
        reading_value=reading_value,
        image_path=file_path
    )
    db.add(reading)
    db.commit()
    db.refresh(reading)

    background_tasks.add_task(run_full_sync_task)
    return RedirectResponse(url=ROUTE_PATH+"/readings", status_code=303)


@app.post("/readings/{reading_id}/delete")
def delete_reading_endpoint(
    reading_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    success = delete_meter_reading(db, reading_id)
    if success:
        background_tasks.add_task(run_full_sync_task)
    return RedirectResponse(url=ROUTE_PATH+"/readings", status_code=303)


@app.post("/sync")
def trigger_sync(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_full_sync_task)
    return RedirectResponse(url=ROUTE_PATH+"/readings", status_code=303)


@app.get("/readings", response_class=HTMLResponse)
def list_readings(request: Request, db: Session = Depends(get_db)):
    readings = db.query(MeterReading).order_by(MeterReading.capture_date.desc()).all()
    records = [calculate_meter_reading_stats(db, r) for r in readings]
    return templates.TemplateResponse(
        request=request,
        name="readings.html",
        context={"records": records,"ROUTE_PATH":ROUTE_PATH}
    )


@app.get("/consumption", response_class=HTMLResponse)
def view_consumption(request: Request, db: Session = Depends(get_db)):
    meters = db.query(Meter).all()
    records = []
    for m in meters:
        latest = (
            db.query(MeterReading)
            .filter(MeterReading.meter_id == m.id)
            .order_by(MeterReading.capture_date.desc())
            .first()
        )
        if latest:
            records.append(calculate_meter_reading_stats(db, latest))
    return templates.TemplateResponse(
        request=request,
        name="consumption.html",
        context={"records": records,"ROUTE_PATH":ROUTE_PATH}
    )


@app.get("/statement", response_class=HTMLResponse)
def view_statement(request: Request, tenant_id: int = None, db: Session = Depends(get_db)):
    tenants = db.query(Tenant).all()
    statement_data = None
    if tenant_id:
        statement_data = get_tenant_statement_data(db, tenant_id)
    return templates.TemplateResponse(
        request=request,
        name="statement.html",
        context={
            "tenants": tenants,
            "selected_tenant_id": tenant_id,
            "data": statement_data,
            "ROUTE_PATH":ROUTE_PATH
        }
    )