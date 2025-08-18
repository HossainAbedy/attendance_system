# FILE: app/views/logs.py
from flask import Blueprint, request, jsonify
from sqlalchemy import or_, cast, String, desc, asc, func
from sqlalchemy.orm import joinedload
from datetime import datetime, time
from typing import Optional, Tuple, Dict, Any

from ..models import Device, AttendanceLog
from .. import db
from ..tasks import fetch_and_forward_for_device
from zk.exception import ZKNetworkError

bp = Blueprint("logs", __name__)

# --- poll endpoint ---
@bp.route("/poll/<int:device_id>", methods=["POST"])
def poll_device(device_id):
    device = Device.query.get_or_404(device_id)
    try:
        count = fetch_and_forward_for_device(device)
        return jsonify({"device": device.id, "fetched_records": count}), 202
    except ZKNetworkError as e:
        return jsonify({"error": "zk_timeout", "message": f"Device {device.name} unreachable: {str(e)}"}), 504
    except Exception as e:
        return jsonify({"error": "internal", "message": str(e)}), 500


# --- helpers ---
def _parse_iso(dt_str):
    """Tolerant parser: accepts YYYY-MM-DD, YYYY-MM-DDTHH:MM, YYYY-MM-DDTHH:MM:SS, with/without ms/Z"""
    if not dt_str:
        return None
    s = dt_str.strip()
    fmts = (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    )
    for f in fmts:
        try:
            return datetime.strptime(s, f)
        except Exception:
            pass
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _serialize_log(l: AttendanceLog) -> Dict[str, Any]:
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


def _count(q):
    """Return a quick count for a query (used only for optional debug)."""
    try:
        return q.order_by(None).count()
    except Exception:
        try:
            return db.session.query(func.count()).select_from(q.subquery()).scalar()
        except Exception:
            return None


def _extract_common_params() -> Dict[str, Any]:
    """Parse and normalize common request args used by both endpoints."""
    page = request.args.get("page", 1, type=int) or 1
    per_page = min(request.args.get("per_page", 25, type=int) or 25, 200)

    q_text = request.args.get("q", type=str)
    q_text = q_text.strip() or None if q_text is not None else None

    device_id = request.args.get("device_id", type=int)
    user_id = request.args.get("user_id", type=str)
    user_id = user_id.strip() or None if user_id else None

    status = request.args.get("status", type=str)
    status = status.strip() or None if status else None

    branch_id = request.args.get("branch_id", type=int) or request.args.get("branch", type=int)

    from_ts = request.args.get("from") or request.args.get("timestamp_from")
    to_ts = request.args.get("to") or request.args.get("timestamp_to")

    sort_by = request.args.get("sort_by", "timestamp")
    sort_dir = (request.args.get("sort_dir", "desc") or "desc").lower()
    debug = request.args.get("debug", type=int) == 1

    return {
        "page": page, "per_page": per_page, "q_text": q_text,
        "device_id": device_id, "user_id": user_id, "status": status,
        "branch_id": branch_id, "from_ts": from_ts, "to_ts": to_ts,
        "sort_by": sort_by, "sort_dir": sort_dir, "debug": debug
    }


def _build_query(params: Dict[str, Any], *, force_device_id: Optional[int] = None):
    """
    Build the AttendanceLog query applying common filters.
    Use force_device_id to create a device-scoped query (used by get_logs_for_device).
    Returns tuple (query, debug_counts, applied_from_iso, applied_to_iso)
    """
    page = params["page"]
    per_page = params["per_page"]
    q_text = params["q_text"]
    device_id = force_device_id if force_device_id is not None else params["device_id"]
    user_id = params["user_id"]
    status = params["status"]
    branch_id = params["branch_id"]
    from_ts = params["from_ts"]
    to_ts = params["to_ts"]
    sort_by = params["sort_by"]
    sort_dir = params["sort_dir"]
    debug = params["debug"]

    query = AttendanceLog.query.join(Device).options(joinedload(AttendanceLog.device))
    debug_counts = {}
    if debug:
        debug_counts["initial"] = _count(query)

    if branch_id is not None:
        query = query.filter(Device.branch_id == branch_id)
        if debug:
            debug_counts["after_branch"] = _count(query)

    if device_id is not None:
        query = query.filter(AttendanceLog.device_id == device_id)
        if debug:
            debug_counts["after_device"] = _count(query)

    if user_id:
        query = query.filter(AttendanceLog.user_id.ilike(f"%{user_id}%"))
        if debug:
            debug_counts["after_user"] = _count(query)

    if status:
        query = query.filter(AttendanceLog.status.ilike(f"%{status}%"))
        if debug:
            debug_counts["after_status"] = _count(query)

    applied_from = applied_to = None
    if from_ts:
        dt_from = _parse_iso(from_ts)
        if dt_from:
            applied_from = dt_from.isoformat()
            query = query.filter(AttendanceLog.timestamp >= dt_from)
            if debug:
                debug_counts["after_from"] = _count(query)

    if to_ts:
        dt_to = _parse_iso(to_ts)
        if dt_to:
            # if only date given, ensure end of day
            if len(to_ts.strip()) == 10:
                dt_to = datetime.combine(dt_to.date(), time.max)
            applied_to = dt_to.isoformat()
            query = query.filter(AttendanceLog.timestamp <= dt_to)
            if debug:
                debug_counts["after_to"] = _count(query)

    # free-text search
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
        if debug:
            debug_counts["after_q"] = _count(query)

    sort_col = getattr(AttendanceLog, sort_by, AttendanceLog.timestamp)
    query = query.order_by(asc(sort_col) if sort_dir == "asc" else desc(sort_col))

    return query, debug_counts, applied_from, applied_to


# --- GET /logs ---
@bp.route("", methods=["GET"])
@bp.route("/", methods=["GET"])
def get_logs():
    try:
        params = _extract_common_params()
        query, debug_counts, applied_from, applied_to = _build_query(params)

        pag = query.paginate(page=params["page"], per_page=params["per_page"], error_out=False)
        items = [_serialize_log(l) for l in pag.items]

        resp = {
            "applied_filters": {
                "branch_id": params["branch_id"],
                "device_id": params["device_id"],
                "user_id": params["user_id"],
                "status": params["status"],
                "from_ts": params["from_ts"],
                "to_ts": params["to_ts"],
                "q": params["q_text"],
            },
            "items": items,
            "total": pag.total,
            "page": pag.page,
            "per_page": pag.per_page,
            "pages": pag.pages,
            "has_next": pag.has_next,
            "has_prev": pag.has_prev,
        }

        if params["debug"]:
            resp["debug_counts"] = debug_counts
            resp["applied_parsed"] = {"from_iso": applied_from, "to_iso": applied_to}

        return jsonify(resp), 200

    except Exception as e:
        return jsonify({"error": "internal", "message": str(e)}), 500


# --- GET /logs/device/<device_id> ---
@bp.route("/device/<int:device_id>", methods=["GET"])
@bp.route("/device/<int:device_id>/", methods=["GET"])
def get_logs_for_device(device_id: int):
    try:
        params = _extract_common_params()
        # force the device_id into the query builder so logic is reused
        query, debug_counts, applied_from, applied_to = _build_query(params, force_device_id=device_id)

        # If no from/to provided, default to today's records for device-scoped endpoint
        if not params["from_ts"] and not params["to_ts"]:
            today = datetime.today().date()
            query = query.filter(
                AttendanceLog.timestamp >= datetime.combine(today, time.min),
                AttendanceLog.timestamp <= datetime.combine(today, time.max)
            )
            if params["debug"]:
                debug_counts["after_default_today"] = _count(query)

        pag = query.paginate(page=params["page"], per_page=params["per_page"], error_out=False)
        items = [_serialize_log(l) for l in pag.items]

        resp = {
            "applied_filters": {
                "device_id": device_id,
                "user_id": params["user_id"],
                "status": params["status"],
                "from_ts": params["from_ts"],
                "to_ts": params["to_ts"],
                "q": params["q_text"],
            },
            "items": items,
            "total": pag.total,
            "page": pag.page,
            "per_page": pag.per_page,
            "pages": pag.pages,
            "has_next": pag.has_next,
            "has_prev": pag.has_prev,
        }

        if params["debug"]:
            resp["debug_counts"] = debug_counts
            resp["applied_parsed"] = {"from_iso": applied_from, "to_iso": applied_to}

        return jsonify(resp), 200

    except Exception as e:
        return jsonify({"error": "internal", "message": str(e)}), 500


# --- DELETE all logs for a specific device ---
@bp.route("/device/<int:device_id>/logs", methods=["DELETE"])
@bp.route("/device/<int:device_id>/logs/", methods=["DELETE"])
def delete_logs_for_device(device_id: int):
    """
    Delete ALL attendance logs for the given device.
    Safety: require `confirm=1` query parameter to proceed to avoid accidental deletion.
    Returns the number of rows deleted.
    """
    try:
        # confirm device exists
        device = Device.query.get_or_404(device_id)

        # safety confirmation
        confirm = request.args.get("confirm", default="0")
        if str(confirm) not in ("1", "true", "yes"):
            return jsonify({
                "error": "confirmation_required",
                "message": "Destructive action. To confirm deletion, call this endpoint with ?confirm=1"
            }), 400

        # count & delete (bulk delete)
        q = AttendanceLog.__table__.delete().where(AttendanceLog.device_id == device_id)
        # Use core delete to avoid loading ORM objects (faster for large deletes)
        res = db.session.execute(q)
        db.session.commit()

        # res.rowcount may be None for some DBs/drivers; try a fallback count
        deleted = res.rowcount if res.rowcount is not None else AttendanceLog.query.filter_by(device_id=device_id).count()

        return jsonify({
            "device_id": device_id,
            "device_name": device.name,
            "deleted": deleted
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "internal", "message": str(e)}), 500
