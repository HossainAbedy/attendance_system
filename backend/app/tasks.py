# app/tasks.py
import re
import os
import time
import json
import threading
import traceback
from datetime import datetime, timedelta
from flask import current_app
from zk import ZK
from colorama import init as colorama_init, Fore
from . import db, socketio
from .locks import DirLock, DirLockTimeout
from .access_helpers import upsert_access_userinfo, get_badge_for_device_userid, ensure_user_and_badge
from .models import AccessUserInfo, CheckinOut, AttendanceLog, Badge, Device

colorama_init(autoreset=True)

# Job registry & locks
_JOB_REGISTRY = {}
_JOB_LOCK = threading.Lock()
_JOB_TTL_SECONDS = 60 * 60

# -----------------------
# Console / socket emitter
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
    return ANSI_RE.sub('', s) if s else s

def console_emit(raw_text_with_color: str, level: str = "info", device=None, extra: dict = None):
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

# -------------------------
# Small device helper utils
# -------------------------
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
        for fn in ("get_serialnumber", "get_serial_number", "get_serial", "get_device_sn", "get_device_info", "get_serialno"):
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
            maybe = getattr(conn, attr, None) or getattr(device, attr, None)
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

# -------------------------
# Job registry helpers
# -------------------------
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
        console_emit(Fore.CYAN + f"[JOB PRUNE] removed {len(removed)} jobs: {removed}", level="debug")

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

# -------------------------
# Fetcher (preserves replica behavior)
# -------------------------
def fetch_and_forward_for_device(device, inspect_only=False):
    zk = ZK(
        device.ip_address,
        port=getattr(device, "port", None) or 4370,
        timeout=5,
        password=0,
        force_udp=False,
        ommit_ping=False
    )
    conn = None
    new_count = 0
    snapshot = None
    console_emit(Fore.YELLOW + f"\n[DEBUG] Connecting to {device.name} ({device.ip_address}:{getattr(device, 'port', None)})",
                 level="debug", device=device)
    try:
        conn = zk.connect()
        console_emit(Fore.GREEN + f"[CONNECTED] {device.name}", level="info", device=device)
        try:
            conn.disable_device()
        except Exception:
            pass
        # Try get users from device
        users = []
        try:
            if hasattr(conn, "get_users"):
                users = conn.get_users() or []
            elif hasattr(conn, "get_user"):
                u = conn.get_user()
                if u:
                    users = [u]
        except Exception as e:
            users = []
            console_emit(Fore.YELLOW + f"    [USER FETCH WARN] Could not fetch users from device {device.name}: {e}", level="warning", device=device)

        sn_val = _resolve_device_sn(device, conn)
        # DirLock to avoid concurrent replica writes for same folder
        lock_dir = os.path.join(current_app.config.get("REPLICA_LOCK_DIR", os.path.dirname(current_app.config.get("SCHEDULER_LOG_DIR", "logs"))), f"access_lock_{sn_val}")
        stale = current_app.config.get("ACCESS_LOCK_STALE_SECONDS", 60)
        timeout = current_app.config.get("ACCESS_LOCK_TIMEOUT", 15)

        with DirLock(lock_dir, stale_seconds=stale, timeout=timeout):
            # Upsert users into AccessUserInfo (replica)
            upsert_count = 0
            for u in users:
                try:
                    device_userid = getattr(u, "user_id", None) or getattr(u, "uid", None) or getattr(u, "userid", None)
                    if not device_userid:
                        continue
                    device_userid = str(device_userid).strip()
                    name = getattr(u, "name", None) or None
                    console_emit(Fore.YELLOW + f"DEBUG: upserting USERID/Badgenumber='{device_userid}' sn='{sn_val}'",
                                 level="debug", device=device)
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

            # Optionally prune missing users from replica if configured
            if current_app.config.get("PRUNE_MISSING_DEVICE_USERS", False):
                try:
                    current_set = {str(getattr(u, "user_id", None) or getattr(u, "uid", None) or getattr(u,"userid",None)).strip() for u in users if (getattr(u, "user_id", None) or getattr(u, "uid", None) or getattr(u,"userid",None))}
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

            # fetch attendance logs
            start_time = time.time()
            try:
                logs = conn.get_attendance() or []
            except Exception as e:
                logs = []
                console_emit(Fore.RED + f"    [ATT FETCH ERROR] Could not fetch attendance from {device.name}: {e}", level="error", device=device)
            elapsed = time.time() - start_time
            console_emit(Fore.BLUE + f"[INFO] Retrieved {len(logs)} logs from {device.name} in {elapsed:.2f}s",
                         level="info", device=device, extra={"count": len(logs)})

            # fetch existing record ids from Flask DB (avoid re-saving duplicates)
            try:
                existing = {rid for (rid,) in db.session.query(AttendanceLog.record_id).filter_by(device_id=device.id).all()}
            except Exception:
                existing = set()

            # Build badge -> USERID map from replica AccessUserInfo
            badge_to_userid = {}
            try:
                rows = db.session.query(AccessUserInfo.USERID, AccessUserInfo.Badgenumber).filter(AccessUserInfo.sn == sn_val).all()
                for uid_val, badge_val in rows:
                    if badge_val is not None:
                        badge_to_userid[str(badge_val).strip()] = str(uid_val)
            except Exception:
                badge_to_userid = {}

            # prepare containers
            checkinout_rows = []
            attendance_rows = []
            unmapped_badges = set()
            rec_meta = {}

            # runtime flags
            AUTO_CREATE_USERINFO = current_app.config.get("AUTO_CREATE_USERINFO", False)
            AUTO_CREATE_USERINFO_NAME = current_app.config.get("AUTO_CREATE_USERINFO_NAME", "FLASK_IMPORT")
            ALLOW_INSERT_RAW_BADGE = current_app.config.get("ALLOW_INSERT_RAW_BADGE", True)
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

                # resolve canonical badge via helper
                badge_obj = None
                try:
                    badge_obj = get_badge_for_device_userid(db.session, device_userid, sn=sn_val)
                except Exception:
                    badge_obj = None

                badge_id = badge_obj.id if badge_obj else None
                badge_number = badge_obj.badge_number if badge_obj else None

                # compute access_userid via replica AccessUserInfo
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

                # optionally auto-create AccessUserInfo rows
                if not access_userid and AUTO_CREATE_USERINFO and device_userid:
                    try:
                        created = upsert_access_userinfo(db.session, device_userid, device_userid, name=AUTO_CREATE_USERINFO_NAME, sn=sn_val, source="auto_create")
                        if created:
                            access_userid = created.USERID
                            badge_to_userid[str(device_userid)] = access_userid
                    except Exception:
                        access_userid = None

                # fallback to using device_userid as USERID for replicas
                if not access_userid and ALLOW_INSERT_RAW_BADGE and device_userid:
                    access_userid = device_userid

                # optionally create central user+badge
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
                        badge_obj = None
                        badge_id = None

                if not badge_obj and not access_userid and device_userid:
                    unmapped_badges.add(device_userid)

                # Build CheckinOut replica row
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

                # central AttendanceLog
                log_entry = AttendanceLog(
                    device_id=device.id,
                    record_id=rid,
                    user_id=device_userid,
                    device_userid=device_userid,
                    badge_id=badge_id,
                    timestamp=rec.timestamp,
                    status=status_str
                )
                attendance_rows.append(log_entry)
                new_count += 1

                console_emit(Fore.GREEN + f"    [NEW ✅] RID {rid}, User={device_userid}, Time={rec.timestamp}",
                             level="new", device=device)

            # write unmapped badges CSV for review
            if unmapped_badges:
                try:
                    with open(csv_unmapped_fn, "a", encoding="utf-8") as uh:
                        uh.write("badge\n")
                        for b in sorted([x for x in unmapped_badges if x]):
                            uh.write(f"{b}\n")
                    console_emit(Fore.YELLOW + f"    [UNMAPPED] Wrote {len(unmapped_badges)} badges to {csv_unmapped_fn}", level="warning", device=device)
                except Exception:
                    pass

            # commit both replica CheckinOut and AttendanceLog
            try:
                insert_start = time.time()
                if attendance_rows:
                    db.session.add_all(attendance_rows)
                if checkinout_rows:
                    db.session.add_all(checkinout_rows)
                db.session.commit()
                insert_elasped = time.time() - insert_start
                console_emit(Fore.WHITE + f"[FLASK DB] Committed {len(attendance_rows)} AttendanceLog and {len(checkinout_rows)} CheckinOut rows from {device.name} in {insert_elasped:.2f}s", level="info", device=device)
            except Exception as e:
                try:
                    db.session.rollback()
                except Exception:
                    pass
                console_emit(Fore.RED + f"[FLASK DB ERROR] Commit failed: {e}", level="error", device=device)

            # persist serial_no to device if sensible
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

            console_emit(Fore.MAGENTA + f"[SUCCESS ✅]", level="info", device=device)

    except Exception as e:
        console_emit(Fore.RED + f"[ERROR] Polling {getattr(device, 'name', str(device))} failed: {e}", level="error", device=device)
        current_app.logger.exception("fetch_and_forward_for_device exception")
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

# -------------------------
# Job runner: update job registry
# -------------------------
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
                    console_emit(Fore.BLUE + f"[JOB {job_id}] {dev.name} -> {count} new", level="debug", device=dev)
                except Exception as e:
                    device_result = {
                        'device_id': getattr(dev, 'id', None),
                        'name': getattr(dev, 'name', str(dev)),
                        'ip': getattr(dev, 'ip_address', None),
                        'fetched': 0,
                        'error': str(e),
                        'timestamp': _now_iso()
                    }
                    console_emit(Fore.RED + f"[JOB {job_id} ERROR] {dev}: {e}", level="error", device=dev)
                _update_job_result(job_id, device_result)
        except Exception as e:
            with _JOB_LOCK:
                job = _JOB_REGISTRY.get(job_id)
                if job:
                    job['status'] = 'failed'
                    job['finished_at'] = _now_iso()
                    job['error'] = str(e)
            console_emit(Fore.RED + f"[JOB ERROR] {e}", level="error")
