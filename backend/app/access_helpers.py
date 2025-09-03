# app/access_helpers.py
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from app.models import AccessUserInfo, Badge, User, UserDeviceMap
from app.extensions import db

def get_badge_by_badgenumber(session, badgenumber):
    if not badgenumber:
        return None
    return session.query(Badge).filter(Badge.badge_number == str(badgenumber)).one_or_none()

def get_badge_for_device_userid(session, userid, sn=None):
    userid_s = str(userid) if userid is not None else None
    if not userid_s:
        return None

    if sn:
        ai = session.query(AccessUserInfo).filter(
            AccessUserInfo.USERID == userid_s,
            AccessUserInfo.sn == sn
        ).one_or_none()
        if ai and ai.Badgenumber:
            return get_badge_by_badgenumber(session, ai.Badgenumber)

    ai = session.query(AccessUserInfo).filter(AccessUserInfo.USERID == userid_s).one_or_none()
    if ai and ai.Badgenumber:
        return get_badge_by_badgenumber(session, ai.Badgenumber)

    return session.query(Badge).filter(Badge.badge_number == userid_s).one_or_none()

def upsert_access_userinfo(session, userid, badgenumber, name=None, sn=None, source="zk_device"):
    """Insert or update an access_userinfo entry for (USERID,sn). Returns AccessUserInfo."""
    if userid is None or badgenumber is None:
        return None

    userid_s = str(userid)
    bad_s = str(badgenumber).strip()
    sn_s = str(sn) if sn is not None else None

    ai = session.query(AccessUserInfo).filter(
        AccessUserInfo.USERID == userid_s,
        AccessUserInfo.sn == sn_s
    ).one_or_none()

    if ai:
        changed = False
        if ai.Badgenumber != bad_s:
            ai.Badgenumber = bad_s
            changed = True
        if name and ai.Name != name:
            ai.Name = name
            changed = True
        if changed:
            ai.updated_at = datetime.utcnow()
            session.add(ai)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
        return ai

    ai = AccessUserInfo(
        USERID=userid_s,
        Badgenumber=bad_s,
        Name=name,
        sn=sn_s,
        source=source
    )
    session.add(ai)
    try:
        session.commit()
        return ai
    except IntegrityError:
        session.rollback()
        return session.query(AccessUserInfo).filter(
            AccessUserInfo.USERID == userid_s,
            AccessUserInfo.sn == sn_s
        ).one_or_none()

# -----------------------
# New helper: ensure central User + Badge + mapping exist
# -----------------------
def ensure_user_and_badge(session, badgenumber, name=None, branch_id=None, device_id=None, default_user_name="IMPORTED"):
    """
    Ensure a central User and Badge exist for the given badgenumber.
    - badgenumber: canonical badge string (device-provided)
    - name: optional full name
    - branch_id: required to create User because users.branch_id is non-nullable
    - device_id: optional, to create UserDeviceMap linking user<->device
    Returns Badge instance or None.
    """
    if not badgenumber:
        return None

    bad_s = str(badgenumber).strip()

    # 1) find existing badge
    try:
        badge = session.query(Badge).filter(func.binary(Badge.badge_number) == bad_s).one_or_none()
    except Exception:
        badge = session.query(Badge).filter(Badge.badge_number == bad_s).one_or_none()

    if badge:
        return badge

    # 2) find or create user
    user = session.query(User).filter(User.employee_code == bad_s).one_or_none()
    if not user:
        if branch_id is None:
            # cannot create user without branch_id — bail
            return None
        user_name = name or default_user_name
        user = User(
            branch_id=branch_id,
            full_name=user_name,
            employee_code=bad_s
        )
        session.add(user)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            user = session.query(User).filter(User.employee_code == bad_s).one_or_none()
            if not user:
                return None

    # 3) create badge for this user
    badge = session.query(Badge).filter(Badge.badge_number == bad_s).one_or_none()
    if not badge:
        badge = Badge(
            user_id=user.id,
            badge_number=bad_s
        )
        session.add(badge)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            badge = session.query(Badge).filter(Badge.badge_number == bad_s).one_or_none()
            if not badge:
                # if still no badge, return None
                return None

    # 4) optionally create user_device_map
    if device_id is not None:
        try:
            udm = session.query(UserDeviceMap).filter(
                UserDeviceMap.user_id == user.id,
                UserDeviceMap.device_id == device_id
            ).one_or_none()
            if not udm:
                udm = UserDeviceMap(user_id=user.id, device_id=device_id)
                session.add(udm)
                try:
                    session.commit()
                except IntegrityError:
                    session.rollback()
        except Exception:
            try:
                session.rollback()
            except Exception:
                pass

    return badge
