# SBAC Attendance System — ZKTeco Fetch & Export Service

## Project Overview

This project automates extraction of attendance logs from ZKTeco biometric devices across **120+ SBAC Bank branches**, inserts them into a central HRBOOK database, and stores a deduplicated copy in a Flask / MySQL backend.

**Key features**

* **Reliable Data Capture:** Poll devices concurrently using IP ranges/subnets.
* **Dual-Persistence:** Logs saved both in Access (legacy) and Flask DB for auditing & integration.
* **Performance:** Bulk insertions for high-volume data, colored logging, elapsed-time metrics.
* **Scalability:** `ThreadPoolExecutor` for parallel device polling, configurable worker count.

---

## Folder Structure

```
attendance-system/
├── backend/
│   ├── app/
│   │   ├── __init__.py       # App factory & extension init
│   │   ├── config.py         # Config: DB URIs, polling intervals
│   │   ├── models.py         # SQLAlchemy models: Branch, Device, AttendanceLog
│   │   ├── views/
│   │   │   ├── devices.py    # CRUD endpoints for branches & devices
│   │   │   └── logs.py       # Polling endpoint and health check
│   │   ├── tasks.py          # Poll scheduler, fetch/forward logic, Access & bulk DB inserts
│   │   └── seed_data.py      # CSV/Excel-driven seeder for Branch & Device tables
│   ├── migrations/           # Flask-Migrate scripts
│   ├── requirements.txt      # Python dependencies
│   └── run.py               # Production entry point (gunicorn/uWSGI)
└── frontend/
    ├── public/
    ├── src/
    │   ├── api/              # axios instance & API wrappers to Flask backend
    │   ├── components/       # React components (BranchList, LogsTable, Dashboard)
    │   ├── contexts/         # React Context (Auth, WebSocket)
    │   ├── App.jsx           # Top-level React component
    │   └── index.jsx         # ReactDOM bootstrap
    └── package.json          # Frontend dependencies
```

---

## Python Dependencies (excerpt)

(See `backend/requirements.txt` for full list)

* Flask
* Flask-SQLAlchemy
* Flask-Migrate
* APScheduler
* pyzk
* pyodbc
* pandas
* openpyxl
* colorama
* SQLAlchemy
* Flask-SocketIO

---

## Setup & Run — Backend

### 1. Clone & enter directory

```bash
git clone <repo-url>
cd attendance-system/backend
```

### 2. Create & activate virtual environment

**Linux / macOS**

```bash
python -m venv venv
source venv/bin/activate
```

**Windows (PowerShell)**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Access DB path and environment

Edit `app/config.py` (or set env variables used by `tasks.py`) and point to the Access DB:

```python
ATTENDANCE_ACCESS_PATH = "/path/to/att2000.mdb"
DATABASE_URL = "mysql+pymysql://user:pass@localhost/attendance"
POLL_INTERVAL = 300  # seconds
```

### 5. Initialize Flask DB (MySQL or SQLite)

```bash
flask db init
flask db migrate -m "Initial"
flask db upgrade
```

### 6. Seed Branches & Devices

```bash
flask shell
>>> exec(open('app/seed_data.py').read())
```

### 7. Run (development)

```bash
flask run
```

> Scheduler auto-starts on app launch and polls devices every `POLL_INTERVAL` seconds (configurable).

---

## Frontend — Setup & Run

**Install & start**

```bash
cd ../frontend
yarn install   # or npm install
yarn start     # or npm start
```

* Frontend expects backend API at: `http://localhost:5000/api`
* Dashboard shows branches, device status, logs in realtime (via polling or WebSocket if enabled).

---

## Important Files to Check

* `backend/tasks.py` — core poller, fetch/forward logic, Access writes, bulk DB inserts.
* `backend/scheduler.py` — APScheduler setup and job registration.
* `backend/exporter.py` — validation and forwarder to End DB.
* `backend/seed_data.py` — seeder to populate Branch & Device tables from CSV/Excel.

---

## CLI Examples

**One-off fetch for a branch**

```bash
python backend/tasks.py --fetch --branch-id 123
```

**Full scan of all active devices**

```bash
python backend/tasks.py --full-scan
```

**Run exporter for a date range**

```bash
python backend/exporter.py --export --from 2025-09-01 --to 2025-09-01
```

**Start scheduler**

```bash
python backend/scheduler.py
```

**Run demo ingestion (from sample file)**

```bash
python backend/tasks.py --demo samples/sample_device_log.csv
```

---

## Key Design Decisions

* **ThreadPoolExecutor:** Parallel device polling to handle 120+ branches concurrently.
* **pyodbc (Access):** Direct writes to Access DB for legacy integration without additional HTTP layers.
* **Bulk Save:** Use `db.session.bulk_save_objects()` for high-volume inserts to improve throughput.
* **Colorama logs:** Colored terminal output for faster manual triage and diagnosis.
* **APScheduler:** Reliable scheduling for per-branch jobs, full scans and retryable tasks.

---

## Performance & Operational Notes

* Tune `ThreadPoolExecutor` worker count and DB bulk size in `config.py` for your environment.
* Monitor Access DB for file locking and disk space; consider rotation or periodic compaction.
* Ship scheduler and application logs to your SIEM (Wazuh/Elastic) for monitoring and alerting.

---

## Future Enhancements

* Add WebSocket push to frontend for live logs & status.
* Implement exponential backoff + smarter retry logic for flaky devices.
* Integrate Prometheus & Grafana for scheduler metrics and alerting.
* Containerize backend & frontend (Docker) for consistent deployments.
* Store device credentials in a secrets manager and add RBAC for API access.

---

## Security & Sensitive Data (IMPORTANT)

* **Never commit** production credentials, device IPs, or personal data. Use `.env` + `config.example` with placeholders.

---

## Contact / Verification

For verification or clarifications about the system, contact: **HOSSAIN ABEDY — abedy.ewu@gmail.com** 
