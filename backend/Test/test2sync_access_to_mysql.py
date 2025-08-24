#!/usr/bin/env python3
"""
compare_zk_vs_access_multi_filtered_with_php_preview.py

Hard-coded compare for 3 devices. Filters ZK fetch to COMPARE_DATE and
generates a preview CSV of the exact INSERT statement/values your PHP script
would execute (so you can see what was sent to MySQL).

Outputs per-device in OUT_DIR/<sn>/:
 - <sn>_zk_raw_filtered.csv
 - <sn>_app_access_rows.csv
 - <sn>_existing_access_rows.csv
 - <sn>_php_insert_preview.csv
 - <sn>_only_zk_keys.csv, _only_app_keys.csv, _only_existing_keys.csv
 - <sn>_summary.json
"""
import os
import time
import json
from datetime import datetime, timedelta
from zk import ZK
import pyodbc
import pandas as pd

# -----------------------------
# HARD-CODED CONFIG - edit if desired
# -----------------------------
APP_ACCESS = r"E:\ShareME\SBAC TAO\NewYear25\attendance-system\backend\att2000.mdb"
EXIST_ACCESS = r"E:\ShareME\SBAC TAO\NewYear25\attendance-system\backend\Test\att2000.mdb"
OUT_DIR = r"E:\ShareME\SBAC TAO\NewYear25\attendance-system\backend\Test\zk_compare_out"
DRIVER = r"Microsoft Access Driver (*.mdb, *.accdb)"
# Date to compare: default = today (YYYY-MM-DD) - change if you want a specific day
COMPARE_DATE = datetime.now().strftime("%Y-%m-%d")

# Devices (hard-coded per your request)
DEVICES = [
    {"id": "10", "branch_id": "25", "name": "K40 Lobby Uttara Branch", "ip": "172.19.109.231", "port": 4370, "sn": "A8N5232360705"},
    {"id": "71", "branch_id": "87", "name": "K40 Lobby Nazipur Branch", "ip": "172.19.171.231", "port": 4370, "sn": "A8N5232360696"},
    {"id": "53", "branch_id": "69", "name": "K40 Lobby Chittagong EPZ Branch", "ip": "172.19.153.231", "port": 4370, "sn": "A8N5232360848"},
]

ACCESS_LOCK_DIR = os.path.join(os.path.dirname(APP_ACCESS), "access_lock")
LOCK_STALE_SECONDS = 60
LOCK_TIMEOUT_SECONDS = 15
# -----------------------------

# Simple directory lock (atomic mkdir)
class DirLock:
    def __init__(self, lock_dir, stale_seconds=LOCK_STALE_SECONDS, timeout=LOCK_TIMEOUT_SECONDS):
        self.lock_dir = lock_dir
        self.stale_seconds = stale_seconds
        self.timeout = timeout

    def __enter__(self):
        start = time.time()
        while True:
            try:
                os.mkdir(self.lock_dir)
                try:
                    with open(os.path.join(self.lock_dir, "lockinfo.txt"), "w", encoding="utf-8") as fh:
                        fh.write(f"pid={os.getpid()}\ncreated={datetime.now().isoformat()}\n")
                except Exception:
                    pass
                return self
            except FileExistsError:
                try:
                    mtime = os.path.getmtime(self.lock_dir)
                    if (time.time() - mtime) > self.stale_seconds:
                        try:
                            for f in os.listdir(self.lock_dir):
                                try:
                                    os.unlink(os.path.join(self.lock_dir, f))
                                except Exception:
                                    pass
                            os.rmdir(self.lock_dir)
                            continue
                        except Exception:
                            pass
                except Exception:
                    pass
                if (time.time() - start) >= self.timeout:
                    raise TimeoutError(f"Could not acquire lock {self.lock_dir} within {self.timeout}s")
                time.sleep(0.2)
            except Exception as e:
                raise

    def __exit__(self, exc_type, exc, tb):
        try:
            for f in os.listdir(self.lock_dir):
                try:
                    os.unlink(os.path.join(self.lock_dir, f))
                except Exception:
                    pass
            os.rmdir(self.lock_dir)
        except Exception:
            pass

def connect_access(mdb_path, driver=DRIVER):
    if not os.path.exists(mdb_path):
        raise FileNotFoundError(f"Access DB not found: {mdb_path}")
    conn_str = rf"DRIVER={{{driver}}};DBQ={mdb_path};"
    return pyodbc.connect(conn_str, autocommit=True)

def fetch_access_rows_for_device(conn, table="CHECKINOUT", sn=None, date_str=None):
    if date_str:
        if sn:
            sql = f"SELECT * FROM {table} WHERE sn = ? AND Format(CHECKTIME,'YYYY-MM-DD') = ? ORDER BY CHECKTIME"
            cur = conn.cursor()
            cur.execute(sql, (sn, date_str))
            rows = cur.fetchall()
            cols = [c[0] for c in cur.description]
            cur.close()
            if rows:
                return pd.DataFrame.from_records(rows, columns=cols)
            else:
                return pd.DataFrame(columns=cols)
        else:
            sql = f"SELECT * FROM {table} WHERE Format(CHECKTIME,'YYYY-MM-DD') = '{date_str}' ORDER BY CHECKTIME"
            return pd.read_sql(sql, conn)
    else:
        if sn:
            cur = conn.cursor()
            cur.execute(f"SELECT * FROM {table} WHERE sn = ?", (sn,))
            rows = cur.fetchall()
            cols = [c[0] for c in cur.description]
            cur.close()
            return pd.DataFrame.from_records(rows, columns=cols)
        else:
            return pd.read_sql(f"SELECT * FROM {table}", conn)

def rec_to_access_dict(rec, device_sn):
    status_str = str(rec.status) if isinstance(rec.status, int) else getattr(rec.status, "name", str(rec.status))
    user_id = getattr(rec, "user_id", None) or getattr(rec, "userId", None) or getattr(rec, "Badgenumber", None)
    checktime = getattr(rec, "timestamp", None) or getattr(rec, "CHECKTIME", None) or getattr(rec, "time", None)
    return {
        "uid": getattr(rec, "uid", None),
        "USERID": user_id,
        "CHECKTIME": checktime,
        "CHECKTYPE": status_str,
        "VERIFYCODE": 1,
        "SENSORID": "1",
        "WorkCode": "0",
        "sn": device_sn,
        "raw_repr": repr(rec)
    }

def normalize_checktime_for_key(val):
    if val is None:
        return ""
    if isinstance(val, (int, float)):
        iv = int(val)
        if iv > 1e11:
            iv = iv // 1000
        dt = datetime.utcfromtimestamp(iv)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    try:
        if hasattr(val, "isoformat"):
            return val.strftime("%Y-%m-%d %H:%M:%S")
        else:
            dt = pd.to_datetime(val, errors='coerce')
            if pd.isna(dt):
                return str(val)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(val)

def zk_records_to_df_filtered(zk_records, device_sn, date_str):
    rows = []
    for rec in zk_records:
        d = rec_to_access_dict(rec, device_sn)
        # Determine record date string
        ct = d.get("CHECKTIME")
        # attempt to get a datetime
        dt = None
        if isinstance(ct, (int, float)):
            iv = int(ct)
            if iv > 1e11:
                iv = iv // 1000
            dt = datetime.utcfromtimestamp(iv)
        else:
            try:
                if hasattr(ct, "isoformat"):
                    dt = ct
                else:
                    dt = pd.to_datetime(ct, errors='coerce')
            except Exception:
                dt = None
        if dt is None or pd.isna(dt):
            # if cannot parse date, skip (not safe to include)
            continue
        # compare date strings (date part)
        rec_date_str = dt.strftime("%Y-%m-%d")
        if rec_date_str != date_str:
            continue
        d['CHECKTIME_norm'] = dt.strftime("%Y-%m-%d %H:%M:%S")
        rows.append(d)
    if rows:
        return pd.DataFrame(rows)
    else:
        return pd.DataFrame(columns=["uid","USERID","CHECKTIME","CHECKTYPE","VERIFYCODE","SENSORID","WorkCode","sn","raw_repr","CHECKTIME_norm"])

def prepare_access_df_for_compare(df):
    out = df.copy()
    if out.empty:
        return out
    if 'USERID' not in out.columns:
        for cand in ('Badgenumber', 'USERID', 'UserID'):
            if cand in out.columns:
                out.rename(columns={cand: 'USERID'}, inplace=True)
                break
    if 'CHECKTIME' in out.columns:
        out['CHECKTIME_norm'] = out['CHECKTIME'].apply(normalize_checktime_for_key)
    else:
        for c in out.columns:
            if 'time' in c.lower() or 'date' in c.lower():
                out['CHECKTIME_norm'] = out[c].apply(normalize_checktime_for_key)
                break
    if 'sn' not in out.columns:
        out['sn'] = ''
    out['__key__'] = out.apply(lambda r: f"{r.get('USERID','')}|{r.get('CHECKTIME_norm','')}|{r.get('sn','')}", axis=1)
    return out

# Build PHP preview: apply same transforms as your p1.php (logDate, -10 minutes, skip badges >4 chars)
def build_php_insert_preview_row(access_row):
    # access_row is a Pandas Series or dict containing CHECKTIME and Badgenumber/USERID, sn
    # Determine userId
    userId = access_row.get('Badgenumber') or access_row.get('USERID') or access_row.get('Badgenumber'.lower()) or ''
    # parse CHECKTIME into datetime
    try:
        ct = access_row.get('CHECKTIME') or access_row.get('CHECKTIME_norm') or ''
        dt = pd.to_datetime(ct)
    except Exception:
        dt = None
    if dt is pd.NaT or dt is None:
        logDate = ''
        logTime = ''
    else:
        logDate = dt.strftime("%Y-%m-%d")
        adjusted = dt - timedelta(minutes=10)
        logTime = adjusted.strftime("%H:%M:%S")
    accessDevice = 'ZKT-' + (str(access_row.get('sn') or '')).strip()
    accessDoor = str(access_row.get('sn') or '')
    # skip if badge length > 4 (php behavior)
    if userId is None:
        userId = ''
    if len(str(userId)) > 4:
        skip = True
    else:
        skip = False
    # build SQL preview string (unescaped for readability)
    sql_values = {
        "logDate": logDate,
        "userId": str(userId),
        "logTime": logTime,
        "accessDoor": accessDoor,
        "accessDev": accessDevice
    }
    sql_str = f"INSERT IGNORE INTO att_raw_data VALUES('null', '{logDate}', '{userId}', '{userId}', '', '{logTime}', '0', '{accessDoor}', '', '{accessDevice}')"
    return {
        "skip": skip,
        "userId": str(userId),
        "logDate": logDate,
        "logTime": logTime,
        "accessDoor": accessDoor,
        "accessDev": accessDevice,
        "sql": sql_str
    }

def compare_and_write(df_zk, df_app, df_exist, out_dir, device_sn, date_str):
    os.makedirs(out_dir, exist_ok=True)
    df_zk['__key__'] = df_zk.apply(lambda r: f"{r.get('USERID','')}|{r.get('CHECKTIME_norm','')}|{r.get('sn','')}", axis=1)
    df_app_p = prepare_access_df_for_compare(df_app) if not (df_app is None) else pd.DataFrame(columns=['__key__'])
    df_exist_p = prepare_access_df_for_compare(df_exist) if not (df_exist is None) else pd.DataFrame(columns=['__key__'])

    zk_keys = set(df_zk['__key__'].astype(str).tolist())
    app_keys = set(df_app_p['__key__'].astype(str).tolist()) if not df_app_p.empty else set()
    exist_keys = set(df_exist_p['__key__'].astype(str).tolist()) if not df_exist_p.empty else set()

    only_zk = sorted(list(zk_keys - app_keys - exist_keys))
    only_app = sorted(list(app_keys - zk_keys - exist_keys))
    only_exist = sorted(list(exist_keys - zk_keys - app_keys))
    in_zk_and_app = sorted(list(zk_keys & app_keys))
    in_zk_and_exist = sorted(list(zk_keys & exist_keys))

    # write dataframes and lists
    df_zk.to_csv(os.path.join(out_dir, f"{device_sn}_zk_raw_filtered.csv"), index=False)
    if not df_app.empty:
        df_app.to_csv(os.path.join(out_dir, f"{device_sn}_app_access_rows.csv"), index=False)
    if not df_exist.empty:
        df_exist.to_csv(os.path.join(out_dir, f"{device_sn}_existing_access_rows.csv"), index=False)

    pd.DataFrame({"key": only_zk}).to_csv(os.path.join(out_dir, f"{device_sn}_only_zk_keys.csv"), index=False)
    pd.DataFrame({"key": only_app}).to_csv(os.path.join(out_dir, f"{device_sn}_only_app_keys.csv"), index=False)
    pd.DataFrame({"key": only_exist}).to_csv(os.path.join(out_dir, f"{device_sn}_only_existing_keys.csv"), index=False)
    pd.DataFrame({"key": in_zk_and_app}).to_csv(os.path.join(out_dir, f"{device_sn}_in_zk_and_app_keys.csv"), index=False)
    pd.DataFrame({"key": in_zk_and_exist}).to_csv(os.path.join(out_dir, f"{device_sn}_in_zk_and_existing_keys.csv"), index=False)

    # Build php insert preview from df_app (the PHP script reads from Access and inserts into MySQL)
    php_rows = []
    if not df_app.empty:
        for idx, r in df_app.iterrows():
            preview = build_php_insert_preview_row(r)
            if not preview['skip']:
                php_rows.append(preview)
            else:
                php_rows.append(dict(preview, note="SKIPPED_BADGE_LEN>4"))
        pd.DataFrame(php_rows).to_csv(os.path.join(out_dir, f"{device_sn}_php_insert_preview.csv"), index=False)

    summary = {
        "device_sn": device_sn,
        "date": date_str,
        "zk_rows_filtered": len(df_zk),
        "app_access_rows": len(df_app) if df_app is not None else 0,
        "existing_access_rows": len(df_exist) if df_exist is not None else 0,
        "only_zk": len(only_zk),
        "only_app": len(only_app),
        "only_existing": len(only_exist),
        "in_zk_and_app": len(in_zk_and_app),
        "in_zk_and_existing": len(in_zk_and_exist),
    }
    with open(os.path.join(out_dir, f"{device_sn}_summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)
    return summary

def run_for_device(dev):
    device_sn = dev['sn']
    date_str = COMPARE_DATE
    out_dir_dev = os.path.join(OUT_DIR, device_sn.replace(" ", "_"))
    os.makedirs(out_dir_dev, exist_ok=True)

    zk = ZK(dev['ip'], port=dev.get('port', 4370), timeout=5, password=0, force_udp=False, ommit_ping=False)
    zk_conn = None
    zk_records = []
    try:
        print(f"[{device_sn}] Connecting to {dev['ip']}...")
        zk_conn = zk.connect()
        print(f"[{device_sn}] Connected, fetching attendance...")
        zk_conn.disable_device()
        zk_records = zk_conn.get_attendance()
        print(f"[{device_sn}] Retrieved {len(zk_records)} records from device (total).")
    except Exception as e:
        print(f"[{device_sn}] ZK fetch failed: {e}")
    finally:
        if zk_conn:
            try:
                zk_conn.enable_device()
            except Exception:
                pass
            try:
                zk_conn.disconnect()
            except Exception:
                pass

    # Filter ZK records to the compare date
    df_zk = zk_records_to_df_filtered(zk_records, device_sn, date_str)
    print(f"[{device_sn}] Filtered ZK records to date {date_str}: {len(df_zk)} rows")

    # read Access under lock
    df_app_access = pd.DataFrame()
    df_exist_access = pd.DataFrame()
    try:
        with DirLock(ACCESS_LOCK_DIR, stale_seconds=LOCK_STALE_SECONDS, timeout=LOCK_TIMEOUT_SECONDS):
            print(f"[{device_sn}] Acquired access lock; opening Access DBs...")
            conn_app = connect_access(APP_ACCESS)
            conn_exist = connect_access(EXIST_ACCESS)
            try:
                df_app_access = fetch_access_rows_for_device(conn_app, table="CHECKINOUT", sn=device_sn, date_str=date_str)
            except Exception as e:
                print(f"[{device_sn}] Could not read app Access CHECKINOUT: {e}")
                df_app_access = pd.DataFrame()
            try:
                df_exist_access = fetch_access_rows_for_device(conn_exist, table="CHECKINOUT", sn=device_sn, date_str=date_str)
            except Exception as e:
                print(f"[{device_sn}] Could not read existing Access CHECKINOUT: {e}")
                df_exist_access = pd.DataFrame()
            conn_app.close()
            conn_exist.close()
    except TimeoutError:
        print(f"[{device_sn}] Could not acquire Access lock; skipping Access read for this run.")
    except Exception as e:
        print(f"[{device_sn}] Access-read error: {e}")

    summary = compare_and_write(df_zk, df_app_access, df_exist_access, out_dir_dev, device_sn, date_str)
    print(f"[{device_sn}] Summary: {json.dumps(summary)}")

def main():
    print("COMPARE ZK vs Access (multi-device, hard-coded, filtered)")
    print("App Access:", APP_ACCESS)
    print("Existing Access:", EXIST_ACCESS)
    print("Out dir:", OUT_DIR)
    print("Date:", COMPARE_DATE)
    for dev in DEVICES:
        try:
            run_for_device(dev)
        except Exception as e:
            print(f"[{dev['sn']}] ERROR running comparison: {e}")

if __name__ == "__main__":
    main()
