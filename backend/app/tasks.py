import json
import pyodbc
import time
from datetime import datetime
from zk import ZK
from flask import current_app
from .models import AttendanceLog, Device
from . import db
from colorama import init as colorama_init, Fore, Style
colorama_init(autoreset=True)  # Automatically resets colors after each print

# Path to Access DB and table name
ACCESS_DB_PATH = r"E:\ShareME\SBAC TAO\NewYear25\attendance-system\backend\att2000.mdb"
ACCESS_TABLE   = "CHECKINOUT"

def insert_into_access_db(record):
    """
    Insert one attendance record into the Access DB's CHECKINOUT table.
    """
    conn_str = (
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
        f"DBQ={ACCESS_DB_PATH};"
    )
    conn = pyodbc.connect(conn_str)
    cur = conn.cursor()

    sql = (
        f"INSERT INTO {ACCESS_TABLE} ("
        "USERID, CHECKTIME, CHECKTYPE, VERIFYCODE, SENSORID, WorkCode, sn) "
        "VALUES (?,?,?,?,?,?,?)"
    )
    cur.execute(sql, (
        record['USERID'], record['CHECKTIME'], record['CHECKTYPE'],
        record['VERIFYCODE'], record['SENSORID'], record['WorkCode'], record['sn']
    ))
    conn.commit()
    cur.close()
    conn.close()
    print(Fore.GREEN + f"    [ACCESS ✅] USERID={record['USERID']} CHECKTIME={record['CHECKTIME']}")

def fetch_and_forward_for_device(device, inspect_only=False):
    """
    Fetch new logs from a ZKTeco device, insert into Access DB, and record in Flask DB.
    Returns count of new logs.
    """
    zk = ZK(
        device.ip_address,
        port=device.port,
        timeout=5,
        password=0,
        force_udp=False,
        ommit_ping=False
    )
    conn = None
    snapshot = []
    new_count = 0

    print(Fore.YELLOW + f"\n[DEBUG] Connecting to {device.name} ({device.ip_address}:{device.port})")
    try:
        conn = zk.connect()
        print(Fore.GREEN + f"[CONNECTED] {device.name}")
        conn.disable_device()

        start_time = time.time()
        logs = conn.get_attendance()
        elapsed = time.time() - start_time
        print(Fore.CYAN + f"[INFO] Retrieved {len(logs)} logs from {device.name} in {elapsed:.2f} seconds")

        # Dedupe by existing record_ids
        existing = {rid for (rid,) in db.session.query(AttendanceLog.record_id)
                    .filter_by(device_id=device.id).all()}

        access_start = time.time()
        flask_start = time.time()

        flask_log_entries = []

        for rec in logs:
            rid = getattr(rec, 'uid', None)
            if rid is None or rid in existing:
                continue

            status_str = str(rec.status) if isinstance(rec.status, int) else getattr(rec.status, 'name', str(rec.status))

            # Build record for Access
            access_record = {
                'USERID':     rec.user_id,
                'CHECKTIME':  rec.timestamp,
                'CHECKTYPE':  status_str,
                'VERIFYCODE': 1,
                'SENSORID':   '1',
                'WorkCode':   '0',
                'sn':         device.serial_no or device.name
            }

            try:
                insert_into_access_db(access_record)
            except Exception as e:
                print(Fore.RED + f"    [ACCESS ❌] RID {rid}: {e}")

            # Build object for Flask DB (but don't insert yet)
            log_entry = AttendanceLog(
                device_id=device.id,
                record_id=rid,
                user_id=rec.user_id,
                timestamp=rec.timestamp,
                status=status_str
            )
            flask_log_entries.append(log_entry)

            snapshot.append(access_record)
            new_count += 1
            print(Fore.BLUE + f"    [NEW] RID {rid}, User={rec.user_id}, Time={rec.timestamp}")

        access_elapsed = time.time() - access_start

        # Bulk insert into Flask DB
        if flask_log_entries:
            db.session.bulk_save_objects(flask_log_entries)
            db.session.commit()

        flask_elapsed = time.time() - flask_start

        print(Fore.MAGENTA + f"[ACCESS INSERT TIME] Inserted {new_count} records into Access DB in {access_elapsed:.2f} seconds from {device.name}")
        print(Fore.WHITE + f"[FLASK DB INSERT TIME] Inserted {new_count} records into Flask DB in {flask_elapsed:.2f} seconds from {device.name}")

    except Exception as e:
        print(Fore.RED + f"[ERROR] Polling {device.name} failed: {e}")
    finally:
        if conn:
            conn.enable_device()
            conn.disconnect()
            print(Fore.RED + f"[DISCONNECTED] {device.name}")

        # Snapshot if requested
        if inspect_only and snapshot:
            fn = f"zk_snapshot_{device.name.replace(' ', '_')}_{datetime.now():%Y%m%d_%H%M%S}.json"
            with open(fn, 'w', encoding='utf-8') as f:
                json.dump(snapshot, f, indent=2, default=str)
            print(Fore.GREEN + f"[SNAPSHOT] saved {len(snapshot)} records to {fn}")

    return new_count


# Scheduler with ThreadPoolExecutor
from concurrent.futures import ThreadPoolExecutor, as_completed

def run_with_context(app, device):
    with app.app_context():
        return fetch_and_forward_for_device(device)

def init_scheduler(app):
    from apscheduler.schedulers.background import BackgroundScheduler
    from .models import Device

    scheduler = BackgroundScheduler()
    interval = app.config.get("POLL_INTERVAL", 3600)

    def poll_all():
        print(Fore.MAGENTA + f"[SCHEDULER] Dispatching polling for devices…")

        with app.app_context():
            devices = Device.query.all()

        max_workers = app.config.get("MAX_POLL_WORKERS", 10)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(run_with_context, app, dev): dev for dev in devices}

            for future in as_completed(futures):
                dev = futures[future]
                try:
                    count = future.result()
                    print(Fore.BLUE + f"[SCHEDULER] {dev.name}: {count} new logs")
                except Exception as e:
                    print(Fore.RED + f"[SCHEDULER ERROR] {dev.name}: {e}")

    scheduler.add_job(poll_all, 'interval', seconds=interval, id="zk_poll_job")
    scheduler.start()
    print(Fore.CYAN + f"[SCHEDULER] Started polling every {interval} seconds with up to {app.config.get('MAX_POLL_WORKERS', 10)} workers.")

