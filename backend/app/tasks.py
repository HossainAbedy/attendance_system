# app/tasks.py
import re
import os
import time
import json
import uuid
import pyodbc
import threading
import traceback
from . import db
from zk import ZK
from . import socketio
from flask import current_app
from datetime import datetime, timedelta
from .locks import DirLock, DirLockTimeout
from .access_helpers import upsert_access_userinfo, get_badge_for_device_userid, ensure_user_and_badge
from .models import AccessUserInfo, CheckinOut, AttendanceLog, Badge, Device
from colorama import init as colorama_init, Fore
colorama_init(autoreset=True)

# Configuration constants
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
    try:
        print(raw_text_with_color)
    except Exception:
        print(strip_ansi(raw_text_with_color))

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

    try:
        socketio.emit("console", payload)
    except Exception:
        pass

# ---------------------------------------------------------------------
# Helpers for Access DB (batch-friendly)
# ---------------------------------------------------------------------
def open_access_conn():
    conn_str = (
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
        f"DBQ={ACCESS_DB_PATH};"
    )
    return pyodbc.connect(conn_str, autocommit=False)

def fetch_existing_access_keys(conn, sn=None):
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

def make_event_payload(device, level, message, extra=None):
    return {
        "device_id": device.id,
        "device_name": device.name,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "level": level,
        "message": message,
        "extra": extra or {}
    }

# ---------------------------------------------------------------------
# Device helpers
# ---------------------------------------------------------------------
import socket
IP_V4_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")

def _is_probably_ip(s):
    try:
        return bool(s) and bool(IP_V4_RE.match(str(s)))
    except Exception:
        return False

def _resolve_device_sn(device, conn):
    try:
        if getattr(device, "serial_no", None):
            return str(device.serial_no)
        if getattr(device, "serial", None):
            return str(device.serial)
    except Exception:
        pass

    try:
        for fn in ("get_serialnumber", "get_serial_number", "get_serial", "get_device_sn", "get_device_info"):
            method = getattr(conn, fn, None)
            if callable(method):
                try:
                    v = method()
                    if isinstance(v, dict):
                        for k in ("serial", "serial_number", "sn", "SerialNumber", "device_sn"):
                            if v.get(k):
                                return str(v.get(k))
                    if v:
                        return str(v)
                except Exception:
                    continue
    except Exception:
        pass

    try:
        for attr in ("serial", "sn", "device_sn", "serial_number"):
            maybe = getattr(conn, attr, None)
            if maybe:
                return str(maybe)
    except Exception:
        pass

    try:
        name = getattr(device, "name", None)
        ip = getattr(device, "ip_address", None)
        if name and not _is_probably_ip(name):
            return str(name)
        if ip:
            return str(ip)
    except Exception:
        pass

    return "UNKNOWN"

# ---------------------------------------------------------------------
# Fecther - updated to always add access_checkinout rows and use device_userid
# ---------------------------------------------------------------------
def fetch_and_forward_for_device(device, inspect_only=False):
    zk = ZK(
        device.ip_address,
        port=device.port,
        timeout=5,
        password=0,
        force_udp=False,
        ommit_ping=False
    )
    conn = None
    new_count = 0

    console_emit(Fore.YELLOW + f"\n[DEBUG] Connecting to {device.name} ({device.ip_address}:{device.port})",
                 level="debug", device=device)

    class _LocalDirLock:
        def __init__(self, lock_dir, stale_seconds=60, timeout=15, poll_interval=0.2):
            self.lock_dir = lock_dir
            self.stale_seconds = stale_seconds
            self.timeout = timeout
            self.poll_interval = poll_interval
            self._acquired = False

        def _is_stale(self):
            try:
                m = os.path.getmtime(self.lock_dir)
                return (time.time() - m) > self.stale_seconds
            except Exception:
                return False

        def __enter__(self):
            start = time.time()
            while True:
                try:
                    os.mkdir(self.lock_dir)
                    try:
                        with open(os.path.join(self.lock_dir, "lockinfo.txt"), "w", encoding="utf-8") as fh:
                            fh.write(f"pid={os.getpid()}\ncreated={datetime.utcnow().isoformat()}Z\n")
                    except Exception:
                        pass
                    self._acquired = True
                    return self
                except FileExistsError:
                    if self._is_stale():
                        try:
                            stamp = os.path.join(self.lock_dir, "lockinfo.txt")
                            if os.path.exists(stamp):
                                os.remove(stamp)
                            os.rmdir(self.lock_dir)
                        except Exception:
                            pass
                    if (time.time() - start) >= self.timeout:
                        raise TimeoutError(f"DirLock: timeout acquiring {self.lock_dir}")
                    time.sleep(self.poll_interval)
                except Exception:
                    raise

        def __exit__(self, exc_type, exc, tb):
            if self._acquired:
                try:
                    stamp = os.path.join(self.lock_dir, "lockinfo.txt")
                    if os.path.exists(stamp):
                        os.remove(stamp)
                except Exception:
                    pass
                try:
                    os.rmdir(self.lock_dir)
                except Exception:
                    pass
            self._acquired = False

    try:
        conn = zk.connect()
        console_emit(Fore.GREEN + f"[CONNECTED] {device.name}", level="info", device=device)

        conn.disable_device()

        # 1) fetch users roster and upsert into access_userinfo (replica)
        try:
            users = []
            if hasattr(conn, "get_users"):
                users = conn.get_users()
            elif hasattr(conn, "get_user"):
                try:
                    u = conn.get_user()
                    if u:
                        users = [u]
                except Exception:
                    users = []
            else:
                users = []
        except Exception as e:
            users = []
            console_emit(Fore.YELLOW + f"    [USER FETCH WARN] Could not fetch users from device {device.name}: {e}", level="warning", device=device)

        # resolve device serial (sn) robustly
        sn_val = _resolve_device_sn(device, conn)

        # Use DirLock so two concurrent polls don't race on the replica tables
        lock_dir = os.path.join(os.path.dirname(ACCESS_DB_PATH), "access_lock")
        stale = current_app.config.get("ACCESS_LOCK_STALE_SECONDS", 60)
        timeout = current_app.config.get("ACCESS_LOCK_TIMEOUT", 15)

        with _LocalDirLock(lock_dir, stale_seconds=stale, timeout=timeout):
            # upsert all users into access_userinfo
            upsert_count = 0
            for u in users:
                try:
                    device_userid = getattr(u, "user_id", None) or getattr(u, "uid", None) or getattr(u, "userid", None)
                    if not device_userid:
                        continue
                    device_userid = str(device_userid).strip()
                    name = getattr(u, "name", None) or None

                    console_emit(
                        Fore.BLUE + f"DEBUG: upserting USERID/Badgenumber='{device_userid}' sn='{sn_val}'",
                        level="debug",
                        device=device
                    )

                    # Use device_userid for both USERID and Badgenumber
                    upsert_access_userinfo(db.session, device_userid, device_userid, name=name, sn=sn_val, source="zk_device")
                    upsert_count += 1
                except Exception as e:
                    console_emit(Fore.YELLOW + f"    [USER UPSERT ERR] {e}", level="warning", device=device)
                    try:
                        db.session.rollback()
                    except Exception:
                        pass
                    continue

            if upsert_count:
                console_emit(Fore.CYAN + f"    [USER SYNC] Upserted {upsert_count} users for device {device.name}", level="info", device=device)

            # Optional prune: remove access_userinfo rows for this sn no longer on device
            if current_app.config.get("PRUNE_MISSING_DEVICE_USERS", False):
                try:
                    current_set = {str(getattr(u, "user_id", None) or getattr(u, "uid", None) or getattr(u, "userid",None)).strip() for u in users if (getattr(u, "user_id", None) or getattr(u, "uid", None) or getattr(u,"userid",None))}
                    if current_set:
                        deleted = db.session.query(AccessUserInfo).filter(AccessUserInfo.sn == sn_val, ~AccessUserInfo.USERID.in_(current_set)).delete(synchronize_session=False)
                        db.session.commit()
                        console_emit(Fore.YELLOW + f"    [PRUNE] Removed {deleted} stale access_userinfo rows for sn={sn_val}", level="info", device=device)
                except Exception as e:
                    try:
                        db.session.rollback()
                    except Exception:
                        pass
                    console_emit(Fore.YELLOW + f"    [PRUNE ERR] {e}", level="warning", device=device)

            # 2) fetch attendance logs from device
            start_time = time.time()
            try:
                logs = conn.get_attendance() or []
            except Exception as e:
                logs = []
                console_emit(Fore.RED + f"    [ATT FETCH ERROR] Could not fetch attendance from {device.name}: {e}", level="error", device=device)
            elapsed = time.time() - start_time
            console_emit(Fore.CYAN + f"[INFO] Retrieved {len(logs)} logs from {device.name} in {elapsed:.2f} seconds",
                         level="info", device=device, extra={"count": len(logs)})

            # fetch existing record ids from Flask DB (avoid re-saving same record)
            try:
                existing = {rid for (rid,) in db.session.query(AttendanceLog.record_id).filter_by(device_id=device.id).all()}
            except Exception:
                existing = set()

            # Build badge->USERID map from our local replica (access_userinfo) for quick lookups
            badge_to_userid = {}
            try:
                rows = db.session.query(AccessUserInfo.USERID, AccessUserInfo.Badgenumber).filter(AccessUserInfo.sn == sn_val).all()
                for uid_val, badge_val in rows:
                    if badge_val is not None:
                        badge_to_userid[str(badge_val).strip()] = str(uid_val)
            except Exception:
                badge_to_userid = {}

            # prepare containers for DB inserts
            checkinout_rows = []
            attendance_rows = []
            unmapped_badges = set()
            rec_meta = {}

            # runtime flags
            AUTO_CREATE_USERINFO = current_app.config.get("AUTO_CREATE_USERINFO", False)
            AUTO_CREATE_USERINFO_NAME = current_app.config.get("AUTO_CREATE_USERINFO_NAME", "FLASK_IMPORT")
            ALLOW_INSERT_RAW_BADGE = current_app.config.get("ALLOW_INSERT_RAW_BADGE", True)  # default True so replica fills
            AUTO_CREATE_USERS_FROM_BADGES = current_app.config.get("AUTO_CREATE_USERS_FROM_BADGES", False)
            AUTO_CREATE_USERS_NAME = current_app.config.get("AUTO_CREATE_USERS_NAME", "IMPORTED")

            # CSV debug file paths
            try:
                log_dir = current_app.config.get("SCHEDULER_LOG_DIR", "logs")
            except Exception:
                log_dir = "logs"
            os.makedirs(log_dir, exist_ok=True)
            csv_fn = os.path.join(log_dir, f"access_inserts_{sn_val}_{datetime.now():%Y%m%d}.csv")
            csv_unmapped_fn = os.path.join(log_dir, f"access_unmapped_{sn_val}_{datetime.now():%Y%m%d}.csv")

            for rec in logs:
                rid = getattr(rec, 'uid', None)
                if rid is None:
                    continue

                if rid in existing:
                    continue

                status_str = str(rec.status) if isinstance(rec.status, int) else getattr(rec.status, 'name', str(rec.status))
                device_userid = getattr(rec, 'user_id', None) or getattr(rec, 'userid', None) or getattr(rec, 'uid', None)
                device_userid = str(device_userid) if device_userid is not None else ""

                # resolve canonical badge via helper (optional)
                badge_obj = None
                try:
                    badge_obj = get_badge_for_device_userid(db.session, device_userid, sn=sn_val)
                except Exception:
                    badge_obj = None

                badge_id = badge_obj.id if badge_obj else None
                badge_number = badge_obj.badge_number if badge_obj else None

                # compute access_userid — but even if missing, we'll still add a replica CHECKINOUT using device_userid
                access_userid = None
                if badge_number:
                    ai = db.session.query(AccessUserInfo).filter(
                        AccessUserInfo.Badgenumber == badge_number,
                        AccessUserInfo.sn == sn_val
                    ).one_or_none()
                    if ai:
                        access_userid = ai.USERID

                if not access_userid and device_userid:
                    mapped = badge_to_userid.get(device_userid)
                    if mapped:
                        access_userid = mapped

                # If still not mapped and AUTO_CREATE_USERINFO is enabled, create a minimal replica userinfo
                if not access_userid and AUTO_CREATE_USERINFO and device_userid:
                    try:
                        created = upsert_access_userinfo(db.session, device_userid, device_userid, name=AUTO_CREATE_USERINFO_NAME, sn=sn_val, source="auto_create")
                        if created:
                            access_userid = created.USERID
                            badge_to_userid[str(device_userid)] = access_userid
                    except Exception:
                        access_userid = None

                # If still not mapped and ALLOW_INSERT_RAW_BADGE is True, use device_userid as USERID
                if not access_userid and ALLOW_INSERT_RAW_BADGE and device_userid:
                    access_userid = device_userid

                # If no badge_obj found but AUTO_CREATE_USERS_FROM_BADGES is enabled, try to create central user+badge
                if not badge_obj and AUTO_CREATE_USERS_FROM_BADGES and device_userid:
                    try:
                        created_badge = ensure_user_and_badge(
                            db.session,
                            badgenumber=device_userid,
                            name=None,
                            branch_id=getattr(device, "branch_id", None),
                            device_id=getattr(device, "id", None),
                            default_user_name=AUTO_CREATE_USERS_NAME
                        )
                        if created_badge:
                            badge_obj = created_badge
                            badge_id = created_badge.id
                    except Exception:
                        # ignore creation failures and continue
                        badge_obj = None
                        badge_id = None

                # Track unmapped if nothing resolved
                if not badge_obj and not access_userid:
                    if device_userid:
                        unmapped_badges.add(device_userid)

                # Build replicated CheckinOut (prefer access_userid if we have it)
                co_userid = access_userid if access_userid else device_userid
                co = CheckinOut(
                    USERID=str(co_userid),
                    CHECKTIME=rec.timestamp,
                    CHECKTYPE=status_str,
                    VERIFYCODE="1",
                    SENSORID="1",
                    Memoinfo="FLASK",
                    WorkCode="FLASK",
                    sn=sn_val
                )
                checkinout_rows.append(co)
                rec_meta[rid] = (rec.timestamp.isoformat() if hasattr(rec.timestamp, 'isoformat') else str(rec.timestamp),
                                 co_userid, status_str)

                # build central AttendanceLog entry (always saved)
                log_entry = AttendanceLog(
                    device_id=device.id,
                    record_id=rid,
                    user_id=device_userid,       # canonical / device-provided identifier (string)
                    device_userid=device_userid, # device-local userid (string)
                    badge_id=badge_id,           # normalized FK (integer) when resolved (nullable)
                    timestamp=rec.timestamp,
                    status=status_str
                )
                attendance_rows.append(log_entry)

                new_count += 1

                console_emit(
                    Fore.GREEN + f"    [NEW ✅] RID {rid}, User={device_userid}, Time={rec.timestamp}",
                    level="new", device=device
                )

            # write unmapped badge CSV for review
            if unmapped_badges:
                try:
                    with open(csv_unmapped_fn, "a", encoding="utf-8") as uh:
                        uh.write("badge\n")
                        for b in sorted([x for x in unmapped_badges if x]):
                            uh.write(f"{b}\n")
                    console_emit(Fore.YELLOW + f"    [UNMAPPED] Wrote {len(unmapped_badges)} badges to {csv_unmapped_fn}", level="warning", device=device)
                except Exception:
                    pass

            # commit replica CheckinOut and AttendanceLog in a single transaction
            flask_start = time.time()
            try:
                if attendance_rows:
                    db.session.add_all(attendance_rows)
                if checkinout_rows:
                    db.session.add_all(checkinout_rows)
                db.session.commit()
                flask_elapsed = time.time() - flask_start
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                console_emit(
                    Fore.WHITE
                    + f"[FLASK DB INSERT TIME:{now_str}]\n"
                    f"Insert attempts: {len(attendance_rows)},\n"
                    f"committed: {len(attendance_rows)} records\n"
                    f"into Flask DB in {flask_elapsed:.2f}s\n"
                    f"from {device.name}",
                    level="info",
                    device=device,
                    extra={"flask_seconds": flask_elapsed},
                )
            except Exception as e:
                try:
                    db.session.rollback()
                except Exception:
                    pass
                console_emit(Fore.RED + f"[FLASK DB ERROR] Commit failed: {e}", level="error", device=device)
                try:
                    sample_att = attendance_rows[:5]
                    sample_co = checkinout_rows[:5]
                    console_emit(Fore.RED + f"[DEBUG] sample attendance_rows: {sample_att}", level="error", device=device)
                    console_emit(Fore.RED + f"[DEBUG] sample checkinout_rows: {sample_co}", level="error", device=device)
                except Exception:
                    pass

            # persist serial_no back to devices table if sensible (avoid persisting IPs)
            try:
                if (not getattr(device, "serial_no", None)) and sn_val and not _is_probably_ip(sn_val):
                    device.serial_no = sn_val
                    db.session.add(device)
                    db.session.commit()
                    console_emit(Fore.CYAN + f"    [DEVICE UPDATE] saved serial_no={sn_val} for device {device.name}", level="debug", device=device)
            except Exception:
                try:
                    db.session.rollback()
                except Exception:
                    pass

            # log summary of this device runs
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            console_emit(
                Fore.MAGENTA
                + f"[ACCESS INSERT TIME:{now_str}]\n"
                f"access_checkinout attempts: {len(checkinout_rows)},\n"
                f"attendance rows: {len(attendance_rows)},\n"
                f"from {device.name}",
                level="info",
                device=device,
                extra={"flask_seconds": flask_elapsed},
            )

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

        if inspect_only and 'snapshot' in locals() and snapshot:
            fn = f"zk_snapshot_{device.name.replace(' ', '_')}_{datetime.now():%Y%m%d_%H%M%S}.json"
            try:
                with open(fn, 'w', encoding='utf-8') as f:
                    json.dump(snapshot, f, indent=2, default=str)
                console_emit(Fore.GREEN + f"[SNAPSHOT] saved {len(snapshot)} records to {fn}", level="info", device=device)
            except Exception:
                pass

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
