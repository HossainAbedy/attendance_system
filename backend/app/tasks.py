# tasks.py
import re
import json
import pyodbc
import time
import threading
import traceback
import uuid
from datetime import datetime, timedelta
from zk import ZK
from flask import current_app
from .models import AttendanceLog, Device
from . import db
from . import socketio
from colorama import init as colorama_init, Fore
colorama_init(autoreset=True)

# Path to Access DB and table name
ACCESS_DB_PATH = r"E:\ShareME\SBAC TAO\NewYear25\attendance-system\backend\att2000.mdb"
ACCESS_TABLE = "CHECKINOUT"

# --- Job registry (in-memory)
_JOB_REGISTRY = {}
_JOB_LOCK = threading.Lock()
_JOB_TTL_SECONDS = 60 * 60  # how long to keep finished jobs (1 hour)

# --- Scheduler holder (will be created on demand)
_scheduler = None
_scheduler_lock = threading.Lock()

# ---------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------
def _resolve_app(app):
    try:
        return app._get_current_object()
    except Exception:
        return app

def _now_iso():
    return datetime.utcnow().isoformat()

def _set_job(job_id, payload):
    with _JOB_LOCK:
        _JOB_REGISTRY[job_id] = payload

def prune_old_jobs(ttl_seconds=_JOB_TTL_SECONDS):
    cutoff = datetime.utcnow() - timedelta(seconds=ttl_seconds)
    removed = []
    with _JOB_LOCK:
        for jid, job in list(_JOB_REGISTRY.items()):
            ts_str = job.get('finished_at') or job.get('started_at')
            if not ts_str:
                continue
            try:
                ts = datetime.fromisoformat(ts_str)
            except Exception:
                continue
            if ts < cutoff:
                removed.append(jid)
                del _JOB_REGISTRY[jid]
    if removed:
        print(Fore.CYAN + f"[JOB PRUNE] removed {len(removed)} jobs: {removed}")

def get_job_status(job_id):
    with _JOB_LOCK:
        job = _JOB_REGISTRY.get(job_id)
        if not job:
            return None
        return {
            'job_id': job.get('job_id'),
            'type': job.get('type'),
            'status': job.get('status'),
            'started_at': job.get('started_at'),
            'finished_at': job.get('finished_at'),
            'total': job.get('total'),
            'done': job.get('done'),
            'results': list(job.get('results', [])),
            'error': job.get('error'),
            'branch_id': job.get('branch_id')
        }

def list_jobs(limit=50):
    with _JOB_LOCK:
        jobs = list(_JOB_REGISTRY.values())
    def key(j):
        v = j.get('started_at')
        try:
            return datetime.fromisoformat(v) if v else datetime.min
        except Exception:
            return datetime.min
    jobs.sort(key=key, reverse=True)
    return [get_job_status(j['job_id']) for j in jobs[:limit]]

# -----------------------
# Helper: console emitter
# -----------------------
ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')
COLOR_MAP = {
    Fore.GREEN: 'green',
    Fore.YELLOW: 'yellow',
    Fore.CYAN: 'cyan',
    Fore.BLUE: 'blue',
    Fore.MAGENTA: 'magenta',
    Fore.WHITE: 'white',
    Fore.RED: 'red',
}

def strip_ansi(s: str) -> str:
    return ANSI_RE.sub('', s)

def console_emit(raw_text_with_color: str, level: str = "info", device=None, extra: dict = None):
    """
    Print to console (keeps colorama colors) AND emit a structured 'console' payload
    to socketio for frontend consumption. The emitted text is ANSI-stripped.
    """
    # preserve the original colored print for terminal
    try:
        print(raw_text_with_color)
    except Exception:
        # fallback if printing fails for any reason
        print(strip_ansi(raw_text_with_color))

    # attempt to detect color name (first matching)
    color_name = None
    for code, name in COLOR_MAP.items():
        if code and code in raw_text_with_color:
            color_name = name
            break

    payload = {
        "type": "console",
        "level": level,
        "text": strip_ansi(raw_text_with_color),
        "color": color_name,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    if device is not None:
        payload["device_id"] = getattr(device, "id", None)
        payload["device_name"] = getattr(device, "name", None)
    if extra:
        payload["extra"] = extra

    # emit but don't let failures break program flow
    try:
        socketio.emit("console", payload)
    except Exception:
        pass

# ---------------------------------------------------------------------
# Helpers for Access DB (batch-friendly)
# ---------------------------------------------------------------------
def open_access_conn():
    """
    Open a pyodbc connection to Access DB. autocommit=False so we control
    commit/rollback as one unit per device poll.
    """
    conn_str = (
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
        f"DBQ={ACCESS_DB_PATH};"
    )
    return pyodbc.connect(conn_str, autocommit=False)


def fetch_existing_access_keys(conn, sn=None):
    """
    Returns a set of keys that identify records already present in Access DB
    to avoid duplicate insertion attempts.

    Key format used here: (str(USERID), str(CHECKTIME), str(sn))
    """
    cur = conn.cursor()
    if sn:
        sql = f"SELECT USERID, CHECKTIME, sn FROM {ACCESS_TABLE} WHERE sn = ?"
        cur.execute(sql, (sn,))
    else:
        sql = f"SELECT USERID, CHECKTIME, sn FROM {ACCESS_TABLE}"
        cur.execute(sql)
    rows = cur.fetchall()
    cur.close()

    keys = set()
    for r in rows:
        keys.add((str(r[0]), str(r[1]), str(r[2])))
    return keys


# ---------------------------------------------------------------------
# Event payload helper (kept for parity)
# ---------------------------------------------------------------------
def make_event_payload(device, level, message, extra=None):
    return {
        "device_id": device.id,
        "device_name": device.name,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "level": level,   # "debug","info","new","error","disconnect"
        "message": message,
        "extra": extra or {}
    }


# ---------------------------------------------------------------------
# Main: fetch and forward for device (batch Access, local save, restored prints)
# ---------------------------------------------------------------------
def fetch_and_forward_for_device(device, inspect_only=False):
    """
    Poll a single device, insert new logs into Access DB (batched) and Flask DB.
    Restores your [NEW ✅] and [ACCESS ✅] console_emit lines.
    Returns number of new logs inserted into Flask DB for this device.
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
    access_conn = None
    snapshot = []
    new_count = 0

    console_emit(Fore.YELLOW + f"\n[DEBUG] Connecting to {device.name} ({device.ip_address}:{device.port})",
                 level="debug", device=device)

    try:
        conn = zk.connect()
        console_emit(Fore.GREEN + f"[CONNECTED] {device.name}", level="info", device=device)

        conn.disable_device()

        start_time = time.time()
        logs = conn.get_attendance()
        elapsed = time.time() - start_time

        console_emit(Fore.CYAN + f"[INFO] Retrieved {len(logs)} logs from {device.name} in {elapsed:.2f} seconds",
                     level="info", device=device, extra={"count": len(logs)})

        # fetch existing record ids from Flask DB (avoid re-saving same record)
        existing = {rid for (rid,) in db.session.query(AttendanceLog.record_id)
                    .filter_by(device_id=device.id).all()}

        # Try to open Access DB once for this device/thread
        try:
            access_conn = open_access_conn()
            existing_access = fetch_existing_access_keys(access_conn, sn=(device.serial_no or device.name))
        except Exception as e:
            access_conn = None
            existing_access = set()
            console_emit(Fore.RED + f"    [ACCESS WARN] Could not open Access DB: {e}",
                         level="error", device=device)

        access_start = time.time()
        flask_start = time.time()
        flask_log_entries = []

        # For batching into Access: list of tuples matching the INSERT placeholders
        access_insert_tuples = []
        # Map rid -> (checktime_iso, user_id, status_str) for building summary and emits
        rec_meta = {}

        # Keep track of items pending Access insertion so we can emit ACCESS ✅ after success
        pending_access = {}  # rid -> {"user_id": .., "checktime": ..}

        for rec in logs:
            rid = getattr(rec, 'uid', None)
            if rid is None:
                continue

            # Skip if already present in local Flask DB
            if rid in existing:
                continue

            status_str = str(rec.status) if isinstance(rec.status, int) else getattr(rec.status, 'name', str(rec.status))

            # normalised key to compare with existing_access
            key = (str(rec.user_id), str(rec.timestamp), str(device.serial_no or device.name))

            # prepare flask ORM object (we will bulk save later regardless of Access outcome)
            log_entry = AttendanceLog(
                device_id=device.id,
                record_id=rid,
                user_id=rec.user_id,
                timestamp=rec.timestamp,
                status=status_str
            )
            flask_log_entries.append(log_entry)

            # snapshot entry for inspection / debugging
            access_record = {
                'USERID':     rec.user_id,
                'CHECKTIME':  rec.timestamp,
                'CHECKTYPE':  status_str,
                'VERIFYCODE': 1,
                'SENSORID':   '1',
                'WorkCode':   '0',
                'sn':         device.serial_no or device.name
            }
            snapshot.append(access_record)

            # If Access already has it, emit ACCESS ✅ now (preserve original message)
            if key in existing_access:
                console_emit(
                    Fore.GREEN + f"    [ACCESS ✅] USERID={rec.user_id} CHECKTIME={rec.timestamp}",
                    level="info", device=device
                )
                checktime_iso = rec.timestamp.isoformat() if hasattr(rec.timestamp, 'isoformat') else str(rec.timestamp)
                rec_meta[rid] = (checktime_iso, rec.user_id, status_str)
            else:
                # queue tuple for batch insertion into Access
                access_insert_tuples.append((
                    rec.user_id, rec.timestamp, status_str, 1, '1', '0', device.serial_no or device.name
                ))
                # remember pending access inserts so we can emit success later
                pending_access[rid] = {
                    "user_id": rec.user_id,
                    "checktime": rec.timestamp
                }
                checktime_iso = rec.timestamp.isoformat() if hasattr(rec.timestamp, 'isoformat') else str(rec.timestamp)
                rec_meta[rid] = (checktime_iso, rec.user_id, status_str)

            new_count += 1

            # ORIGINAL [NEW ✅] message restored (we now print when we accepted the record locally)
            console_emit(
                Fore.BLUE + f"    [NEW ✅] RID {rid}, User={rec.user_id}, Time={rec.timestamp}",
                level="new", device=device
            )

        # Batch insert into Access DB (if we have any to insert)
        inserted_ok_count = 0
        if access_conn and access_insert_tuples:
            cur = access_conn.cursor()
            insert_sql = (
                f"INSERT INTO {ACCESS_TABLE} "
                "(USERID, CHECKTIME, CHECKTYPE, VERIFYCODE, SENSORID, WorkCode, sn) "
                "VALUES (?,?,?,?,?,?,?)"
            )
            try:
                # Attempt bulk insert first - faster
                cur.executemany(insert_sql, access_insert_tuples)
                access_conn.commit()
                inserted_ok_count = len(access_insert_tuples)

                # emit ACCESS ✅ for each pending_access we just wrote
                for rid, info in list(pending_access.items()):
                    console_emit(
                        Fore.GREEN + f"    [ACCESS ✅] USERID={info['user_id']} CHECKTIME={info['checktime']}",
                        level="info", device=device
                    )
                    # remove from pending map since handled
                    pending_access.pop(rid, None)

            except Exception as bulk_err:
                # Bulk failed (possible duplicate in the batch or constraint). Fallback to per-row with duplicate handling.
                console_emit(Fore.YELLOW + f"    [ACCESS BULK WARN] Bulk insert failed: {bulk_err}. Falling back to per-row inserts.",
                             level="warning", device=device)
                access_conn.rollback()

                # Per-row fallback (we emit ACCESS ✅ on successful row inserts; duplicates are logged/ignored)
                for t in access_insert_tuples:
                    try:
                        cur.execute(insert_sql, t)
                        access_conn.commit()
                        inserted_ok_count += 1

                        # Emit ACCESS ✅ for this tuple (we don't have the RID directly here).
                        # Use the tuple values (user_id, checktime) to display the message.
                        user_id, checktime = t[0], t[1]
                        console_emit(
                            Fore.GREEN + f"    [ACCESS ✅] USERID={user_id} CHECKTIME={checktime}",
                            level="info", device=device
                        )

                        # remove any matching pending_access entry(s)
                        # best-effort: find rid(s) with same user_id & checktime
                        to_remove = []
                        for prid, info in pending_access.items():
                            if str(info['user_id']) == str(user_id) and str(info['checktime']) == str(checktime):
                                to_remove.append(prid)
                        for pr in to_remove:
                            pending_access.pop(pr, None)

                    except Exception as row_err:
                        msg = str(row_err).lower()
                        if "duplicate" in msg or "unique" in msg or "constraint" in msg:
                            access_conn.rollback()
                            console_emit(Fore.YELLOW + f"    [ACCESS DUP] Duplicate row ignored: USERID={t[0]} CHECKTIME={t[1]} sn={t[6]}",
                                         level="debug", device=device)
                            # remove matching pending_access as it's effectively present
                            to_remove = []
                            for prid, info in pending_access.items():
                                if str(info['user_id']) == str(t[0]) and str(info['checktime']) == str(t[1]):
                                    to_remove.append(prid)
                            for pr in to_remove:
                                pending_access.pop(pr, None)
                        else:
                            access_conn.rollback()
                            console_emit(Fore.RED + f"    [ACCESS ERROR] Failed to insert row USERID={t[0]} CHECKTIME={t[1]}: {row_err}",
                                         level="error", device=device)

                # end per-row fallback
            finally:
                cur.close()

        access_elapsed = time.time() - access_start

        # commit flask DB once for this device
        if flask_log_entries:
            try:
                db.session.bulk_save_objects(flask_log_entries)
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                console_emit(Fore.RED + f"[FLASK DB ERROR] Bulk save failed: {e}", level="error", device=device)
        flask_elapsed = time.time() - flask_start

        # Build aggregated new_logs_for_device using rec_meta (kept for internal use or future emits)
        new_logs_for_device = []
        for rid, (checktime_iso, user_id, status_str) in rec_meta.items():
            new_logs_for_device.append({
                "rid": rid,
                "user_id": user_id,
                "timestamp": checktime_iso,
                "status": status_str,
            })

        # Keep only console emits (no socket.io). Print concise summary (including Access success count).
        console_emit(Fore.MAGENTA + f"[ACCESS INSERT TIME] Insert attempts: {len(access_insert_tuples)}, successful: {inserted_ok_count} records into Access DB in {access_elapsed:.2f}s from {device.name}",
                     level="info", device=device, extra={"access_seconds": access_elapsed})
        console_emit(Fore.WHITE + f"[FLASK DB INSERT TIME] Insert attempts: {len(flask_log_entries)}, committed: {len(flask_log_entries)} records into Flask DB in {flask_elapsed:.2f}s from {device.name}",
                     level="info", device=device, extra={"flask_seconds": flask_elapsed})

    except Exception as e:
        console_emit(Fore.RED + f"[ERROR] Polling {device.name} failed: {e}", level="error", device=device)
    finally:
        if conn:
            try:
                conn.enable_device()
            except Exception:
                pass
            try:
                conn.disconnect()
            except Exception:
                pass
            console_emit(Fore.RED + f"[DISCONNECTED] {device.name}", level="info", device=device)

        if access_conn:
            try:
                access_conn.close()
            except Exception:
                pass

        if inspect_only and snapshot:
            fn = f"zk_snapshot_{device.name.replace(' ', '_')}_{datetime.now():%Y%m%d_%H%M%S}.json"
            with open(fn, 'w', encoding='utf-8') as f:
                json.dump(snapshot, f, indent=2, default=str)
            console_emit(Fore.GREEN + f"[SNAPSHOT] saved {len(snapshot)} records to {fn}", level="info", device=device)

    return new_count

# ---------------------------------------------------------------------
# Background job runner that updates the job registry
# ---------------------------------------------------------------------
def _update_job_result(job_id, device_result):
    with _JOB_LOCK:
        job = _JOB_REGISTRY.get(job_id)
        if not job:
            return
        job['results'].append(device_result)
        job['done'] += 1
        if job['done'] >= job['total']:
            job['status'] = 'finished'
            job['finished_at'] = _now_iso()

def _run_poll_devices_job(app, devices, job_id):
    real_app = _resolve_app(app)
    with real_app.app_context():
        if not devices:
            with _JOB_LOCK:
                job = _JOB_REGISTRY.get(job_id)
                if job:
                    job['status'] = 'finished'
                    job['finished_at'] = _now_iso()
            return

        try:
            for dev in devices:
                try:
                    count = fetch_and_forward_for_device(dev)
                    device_result = {
                        'device_id': dev.id,
                        'name': dev.name,
                        'ip': dev.ip_address,
                        'fetched': int(count),
                        'error': None,
                        'timestamp': _now_iso()
                    }
                    print(Fore.BLUE + f"[JOB {job_id}] {dev.name} -> {count} new")
                except Exception as e:
                    device_result = {
                        'device_id': getattr(dev, 'id', None),
                        'name': getattr(dev, 'name', str(dev)),
                        'ip': getattr(dev, 'ip_address', None),
                        'fetched': 0,
                        'error': str(e),
                        'timestamp': _now_iso()
                    }
                    print(Fore.RED + f"[JOB {job_id} ERROR] {dev}: {e}")
                _update_job_result(job_id, device_result)
        except Exception as e:
            with _JOB_LOCK:
                job = _JOB_REGISTRY.get(job_id)
                if job:
                    job['status'] = 'failed'
                    job['finished_at'] = _now_iso()
                    job['error'] = str(e)

# ---------------------------------------------------------------------
# Public job starters (one-off)
# ---------------------------------------------------------------------
def start_poll_all_job(app):
    from .models import Device
    real_app = _resolve_app(app)
    with real_app.app_context():
        devices = Device.query.all()

    job_id = str(uuid.uuid4())
    payload = {
        'job_id': job_id,
        'type': 'poll_all',
        'status': 'running',
        'started_at': _now_iso(),
        'finished_at': None,
        'total': len(devices),
        'done': 0,
        'results': [],
        'error': None
    }
    _set_job(job_id, payload)

    if payload['total'] == 0:
        with _JOB_LOCK:
            payload['status'] = 'finished'
            payload['finished_at'] = _now_iso()
        return job_id

    thread = threading.Thread(target=_run_poll_devices_job, args=(real_app, devices, job_id), daemon=True)
    thread.start()
    print(Fore.CYAN + f"[JOB STARTED] id={job_id} (all devices, total={payload['total']})")
    return job_id

def start_poll_branch_job(app, branch_id):
    from .models import Device
    real_app = _resolve_app(app)
    with real_app.app_context():
        devices = Device.query.filter_by(branch_id=branch_id).all()

    job_id = str(uuid.uuid4())
    payload = {
        'job_id': job_id,
        'type': 'poll_branch',
        'branch_id': branch_id,
        'status': 'running',
        'started_at': _now_iso(),
        'finished_at': None,
        'total': len(devices),
        'done': 0,
        'results': [],
        'error': None
    }
    _set_job(job_id, payload)

    if payload['total'] == 0:
        with _JOB_LOCK:
            payload['status'] = 'finished'
            payload['finished_at'] = _now_iso()
        return job_id

    thread = threading.Thread(target=_run_poll_devices_job, args=(real_app, devices, job_id), daemon=True)
    thread.start()
    print(Fore.CYAN + f"[JOB STARTED] id={job_id} (branch={branch_id}, total={payload['total']})")
    return job_id

def _make_scheduler_job_record(job_id, job_type, meta=None):
    payload = {
        'job_id': job_id,
        'type': job_type,
        'status': 'running',
        'started_at': _now_iso(),
        'finished_at': None,
        'total': 1,
        'done': 0,
        'results': [],
        'meta': meta or {},
        'error': None
    }
    return payload

def _resolve_app_object(maybe_proxy_or_app):
    """
    Ensure we return a real Flask app object, not a LocalProxy.
    If the argument is a LocalProxy (has _get_current_object), call that.
    Otherwise try _resolve_app (your existing helper) as a fallback.
    """
    try:
        # LocalProxy has _get_current_object
        if hasattr(maybe_proxy_or_app, "_get_current_object"):
            return maybe_proxy_or_app._get_current_object()
    except Exception:
        pass

    # fallback to your resolver (keeps original behaviour)
    return _resolve_app(maybe_proxy_or_app)


def start_scheduler_job(app, interval_seconds: int = None):
    real_app = _resolve_app_object(app)

    job_id = str(uuid.uuid4())
    meta = {}
    if interval_seconds is not None:
        meta['interval_seconds'] = int(interval_seconds)

    payload = _make_scheduler_job_record(job_id, 'start_scheduler', meta=meta)
    _set_job(job_id, payload)

    def _task(resolved_app, job_id, interval_seconds):
        try:
            # Use the resolved Flask app object directly
            with resolved_app.app_context():
                if interval_seconds is not None:
                    start_recurring_scheduler(resolved_app, interval_seconds=interval_seconds)
                else:
                    start_recurring_scheduler(resolved_app)

            with _JOB_LOCK:
                job = _JOB_REGISTRY.get(job_id)
                if job:
                    job['done'] = 1
                    job['status'] = 'finished'
                    job['finished_at'] = _now_iso()
                    job['results'].append({'message': 'scheduler started', 'timestamp': _now_iso()})
        except Exception:
            tb = traceback.format_exc()
            print(Fore.RED + f"[JOB ERROR] start_scheduler_job {job_id}\n{tb}")
            with _JOB_LOCK:
                job = _JOB_REGISTRY.get(job_id)
                if job:
                    job['status'] = 'failed'
                    job['finished_at'] = _now_iso()
                    job['error'] = tb

    # pass the concrete Flask app object into the thread
    thread = threading.Thread(target=_task, args=(real_app, job_id, interval_seconds), daemon=True)
    thread.start()
    print(Fore.CYAN + f"[JOB STARTED] id={job_id} (start_scheduler meta={meta})")
    return job_id


def stop_scheduler_job(app):
    real_app = _resolve_app_object(app)

    job_id = str(uuid.uuid4())
    payload = _make_scheduler_job_record(job_id, 'stop_scheduler', meta={})
    _set_job(job_id, payload)

    def _task(resolved_app, job_id):
        try:
            with resolved_app.app_context():
                stop_recurring_scheduler()

            with _JOB_LOCK:
                job = _JOB_REGISTRY.get(job_id)
                if job:
                    job['done'] = 1
                    job['status'] = 'finished'
                    job['finished_at'] = _now_iso()
                    job['results'].append({'message': 'scheduler stopped', 'timestamp': _now_iso()})
        except Exception:
            tb = traceback.format_exc()
            print(Fore.RED + f"[JOB ERROR] stop_scheduler_job {job_id}\n{tb}")
            with _JOB_LOCK:
                job = _JOB_REGISTRY.get(job_id)
                if job:
                    job['status'] = 'failed'
                    job['finished_at'] = _now_iso()
                    job['error'] = tb

    thread = threading.Thread(target=_task, args=(real_app, job_id), daemon=True)
    thread.start()
    print(Fore.CYAN + f"[JOB STARTED] id={job_id} (stop_scheduler)")
    return job_id

# ---------------------------------------------------------------------
# Recurring scheduler control (start/stop) - must be called explicitly
# ---------------------------------------------------------------------
from concurrent.futures import ThreadPoolExecutor, as_completed
def _poll_all_for_scheduler(app):
    print(Fore.MAGENTA + f"[SCHEDULER] Dispatching polling for devices…")
    real_app = _resolve_app(app)
    with real_app.app_context():
        devices = Device.query.all()

    max_workers = current_app.config.get("MAX_POLL_WORKERS", 10) if current_app else 10

    def run_with_app_context(dev, app):
        with app.app_context():
            return fetch_and_forward_for_device(dev)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(run_with_app_context, dev, real_app): dev for dev in devices}
        for future in as_completed(futures):
            dev = futures[future]
            try:
                count = future.result()
                print(Fore.BLUE + f"[SCHEDULER] {dev.name}: {count} new logs")
            except Exception as e:
                print(Fore.RED + f"[SCHEDULER ERROR] {dev.name}: {e}")


def start_recurring_scheduler(app, interval_seconds=3600, prune_interval_seconds=600):
    """
    Create and start a BackgroundScheduler that runs the polling job every `interval_seconds`.
    Call this from your endpoint or app factory when you want recurring sync to begin.
    """
    global _scheduler
    with _scheduler_lock:
        if _scheduler and _scheduler.running:
            print(Fore.CYAN + "[SCHEDULER] already running")
            return

        from apscheduler.schedulers.background import BackgroundScheduler
        real_app = _resolve_app(app)
        _scheduler = BackgroundScheduler()
        _scheduler.add_job(_poll_all_for_scheduler, 'interval', seconds=interval_seconds, args=[real_app], id="zk_poll_job")
        _scheduler.add_job(prune_old_jobs, 'interval', seconds=prune_interval_seconds, args=[_JOB_TTL_SECONDS], id="job_prune")
        _scheduler.start()
        print(Fore.CYAN + f"[SCHEDULER] Started recurring polling every {interval_seconds} seconds.")

def stop_recurring_scheduler():
    """
    Stop and shutdown the recurring scheduler if it exists.
    """
    global _scheduler
    with _scheduler_lock:
        if not _scheduler:
            print("[SCHEDULER] no scheduler to stop")
            return
        try:
            _scheduler.remove_job("zk_poll_job")
        except Exception:
            pass
        try:
            _scheduler.remove_job("job_prune")
        except Exception:
            pass
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            pass
        _scheduler = None
        print("[SCHEDULER] Stopped and shutdown.")

# End of file
