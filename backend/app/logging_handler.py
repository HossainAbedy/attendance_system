# logging_handler.py
import logging
import sys
import os
import re
import threading
import subprocess
from datetime import datetime
from .extensions import socketio  # your socketio instance

# ------------ Configuration ------------
SKIP_PATTERNS = [
    r"Restarting with stat",
    r"Debugger is active",
    r"Debugger PIN",
    r"Serving Flask app",
    r"Running on http://",
    r"Press CTRL\+C to quit",
    r"werkzeug",
    r"Started reloader",
]

WHITELIST_LOGGER_PREFIXES = os.getenv("SOCKETIO_WHITELIST_LOGGERS")  # e.g. "myapp,worker"
if WHITELIST_LOGGER_PREFIXES:
    WHITELIST_LOGGER_PREFIXES = [p.strip() for p in WHITELIST_LOGGER_PREFIXES.split(",") if p.strip()]
else:
    WHITELIST_LOGGER_PREFIXES = None

_SKIP_REGEXES = [re.compile(p, re.IGNORECASE) for p in SKIP_PATTERNS]


def _should_skip_message(msg: str) -> bool:
    if not msg:
        return True
    for rx in _SKIP_REGEXES:
        if rx.search(msg):
            return True
    return False


def _now_iso():
    return datetime.utcnow().isoformat(timespec="milliseconds") + "Z"


def send_socket_log(payload: dict, event: str = "log"):
    """
    Helper to emit a structured payload safely to socket.io and optionally print debug.
    """
    try:
        sys.__stdout__.write(f"[SocketIO EMIT] {event}: {payload}\n")
        socketio.emit(event, payload)
    except Exception as e:
        sys.__stdout__.write(f"[SocketIO EMIT ERROR] {e}\n")


class SocketIOLogHandler(logging.Handler):
    """
    Logging handler that emits structured logs over socketio.
    Filters out noisy devserver messages, and supports optional whitelist of logger prefixes.
    """
    def __init__(self):
        super().__init__()

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            if _should_skip_message(msg):
                return

            if WHITELIST_LOGGER_PREFIXES:
                if not any(record.name.startswith(pref) for pref in WHITELIST_LOGGER_PREFIXES):
                    return

            payload = {
                "timestamp": _now_iso(),
                "device_name": getattr(record, "device_name", record.name or "system"),
                "logger": record.name,
                "level": record.levelname,
                "message": msg,
                "pathname": getattr(record, "pathname", None),
                "lineno": getattr(record, "lineno", None),
            }

            sys.__stdout__.write(f"[DEBUG emit()] Prepared payload: {payload}\n")
            socketio.emit('log', payload)
            sys.__stdout__.write(f"[DEBUG emit()] Emitted via socketio.emit\n")

        except Exception as e:
            sys.__stdout__.write(f"SocketIOLogHandler error: {e}\n")


class SocketIOStdout:
    def __init__(self, socketio_instance):
        self.socketio = socketio_instance

    def write(self, message):
        message = message.strip()
        if message:
            payload = {
                'timestamp': datetime.utcnow().isoformat(timespec='milliseconds') + 'Z',
                'device_name': 'stdout',
                'level': 'INFO',
                'message': message
            }
            self.socketio.emit('log', payload)
        sys.__stdout__.write(message + '\n')

    def flush(self):
        sys.__stdout__.flush()


def init_socketio_logging():
    try:
        handler = SocketIOLogHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.DEBUG)
        sys.stdout = SocketIOStdout(socketio)
        sys.__stdout__.write("[SocketIO] socketio logging initialized\n")
        print("[DEBUG] SocketIO logging initialized")  # <-- add this line
    except Exception as e:
        sys.__stdout__.write(f"init_socketio_logging error: {e}\n")

def stream_subprocess(command, event="terminal_output", device_name=None, encoding="utf-8"):
    """
    Spawn a background thread to run a command and stream each stdout line to socketio.
    Use this to get the *real* terminal/process output.
    Example: stream_subprocess(["python", "myscript.py"])
    """
    def _runner(cmd, ev, dev, enc):
        try:
            start_payload = {
                "timestamp": _now_iso(),
                "device_name": dev or (cmd[0] if isinstance(cmd, (list, tuple)) else str(cmd)),
                "level": "INFO",
                "message": f"[PROCESS START] {' '.join(cmd) if isinstance(cmd, (list,tuple)) else cmd}",
            }
            send_socket_log(start_payload, event="log")

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
            )

            for raw in iter(proc.stdout.readline, ""):
                if raw is None:
                    break
                line = raw.rstrip("\n")
                if not line:
                    continue
                payload = {
                    "timestamp": _now_iso(),
                    "device_name": dev or (cmd[0] if isinstance(cmd, (list,tuple)) else str(cmd)),
                    "level": "INFO",
                    "message": line,
                }
                send_socket_log(payload, event=ev)

            proc.stdout.close()
            rc = proc.wait()
            end_payload = {
                "timestamp": _now_iso(),
                "device_name": dev or (cmd[0] if isinstance(cmd, (list,tuple)) else str(cmd)),
                "level": "INFO" if rc == 0 else "ERROR",
                "message": f"[PROCESS EXIT] rc={rc}",
            }
            send_socket_log(end_payload, event="log")
        except Exception as e:
            send_socket_log({
                "timestamp": _now_iso(),
                "device_name": dev or "process",
                "level": "ERROR",
                "message": f"[PROCESS ERROR] {e}",
            }, event="log")

    thread = threading.Thread(target=_runner, args=(command, event, device_name, encoding), daemon=True)
    thread.start()
    return thread
