#!/usr/bin/env python3
"""
export_access_diagnostics.py

Export CHECKINOUT and USERINFO from a Microsoft Access .mdb/.accdb file and run diagnostics.

Produces CSVs in the export directory and a short human-readable report:
  - CHECKINOUT_lastN.csv
  - USERINFO.csv
  - CHECKINOUT_suspicious_times.csv
  - CHECKINOUT_missing_userinfo.csv
  - CHECKINOUT_bad_badgenumber_length.csv
  - CHECKINOUT_duplicates.csv
  - report.txt

Usage:
  python export_access_diagnostics.py --mdb "C:/path/to/att2000.mdb" --outdir ./out --days 30 --mask

Dependencies:
  pip install pyodbc pandas python-dateutil

Notes:
  - On Windows you must have the Access ODBC driver installed:
    - "Microsoft Access Driver (*.mdb, *.accdb)"
  - Run this on the machine that has access to the .mdb file (the PHP/Flask server).
  - If you cannot install pyodbc, the script can be adapted to use pypyodbc or run via PHP export.
  - Use --mask to hash Badgenumber (recommended before sharing CSVs).

Be careful with any PII before sharing CSVs publicly.
"""

import os
import sys
import argparse
import hashlib
from datetime import datetime, timedelta
import pyodbc
import pandas as pd

DEFAULT_DRIVER = r"Microsoft Access Driver (*.mdb, *.accdb)"

def parse_args():
    p = argparse.ArgumentParser(description="Export Access CHECKINOUT/USERINFO and run diagnostics.")
    p.add_argument('--mdb', required=True, help="Path to the .mdb/.accdb file (e.g. C:/.../att2000.mdb)")
    p.add_argument('--outdir', default='./access_export', help="Output directory for CSVs and report")
    p.add_argument('--driver', default=DEFAULT_DRIVER, help="ODBC driver name (default: %(default)s)")
    p.add_argument('--days', type=int, default=30, help="How many days lookback for CHECKINOUT export (default 30)")
    p.add_argument('--mask', action='store_true', help="Mask (hash) Badgenumber/USERID columns in exported CSVs")
    return p.parse_args()

def connect_access(mdb_path, driver):
    # Build connection string for pyodbc
    conn_str = (
        r"DRIVER={%s};" % driver +
        r"DBQ=%s;" % mdb_path
    )
    try:
        conn = pyodbc.connect(conn_str, autocommit=True)
        return conn
    except Exception as e:
        raise RuntimeError(f"Failed to open Access DB with driver '{driver}': {e}")

def hash_value(v):
    if pd.isna(v):
        return v
    s = str(v)
    return hashlib.sha1(s.encode('utf-8')).hexdigest()[:12]  # short hash

def export_table_df(conn, sql, outfn, mask=False, mask_cols=None):
    try:
        df = pd.read_sql(sql, conn)
    except Exception as e:
        # Fallback: run lower-level fetch
        cur = conn.cursor()
        cur.execute(sql)
        cols = [c[0] for c in cur.description]
        rows = cur.fetchall()
        df = pd.DataFrame.from_records(rows, columns=cols)

    if mask and mask_cols:
        for c in mask_cols:
            if c in df.columns:
                df[c] = df[c].apply(hash_value)
    df.to_csv(outfn, index=False)
    return df

def main():
    args = parse_args()
    mdb = args.mdb
    outdir = os.path.abspath(args.outdir)
    days = args.days

    if not os.path.exists(mdb):
        print(f"ERROR: mdb file not found: {mdb}", file=sys.stderr)
        sys.exit(2)
    os.makedirs(outdir, exist_ok=True)

    print("Connecting to Access...")
    conn = connect_access(mdb, args.driver)

    lookback_date_access = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    # Export CHECKINOUT last N days (uses Access Format function in SQL if available)
    # Use a safe SQL that works with Access SQL dialect via ODBC.
    chk_sql = (
        f"SELECT * FROM CHECKINOUT WHERE Format(CHECKTIME,'YYYY-MM-DD') >= '{lookback_date_access}' ORDER BY CHECKTIME"
    )
    print("Exporting CHECKINOUT...")
    chk_csv = os.path.join(outdir, f"CHECKINOUT_last{days}.csv")
    chk_df = export_table_df(conn, chk_sql, chk_csv, mask=args.mask, mask_cols=['Badgenumber', 'USERID', 'USERID2'] if args.mask else None)
    print(f"Wrote {chk_csv} ({len(chk_df)} rows)")

    # Export entire USERINFO table
    print("Exporting USERINFO...")
    usr_sql = "SELECT * FROM USERINFO"
    usr_csv = os.path.join(outdir, "USERINFO.csv")
    usr_df = export_table_df(conn, usr_sql, usr_csv, mask=args.mask, mask_cols=['USERID', 'Badgenumber'] if args.mask else None)
    print(f"Wrote {usr_csv} ({len(usr_df)} rows)")

    # DIAGNOSTICS
    print("Running diagnostics...")
    report_lines = []
    report_lines.append(f"Access file: {mdb}")
    report_lines.append(f"Export path: {outdir}")
    report_lines.append(f"Rows exported (CHECKINOUT): {len(chk_df)}")
    report_lines.append(f"Rows exported (USERINFO): {len(usr_df)}")
    report_lines.append("")

    # Suspicious times: non-parseable or year outside [2000,2030]
    def is_bad_time(val):
        if pd.isna(val):
            return True
        try:
            dt = pd.to_datetime(val)
            if dt.year < 2000 or dt.year > 2030:
                return True
            return False
        except Exception:
            return True

    bad_time_mask = chk_df['CHECKTIME'].apply(is_bad_time)
    bad_time_df = chk_df[bad_time_mask]
    bad_time_csv = os.path.join(outdir, "CHECKINOUT_suspicious_times.csv")
    bad_time_df.to_csv(bad_time_csv, index=False)
    report_lines.append(f"Suspicious CHECKTIME rows: {len(bad_time_df)} (written to {bad_time_csv})")

    # Entries with Badgenumber not present in USERINFO.USERID (or USERID mismatch)
    if 'Badgenumber' in chk_df.columns:
        usr_ids = set(usr_df['USERID'].astype(str)) if 'USERID' in usr_df.columns else set()
        missing_mask = ~chk_df['Badgenumber'].astype(str).isin(usr_ids)
        missing_df = chk_df[missing_mask]
        missing_csv = os.path.join(outdir, "CHECKINOUT_missing_userinfo.csv")
        missing_df.to_csv(missing_csv, index=False)
        report_lines.append(f"CHECKINOUT rows with Badgenumber missing from USERINFO: {len(missing_df)} (written to {missing_csv})")
    else:
        report_lines.append("CHECKINOUT has no Badgenumber column; skipping missing-userinfo check.")

    # Rows with Badgenumber length > 4 (your scripts skip those)
    if 'Badgenumber' in chk_df.columns:
        long_bad_mask = chk_df['Badgenumber'].astype(str).str.len() > 4
        long_bad_df = chk_df[long_bad_mask]
        long_bad_csv = os.path.join(outdir, "CHECKINOUT_bad_badgenumber_length.csv")
        long_bad_df.to_csv(long_bad_csv, index=False)
        report_lines.append(f"CHECKINOUT rows with Badgenumber length>4: {len(long_bad_df)} (written to {long_bad_csv})")

    # Duplicate events in CHECKINOUT (same Badgenumber and same CHECKTIME)
    if 'Badgenumber' in chk_df.columns and 'CHECKTIME' in chk_df.columns:
        dups = chk_df.groupby(['Badgenumber', 'CHECKTIME']).size().reset_index(name='count')
        dups = dups[dups['count'] > 1].sort_values('count', ascending=False)
        dup_csv = os.path.join(outdir, "CHECKINOUT_duplicates.csv")
        dup_df = chk_df.merge(dups[['Badgenumber','CHECKTIME']], on=['Badgenumber','CHECKTIME'], how='inner')
        dup_df.to_csv(dup_csv, index=False)
        report_lines.append(f"Duplicate CHECKINOUT events (same Badgenumber+CHECKTIME): {len(dup_df)} (written to {dup_csv})")
    else:
        report_lines.append("Dup check skipped (missing columns).")

    # Additional heuristic: events that after -10min adjustment may roll to previous day
    # We'll compute adjusted time and show rows where date changes
    try:
        # parse as datetimes; create adjusted column
        parsed = pd.to_datetime(chk_df['CHECKTIME'], errors='coerce')
        adj = parsed - pd.Timedelta(minutes=10)
        # rows where original date != adjusted date
        date_roll_mask = parsed.dt.date != adj.dt.date
        date_roll_df = chk_df[date_roll_mask]
        date_roll_csv = os.path.join(outdir, "CHECKINOUT_date_rollover_due_to_minus10.csv")
        date_roll_df.to_csv(date_roll_csv, index=False)
        report_lines.append(f"Rows that would move to previous day after '-10 minutes' adjustment: {len(date_roll_df)} (written to {date_roll_csv})")
    except Exception as e:
        report_lines.append(f"Date-roll check failed: {e}")

    # Save report
    report_fn = os.path.join(outdir, "report.txt")
    with open(report_fn, "w", encoding="utf-8") as fh:
        fh.write("\\n".join(report_lines))
    print("\\n".join(report_lines))
    print(f"Report written to {report_fn}")
    print("All CSVs in:", outdir)

if __name__ == "__main__":
    main()

