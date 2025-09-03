# FILE: app/views/logs.py
from flask import Blueprint, request, jsonify, current_app
from sqlalchemy import or_, cast, String, desc, asc, func
from sqlalchemy.orm import joinedload
from datetime import datetime, time, timedelta
from typing import Optional, Dict, Any

from ..models import Device, AttendanceLog, Badge
from .. import db
from ..tasks import fetch_and_forward_for_device
from zk.exception import ZKNetworkError

bp = Blueprint("logs", __name__)

# ---------- helpers ----------
def _parse_iso(dt_str: Optional[str]):
    """Tolerant parser: accepts YYYY-MM-DD, YYYY-MM-DDTHH:MM[:SS][.ms][Z]."""
    if not dt_str:
        return None
    s = str(dt_str).strip()
    fmts = (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S.%f",
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
        # fallback to fromisoformat
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _serialize_log(l: AttendanceLog) -> Dict[str, Any]:
    return {
        "id": l.id,
        "device_id": l.device_id,
        "record_id": l.record_id,
        "user_id": l.user_id,
        "device_userid": getattr(l, "device_userid", None),
        "badge_id": getattr(l, "badge_id", None),
        "badge_number": getattr(getattr(l, "badge", None), "badge_number", None),
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
    """
    Parse and normalize request args used by endpoints.
    Accepts both `user_id` and `badge` as synonyms for searching by badge/user.
    """
    page = request.args.get("page", 1, type=int) or 1
    per_page = min(request.args.get("per_page", current_app.config.get("LOGS_PER_PAGE", 25), type=int) or 25, 1000)

    q_text = request.args.get("q", type=str)
    q_text = q_text.strip() or None if q_text is not None else None

    # badge / user search (accept either param)
    user_id = request.args.get("user_id", type=str) or request.args.get("badge", type=str)
    user_id = user_id.strip() or None if user_id else None

    device_id = request.args.get("device_id", type=int)
    status = request.args.get("status", type=str)
    status = status.strip() or None if status else None

    branch_id = request.args.get("branch_id", type=int) or request.args.get("branch", type=int)

    from_ts = request.args.get("from") or request.args.get("timestamp_from")
    to_ts = request.args.get("to") or request.args.get("timestamp_to")

    sort_by = request.args.get("sort_by", "timestamp")
    sort_dir = (request.args.get("sort_dir", "desc") or "desc").lower()
    debug = request.args.get("debug", type=int) == 1
    include_aggregates = request.args.get("include_aggregates", "0") in ("1", "true", "yes")

    return {
        "page": page, "per_page": per_page, "q_text": q_text,
        "device_id": device_id, "user_id": user_id, "status": status,
        "branch_id": branch_id, "from_ts": from_ts, "to_ts": to_ts,
        "sort_by": sort_by, "sort_dir": sort_dir, "debug": debug, "include_aggregates": include_aggregates
    }


def _build_query(params: Dict[str, Any], *, force_device_id: Optional[int] = None):
    """
    Build AttendanceLog query applying filters. Returns (query, debug_counts, applied_from_iso, applied_to_iso).
    - badge/user search will check AttendanceLog.user_id, AttendanceLog.device_userid, and Badge.badge_number (joined).
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

    # join Device and (left) Badge so we can filter on badge_number easily
    query = AttendanceLog.query.join(Device).options(joinedload(AttendanceLog.device)).outerjoin(Badge, AttendanceLog.badge_id == Badge.id)
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
        # search across user_id (legacy), device_userid (device-local), and badge.badge_number
        pattern = f"%{user_id}%"
        query = query.filter(
            or_(
                AttendanceLog.user_id.ilike(pattern),
                getattr(AttendanceLog, "device_userid", "").ilike(pattern),
                Badge.badge_number.ilike(pattern)
            )
        )
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
            # if only a date string (YYYY-MM-DD) was provided, include the full day (end of day)
            if len(str(to_ts).strip()) == 10:
                dt_to = datetime.combine(dt_to.date(), time.max)
            applied_to = dt_to.isoformat()
            query = query.filter(AttendanceLog.timestamp <= dt_to)
            if debug:
                debug_counts["after_to"] = _count(query)

    # free-text search across common fields
    if q_text:
        pattern = f"%{q_text}%"
        query = query.filter(
            or_(
                cast(AttendanceLog.id, String).ilike(pattern),
                cast(AttendanceLog.device_id, String).ilike(pattern),
                cast(AttendanceLog.record_id, String).ilike(pattern),
                AttendanceLog.user_id.ilike(pattern),
                getattr(AttendanceLog, "device_userid", "").ilike(pattern),
                cast(AttendanceLog.timestamp, String).ilike(pattern),
                AttendanceLog.status.ilike(pattern),
                cast(AttendanceLog.created_at, String).ilike(pattern),
            )
        )
        if debug:
            debug_counts["after_q"] = _count(query)

    # sort
    sort_col = getattr(AttendanceLog, sort_by, AttendanceLog.timestamp)
    query = query.order_by(asc(sort_col) if sort_dir == "asc" else desc(sort_col))

    return query, debug_counts, applied_from, applied_to


# ---------- endpoints ----------

# poll endpoint (unchanged)
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


# GET /logs (supports page/per_page, user_id or badge, device_id, from/to, q, sort, include_aggregates)
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

        # optional aggregates for the SAME filter (useful to show summary on frontend)
        if params.get("include_aggregates"):
            # top devices (limit reasonable)
            top_n = int(request.args.get("agg_top_n", 20))
            dev_q = db.session.query(AttendanceLog.device_id, func.count(AttendanceLog.id).label("cnt")).group_by(AttendanceLog.device_id)
            # reapply same filters to dev_q by reusing _build_query logic with subquery filters:
            # easiest: use the filtered query's subquery to aggregate
            subq = query.with_entities(AttendanceLog.id, AttendanceLog.device_id).subquery()
            dev_counts = db.session.query(subq.c.device_id, func.count(subq.c.device_id).label("cnt")).group_by(subq.c.device_id).order_by(desc("cnt")).limit(top_n).all()
            total_by_device = []
            for did, cnt in dev_counts:
                dev_obj = Device.query.get(did)
                total_by_device.append({"device_id": did, "device_name": getattr(dev_obj, "name", None) if dev_obj else None, "count": int(cnt)})
            resp["aggregates"] = {"total_by_device": total_by_device}

        if params["debug"]:
            resp["debug_counts"] = debug_counts
            resp["applied_parsed"] = {"from_iso": applied_from, "to_iso": applied_to}

        return jsonify(resp), 200
    except Exception as e:
        current_app.logger.exception("get_logs failed")
        return jsonify({"error": "internal", "message": str(e)}), 500


# GET logs for specific device (keeps your 'today default' behavior)
@bp.route("/device/<int:device_id>", methods=["GET"])
@bp.route("/device/<int:device_id>/", methods=["GET"])
def get_logs_for_device(device_id: int):
    try:
        params = _extract_common_params()
        query, debug_counts, applied_from, applied_to = _build_query(params, force_device_id=device_id)

        # default to today's records if no from/to
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
        current_app.logger.exception("get_logs_for_device failed")
        return jsonify({"error": "internal", "message": str(e)}), 500


# convenience: fetch logs for a user/badge (paged)
@bp.route("/user/<string:badge>", methods=["GET"])
def get_logs_for_user(badge: str):
    try:
        params = _extract_common_params()
        # force user_id
        params["user_id"] = badge
        query, debug_counts, applied_from, applied_to = _build_query(params)

        pag = query.paginate(page=params["page"], per_page=params["per_page"], error_out=False)
        items = [_serialize_log(l) for l in pag.items]

        resp = {
            "applied_filters": {"user_id": badge, "from_ts": params["from_ts"], "to_ts": params["to_ts"]},
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
        current_app.logger.exception("get_logs_for_user failed")
        return jsonify({"error": "internal", "message": str(e)}), 500


# stats endpoint for date-range aggregates (useful for comparison)
@bp.route("/stats", methods=["GET"])
def logs_stats():
    try:
        start_date = _parse_iso(request.args.get("start_date")) or (datetime.utcnow() - timedelta(days=10))
        end_date = _parse_iso(request.args.get("end_date")) or datetime.utcnow()
        top_n = int(request.args.get("top_n", 20))

        s_dt = datetime.combine(start_date.date(), time.min) if isinstance(start_date, datetime) else datetime.utcnow() - timedelta(days=10)
        e_dt = datetime.combine(end_date.date(), time.max) if isinstance(end_date, datetime) else datetime.utcnow()

        total = db.session.query(func.count(AttendanceLog.id)).filter(AttendanceLog.timestamp.between(s_dt, e_dt)).scalar() or 0

        q_by_date = db.session.query(
            func.date(AttendanceLog.timestamp).label("log_date"),
            func.count(AttendanceLog.id).label("cnt")
        ).filter(AttendanceLog.timestamp.between(s_dt, e_dt)).group_by(func.date(AttendanceLog.timestamp)).order_by(func.date(AttendanceLog.timestamp))
        by_date = [{ "date": (row.log_date.isoformat() if hasattr(row.log_date, "isoformat") else str(row.log_date)), "count": int(row.cnt)} for row in q_by_date.all()]

        q_top_users = db.session.query(
            AttendanceLog.user_id,
            func.count(AttendanceLog.id).label("cnt")
        ).filter(AttendanceLog.timestamp.between(s_dt, e_dt)).group_by(AttendanceLog.user_id).order_by(desc("cnt")).limit(top_n)
        top_users = [{ "user": row.user_id, "count": int(row.cnt)} for row in q_top_users.all()]

        q_top_devs = db.session.query(
            AttendanceLog.device_id,
            func.count(AttendanceLog.id).label("cnt")
        ).filter(AttendanceLog.timestamp.between(s_dt, e_dt)).group_by(AttendanceLog.device_id).order_by(desc("cnt")).limit(top_n)
        top_devices = []
        for row in q_top_devs.all():
            dev = Device.query.get(row.device_id)
            top_devices.append({"device_id": row.device_id, "device_name": getattr(dev, "name", None) if dev else None, "count": int(row.cnt)})

        return jsonify({
            "start_date": s_dt.isoformat(),
            "end_date": e_dt.isoformat(),
            "total": int(total),
            "by_date": by_date,
            "top_users": top_users,
            "top_devices": top_devices
        }), 200
    except Exception as e:
        current_app.logger.exception("logs_stats failed")
        return jsonify({"error": "internal", "message": str(e)}), 500


# Delete endpoints (unchanged behavior)
@bp.route("/device/<int:device_id>/logs", methods=["DELETE"])
@bp.route("/device/<int:device_id>/logs/", methods=["DELETE"])
def delete_logs_for_device(device_id: int):
    try:
        device = Device.query.get_or_404(device_id)
        confirm = request.args.get("confirm", default="0")
        if str(confirm) not in ("1", "true", "yes"):
            return jsonify({
                "error": "confirmation_required",
                "message": "Destructive action. To confirm deletion, call this endpoint with ?confirm=1"
            }), 400

        q = AttendanceLog.__table__.delete().where(AttendanceLog.device_id == device_id)
        res = db.session.execute(q)
        db.session.commit()
        deleted = res.rowcount if res.rowcount is not None else AttendanceLog.query.filter_by(device_id=device_id).count()

        return jsonify({
            "device_id": device_id,
            "device_name": device.name,
            "deleted": deleted
        }), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("delete_logs_for_device failed")
        return jsonify({"error": "internal", "message": str(e)}), 500


@bp.route("/device/<int:device_id>/logs/today", methods=["DELETE"])
def delete_today_logs_for_device(device_id: int):
    try:
        device = Device.query.get_or_404(device_id)
        confirm = request.args.get("confirm", default="0")
        if str(confirm).lower() not in ("1", "true", "yes"):
            return jsonify({
                "error": "confirmation_required",
                "message": "To confirm deletion, call this endpoint with ?confirm=1"
            }), 400

        today = datetime.now().date()
        start_dt = datetime(today.year, today.month, today.day, 0, 0, 0)
        end_dt = start_dt + timedelta(days=1)

        q = AttendanceLog.__table__.delete().where(
            (AttendanceLog.device_id == device_id) &
            (AttendanceLog.timestamp >= start_dt) &
            (AttendanceLog.timestamp < end_dt)
        )
        res = db.session.execute(q)
        db.session.commit()
        deleted = res.rowcount if res.rowcount is not None else 0

        return jsonify({
            "device_id": device_id,
            "device_name": device.name,
            "deleted_today": deleted,
            "date": today.isoformat()
        }), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("delete_today_logs_for_device failed")
        return jsonify({"error": "internal", "message": str(e)}), 500
