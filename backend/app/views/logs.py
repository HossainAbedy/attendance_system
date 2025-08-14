# FILE: app/views/logs.py
from flask import Blueprint, request, jsonify
from sqlalchemy import or_, cast, String, desc, asc, func
from sqlalchemy.orm import joinedload
from datetime import datetime, time

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
    # try common formats including "YYYY-MM-DDTHH:MM"
    fmts = ("%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M",        # <-- important for frontend datetime-local without seconds
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d")
    for f in fmts:
        try:
            return datetime.strptime(s, f)
        except Exception:
            pass
    try:
        # last effort
        return datetime.fromisoformat(s)
    except Exception:
        return None


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


def _count(q):
    """Return a quick count for a query (used only for optional debug)."""
    try:
        return q.order_by(None).count()
    except Exception:
        # fallback: try scalar count
        try:
            return db.session.query(func.count()).select_from(q.subquery()).scalar()
        except Exception:
            return None


# --- GET /logs ---
@bp.route("", methods=["GET"])
@bp.route("/", methods=["GET"])
def get_logs():
    try:
        # pagination
        page = request.args.get("page", 1, type=int) or 1
        per_page = min(request.args.get("per_page", 25, type=int) or 25, 200)

        # filters
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

        # base query
        query = AttendanceLog.query.join(Device).options(joinedload(AttendanceLog.device))
        debug_counts = {}
        if debug:
            debug_counts["initial"] = _count(query)

        # branch filter (apply only if not None)
        if branch_id is not None:
            query = query.filter(Device.branch_id == branch_id)
            if debug:
                debug_counts["after_branch"] = _count(query)

        # device filter
        if device_id is not None:
            query = query.filter(AttendanceLog.device_id == device_id)
            if debug:
                debug_counts["after_device"] = _count(query)

        # user filter
        if user_id:
            query = query.filter(AttendanceLog.user_id.ilike(f"%{user_id}%"))
            if debug:
                debug_counts["after_user"] = _count(query)

        # status filter
        if status:
            query = query.filter(AttendanceLog.status.ilike(f"%{status}%"))
            if debug:
                debug_counts["after_status"] = _count(query)

        # timestamp filters
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

        # sorting
        sort_col = getattr(AttendanceLog, sort_by, AttendanceLog.timestamp)
        query = query.order_by(asc(sort_col) if sort_dir == "asc" else desc(sort_col))

        # paginate & serialize
        pag = query.paginate(page=page, per_page=per_page, error_out=False)
        items = [_serialize_log(l) for l in pag.items]

        resp = {
            "applied_filters": {
                "branch_id": branch_id,
                "device_id": device_id,
                "user_id": user_id,
                "status": status,
                "from_ts": from_ts,
                "to_ts": to_ts,
                "q": q_text,
            },
            "items": items,
            "total": pag.total,
            "page": pag.page,
            "per_page": pag.per_page,
            "pages": pag.pages,
            "has_next": pag.has_next,
            "has_prev": pag.has_prev,
        }

        if debug:
            resp["debug_counts"] = debug_counts
            resp["applied_parsed"] = {"from_iso": applied_from, "to_iso": applied_to}

        return jsonify(resp), 200

    except Exception as e:
        return jsonify({"error": "internal", "message": str(e)}), 500



# --- GET /logs/device/<device_id> ---
@bp.route("/device/<int:device_id>", methods=["GET"])
@bp.route("/device/<int:device_id>/", methods=["GET"])
def get_logs_for_device(device_id):
    try:
        page = request.args.get("page", 1, type=int) or 1
        per_page = min(request.args.get("per_page", 25, type=int) or 25, 200)

        q_text = request.args.get("q", type=str)
        if q_text is not None:
            q_text = q_text.strip() or None

        user_id = request.args.get("user_id", type=str)
        if user_id is not None:
            user_id = user_id.strip() or None

        status = request.args.get("status", type=str)
        if status is not None:
            status = status.strip() or None

        from_ts = request.args.get("from") or request.args.get("timestamp_from")
        to_ts = request.args.get("to") or request.args.get("timestamp_to")
        sort_by = request.args.get("sort_by", "timestamp")
        sort_dir = (request.args.get("sort_dir", "desc") or "desc").lower()
        debug = request.args.get("debug", type=int) == 1

        query = AttendanceLog.query.filter(AttendanceLog.device_id == device_id).join(Device).options(joinedload(AttendanceLog.device))
        debug_counts = {}
        if debug:
            debug_counts["initial"] = _count(query)

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
                if len(to_ts.strip()) == 10:
                    dt_to = datetime.combine(dt_to.date(), time.max)
                applied_to = dt_to.isoformat()
                query = query.filter(AttendanceLog.timestamp <= dt_to)
                if debug:
                    debug_counts["after_to"] = _count(query)
        if not from_ts and not to_ts:
            today = datetime.today().date()
            query = query.filter(AttendanceLog.timestamp >= datetime.combine(today, time.min), AttendanceLog.timestamp <= datetime.combine(today, time.max))
            if debug:
                debug_counts["after_default_today"] = _count(query)

        if q_text:
            pattern = f"%{q_text}%"
            query = query.filter(or_(
                cast(AttendanceLog.id, String).ilike(pattern),
                cast(AttendanceLog.record_id, String).ilike(pattern),
                AttendanceLog.user_id.ilike(pattern),
                cast(AttendanceLog.timestamp, String).ilike(pattern),
                AttendanceLog.status.ilike(pattern),
            ))
            if debug:
                debug_counts["after_q"] = _count(query)

        sort_col = getattr(AttendanceLog, sort_by, AttendanceLog.timestamp)
        query = query.order_by(asc(sort_col) if sort_dir == "asc" else desc(sort_col))

        pag = query.paginate(page=page, per_page=per_page, error_out=False)
        items = [_serialize_log(l) for l in pag.items]

        resp = {
            "applied_filters": {
                "device_id": device_id,
                "user_id": user_id,
                "status": status,
                "from_ts": from_ts,
                "to_ts": to_ts,
                "q": q_text,
            },
            "items": items,
            "total": pag.total,
            "page": pag.page,
            "per_page": pag.per_page,
            "pages": pag.pages,
            "has_next": pag.has_next,
            "has_prev": pag.has_prev,
        }

        if debug:
            resp["debug_counts"] = debug_counts
            resp["applied_parsed"] = {"from_iso": applied_from, "to_iso": applied_to}

        return jsonify(resp), 200

    except Exception as e:
        return jsonify({"error": "internal", "message": str(e)}), 500
