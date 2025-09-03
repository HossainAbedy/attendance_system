# app/views/admin.py
from flask import Blueprint, jsonify, current_app
from app.exporter import export_attendance_direct
from colorama import Fore
import traceback

bp = Blueprint("admin", __name__)

@bp.post("/export/enddb")
def trigger_export():
    try:
        batch_size = current_app.config.get("EXPORT_BATCH_SIZE", 1500)
        lookback_days = current_app.config.get("EXPORT_LOOKBACK_DAYS", 10)

        # run export directly (synchronous)
        result = export_attendance_direct(
            batch_size=batch_size,
            lookback_days=lookback_days
        )

        print(Fore.GREEN + f"[ADMIN] Manual export finished. {result}")
        return jsonify({"status": "ok", "result": result})
    except Exception as e:
        tb = traceback.format_exc()
        print(Fore.RED + f"[ADMIN ERROR] Manual export failed: {e}\n{tb}")
        return jsonify({"status": "error", "error": str(e)}), 500
