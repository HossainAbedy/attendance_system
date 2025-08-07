from flask import Blueprint, request, jsonify
from ..models import Device
from ..tasks import fetch_and_forward_for_device
from zk.exception import ZKNetworkError

bp = Blueprint("logs", __name__)

@bp.route("/poll/<int:device_id>", methods=["POST"])
def poll_device(device_id):
    """
    Manually trigger polling for a specific ZKTeco device by ID.
    Returns the number of records fetched and forwarded.
    """
    device = Device.query.get_or_404(device_id)
    
    try:
        count = fetch_and_forward_for_device(device)
        return jsonify({
            "device": device.id,
            "fetched_records": count
        }), 202

    except ZKNetworkError as e:
        return jsonify({
            "error": "zk_timeout",
            "message": f"Device {device.name} unreachable: {str(e)}"
        }), 504

    except Exception as e:
        return jsonify({
            "error": "internal",
            "message": str(e)
        }), 500
