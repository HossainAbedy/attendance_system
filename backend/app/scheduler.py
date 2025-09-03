# backend/app/scheduler.py
import os
import sys
import uuid
import time
import json
import threading
import traceback
import contextlib
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import current_app
from colorama import Fore, Style, init as colorama_init

# initialize colorama (keeps ANSI codes)
colorama_init(autoreset=False)

# Use the canonical job registry & helpers from tasks.py to avoid duplication.
# If tasks.py isn't ready yet, fallback to a minimal local implementation.
try:
    # Import the registry, lock and helpers from tasks.py
    from .tasks import _JOB_REGISTRY, _JOB_LOCK, _set_job, _now_iso, prune_old_jobs  # noqa
except Exception:
    # Fallback local definitions (temporary; remove once tasks.py has the real ones)
    _JOB_REGISTRY = {}
    _JOB_LOCK = threading.Lock()

    def _set_job(job_id, payload):
        with _JOB_LOCK:
            _JOB_REGISTRY[job_id] = payload

    def _now_iso():
        return datetime.utcnow().isoformat() + "Z"

    # Minimal no-op prune implementation (keeps scheduler safe if prune is referenced)
    def prune_old_jobs(ttl_seconds=None):
        return

# TTL (can still be overridden via env/config)
_JOB_TTL_SECONDS = int(os.environ.get("JOB_TTL_SECONDS", 24 * 3600))

_scheduler = None
_scheduler_lock = threading.Lock()

# Run-capture globals (per poll run)
_RUN_FH = None
_RUN_REDIRECT_CTX = None
_RUN_META = {}
_RUN_LOCK = threading.Lock()


# -------------------------
# Helpers: formatting / job registry
# -------------------------
def _now_iso():
    return datetime.utcnow().isoformat() + "Z"


def _set_job(job_id, payload):
    with _JOB_LOCK:
        _JOB_REGISTRY[job_id] = payload


def _resolve_app(maybe_proxy_or_app):
    """
    Resolve a Flask app object. Accepts LocalProxy, actual Flask, or current_app.
    """
    try:
        if hasattr(maybe_proxy_or_app, "_get_current_object"):
            return maybe_proxy_or_app._get_current_object()
    except Exception:
        pass

    # If it's likely a Flask app already, return as-is
    try:
        # simple duck-typing
        if hasattr(maybe_proxy_or_app, "app_context"):
            return maybe_proxy_or_app
    except Exception:
        pass

    # fallback to current_app
    try:
        return current_app._get_current_object()
    except Exception:
        # last resort: return the original object
        return maybe_proxy_or_app


# Export job globals (use same registry)
_EXPORT_LOCK = threading.Lock()   # protects concurrent exporter runs

def start_export_job(app, batch_size=1000, background=True):
    """
    Start an export job that calls export_attendance_direct (exporter).
    Runs in a daemon thread when background=True.
    """
    real_app = _resolve_app(app)
    job_id = str(uuid.uuid4())
    payload = {
        'job_id': job_id,
        'type': 'export_enddb',
        'status': 'running',
        'started_at': _now_iso(),
        'finished_at': None,
        'total': 1,
        'done': 0,
        'results': [],
        'error': None
    }
    _set_job(job_id, payload)

    def _worker(resolved_app, job_id_inner, batch_size_inner):
        try:
            with resolved_app.app_context():
                # import the exporter function name you have in exporter.py
                from .exporter import export_attendance_direct
                # Acquire simple export lock so two exports can't run at once
                got = _EXPORT_LOCK.acquire(blocking=False)
                if not got:
                    raise RuntimeError("Export already running")
                try:
                    lookback = resolved_app.config.get("EXPORT_LOOKBACK_DAYS", None)
                    res = export_attendance_direct(batch_size=batch_size_inner, lookback_days=lookback, dry_run=False)
                finally:
                    _EXPORT_LOCK.release()

                # Print summary to console/log (and keep it in job registry)
                try:
                    exported_count = int(res.get("exported", 0))
                    skipped = int(res.get("skipped_existing", 0)) if res.get("skipped_existing") is not None else 0
                    errors = int(res.get("errors", 0)) if res.get("errors") is not None else 0
                    print(Fore.CYAN + f"[EXPORT JOB RESULT] exported={exported_count} skipped_existing={skipped} errors={errors}")
                except Exception:
                    print(Fore.CYAN + f"[EXPORT JOB RESULT] {res}")

                # update job
                with _JOB_LOCK:
                    job = _JOB_REGISTRY.get(job_id_inner)
                    if job:
                        job['results'].append(res)
                        job['done'] = 1
                        job['status'] = 'finished'
                        job['finished_at'] = _now_iso()
        except Exception as e:
            tb = traceback.format_exc()
            with _JOB_LOCK:
                job = _JOB_REGISTRY.get(job_id_inner)
                if job:
                    job['status'] = 'failed'
                    job['error'] = tb
                    job['finished_at'] = _now_iso()
            print(Fore.RED + f"[EXPORT JOB ERROR] {e}\n{tb}")

    if background:
        thr = threading.Thread(target=_worker, args=(real_app, job_id, batch_size), daemon=True)
        thr.start()
        print(Fore.CYAN + f"[EXPORT JOB STARTED] id={job_id} (background)")
        return job_id
    else:
        # run inline and return summary
        _worker(real_app, job_id, batch_size)
        with _JOB_LOCK:
            return _JOB_REGISTRY.get(job_id)


# -------------------------
# Scheduler run logging (captures stdout/stderr into timestamped log)
# -------------------------
class _MultiWriter:
    def __init__(self, filehandle, original_stream):
        self.filehandle = filehandle
        self.original = original_stream
        self.lock = _RUN_LOCK

    def write(self, data):
        with self.lock:
            try:
                if self.original:
                    self.original.write(data)
                    try:
                        self.original.flush()
                    except Exception:
                        pass
                if self.filehandle:
                    try:
                        self.filehandle.write(data)
                        self.filehandle.flush()
                    except Exception:
                        pass
            except Exception:
                # swallow logging exceptions
                pass

    def flush(self):
        with self.lock:
            try:
                if self.original:
                    self.original.flush()
                if self.filehandle:
                    self.filehandle.flush()
            except Exception:
                pass


def _ensure_log_dir(app=None):
    """
    Determine the SCHEDULER_LOG_DIR from Flask config (if app provided or current_app).
    Ensure it exists and return the path.
    """
    log_dir = "logs"
    try:
        if app:
            log_dir = app.config.get("SCHEDULER_LOG_DIR", log_dir)
        else:
            # when called from within a request context
            log_dir = current_app.config.get("SCHEDULER_LOG_DIR", log_dir)
    except Exception:
        # fallback to environment
        log_dir = os.environ.get("SCHEDULER_LOG_DIR", log_dir)

    if not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir, exist_ok=True)
        except Exception:
            # On permission error, fallback to local 'logs'
            log_dir = "logs"
            os.makedirs(log_dir, exist_ok=True)
    return log_dir


def _make_run_filename(app=None):
    log_dir = _ensure_log_dir(app)
    now = datetime.now()
    return os.path.join(log_dir, f"zk_sync_{now:%Y%m%d_%H%M%S}.log")


def start_run_capture(app=None):
    """
    Start capturing stdout/stderr into a per-run logfile.
    Returns filename.
    """
    global _RUN_FH, _RUN_REDIRECT_CTX, _RUN_META
    with _RUN_LOCK:
        if _RUN_FH:
            return _RUN_META.get("filename")

        fn = _make_run_filename(app)
        fh = open(fn, "a", encoding="utf-8", errors="replace")
        header = f"\n===== ZK SYNC RUN START: {datetime.now():%Y-%m-%d %H:%M:%S} =====\n"
        fh.write(header)
        fh.flush()

        multi = _MultiWriter(fh, sys.__stdout__)
        ctx = contextlib.ExitStack()
        ctx.enter_context(contextlib.redirect_stdout(multi))
        ctx.enter_context(contextlib.redirect_stderr(multi))

        _RUN_FH = fh
        _RUN_REDIRECT_CTX = ctx
        _RUN_META = {"filename": fn, "start_ts": datetime.now()}
        return fn


def stop_run_capture():
    """
    Stop capturing and close the run logfile; write footer w/ elapsed time.
    Returns filename.
    """
    global _RUN_FH, _RUN_REDIRECT_CTX, _RUN_META
    with _RUN_LOCK:
        if not _RUN_FH:
            return None
        end_ts = datetime.now()
        start_ts = _RUN_META.get("start_ts", end_ts)
        elapsed = (end_ts - start_ts).total_seconds()
        footer = f"\n===== ZK SYNC RUN STOP: {end_ts:%Y-%m-%d %H:%M:%S} (elapsed {elapsed:.2f}s) =====\n\n"
        try:
            _RUN_FH.write(footer)
            _RUN_FH.flush()
        except Exception:
            pass
        try:
            if _RUN_REDIRECT_CTX:
                _RUN_REDIRECT_CTX.close()
        except Exception:
            pass
        try:
            _RUN_FH.close()
        except Exception:
            pass
        fn = _RUN_META.get("filename")
        _RUN_FH = None
        _RUN_REDIRECT_CTX = None
        _RUN_META = {}
        return fn


# -------------------------
# Public job starters (one-off)  (copied/adapted from your original)
# -------------------------
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

    def _run_wrapper(real_app_inner, devs, job_id_inner):
        """
        Run the poll in a separate thread while capturing output to a run logfile.
        This ensures one-off runs are also logged similarly to recurring runs.
        """
        logfile = start_run_capture(real_app_inner)
        print(Fore.MAGENTA + f"[JOB] Dispatching poll_all (job_id={job_id_inner}) — log: {logfile}")
        try:
            _run_poll_devices_job(real_app_inner, devs, job_id_inner)
        finally:
            # ensure footer & filename returned
            final_log = stop_run_capture()
            print(Fore.MAGENTA + f"[JOB] Finished poll_all (job_id={job_id_inner}) — log: {final_log}")

    thread = threading.Thread(target=_run_wrapper, args=(real_app, devices, job_id), daemon=True)
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

    def _run_wrapper(real_app_inner, devs, job_id_inner):
        logfile = start_run_capture(real_app_inner)
        print(Fore.MAGENTA + f"[JOB] Dispatching poll_branch={branch_id} (job_id={job_id_inner}) — log: {logfile}")
        try:
            _run_poll_devices_job(real_app_inner, devs, job_id_inner)
        finally:
            final_log = stop_run_capture()
            print(Fore.MAGENTA + f"[JOB] Finished poll_branch (job_id={job_id_inner}) — log: {final_log}")

    thread = threading.Thread(target=_run_wrapper, args=(real_app, devices, job_id), daemon=True)
    thread.start()
    print(Fore.CYAN + f"[JOB STARTED] id={job_id} (branch={branch_id}, total={payload['total']})")
    return job_id


# -------------------------
# Helpers used by job starters: _run_poll_devices_job
# -------------------------
try:
    # Try to import the helper from tasks (preferred, avoids duplication)
    from .tasks import _run_poll_devices_job  # noqa
except Exception:
    # If not present in tasks.py, provide a simple fallback skeleton to avoid crashes.
    def _run_poll_devices_job(app, devices, job_id):
        """
        Fallback minimal runner: iterate devices and call fetch_and_forward_for_device.
        If you already have a richer implementation in tasks.py, keep that and remove this fallback.
        """
        total = len(devices)
        done = 0
        results = []
        for dev in devices:
            try:
                # Note: fetch_and_forward_for_device should be defined in your tasks module
                # and returns the number of new logs inserted.
                from .tasks import fetch_and_forward_for_device  # local import
                cnt = fetch_and_forward_for_device(dev)
                results.append({'device': getattr(dev, 'name', str(dev)), 'new': cnt})
            except Exception as e:
                results.append({'device': getattr(dev, 'name', str(dev)), 'error': str(e)})
            done += 1
            with _JOB_LOCK:
                job = _JOB_REGISTRY.get(job_id)
                if job:
                    job['done'] = done
                    job['results'] = results
        with _JOB_LOCK:
            job = _JOB_REGISTRY.get(job_id)
            if job:
                job['status'] = 'finished'
                job['finished_at'] = _now_iso()


# -------------------------
# Scheduler job wrappers (start/stop) that run async and update registry
# -------------------------
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
    Alias wrapper to ensure we return a real Flask app object, not a LocalProxy.
    """
    return _resolve_app(maybe_proxy_or_app)


def start_scheduler_job(app, interval_seconds: int = None):
    real_app = _resolve_app_object(app)

    job_id = str(uuid.uuid4())
    meta = {}
    if interval_seconds is not None:
        meta['interval_seconds'] = int(interval_seconds)

    payload = _make_scheduler_job_record(job_id, 'start_scheduler', meta=meta)
    _set_job(job_id, payload)

    def _task(resolved_app, job_id_inner, interval_seconds_inner):
        try:
            with resolved_app.app_context():
                if interval_seconds_inner is not None:
                    start_recurring_scheduler(resolved_app, interval_seconds=interval_seconds_inner)
                else:
                    start_recurring_scheduler(resolved_app)

            with _JOB_LOCK:
                job = _JOB_REGISTRY.get(job_id_inner)
                if job:
                    job['done'] = 1
                    job['status'] = 'finished'
                    job['finished_at'] = _now_iso()
                    job['results'].append({'message': 'scheduler started', 'timestamp': _now_iso()})
        except Exception:
            tb = traceback.format_exc()
            print(Fore.RED + f"[JOB ERROR] start_scheduler_job {job_id_inner}\n{tb}")
            with _JOB_LOCK:
                job = _JOB_REGISTRY.get(job_id_inner)
                if job:
                    job['status'] = 'failed'
                    job['finished_at'] = _now_iso()
                    job['error'] = tb

    thread = threading.Thread(target=_task, args=(real_app, job_id, interval_seconds), daemon=True)
    thread.start()
    print(Fore.CYAN + f"[JOB STARTED] id={job_id} (start_scheduler meta={meta})")
    return job_id


def stop_scheduler_job(app):
    real_app = _resolve_app_object(app)

    job_id = str(uuid.uuid4())
    payload = _make_scheduler_job_record(job_id, 'stop_scheduler', meta={})
    _set_job(job_id, payload)

    def _task(resolved_app, job_id_inner):
        try:
            with resolved_app.app_context():
                stop_recurring_scheduler()

            with _JOB_LOCK:
                job = _JOB_REGISTRY.get(job_id_inner)
                if job:
                    job['done'] = 1
                    job['status'] = 'finished'
                    job['finished_at'] = _now_iso()
                    job['results'].append({'message': 'scheduler stopped', 'timestamp': _now_iso()})
        except Exception:
            tb = traceback.format_exc()
            print(Fore.RED + f"[JOB ERROR] stop_scheduler_job {job_id_inner}\n{tb}")
            with _JOB_LOCK:
                job = _JOB_REGISTRY.get(job_id_inner)
                if job:
                    job['status'] = 'failed'
                    job['finished_at'] = _now_iso()
                    job['error'] = tb

    thread = threading.Thread(target=_task, args=(real_app, job_id), daemon=True)
    thread.start()
    print(Fore.CYAN + f"[JOB STARTED] id={job_id} (stop_scheduler)")
    return job_id


# -------------------------
# Recurring scheduler control & poll loop (moved from tasks.py)
# -------------------------
def _poll_all_for_scheduler(app):
    """
    This orchestration captures per-run stdout/stderr into a timestamped log file,
    and runs the device polling across a ThreadPool (just like your original).
    """
    logfile = start_run_capture(app)
    print(Fore.MAGENTA + f"[SCHEDULER] Dispatching polling for devices… (log: {logfile})")

    real_app = _resolve_app(app)
    with real_app.app_context():
        # local import to avoid circular imports at module load
        from .models import Device
        devices = Device.query.all()

    max_workers = current_app.config.get("MAX_POLL_WORKERS", 10) if current_app else 10

    def run_with_app_context(dev, app):
        with app.app_context():
            # import here to reuse previously defined function
            from .tasks import fetch_and_forward_for_device
            return fetch_and_forward_for_device(dev)

    run_start = time.time()
    total_new = 0
    devices_count = len(devices)
    exceptions = []

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(run_with_app_context, dev, real_app): dev for dev in devices}
            for future in as_completed(futures):
                dev = futures[future]
                try:
                    count = future.result()
                    total_new += int(count or 0)
                    print(Fore.BLUE + f"[SCHEDULER] {dev.name}: {count} new logs")
                except Exception as e:
                    exceptions.append((getattr(dev, "name", None), str(e)))
                    print(Fore.RED + f"[SCHEDULER ERROR] {dev.name}: {e}")
    except Exception as e:
        tb = traceback.format_exc()
        print(Fore.RED + f"[SCHEDULER RUN ERROR] {e}\n{tb}")
        exceptions.append(("scheduler_run", str(e)))

    run_end = time.time()
    run_elapsed = run_end - run_start

    # --- <<< EXPORT: offload to export job (non-blocking) & robust handling) >>> ---
    try:
        if real_app.config.get("EXPORT_AFTER_POLL", True):
            try:
                # start export in background (uses _EXPORT_LOCK to avoid concurrent exports)
                start_export_job(real_app, batch_size=real_app.config.get("EXPORT_BATCH_SIZE", 1000), background=True)
                print(Fore.CYAN + "[EXPORT] Export job launched (background).")
            except Exception as e:
                tb = traceback.format_exc()
                print(Fore.RED + f"[EXPORT ERROR] Failed to launch export job: {e}\n{tb}")
    except Exception as e:
        tb = traceback.format_exc()
        print(Fore.RED + f"[EXPORT ERROR] Unexpected failure preparing export: {e}\n{tb}")
    # --- <<< END EXPORT >>> ---

    # summary to console & appended to run logfile
    print(Fore.CYAN + f"[SCHEDULER] Completed polling {devices_count} devices. Total new logs: {total_new}. Run time: {run_elapsed:.2f}s")

    # write JSON summary to run file (if open)
    try:
        summary = {
            "start": _RUN_META.get("start_ts").isoformat() if _RUN_META.get("start_ts") else None,
            "end": datetime.now().isoformat(),
            "devices_polled": devices_count,
            "new_logs": total_new,
            "elapsed_seconds": round(run_elapsed, 3),
            "exceptions": exceptions,
            "logfile": logfile
        }
        if _RUN_FH:
            with _RUN_LOCK:
                _RUN_FH.write("\nRUN_SUMMARY_JSON: " + json.dumps(summary, default=str) + "\n")
                _RUN_FH.flush()
    except Exception as e:
        tb = traceback.format_exc()
        print(Fore.RED + f"[SCHEDULER UNHANDLED ERROR] Exception in _poll_all_for_scheduler: {e}\n{tb}")
        # best-effort summary to runlog
        try:
            if _RUN_FH:
                with _RUN_LOCK:
                    _RUN_FH.write("\nUNHANDLED ERROR IN POLL: " + tb + "\n")
                    _RUN_FH.flush()
        except Exception:
            pass
    final_log = stop_run_capture()
    print(Fore.MAGENTA + f"[SCHEDULER] Run finished. Logfile: {final_log}")


def start_recurring_scheduler(app, interval_seconds=None, prune_interval_seconds=None):
    """
    Start the background APScheduler that fires _poll_all_for_scheduler every interval_seconds.
    Defaults:
      - interval_seconds: read from app.config['SCHEDULER_INTERVAL_SECONDS'] or 5s for quick testing
      - prune_interval_seconds: read from app.config['JOB_PRUNE_INTERVAL_SECONDS'] or 600s
    """
    global _scheduler
    with _scheduler_lock:
        if _scheduler and getattr(_scheduler, "running", False):
            print(Fore.CYAN + "[SCHEDULER] already running")
            return

        from apscheduler.schedulers.background import BackgroundScheduler
        real_app = _resolve_app(app)
        # determine effective intervals (prefer passed argument -> config -> default)
        cfg_interval = real_app.config.get("SCHEDULER_INTERVAL_SECONDS", 5)
        interval_seconds = int(interval_seconds if interval_seconds is not None else cfg_interval)
        cfg_prune = real_app.config.get("JOB_PRUNE_INTERVAL_SECONDS", 600)
        prune_interval_seconds = int(prune_interval_seconds if prune_interval_seconds is not None else cfg_prune)

        _scheduler = BackgroundScheduler()
        # schedule polling job
        _scheduler.add_job(
            _poll_all_for_scheduler,
            'interval',
            seconds=interval_seconds,
            args=[real_app],
            id="zk_poll_job",
            replace_existing=True,
            max_instances=1,
            misfire_grace_time=300
        )

        # try to import prune_old_jobs from tasks to keep original behavior (optional)
        try:
            from .tasks import prune_old_jobs as tasks_prune_fn, _JOB_TTL_SECONDS as TASKS_JOB_TTL
            ttl = real_app.config.get("JOB_TTL_SECONDS", TASKS_JOB_TTL)
            ttl = int(ttl)
            _scheduler.add_job(
                tasks_prune_fn,
                'interval',
                seconds=prune_interval_seconds,
                args=[ttl],
                id="job_prune",
                replace_existing=True
            )
        except Exception:
            # If prune_old_jobs isn't present, skip adding that job
            pass

        _scheduler.start()
        print(Fore.CYAN + f"[SCHEDULER] Started recurring polling every {interval_seconds} seconds.")


def stop_recurring_scheduler():
    """
    Stop and shutdown the recurring scheduler if it exists.
    """
    global _scheduler
    with _scheduler_lock:
        if not _scheduler:
            print(Fore.CYAN + "[SCHEDULER] no scheduler to stop")
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
        print(Fore.CYAN + "[SCHEDULER] Stopped and shutdown.")
