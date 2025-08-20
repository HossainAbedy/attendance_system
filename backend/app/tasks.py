# tasks.py
import re
import json
import pyodbc
import time
import threading
import traceback
import uuid
import os
from .locks import DirLock, DirLockTimeout
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

        # Prepare containers used for both Access and Flask work
        access_insert_tuples = []
        flask_log_entries = []
        snapshot = []
        rec_meta = {}
        pending_access = {}

        # We'll hold the Access lock while we:
        #  - read existing Access keys,
        #  - decide which records need inserting,
        #  - perform the inserts (bulk or fallback),
        # then close Access connection and release the lock.
        lock_dir = os.path.join(os.path.dirname(ACCESS_DB_PATH), "access_lock")
        stale = current_app.config.get("ACCESS_LOCK_STALE_SECONDS", 60)
        timeout = current_app.config.get("ACCESS_LOCK_TIMEOUT", 15)

        # Acquire lock and do Access-related prep + insert while holding it.
        try:
            with DirLock(lock_dir, stale_seconds=stale, timeout=timeout):
                # Open Access DB under lock
                try:
                    access_conn = open_access_conn()
                    existing_access = fetch_existing_access_keys(access_conn, sn=(device.serial_no or device.name))
                except Exception as e:
                    access_conn = None
                    existing_access = set()
                    console_emit(Fore.RED + f"    [ACCESS WARN] Could not open Access DB: {e}",
                                 level="error", device=device)

                # Build Flask entries & Access tuples while checking existing_access
                for rec in logs:
                    rid = getattr(rec, 'uid', None)
                    if rid is None:
                        continue

                    # Skip if already present in local Flask DB
                    if rid in existing:
                        continue

                    status_str = str(rec.status) if isinstance(rec.status, int) else getattr(rec.status, 'name', str(rec.status))

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

                    # normalised key to compare with existing_access
                    key = (str(rec.user_id), str(rec.timestamp), str(device.serial_no or device.name))

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

                # Now perform batch insert into Access DB (if we have any to insert)
                inserted_ok_count = 0
                access_start = time.time()
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
                        try:
                            access_conn.rollback()
                        except Exception:
                            pass

                        # Per-row fallback (we emit ACCESS ✅ on successful row inserts; duplicates are logged/ignored)
                        for t in access_insert_tuples:
                            try:
                                cur.execute(insert_sql, t)
                                access_conn.commit()
                                inserted_ok_count += 1

                                # Emit ACCESS ✅ for this tuple (we don't have the RID directly here).
                                user_id, checktime = t[0], t[1]
                                console_emit(
                                    Fore.GREEN + f"    [ACCESS ✅] USERID={user_id} CHECKTIME={checktime}",
                                    level="info", device=device
                                )

                                # remove any matching pending_access entry(s)
                                to_remove = []
                                for prid, info in pending_access.items():
                                    if str(info['user_id']) == str(user_id) and str(info['checktime']) == str(checktime):
                                        to_remove.append(prid)
                                for pr in to_remove:
                                    pending_access.pop(pr, None)

                            except Exception as row_err:
                                msg = str(row_err).lower()
                                if "duplicate" in msg or "unique" in msg or "constraint" in msg:
                                    try:
                                        access_conn.rollback()
                                    except Exception:
                                        pass
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
                                    try:
                                        access_conn.rollback()
                                    except Exception:
                                        pass
                                    console_emit(Fore.RED + f"    [ACCESS ERROR] Failed to insert row USERID={t[0]} CHECKTIME={t[1]}: {row_err}",
                                                 level="error", device=device)

                        # end per-row fallback
                    finally:
                        try:
                            cur.close()
                        except Exception:
                            pass

                    access_elapsed = time.time() - access_start
                else:
                    # no access inserts performed
                    access_elapsed = 0.0

                # Close access_conn under the lock before releasing
                if access_conn:
                    try:
                        access_conn.close()
                    except Exception:
                        pass

        except DirLockTimeout:
            # Could not acquire lock in time — skip Access writes for this device
            console_emit(Fore.YELLOW + f"    [ACCESS LOCK] Could not acquire Access lock within {timeout}s. Skipping Access writes for device {device.name}",
                         level="warning", device=device)
            # nothing was written to Access; set defaults
            access_conn = None
            existing_access = set()
            access_insert_tuples = []
            inserted_ok_count = 0
            access_elapsed = 0.0

        # commit flask DB once for this device (outside the Access lock)
        flask_start = time.time()
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

        # Get current time string
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Keep only console emits (no socket.io). Print concise summary (including Access success count).
        console_emit(
            Fore.MAGENTA
            + f"[ACCESS INSERT TIME:{now_str}]\n"
            f"Insert attempts: {len(access_insert_tuples)},\n"
            f"successful: {inserted_ok_count} records\n"
            f"into Access DB in {access_elapsed:.2f}s\n"
            f"from {device.name}",
            level="info",
            device=device,
            extra={"access_seconds": access_elapsed},
        )

        console_emit(
            Fore.WHITE
            + f"[FLASK DB INSERT TIME:{now_str}]\n"
            f"Insert attempts: {len(flask_log_entries)},\n"
            f"committed: {len(flask_log_entries)} records\n"
            f"into Flask DB in {flask_elapsed:.2f}s\n"
            f"from {device.name}",
            level="info",
            device=device,
            extra={"flask_seconds": flask_elapsed},
        )

    except Exception as e:
        console_emit(Fore.RED + f"[ERROR] Polling {device.name} failed: {e}", level="error", device=device)
        # Ensure we still increment nothing or fail gracefully (rethrow optional)
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

        # ensure access_conn closed if still open (defensive)
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

