# compare_att.py
import pymysql
import csv
import json
from datetime import datetime

# ---------- CONFIG (hard-coded per your request) ----------
DB_HOST = "localhost"
DB_PORT = 3306
DB_USER = "test_user"
DB_PASS = "test_pass"
DB_NAME = "test_end_db"

# date to compare (YYYY-MM-DD) - change if needed
TARGET_DATE = "2025-08-24"

OLD_TABLE = "att_raw_data_old"
FLASK_TABLE = "att_raw_data_flask"

OUT_DIR = "compare_out"
# --------------------------------------------------------

import os
os.makedirs(OUT_DIR, exist_ok=True)

def fetch_rows(conn, table, datecol='log_date', date=TARGET_DATE):
    with conn.cursor() as cur:
        sql = f"SELECT id, log_date, badge, log_time, access_device, access_door, batch, source FROM {table} WHERE {datecol} = %s"
        cur.execute(sql, (date,))
        rows = cur.fetchall()
        # normalize into tuple keys for easy diffing
        norm = []
        for r in rows:
            id_, log_date, badge, log_time, device, door, batch, source = r
            badge_norm = (str(badge).strip() if badge is not None else "")
            time_norm = (log_time.strftime("%H:%M:%S") if hasattr(log_time, "strftime") else (str(log_time) if log_time is not None else ""))
            device_norm = (device or "").strip()
            door_norm = (door or "").strip()
            batch_norm = (batch or "").strip()
            norm.append({
                "id": id_,
                "badge": badge_norm,
                "time": time_norm,
                "device": device_norm,
                "door": door_norm,
                "batch": batch_norm,
                "source": source or table
            })
        return norm

def key_for_row(r):
    # key for set membership: (badge, time, door) - adjust if you want looser matching
    return (r["badge"], r["time"], r["door"])

def main():
    conn = pymysql.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS, database=DB_NAME, cursorclass=pymysql.cursors.Cursor)
    try:
        old_rows = fetch_rows(conn, OLD_TABLE)
        flask_rows = fetch_rows(conn, FLASK_TABLE)

        old_map = { key_for_row(r): r for r in old_rows }
        flask_map = { key_for_row(r): r for r in flask_rows }

        only_old_keys = set(old_map.keys()) - set(flask_map.keys())
        only_flask_keys = set(flask_map.keys()) - set(old_map.keys())
        both_keys = set(old_map.keys()) & set(flask_map.keys())

        # badge-based mismatches: same badge exists but time differs (or door differs)
        # build maps keyed by badge -> list of rows
        from collections import defaultdict
        old_by_badge = defaultdict(list)
        flask_by_badge = defaultdict(list)
        for r in old_rows:
            old_by_badge[r["badge"]].append(r)
        for r in flask_rows:
            flask_by_badge[r["badge"]].append(r)

        badge_mismatches = []
        for badge in set(list(old_by_badge.keys()) + list(flask_by_badge.keys())):
            old_times = sorted({(rr["time"], rr["door"]) for rr in old_by_badge.get(badge, [])})
            flask_times = sorted({(rr["time"], rr["door"]) for rr in flask_by_badge.get(badge, [])})
            if old_times != flask_times:
                badge_mismatches.append({
                    "badge": badge,
                    "old": old_times,
                    "flask": flask_times
                })

        report = {
            "date": TARGET_DATE,
            "old_count": len(old_rows),
            "flask_count": len(flask_rows),
            "only_old_count": len(only_old_keys),
            "only_flask_count": len(only_flask_keys),
            "both_count": len(both_keys),
            "only_old_examples": [ old_map[k] for k in list(only_old_keys)[:20] ],
            "only_flask_examples": [ flask_map[k] for k in list(only_flask_keys)[:20] ],
            "badge_mismatches_count": len(badge_mismatches),
            "badge_mismatches_sample": badge_mismatches[:50]
        }

        # Write JSON report
        with open(os.path.join(OUT_DIR, f"compare_report_{TARGET_DATE}.json"), "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, default=str)

        # Write CSVs for manual inspection
        def rows_to_csv(rows, fn):
            with open(os.path.join(OUT_DIR, fn), "w", newline='', encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=["id","badge","time","device","door","batch","source"])
                writer.writeheader()
                for r in rows:
                    writer.writerow(r)

        rows_to_csv([old_map[k] for k in sorted(old_map.keys())], f"old_{TARGET_DATE}.csv")
        rows_to_csv([flask_map[k] for k in sorted(flask_map.keys())], f"flask_{TARGET_DATE}.csv")
        rows_to_csv([old_map[k] for k in list(only_old_keys)], f"only_old_{TARGET_DATE}.csv")
        rows_to_csv([flask_map[k] for k in list(only_flask_keys)], f"only_flask_{TARGET_DATE}.csv")

        print("REPORT SUMMARY:")
        print(json.dumps(report, indent=2, default=str))

        # Print suggested DELETE SQL for Flask rows for that date (hand to DBA)
        print("\n-- Suggested delete (Flask rows for date) --")
        print(f"DELETE FROM {FLASK_TABLE} WHERE log_date = '{TARGET_DATE}';")
        print("-- If you prefer to delete only the rows that are not present in old system:")
        if only_flask_keys:
            print("/* Delete only these specific rows (flask-only): */")
            for r in [flask_map[k] for k in list(only_flask_keys)[:200]]:
                # include guard for empty badge - DBA can review
                badge = r['badge'] or ''
                time = r['time'] or ''
                door = r['door'] or ''
                print(f"-- Row sample badge={badge} time={time} door={door}")
            print(f"/* Compose DELETE WHERE (badge,time,door) IN (...) based on above list. */")

    finally:
        conn.close()

if __name__ == '__main__':
    main()
