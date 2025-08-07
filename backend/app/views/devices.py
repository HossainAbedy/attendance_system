from flask import Blueprint, request, jsonify
from ..models import Branch, Device
from .. import db
from sqlalchemy.exc import IntegrityError

bp = Blueprint('devices', __name__)

@bp.route('/', methods=['GET'])
def list_branches():
    branches = Branch.query.all()
    return jsonify([{'id': b.id, 'name': b.name, 'ip_range': b.ip_range} for b in branches])

@bp.route('/', methods=['POST'])
def create_branch():
    data = request.get_json()
    b = Branch(name=data['name'], ip_range=data['ip_range'])
    db.session.add(b)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({'error': 'Branch already exists'}), 409
    return jsonify({'id': b.id, 'name': b.name, 'ip_range': b.ip_range}), 201

@bp.route('/<int:branch_id>/devices', methods=['GET'])
def list_devices(branch_id):
    devices = Device.query.filter_by(branch_id=branch_id).all()
    return jsonify([{'id': d.id, 'name': d.name, 'ip_address': d.ip_address, 'port': d.port, 'serial_no': d.serial_no} for d in devices])

@bp.route('/<int:branch_id>/devices', methods=['POST'])
def create_device(branch_id):
    data = request.get_json()
    d = Device(branch_id=branch_id,
               name=data['name'],
               ip_address=data['ip_address'],
               port=data.get('port', 4370),
               serial_no=data.get('serial_no'))
    db.session.add(d)
    db.session.commit()
    return jsonify({'id': d.id, 'name': d.name, 'ip_address': d.ip_address, 'port': d.port}), 201