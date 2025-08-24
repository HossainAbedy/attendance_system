# backend/app/locks.py
import os
import time
import errno
from datetime import datetime

class DirLockTimeout(Exception):
    pass

class DirLock:
    """
    Directory-based lock (atomic mkdir). Cross-platform (Windows & Linux).
    lock_dir: path to the directory used as the lock (e.g. D:/.../access_lock)
    stale_seconds: if the lock directory is older than this, consider it stale and remove it.
    retry_delay: sleep between retries (seconds)
    timeout: total time to wait for acquiring the lock (seconds)
    """
    def __init__(self, lock_dir, stale_seconds=60, retry_delay=0.2, timeout=15):
        self.lock_dir = lock_dir
        self.stale_seconds = float(stale_seconds)
        self.retry_delay = float(retry_delay)
        self.timeout = float(timeout)
        self._acquired = False
        self._stamp_file = os.path.join(lock_dir, "lockinfo.txt")

    def _is_stale(self):
        try:
            mtime = os.path.getmtime(self.lock_dir)
        except Exception:
            return False
        return (time.time() - mtime) > self.stale_seconds

    def acquire(self):
        deadline = time.time() + self.timeout
        pid = os.getpid()
        while True:
            try:
                # Attempt atomic mkdir. If it exists, FileExistsError is raised.
                os.mkdir(self.lock_dir)
                # Write stamp file for debugging purposes
                try:
                    with open(self._stamp_file, "w", encoding="utf-8") as fh:
                        fh.write(f"pid={pid}\ncreated={datetime.utcnow().isoformat()}\n")
                except Exception:
                    pass
                self._acquired = True
                return True
            except FileExistsError:
                # exists -> check stale
                if self._is_stale():
                    try:
                        # best-effort remove stale stamp and dir
                        try:
                            os.unlink(self._stamp_file)
                        except Exception:
                            pass
                        os.rmdir(self.lock_dir)
                        # small pause then retry immediately
                        time.sleep(0.05)
                        continue
                    except Exception:
                        pass
                # not stale -> wait and retry
                if time.time() > deadline:
                    raise DirLockTimeout(f"Timeout acquiring lock {self.lock_dir}")
                time.sleep(self.retry_delay)
            except Exception as e:
                # unexpected error, re-raise
                raise

    def release(self):
        if not self._acquired:
            return
        try:
            try:
                os.unlink(self._stamp_file)
            except Exception:
                pass
            os.rmdir(self.lock_dir)
        except Exception:
            pass
        self._acquired = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()
        return False
