import json
from collections import defaultdict

# Path to your log file
log_file = "find_empty_badge.txt"

empty_badges = defaultdict(int)
empty_rows = []

with open(log_file, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line.startswith("ROW:"):
            try:
                row_json = line.split("ROW:", 1)[1].strip()
                row = json.loads(row_json)

                # Check for empty badge
                if row.get("badge", "") == "":
                    key = (row.get("date", "UNKNOWN"), row.get("device", "UNKNOWN"))
                    empty_badges[key] += 1
                    empty_rows.append(row)

            except Exception as e:
                print("Parse error:", e, "in line:", line)

# Print summary
print("=== Devices with Empty Badges by Date ===")
for (date, device), count in sorted(empty_badges.items()):
    print(f"{date} — {device}: {count} empty badge logs")

print("\n=== Raw Rows with Empty Badges ===")
for row in empty_rows:
    print(row)
