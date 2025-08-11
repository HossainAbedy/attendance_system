# FILE: app/views/logs.py
from flask import Blueprint, request, jsonify
from sqlalchemy import or_, cast, String, desc, asc
from sqlalchemy.orm import joinedload
from datetime import datetime

from ..models import Device, AttendanceLog
from .. import db
from ..tasks import fetch_and_forward_for_device
from zk.exception import ZKNetworkError

bp = Blueprint("logs", __name__)

# --- existing poll endpoint (kept relative) ---
@bp.route("/poll/<int:device_id>", methods=["POST"])
def poll_device(device_id):
    """
    Manually trigger polling for a specific ZKTeco device by ID.
    Returns the number of records fetched and forwarded.
    Final URL (with blueprint prefix): /api/logs/poll/<device_id>
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


# --- helpers ---
def _parse_iso(dt_str):
    """Tolerant ISO / common datetime parsing; returns None on failure."""
    if not dt_str:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(dt_str, fmt)
        except Exception:
            pass
    try:
        return datetime.fromisoformat(dt_str)
    except Exception:
        return None


def _base_logs_query(join_device=True):
    q = AttendanceLog.query
    if join_device:
        q = q.options(joinedload(AttendanceLog.device))
    return q


def _serialize_log(l):
    return {
        "id": l.id,
        "device_id": l.device_id,
        "record_id": l.record_id,
        "user_id": l.user_id,
        "timestamp": l.timestamp.isoformat() if l.timestamp else None,
        "status": l.status,
        "created_at": l.created_at.isoformat() if l.created_at else None,
        "device": {
            "id": l.device.id if l.device else None,
            "name": getattr(l.device, "name", None) if l.device else None
        } if l.device else None
    }


# --- GET / (global logs) ---
@bp.route("", methods=["GET"])
@bp.route("/", methods=["GET"])
def get_logs():
    """
    GET /   -> with blueprint prefix '/api/logs' becomes GET /api/logs
    Query params:
      - page, per_page
      - q (free-text)
      - device_id, user_id, status, branch_id
      - from, to (ISO datetimes)
      - sort_by, sort_dir
    """
    try:
        # pagination params
        page = request.args.get("page", default=1, type=int) or 1
        per_page = request.args.get("per_page", default=25, type=int) or 25
        per_page = min(per_page, 200)

        q_text = request.args.get("q", type=str)
        device_id = request.args.get("device_id", type=int)
        user_id = request.args.get("user_id", type=str)
        status = request.args.get("status", type=str)
        branch_id = request.args.get("branch_id", type=int)
        from_ts = request.args.get("from", type=str)
        to_ts = request.args.get("to", type=str)
        sort_by = request.args.get("sort_by", "timestamp")
        sort_dir = request.args.get("sort_dir", "desc")

        query = _base_logs_query(join_device=True)

        # filters
        if device_id:
            query = query.filter(AttendanceLog.device_id == device_id)
        if user_id:
            query = query.filter(AttendanceLog.user_id.ilike(f"%{user_id}%"))
        if status:
            query = query.filter(AttendanceLog.status.ilike(f"%{status}%"))
        if from_ts:
            dt = _parse_iso(from_ts)
            if dt:
                query = query.filter(AttendanceLog.timestamp >= dt)
        if to_ts:
            dt = _parse_iso(to_ts)
            if dt:
                query = query.filter(AttendanceLog.timestamp <= dt)

        # optional branch filter if Device has branch_id column
        if branch_id:
            try:
                if hasattr(Device, "branch_id") or ("branch_id" in getattr(Device, "__table__").columns):
                    query = query.join(Device).filter(getattr(Device, "branch_id") == branch_id)
            except Exception:
                pass

        # free-text search across common fields (casts numeric/datetime to string)
        if q_text:
            pattern = f"%{q_text}%"
            query = query.filter(
                or_(
                    cast(AttendanceLog.id, String).ilike(pattern),
                    cast(AttendanceLog.device_id, String).ilike(pattern),
                    cast(AttendanceLog.record_id, String).ilike(pattern),
                    AttendanceLog.user_id.ilike(pattern),
                    cast(AttendanceLog.timestamp, String).ilike(pattern),
                    AttendanceLog.status.ilike(pattern),
                    cast(AttendanceLog.created_at, String).ilike(pattern),
                )
            )

        # sorting
        if hasattr(AttendanceLog, sort_by):
            sort_col = getattr(AttendanceLog, sort_by)
        else:
            sort_col = AttendanceLog.timestamp

        if str(sort_dir).lower() == "asc":
            query = query.order_by(asc(sort_col))
        else:
            query = query.order_by(desc(sort_col))

        pag = query.paginate(page=page, per_page=per_page, error_out=False)
        items = [_serialize_log(it) for it in pag.items]

        return jsonify({
            "items": items,
            "total": pag.total,
            "page": pag.page,
            "per_page": pag.per_page,
            "pages": pag.pages,
            "has_next": pag.has_next,
            "has_prev": pag.has_prev,
        }), 200

    except Exception as e:
        # always return JSON on error
        return jsonify({"error": "internal", "message": str(e)}), 500


# --- GET /device/<device_id> (device-specific) ---
@bp.route("/device/<int:device_id>", methods=["GET"])
@bp.route("/device/<int:device_id>/", methods=["GET"])
def get_logs_for_device(device_id):
    """
    GET /device/<id> -> with blueprint prefix '/api/logs' becomes /api/logs/device/<id>
    Supports same query params as get_logs (except device_id in path)
    """
    try:
        page = request.args.get("page", default=1, type=int) or 1
        per_page = request.args.get("per_page", default=25, type=int) or 25
        per_page = min(per_page, 200)

        q_text = request.args.get("q", type=str)
        user_id = request.args.get("user_id", type=str)
        status = request.args.get("status", type=str)
        from_ts = request.args.get("from", type=str)
        to_ts = request.args.get("to", type=str)
        sort_by = request.args.get("sort_by", "timestamp")
        sort_dir = request.args.get("sort_dir", "desc")

        query = _base_logs_query(join_device=True).filter(AttendanceLog.device_id == device_id)

        if user_id:
            query = query.filter(AttendanceLog.user_id.ilike(f"%{user_id}%"))
        if status:
            query = query.filter(AttendanceLog.status.ilike(f"%{status}%"))
        if from_ts:
            dt = _parse_iso(from_ts)
            if dt:
                query = query.filter(AttendanceLog.timestamp >= dt)
        if to_ts:
            dt = _parse_iso(to_ts)
            if dt:
                query = query.filter(AttendanceLog.timestamp <= dt)

        if q_text:
            pattern = f"%{q_text}%"
            query = query.filter(
                or_(
                    cast(AttendanceLog.id, String).ilike(pattern),
                    cast(AttendanceLog.record_id, String).ilike(pattern),
                    AttendanceLog.user_id.ilike(pattern),
                    cast(AttendanceLog.timestamp, String).ilike(pattern),
                    AttendanceLog.status.ilike(pattern),
                )
            )

        # sorting
        if hasattr(AttendanceLog, sort_by):
            sort_col = getattr(AttendanceLog, sort_by)
        else:
            sort_col = AttendanceLog.timestamp

        if str(sort_dir).lower() == "asc":
            query = query.order_by(asc(sort_col))
        else:
            query = query.order_by(desc(sort_col))

        pag = query.paginate(page=page, per_page=per_page, error_out=False)
        items = [_serialize_log(l) for l in pag.items]

        return jsonify({
            "items": items,
            "total": pag.total,
            "page": pag.page,
            "per_page": pag.per_page,
            "pages": pag.pages,
            "has_next": pag.has_next,
            "has_prev": pag.has_prev,
        }), 200

    except Exception as e:
        return jsonify({"error": "internal", "message": str(e)}), 500
