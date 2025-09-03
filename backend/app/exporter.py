# backend/app/exporter.py
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from flask import current_app
from app.extensions import db
from app.models import AttendanceLog, Device
import logging

logger = logging.getLogger(__name__)


def export_attendance_direct(batch_size=1500, lookback_days=None, dry_run=False):
   
    end_db_uri = current_app.config.get("END_DB_URI") or current_app.config.get("ENDDB_DATABASE_URI")
    if not end_db_uri:
        raise RuntimeError("END_DB_URI (or ENDDB_DATABASE_URI) not configured")

    engine = create_engine(end_db_uri, pool_pre_ping=True)
    target_table = current_app.config.get("END_TARGET_TABLE", "att_raw_data_old")

    q = AttendanceLog.query.order_by(AttendanceLog.id)
    if hasattr(AttendanceLog, "exported"):
        q = q.filter_by(exported=False)

    if lookback_days is not None:
        cutoff = datetime.utcnow() - timedelta(days=int(lookback_days))
        q = q.filter(AttendanceLog.timestamp >= cutoff)

    rows = q.limit(batch_size).all()
    if not rows:
        return {"exported": 0, "skipped_existing": 0, "skipped_empty_user": 0, "errors": 0}

    exported = 0
    skipped_existing = 0
    skipped_empty_user = 0
    errors = 0

    dup_check_sql = text(
        f"SELECT COUNT(1) FROM {target_table} "
        "WHERE log_date = :logDate AND badge = :userId AND log_time = :logTime AND access_device = :accessDev"
    )

    # Match PHP exporter: column order (without id, created_at, source)
    insert_sql = text(
        f"INSERT INTO {target_table} "
        "(log_date, badge, badge_dup, placeholder, log_time, flag, access_door, batch, access_device) "
        "VALUES (:u_logDate, :u_userId, :u_userId, '', :u_logTime, '0', :u_accessDoor, '', :u_accessDev)"
    )

    with engine.begin() as conn:
        for rec in rows:
            try:
                # Get userId (badge)
                raw_user = None
                if getattr(rec, "user_id", None):
                    raw_user = str(rec.user_id).strip()
                elif getattr(rec, "device_userid", None):
                    raw_user = str(rec.device_userid).strip()
                if not raw_user:
                    skipped_empty_user += 1
                    continue

                # log_date & log_time (subtract 10 min)
                log_dt = rec.timestamp - timedelta(minutes=10)
                u_logDate = log_dt.strftime("%Y-%m-%d")
                u_logTime = log_dt.strftime("%H:%M:%S")

                # Device mapping
                dev_obj = getattr(rec, "device", None)
                serial_no = None
                if dev_obj:
                    serial_no = getattr(dev_obj, "serial_no", None) or str(getattr(rec, "device_id", ""))
                else:
                    serial_no = str(getattr(rec, "device_id", "") or "")

                u_accessDoor = serial_no
                u_accessDev = f"ZKT-FLASK-{serial_no}"

                # Duplicate check
                dup_params = {
                    "logDate": u_logDate,
                    "userId": raw_user,
                    "logTime": u_logTime,
                    "accessDev": u_accessDev
                }
                dup_row = conn.execute(dup_check_sql, dup_params).scalar()
                if dup_row and int(dup_row) > 0:
                    skipped_existing += 1
                    if hasattr(rec, "exported"):
                        try:
                            rec.exported = True
                            rec.exported_at = datetime.utcnow()
                            db.session.add(rec)
                            db.session.commit()
                        except Exception:
                            db.session.rollback()
                    continue

                if dry_run:
                    exported += 1
                    continue

                conn.execute(insert_sql, {
                    "u_logDate": u_logDate,
                    "u_userId": raw_user,
                    "u_logTime": u_logTime,
                    "u_accessDoor": u_accessDoor,
                    "u_accessDev": u_accessDev,
                })
                exported += 1

                if hasattr(rec, "exported"):
                    try:
                        rec.exported = True
                        rec.exported_at = datetime.utcnow()
                        db.session.add(rec)
                        db.session.commit()
                    except Exception:
                        db.session.rollback()

            except Exception as e:
                errors += 1
                logger.exception("Exporter row error: %s", e)

    return {
        "exported": exported,
        "skipped_existing": skipped_existing,
        "skipped_empty_user": skipped_empty_user,
        "errors": errors
    }


# Alias for scheduler compatibility
export_attendance_to_enddb_noaccess = export_attendance_direct
