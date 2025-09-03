# app/models.py
from .extensions import db
from datetime import datetime

class Branch(db.Model):
    __tablename__ = 'branches'
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(128), unique=True, nullable=False)
    ip_range    = db.Column(db.String(64), nullable=False)  # e.g. "172.19.101.0/24"
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    devices     = db.relationship('Device', back_populates='branch', cascade='all, delete-orphan')
    users       = db.relationship('User', back_populates='branch', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Branch {self.name} ({self.ip_range})>"


class Device(db.Model):
    __tablename__ = 'devices'
    id          = db.Column(db.Integer, primary_key=True)
    branch_id   = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=False)
    name        = db.Column(db.String(128), nullable=False)  # e.g. "K40-1"
    ip_address  = db.Column(db.String(45), nullable=False)
    port        = db.Column(db.Integer, default=4370)
    serial_no   = db.Column(db.String(128), nullable=True, index=True)
    last_seen   = db.Column(db.DateTime, nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    branch      = db.relationship('Branch', back_populates='devices')
    logs        = db.relationship('AttendanceLog', back_populates='device', cascade='all, delete-orphan')
    user_maps   = db.relationship('UserDeviceMap', back_populates='device', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Device {self.name}@{self.ip_address}:{self.port}>"


# ---------------- Core user/badge models ----------------
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=False)
    full_name = db.Column(db.String(128), nullable=False)
    employee_code = db.Column(db.String(64), unique=True, nullable=False)
    designation = db.Column(db.String(128), nullable=True)
    status = db.Column(db.String(32), default="active")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    branch = db.relationship('Branch', back_populates='users')
    badges = db.relationship('Badge', back_populates='user', cascade='all, delete-orphan')
    device_maps = db.relationship('UserDeviceMap', back_populates='user', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<User {self.full_name} ({self.employee_code})>"


class Badge(db.Model):
    __tablename__ = 'badges'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    badge_number = db.Column(db.String(64), unique=True, nullable=False, index=True)
    issue_date = db.Column(db.DateTime, default=datetime.utcnow)
    expiry_date = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(32), default="active")

    user = db.relationship('User', back_populates='badges')

    def __repr__(self):
        return f"<Badge {self.badge_number} for User {self.user_id}>"


class UserDeviceMap(db.Model):
    __tablename__ = 'user_device_map'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    device_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', back_populates='device_maps')
    device = db.relationship('Device', back_populates='user_maps')

    __table_args__ = (db.UniqueConstraint('user_id', 'device_id', name='_user_device_uc'),)

    def __repr__(self):
        return f"<UserDeviceMap User {self.user_id} ↔ Device {self.device_id}>"


# ---------------- Attendance log (enhanced) ----------------
class AttendanceLog(db.Model):
    __tablename__ = 'attendance_logs'

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=False)
    record_id = db.Column(db.Integer, nullable=False)

    # legacy user_id (string) — kept for backward compatibility
    user_id = db.Column(db.String(64), nullable=True)

    # raw device USERID (device-local) — recommended to use this for mapping/replication
    device_userid = db.Column(db.String(128), nullable=True, index=True)

    # normalized FK to central Badge if resolved (nullable)
    badge_id = db.Column(db.Integer, db.ForeignKey('badges.id'), nullable=True, index=True)

    timestamp = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(32), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # ✅ New export tracking fields
    exported = db.Column(db.Boolean, default=False, nullable=False)
    exported_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    device = db.relationship('Device', back_populates='logs')
    badge = db.relationship('Badge')

    __table_args__ = (
        db.UniqueConstraint('device_id', 'record_id', name='_device_record_uc'),
    )

    def __repr__(self):
        return (
            f"<Log {self.device_id}#{self.record_id} "
            f"device_userid={self.device_userid} badge_id={self.badge_id} "
            f"exported={self.exported} @ {self.timestamp}>"
        )


# ---------------- Replicated Access models (USERINFO / CHECKINOUT) ----------------
class AccessUserInfo(db.Model):
    """
    Replica of Access USERINFO table from devices (replicated by your sync).
    Keep Badgenumber canonical and include sn (device serial).
    """
    __tablename__ = 'access_userinfo'
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    USERID = db.Column(db.String(64), nullable=False)   # device-local user id (string)
    Badgenumber = db.Column(db.String(128), nullable=False)  # canonical badge string
    Name = db.Column(db.String(255), nullable=True)
    SSN = db.Column(db.String(64), nullable=True)
    sn = db.Column(db.String(128), nullable=True, index=True)  # device serial - important
    source = db.Column(db.String(64), default='access')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('USERID', 'sn', name='uix_access_userinfo_userid_sn'),
        db.UniqueConstraint('Badgenumber', name='uix_access_userinfo_badgenumber'),
        db.Index('ix_access_userinfo_sn', 'sn'),
    )

    def __repr__(self):
        return f"<AccessUserInfo USERID={self.USERID} Badge={self.Badgenumber} sn={self.sn}>"


class CheckinOut(db.Model):
    """
    Replica of Access CHECKINOUT table (replicated into Flask DB).
    """
    __tablename__ = 'access_checkinout'
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    USERID = db.Column(db.String(64), nullable=False, index=True)
    CHECKTIME = db.Column(db.DateTime, nullable=False, index=True)
    CHECKTYPE = db.Column(db.String(16), nullable=True)
    VERIFYCODE = db.Column(db.String(16), nullable=True)
    SENSORID = db.Column(db.String(32), nullable=True)
    Memoinfo = db.Column(db.String(255), nullable=True)
    WorkCode = db.Column(db.String(64), nullable=True)
    sn = db.Column(db.String(128), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.Index('ix_access_checkinout_user_time_sn', 'USERID', 'CHECKTIME', 'sn'),
    )

    def __repr__(self):
        return f"<CheckinOut {self.USERID}@{self.CHECKTIME} sn={self.sn}>"
