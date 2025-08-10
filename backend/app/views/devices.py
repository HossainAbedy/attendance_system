from flask import Blueprint, request, jsonify
from ..models import Branch, Device, AttendanceLog
from .. import db
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from zk import ZK

bp = Blueprint('devices', __name__)

# -----------------------
# Branch list + create
# -----------------------
@bp.route('/', methods=['GET'])
def list_branches():
    branches = Branch.query.all()

    devices_counts = dict(db.session.query(Device.branch_id, func.count(Device.id)).group_by(Device.branch_id).all())

    logs_counts = dict(
        db.session.query(Branch.id, func.count(AttendanceLog.id))
        .join(Branch.devices)
        .join(Device.logs)
        .group_by(Branch.id)
        .all()
    )

    result = []
    for b in branches:
        result.append({
            'id': b.id,
            'name': b.name,
            'ip_range': b.ip_range,
            'device_count': devices_counts.get(b.id, 0),
            'log_count': logs_counts.get(b.id, 0),
        })

    return jsonify(result)


@bp.route('/', methods=['POST'])
def create_branch():
    data = request.get_json() or {}
    name = data.get('name')
    ip_range = data.get('ip_range')
    if not name or not ip_range:
        return jsonify({'error': 'Missing name or ip_range'}), 400

    b = Branch(name=name, ip_range=ip_range)
    db.session.add(b)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({'error': 'Branch already exists'}), 409
    return jsonify({'id': b.id, 'name': b.name, 'ip_range': b.ip_range}), 201


# -----------------------
# Branch update + delete
# -----------------------
@bp.route('/<int:branch_id>', methods=['PUT'])
def update_branch(branch_id):
    data = request.get_json() or {}
    branch = Branch.query.get_or_404(branch_id)
    # Only update allowed fields
    branch.name = data.get('name', branch.name)
    branch.ip_range = data.get('ip_range', branch.ip_range)
    try:
        db.session.commit()
        return jsonify({'id': branch.id, 'name': branch.name, 'ip_range': branch.ip_range}), 200
    except IntegrityError:
        db.session.rollback()
        return jsonify({'error': 'Conflict updating branch'}), 409
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/<int:branch_id>', methods=['DELETE'])
def delete_branch(branch_id):
    branch = Branch.query.get_or_404(branch_id)
    try:
        # If your relationship is configured with cascade deletes, this will remove devices/logs too.
        db.session.delete(branch)
        db.session.commit()
        return jsonify({'success': True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# -----------------------
# Devices listing + create (under branch)
# -----------------------
@bp.route('/<int:branch_id>/devices', methods=['GET'])
def list_devices(branch_id):
    devices = Device.query.filter_by(branch_id=branch_id).all()
    return jsonify([{
        'id': d.id,
        'name': d.name,
        'ip_address': d.ip_address,
        'port': d.port,
        'serial_no': d.serial_no
    } for d in devices])


@bp.route('/<int:branch_id>/devices', methods=['POST'])
def create_device(branch_id):
    data = request.get_json() or {}
    name = data.get('name')
    ip_address = data.get('ip_address')
    port = data.get('port', 4370)
    serial_no = data.get('serial_no')

    if not name or not ip_address:
        return jsonify({'error': 'Missing name or ip_address'}), 400

    d = Device(branch_id=branch_id,
               name=name,
               ip_address=ip_address,
               port=port,
               serial_no=serial_no)
    db.session.add(d)
    try:
        db.session.commit()
        return jsonify({'id': d.id, 'name': d.name, 'ip_address': d.ip_address, 'port': d.port}), 201
    except IntegrityError:
        db.session.rollback()
        return jsonify({'error': 'Device conflict'}), 409
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# -----------------------
# Single device GET / PUT / DELETE
# -----------------------
@bp.route('/device/<int:device_id>', methods=['GET'])
def get_device(device_id):
    d = Device.query.get_or_404(device_id)
    return jsonify({
        'id': d.id,
        'branch_id': d.branch_id,
        'name': d.name,
        'ip_address': d.ip_address,
        'port': d.port,
        'serial_no': d.serial_no
    })


@bp.route('/device/<int:device_id>', methods=['PUT'])
def update_device(device_id):
    data = request.get_json() or {}
    d = Device.query.get_or_404(device_id)

    # Update allowed fields
    d.name = data.get('name', d.name)
    d.ip_address = data.get('ip_address', d.ip_address)
    d.port = data.get('port', d.port)
    d.serial_no = data.get('serial_no', d.serial_no)
    # optional: allow branch move (only if provided)
    if 'branch_id' in data:
        d.branch_id = data.get('branch_id')

    try:
        db.session.commit()
        return jsonify({
            'id': d.id,
            'branch_id': d.branch_id,
            'name': d.name,
            'ip_address': d.ip_address,
            'port': d.port,
            'serial_no': d.serial_no
        }), 200
    except IntegrityError:
        db.session.rollback()
        return jsonify({'error': 'Device conflict'}), 409
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/device/<int:device_id>', methods=['DELETE'])
def delete_device(device_id):
    d = Device.query.get_or_404(device_id)
    try:
        db.session.delete(d)
        db.session.commit()
        return jsonify({'success': True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# -----------------------
# Ping (unchanged)
# -----------------------
@bp.route('/device/<int:device_id>/ping', methods=['POST'])
def ping_device(device_id):
    device = Device.query.get_or_404(device_id)

    try:
        zk = ZK(device.ip_address, port=device.port, timeout=1, password=0)
        conn = zk.connect()
        conn.disconnect()
        return jsonify({'online': True})
    except Exception:
        return jsonify({'online': False})