import subprocess
import pandas as pd
from zk import ZK
from concurrent.futures import ThreadPoolExecutor, as_completed

PORT = 4370
TIMEOUT = 3  # seconds
DEVICE_SUFFIX = "231"
EXCEL_INPUT = "IP_List.xlsx"
EXCEL_OUTPUT = "Scan_Results.xlsx"

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
    except Exception:
        return None

def load_subnets_from_excel(filename=EXCEL_INPUT):
    try:
        df = pd.read_excel(filename)
    except ImportError:
        raise ImportError("Missing 'openpyxl'. Please run: pip install openpyxl")
    except Exception as e:
        raise RuntimeError(f"Error loading Excel file: {e}")
    
    # 3. Ensure expected columns are present
    if "Branch/Sub-Branch Name" not in df.columns or "IP List" not in df.columns:
        raise ValueError("Excel must have 'Branch/Sub-Branch Name' and 'IP List' columns")
    
    subnets = []
    for _, row in df.iterrows():
        subnet = row["IP List"]
        if isinstance(subnet, str) and subnet.count(".") == 3:
            third_octet = subnet.split(".")[2]
            ip = f"172.19.{third_octet}.{DEVICE_SUFFIX}"
            subnets.append((row["Branch/Sub-Branch Name"], ip))
    return subnets

def export_results_to_excel(results, filename=EXCEL_OUTPUT):
    df = pd.DataFrame(results)
    df.to_excel(filename, index=False)
    print(f"\n📁 Results exported to '{filename}'")

def scan_and_collect():
    print("[SCANNING] Starting device scan from Excel...\n")
    serials = []
    branches = load_subnets_from_excel()

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {}
        for branch_name, ip in branches:
            if is_pingable(ip):
                futures[executor.submit(connect_and_get_serial, ip)] = (branch_name, ip)
            else:
                print(f"[UNREACHABLE] {branch_name} → {ip}")

        for future in as_completed(futures):
            branch_name, ip = futures[future]
            result = future.result()
            if result:
                print(f"[CONNECTED] {branch_name} → {ip} → Serial: {result['serial']}")
                serials.append({"Branch": branch_name, "IP": ip, "Serial": result["serial"]})
            else:
                print(f"[FAILED] {branch_name} → {ip} → Connection or fetch failed")

    return serials

if __name__ == "__main__":
    results = scan_and_collect()
    print("\n✅ Completed Scan. Found:")
    for entry in results:
        print(f"  {entry['Branch']} => {entry['IP']} => {entry['Serial']}")

    if results:
        export_results_to_excel(results)
