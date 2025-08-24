from .extensions import db
from datetime import datetime

class Branch(db.Model):
    __tablename__ = 'branches'
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(128), unique=True, nullable=False)
    ip_range    = db.Column(db.String(64), nullable=False)  # e.g. "172.19.101.0/24"
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    devices     = db.relationship('Device', back_populates='branch', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Branch {self.name} ({self.ip_range})>"

class Device(db.Model):
    __tablename__ = 'devices'
    id          = db.Column(db.Integer, primary_key=True)
    branch_id   = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=False)
    name        = db.Column(db.String(128), nullable=False)  # e.g. "K40-1"
    ip_address  = db.Column(db.String(45), nullable=False)
    port        = db.Column(db.Integer, default=4370)
    serial_no   = db.Column(db.String(64), nullable=True)
    last_seen   = db.Column(db.DateTime, nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    branch      = db.relationship('Branch', back_populates='devices')
    logs        = db.relationship('AttendanceLog', back_populates='device', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Device {self.name}@{self.ip_address}:{self.port}>"

class AttendanceLog(db.Model):
    __tablename__ = 'attendance_logs'
    id          = db.Column(db.Integer, primary_key=True)
    device_id   = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=False)
    record_id   = db.Column(db.Integer, nullable=False)
    user_id     = db.Column(db.String(64), nullable=False)
    timestamp   = db.Column(db.DateTime, nullable=False)
    status      = db.Column(db.String(32), nullable=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    device      = db.relationship('Device', back_populates='logs')

    __table_args__ = (
        db.UniqueConstraint('device_id', 'record_id', name='_device_record_uc'),
    )

    def __repr__(self):
        return f"<Log {self.device_id}#{self.record_id} {self.user_id} @ {self.timestamp}>"