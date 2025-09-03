# app/logging_handler.py
import logging
import sys
import re
import threading
from datetime import datetime
from collections import deque
from .extensions import socketio  # must be initialized before calling init_socketio_logging

# ---------- small config ----------
_SKIP_PATTERNS = [
    r"Restarting with stat",
    r"Debugger is active",
    r"Debugger PIN",
    r"Serving Flask app",
    r"Press CTRL\+C to quit",
    r"Started reloader",
]
_SKIP_REGEXES = [re.compile(p, re.IGNORECASE) for p in _SKIP_PATTERNS]
ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')

def _now_iso():
    return datetime.utcnow().isoformat(timespec='milliseconds') + 'Z'

def strip_ansi(s: str) -> str:
    return ANSI_RE.sub('', s) if s else s

def _should_skip(msg: str) -> bool:
    if not msg:
        return True
    for rx in _SKIP_REGEXES:
        if rx.search(msg):
            return True
    return False

def safe_emit(event: str, payload: dict):
    try:
        socketio.emit(event, payload)
    except Exception:
        try:
            sys.__stdout__.write(f"[socketio emit failed] {event} {payload}\n")
        except Exception:
            pass

# dedupe cache
_DEDUPE_LOCK = threading.Lock()
_LAST_MSGS = deque(maxlen=200)

def _is_duplicate(msg: str, window_seconds: float = 0.5) -> bool:
    now = datetime.utcnow()
    with _DEDUPE_LOCK:
        # purge older than 10s
        while _LAST_MSGS and (now - _LAST_MSGS[0][1]).total_seconds() > 10:
            _LAST_MSGS.popleft()
        for text, ts in reversed(_LAST_MSGS):
            if text == msg and (now - ts).total_seconds() <= window_seconds:
                return True
        _LAST_MSGS.append((msg, now))
    return False

class SocketIOLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            if _should_skip(msg):
                return
            if _is_duplicate(msg):
                return
            payload = {
                "timestamp": _now_iso(),
                "device_name": getattr(record, "device_name", record.name or "system"),
                "logger": record.name,
                "level": record.levelname,
                "message": strip_ansi(msg),
                "pathname": getattr(record, "pathname", None),
                "lineno": getattr(record, "lineno", None),
            }
            safe_emit('log', payload)
        except Exception:
            try:
                sys.__stdout__.write("SocketIOLogHandler emit error\n")
            except Exception:
                pass

class SocketIOStream:
    def __init__(self, kind="stdout"):
        self.kind = kind

    def write(self, message):
        if message is None:
            return
        raw = str(message).rstrip('\n')
        if raw == '':
            return
        text = strip_ansi(raw)
        if _is_duplicate(text):
            return
        payload_console = {
            "timestamp": _now_iso(),
            "device_name": self.kind,
            "level": "ERROR" if self.kind == "stderr" else "INFO",
            "message": text,
            "ansi": raw,
        }
        try:
            safe_emit('console', payload_console)
        except Exception:
            pass
        payload_log = {
            "timestamp": payload_console["timestamp"],
            "device_name": self.kind,
            "logger": self.kind,
            "level": payload_console["level"],
            "message": text,
        }
        try:
            safe_emit('log', payload_log)
        except Exception:
            pass
        try:
            if self.kind == "stderr":
                sys.__stderr__.write(raw + '\n')
            else:
                sys.__stdout__.write(raw + '\n')
        except Exception:
            pass

    def flush(self):
        try:
            if self.kind == "stderr":
                sys.__stderr__.flush()
            else:
                sys.__stdout__.flush()
        except Exception:
            pass

_initialized = False

def init_socketio_logging():
    global _initialized
    if _initialized:
        return
    try:
        handler = SocketIOLogHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        root = logging.getLogger()
        root.addHandler(handler)
        if root.level > logging.DEBUG:
            root.setLevel(logging.DEBUG)
        sys.stdout = SocketIOStream("stdout")
        sys.stderr = SocketIOStream("stderr")
        _initialized = True
        try:
            sys.__stdout__.write("[logging_handler] socketio logging initialized\n")
        except Exception:
            pass
    except Exception as e:
        try:
            sys.__stdout__.write(f"[logging_handler init error] {e}\n")
        except Exception:
            pass
