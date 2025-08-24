# logging_handler.py
"""
Minimal Socket.IO logging bridge.
- Call init_socketio_logging() once after socketio is created.
- Replaces sys.stdout/sys.stderr so print()/errors are forwarded as 'console' and 'log'.
- Installs a logging.Handler that forwards Python logging records as 'log'.
"""

import logging
import sys
import re
import threading
import subprocess
from datetime import datetime
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


# ---------- helpers ----------
def _now_iso():
    return datetime.utcnow().isoformat(timespec='milliseconds') + 'Z'


def _should_skip(msg: str) -> bool:
    if not msg:
        return True
    for rx in _SKIP_REGEXES:
        if rx.search(msg):
            return True
    return False


def strip_ansi(s: str) -> str:
    return ANSI_RE.sub('', s) if s else s


def safe_emit(event: str, payload: dict):
    """Emit to socketio but never raise an exception."""
    try:
        socketio.emit(event, payload)
    except Exception:
        try:
            sys.__stdout__.write(f"[socketio emit failed] {event} {payload}\n")
        except Exception:
            pass


# ---------- logging handler ----------
class SocketIOLogHandler(logging.Handler):
    """Forward Python logging records to socket.io as 'log' events."""

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            if _should_skip(msg):
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
            safe_emit('log', payload)
        except Exception:
            try:
                sys.__stdout__.write("SocketIOLogHandler emit error\n")
            except Exception:
                pass


# ---------- stdout/stderr shim ----------
class SocketIOStream:
    """
    Replace sys.stdout and sys.stderr with this.
    Emits:
      - 'console' (ansi + stripped text) for terminal UI
      - 'log' (structured) for compatibility
    """

    def __init__(self, kind="stdout"):
        self.kind = kind  # 'stdout' or 'stderr'

    def write(self, message):
        if message is None:
            return
        raw = str(message).rstrip('\n')
        if raw == '':
            return

        text = strip_ansi(raw)
        color = None
        # quick color detect (optional)
        if '\x1b[32m' in raw:
            color = 'green'
        elif '\x1b[31m' in raw:
            color = 'red'

        payload_console = {
            "timestamp": _now_iso(),
            "device_name": self.kind,
            "level": "ERROR" if self.kind == "stderr" else "INFO",
            "message": text,
            "ansi": raw,
            "color": color,
        }
        # emit console (terminal-style)
        try:
            safe_emit('console', payload_console)
        except Exception:
            pass

        # also emit structured log for backwards compatibility
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

        # keep printing to the real stdout/stderr so server console still shows messages
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


# ---------- init ----------
_initialized = False


def init_socketio_logging():
    """
    Install the SocketIOLogHandler and replace sys.stdout & sys.stderr.
    Call once after socketio has been created (app factory).
    """
    global _initialized
    if _initialized:
        return
    try:
        handler = SocketIOLogHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        root = logging.getLogger()
        root.addHandler(handler)
        # ensure root captures debug+ info
        if root.level > logging.DEBUG:
            root.setLevel(logging.DEBUG)

        # replace stdout and stderr
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


# ---------- optional: stream a subprocess to socket.io ----------
def stream_subprocess(command, event="terminal_output", device_name=None):
    """
    Spawn a thread to stream subprocess stdout/stderr lines to socket.io event.
    Returns the Thread object.
    """
    def _runner(cmd, ev, dev):
        try:
            safe_emit('log', {
                "timestamp": _now_iso(),
                "device_name": dev or (cmd[0] if isinstance(cmd, (list, tuple)) else str(cmd)),
                "level": "INFO",
                "message": f"[PROCESS START] {' '.join(cmd) if isinstance(cmd, (list,tuple)) else cmd}",
            })

            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, bufsize=1)
            for raw in iter(proc.stdout.readline, ""):
                if raw is None:
                    break
                line = raw.rstrip("\n")
                if not line:
                    continue
                safe_emit(ev, {
                    "timestamp": _now_iso(),
                    "device_name": dev or (cmd[0] if isinstance(cmd, (list, tuple)) else str(cmd)),
                    "level": "INFO",
                    "message": line,
                })

            proc.stdout.close()
            rc = proc.wait()
            safe_emit('log', {
                "timestamp": _now_iso(),
                "device_name": dev or (cmd[0] if isinstance(cmd, (list, tuple)) else str(cmd)),
                "level": "INFO" if rc == 0 else "ERROR",
                "message": f"[PROCESS EXIT] rc={rc}",
            })
        except Exception as e:
            safe_emit('log', {
                "timestamp": _now_iso(),
                "device_name": dev or "process",
                "level": "ERROR",
                "message": f"[PROCESS ERROR] {e}",
            })

    thread = threading.Thread(target=_runner, args=(command, event, device_name), daemon=True)
    thread.start()
    return thread
