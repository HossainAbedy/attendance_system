import json
from zk import ZK, const

def fetch_device_data(ip: str, port: int = 4370, timeout: int = 10):
    """
    Connect to ZKTeco device and fetch users + attendance logs
    """
    zk = ZK(ip, port=port, timeout=timeout, password=0, force_udp=False, ommit_ping=False)
    conn = None
    data = {"users": [], "attendance": []}

    try:
        print(f"Connecting to device {ip}:{port} ...")
        conn = zk.connect()
        conn.disable_device()

        # Fetch all users (employees registered on device)
        users = conn.get_users()
        for user in users:
            data["users"].append({
                "user_id": user.user_id,        # internal device ID
                "name": user.name,              # may be blank
                "privilege": user.privilege,
                "password": user.password,
                "group_id": user.group_id,
                "user_uid": user.uid,
                "badge_number": getattr(user, "card", None)  # sometimes mapped here
            })

        # Fetch all attendance logs
        attendances = conn.get_attendance()
        for att in attendances:
            data["attendance"].append({
                "user_id": att.user_id,
                "timestamp": att.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "status": att.status,
                "punch": att.punch,
                #"workcode": att.workcode,
                "badge_number": att.user_id  # often user_id = badge number
            })

        print("Data fetch complete.")

    except Exception as e:
        print(f"Process failed: {e}")
    finally:
        if conn:
            conn.enable_device()
            conn.disconnect()

    return data


if __name__ == "__main__":
    DEVICE_IP = "172.19.122.231"  # replace with your device IP
    DEVICE_PORT = 4370           # default ZKTeco port

    result = fetch_device_data(DEVICE_IP, DEVICE_PORT)

    # Save to JSON file
    with open("device_dump.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=4, ensure_ascii=False)

    print("✅ JSON saved to device_dump.json")
