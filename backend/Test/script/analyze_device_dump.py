# scripts/analyze_device_dump.py
import json, csv
from pathlib import Path

IN = "device_dump.json"
OUT_SQL = "device_dump_inserts.sql"
OUT_CSV = "device_dump_preview.csv"

def analyze(infile=IN):
    j = json.load(open(infile, "r", encoding="utf-8"))
    sn = j.get("meta", {}).get("ip", "DEVICE_IP")  # you can replace with device.serial if you know it
    users = j.get("users", [])
    attendance = j.get("attendance", [])

    sql_lines = []
    csv_rows = []
    csv_rows.append(["type","user_id_or_badge","name_or_ts","extra","recommended_insert_sql"])

    for u in users:
        uid = u.get("user_id") or u.get("uid") or ""
        name = u.get("name") or ""
        bad = u.get("card") or u.get("badge") or uid or ""
        # escape quotes safely
        esc_name = name.replace("'", "''") if name else ""
        sql = (
            "-- upsert access_userinfo (preview)\n"
            f"REPLACE INTO access_userinfo (USERID, Badgenumber, Name, sn, source) "
            f"VALUES ('{uid}', '{bad}', '{esc_name}', '{sn}', 'zk_device');"
        )
        sql_lines.append(sql)
        csv_rows.append(["access_userinfo", uid, name, bad, sql])

    for a in attendance[:200]:
        badge = a.get("user_id") or ""
        ts = a.get("timestamp") or ""
        if ts and " " in ts:
            ld, lt = ts.split(" ",1)
            lt = lt.split(".")[0]
        else:
            ld, lt = ts, ""
        sql = (
            f"INSERT INTO att_raw_data_old VALUES (NULL, '{ld}', '{badge}', '{badge}', '', '{lt}', '0', '1', '', '{sn}');"
        )
        sql_lines.append(sql)
        csv_rows.append(["att_raw_data_old", badge, ts, "", sql])

    open(OUT_SQL, "w", encoding="utf-8").write("\n".join(sql_lines))
    with open(OUT_CSV, "w", newline='', encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerows(csv_rows)

    print(f"SQL preview written to {OUT_SQL}")
    print(f"CSV preview written to {OUT_CSV}")
    print("Open these files and verify carefully before applying to DB.")

if __name__ == "__main__":
    analyze()
