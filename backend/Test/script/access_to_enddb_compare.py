# compare_by_badge_date.py
import pymysql
from datetime import datetime
import sys

# ---------------------------
# CONFIG - edit if needed
# ---------------------------
DB_CONFIG = {
    "host": "localhost",
    "user": "test_user",
    "password": "test_pass",
    "database": "test_end_db",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor
}
OLD_TABLE = "att_raw_data_old"
NEW_TABLE = "att_raw_data_new"
# ---------------------------

def get_conn():
    return pymysql.connect(**DB_CONFIG)

def normalize_badge(b):
    if b is None:
        return None
    s = str(b).strip()
    if not s:
        return None
    # drop leading zeros for normalization but preserve if all zeros
    s_n = s.lstrip('0')
    return s_n if s_n != '' else s

def fetch_aggregated_counts(table, start_date, end_date):
    """Return dict keyed by (norm_badge, log_date) -> { 'raw_examples': set(...), 'count': int }"""
    q = f"""
        SELECT badge, log_date, COUNT(*) AS cnt
        FROM {table}
        WHERE log_date BETWEEN %s AND %s
        GROUP BY badge, log_date
        ORDER BY badge, log_date
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(q, (start_date, end_date))
        rows = cur.fetchall()
    finally:
        conn.close()

    result = {}
    badges_seen = set()
    for r in rows:
        raw_badge = r.get('badge')
        log_date = r.get('log_date')
        cnt = int(r.get('cnt') or 0)

        norm = normalize_badge(raw_badge)
        # use text yyyy-mm-dd for consistency
        if hasattr(log_date, "strftime"):
            dstr = log_date.strftime("%Y-%m-%d")
        else:
            dstr = str(log_date)

        key = (norm, dstr)
        if key not in result:
            result[key] = {"raw_examples": set(), "count": 0}
        result[key]["raw_examples"].add(str(raw_badge))
        result[key]["count"] += cnt
        badges_seen.add(norm)
    return result, badges_seen

def build_report(old_map, new_map):
    # gather union keys
    keys = set(old_map.keys()) | set(new_map.keys())
    rows = []
    for key in sorted(keys, key=lambda x: (x[0] or "", x[1])):  # sort by norm_badge then date
        norm_badge, log_date = key
        old_cnt = old_map.get(key, {}).get("count", 0)
        new_cnt = new_map.get(key, {}).get("count", 0)
        raw_examples = set()
        raw_examples |= old_map.get(key, {}).get("raw_examples", set())
        raw_examples |= new_map.get(key, {}).get("raw_examples", set())

        if old_cnt == new_cnt:
            status = "MATCH"
            missing_count = 0
        elif old_cnt > new_cnt:
            status = "MISSING_IN_NEW"
            missing_count = old_cnt - new_cnt
        else:
            status = "EXTRA_IN_NEW"
            missing_count = new_cnt - old_cnt

        rows.append({
            "norm_badge": norm_badge or "<NULL>",
            "log_date": log_date,
            "status": status,
            "missing_count": missing_count,
            "old_count": old_cnt,
            "new_count": new_cnt,
            "raw_examples": ";".join(sorted(raw_examples))
        })
    return rows

def print_report(rows, old_only_badges, new_only_badges):
    # header
    print("Badge | Date       | Status        | MissingCnt | old_count | new_count | raw_examples")
    print("-" * 100)
    for r in rows:
        print(f"{r['norm_badge']:<6} | {r['log_date']} | {r['status']:<13} | "
              f"{r['missing_count']:>10} | {r['old_count']:>9} | {r['new_count']:>9} | {r['raw_examples']}")
    print("-" * 100)

    total_rows = len(rows)
    total_missing = sum(r['missing_count'] for r in rows if r['status'] == 'MISSING_IN_NEW')
    total_extra = sum(r['missing_count'] for r in rows if r['status'] == 'EXTRA_IN_NEW')

    print("\nSUMMARY")
    print(f"Total badge×date rows compared : {total_rows}")
    print(f"Total missing in NEW (sum)     : {total_missing}")
    print(f"Total extra in NEW (sum)       : {total_extra}")
    print(f"Badges present only in OLD     : {len(old_only_badges)}")
    print(f"Badges present only in NEW     : {len(new_only_badges)}")

    if old_only_badges:
        print("\nBadges only in OLD (sample up to 50):")
        for b in sorted(list(old_only_badges)[:50]):
            print(" ", b)
    if new_only_badges:
        print("\nBadges only in NEW (sample up to 50):")
        for b in sorted(list(new_only_badges)[:50]):
            print(" ", b)

def main():
    # input dates: YYYY-MM-DD
    if len(sys.argv) >= 3:
        start_date = sys.argv[1]
        end_date = sys.argv[2]
    else:
        # default to today
        today = datetime.utcnow().strftime("%Y-%m-%d")
        start_date = today
        end_date = today

    print(f"[INFO] Date range: {start_date} .. {end_date}")

    old_map, old_badges = fetch_aggregated_counts(OLD_TABLE, start_date, end_date)
    new_map, new_badges = fetch_aggregated_counts(NEW_TABLE, start_date, end_date)

    # badges only present in one side
    old_only = (old_badges - new_badges) - {None}
    new_only = (new_badges - old_badges) - {None}

    rows = build_report(old_map, new_map)
    print_report(rows, old_only, new_only)

if __name__ == "__main__":
    main()
