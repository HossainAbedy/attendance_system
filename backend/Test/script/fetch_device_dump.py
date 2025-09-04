# scripts/fetch_device_dump.py
import json
from zk import ZK, const
from datetime import datetime

def fetch_device_data(ip: str, port: int = 4370, timeout: int = 10):
    zk = ZK(ip, port=port, timeout=timeout, password=0, force_udp=False, ommit_ping=False)
    conn = None
    data = {"meta": {"ip": ip, "port": port, "fetched_at": datetime.utcnow().isoformat()}, "users": [], "attendance": []}

    try:
        print(f"Connecting to device {ip}:{port} ...")
        conn = zk.connect()
        conn.disable_device()

        # Fetch all users (employees registered on device)
        users = []
        if hasattr(conn, "get_users"):
            users = conn.get_users()
        elif hasattr(conn, "get_user"):
            try:
                u = conn.get_user()
                if u:
                    users = [u]
            except Exception:
                users = []

        for user in users:
            data["users"].append({
                "raw": repr(user),
                "user_id": getattr(user, "user_id", None),
                "uid": getattr(user, "uid", None),
                "card": getattr(user, "card", None),
                "badge": getattr(user, "badge", None),
                "cardnumber": getattr(user, "cardnumber", None),
                "name": getattr(user, "name", None),
                "privilege": getattr(user, "privilege", None),
                "password": getattr(user, "password", None),
                "group_id": getattr(user, "group_id", None)
            })

        # Fetch all attendance logs
        attendances = []
        if hasattr(conn, "get_attendance"):
            attendances = conn.get_attendance() or []

        for att in attendances:
            data["attendance"].append({
                "raw": repr(att),
                "user_id": getattr(att, "user_id", None),
                "uid": getattr(att, "uid", None),
                "timestamp": getattr(att, "timestamp", None).strftime("%Y-%m-%d %H:%M:%S") if getattr(att, "timestamp", None) else None,
                "status": getattr(att, "status", None),
                "punch": getattr(att, "punch", None)
            })

        print("Data fetch complete.")

    except Exception as e:
        print(f"Process failed: {e}")
    finally:
        if conn:
            try:
                conn.enable_device()
            except Exception:
                pass
            try:
                conn.disconnect()
            except Exception:
                pass

    return data

if __name__ == "__main__":
    DEVICE_IP = "172.19.122.231"  # replace with your device IP
    DEVICE_PORT = 4370           # default ZKTeco port

    result = fetch_device_data(DEVICE_IP, DEVICE_PORT)

    out_fn = "device_dump.json"
    with open(out_fn, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"✅ JSON saved to {out_fn}")
