# Water Meter Management System

Standalone FastAPI/Jinja2 application for capturing water-meter readings, retaining meter images,
calculating meter consumption, generating tenant statements, and synchronizing readings to Google Sheets.

## Local run

```bash
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 4006
```

Open `http://127.0.0.1:4006`.

## Google Sheets

Set `GOOGLE_SHEETS_ENABLED=true`, `GOOGLE_SHEET_ID`, `GOOGLE_SHEET_TAB`, and
`GOOGLE_SERVICE_ACCOUNT_FILE`. Share the spreadsheet with the service-account email.

SQLite remains authoritative. If Sheets is unavailable, the reading is retained locally as Pending and can be retried.

## Docker

```bash
docker compose up -d --build
```

The existing reverse proxy can route to port 4006; no reverse proxy is included here.
