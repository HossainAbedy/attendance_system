import subprocess
from zk import ZK
from concurrent.futures import ThreadPoolExecutor, as_completed

START = 51
END = 65
DEVICE_SUFFIX = "230"
PORT = 4370
TIMEOUT = 3  # seconds

def is_pingable(ip):
    try:
        result = subprocess.run(["ping", "-n", "1", "-w", "500", ip], stdout=subprocess.DEVNULL)
        return result.returncode == 0
    except Exception:
        return False

def connect_and_get_serial(ip):
    zk = ZK(ip, port=PORT, timeout=TIMEOUT, password=0)
    try:
        conn = zk.connect()
        serial = conn.get_serialnumber()
        conn.disconnect()
        return {"ip": ip, "serial": serial}
    except Exception as e:
        return None

def scan_and_collect():
    print("[SCANNING] Starting device scan...\n")
    serials = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {}
        for i in range(START, END + 1):
            ip = f"172.19.{i}.{DEVICE_SUFFIX}"
            if is_pingable(ip):
                futures[executor.submit(connect_and_get_serial, ip)] = ip
            else:
                print(f"[UNREACHABLE] {ip}")

        for future in as_completed(futures):
            result = future.result()
            if result:
                print(f"[CONNECTED] {result['ip']} → Serial: {result['serial']}")
                serials.append(result)
            else:
                print(f"[FAILED] {futures[future]} → Connection or fetch failed")

    return serials

if __name__ == "__main__":
    results = scan_and_collect()
    print("\n✅ Completed Scan. Found:")
    for entry in results:
        print(f"  {entry['ip']} => {entry['serial']}")
