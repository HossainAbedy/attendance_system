# tasks.py
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

# ---------------------------------------------------------------------
# Access DB insert
# ---------------------------------------------------------------------
def insert_into_access_db(record):
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

    # Prepare a JSON-safe timestamp
    checktime = record.get('CHECKTIME')
    if hasattr(checktime, 'isoformat'):
        checktime_for_emit = checktime.isoformat()
    else:
        checktime_for_emit = str(checktime)

    message = {
        "type": "access",
        "userid": record.get('USERID'),
        "checktime": checktime_for_emit
    }

    # Emit to all connected clients, but don't let emit failures break DB insert flow
    try:
        socketio.emit("access_log", message)
    except Exception:
        # optional: log the exception here with print() if you want visibility
        pass

    # original console print 
    print(Fore.GREEN + f"    [ACCESS ✅] USERID={record['USERID']} CHECKTIME={record['CHECKTIME']}")
# ---------------------------------------------------------------------
# Core fetch function (unchanged)
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


def fetch_and_forward_for_device(device, inspect_only=False):
    """
    Poll a single device, insert new logs into Access DB and Flask DB.
    Emit only aggregated notifications to socket.io to avoid flooding the client.
    Returns number of new logs inserted.
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

    def safe_emit(event, payload):
        try:
            socketio.emit(event, payload)
        except Exception:
            # swallow emit exceptions so DB work is not affected
            pass
    
    def emit_log(device, level, message, extra=None):
        safe_emit('log', {
            "device_id": device.id,
            "device_name": device.name,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "message": message,
            "extra": extra or {},
        })     

    print(Fore.YELLOW + f"\n[DEBUG] Connecting to {device.name} ({device.ip_address}:{device.port})")
    safe_emit('device_status', make_event_payload(device, 'debug', f"Connecting to {device.ip_address}:{device.port}"))
    emit_log(device, 'debug', f"Connecting to {device.ip_address}:{device.port}")

    try:
        conn = zk.connect()
        print(Fore.GREEN + f"[CONNECTED] {device.name}")
        safe_emit('device_status', make_event_payload(device, 'info', "[CONNECTED]"))
        emit_log(device, 'info', "[CONNECTED]")

        conn.disable_device()

        start_time = time.time()
        logs = conn.get_attendance()
        elapsed = time.time() - start_time

        # high-level info
        print(Fore.CYAN + f"[INFO] Retrieved {len(logs)} logs from {device.name} in {elapsed:.2f} seconds")
        safe_emit('device_status', make_event_payload(device, 'info', f"Retrieved {len(logs)} logs", {"count": len(logs)}))
        emit_log(device, 'info', f"Retrieved {len(logs)} logs", {"count": len(logs)})

        # fetch existing record ids from flask db
        existing = {rid for (rid,) in db.session.query(AttendanceLog.record_id)
                    .filter_by(device_id=device.id).all()}

        access_start = time.time()
        flask_start = time.time()
        flask_log_entries = []

        # collect new logs for batch emit later
        new_logs_for_device = []  # list of dicts {rid,user_id,timestamp,status}

        for rec in logs:
            rid = getattr(rec, 'uid', None)
            if rid is None or rid in existing:
                continue

            status_str = str(rec.status) if isinstance(rec.status, int) else getattr(rec.status, 'name', str(rec.status))

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
                # insert into Access
                checktime_iso = insert_into_access_db(access_record)
            except Exception as e:
                # emit an error-level device_status and continue
                print(Fore.RED + f"    [ACCESS ❌] RID {rid}: {e}")
                err_payload = make_event_payload(device, 'error', f"Access DB insert failed for RID {rid}: {e}", {"rid": rid})
                safe_emit('device_status', err_payload)
                emit_log(device, 'error', f"Access DB insert failed for RID {rid}: {e}", {"rid": rid})
                continue

            # prepare flask ORM object (do not commit per-item — we bulk save later)
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

            # aggregate for frontend notification (no per-item emit)
            new_logs_for_device.append({
                "rid": rid,
                "user_id": rec.user_id,
                "timestamp": checktime_iso,
                "status": status_str,
            })

        access_elapsed = time.time() - access_start

        # commit flask DB once for this device
        if flask_log_entries:
            db.session.bulk_save_objects(flask_log_entries)
            db.session.commit()
        flask_elapsed = time.time() - flask_start

        # Emit aggregated batch of new logs for this device (frontend-friendly)
        if new_logs_for_device:
            safe_emit('new_logs_batch', {
                "device_id": device.id,
                "device_name": device.name,
                # include branch_id if device has it (some models do)
                "branch_id": getattr(device, 'branch_id', None),
                "count": len(new_logs_for_device),
                "logs": new_logs_for_device
            })

        # Emit DB insertion times (access / flask) — useful for perf/notifications
        safe_emit('db_insert_times', {
            "device_id": device.id,
            "device_name": device.name,
            "new_count": new_count,
            "access_insert_seconds": round(access_elapsed, 3),
            "flask_insert_seconds": round(flask_elapsed, 3),
        })

        # log a concise summary to console
        print(Fore.MAGENTA + f"[ACCESS INSERT TIME] Inserted {new_count} records into Access DB in {access_elapsed:.2f}s from {device.name}")
        print(Fore.WHITE + f"[FLASK DB INSERT TIME] Inserted {new_count} records into Flask DB in {flask_elapsed:.2f}s from {device.name}")

    except Exception as e:
        safe_emit('device_status', make_event_payload(device, 'error', f"Polling failed: {e}"))
        print(Fore.RED + f"[ERROR] Polling {device.name} failed: {e}")
        emit_log(device, 'error', f"Polling failed: {e}")
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
            safe_emit('device_status', make_event_payload(device, 'info', "[DISCONNECTED]"))
            print(Fore.RED + f"[DISCONNECTED] {device.name}")

        if inspect_only and snapshot:
            fn = f"zk_snapshot_{device.name.replace(' ', '_')}_{datetime.now():%Y%m%d_%H%M%S}.json"
            with open(fn, 'w', encoding='utf-8') as f:
                json.dump(snapshot, f, indent=2, default=str)
            safe_emit('device_status', make_event_payload(device, 'info', f"[SNAPSHOT] saved {len(snapshot)} records to {fn}"))
            print(Fore.GREEN + f"[SNAPSHOT] saved {len(snapshot)} records to {fn}")

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
