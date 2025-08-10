# views/sync.py
from flask import Blueprint, jsonify, current_app
from ..tasks import start_poll_all_job, start_poll_branch_job, get_job_status, stop_recurring_scheduler
from ..models import Branch

bp = Blueprint('sync', __name__)

@bp.route('/', methods=['POST'])
def start_sync_all():
    """
    Start 'sync all' job (poll all devices). Returns job_id (202 accepted).
    """
    job_id = start_poll_all_job(current_app)
    return jsonify({'job_id': job_id}), 202

@bp.route('/<job_id>/status', methods=['GET'])
def job_status(job_id):
    job = get_job_status(job_id)
    if not job:
        return jsonify({'error': 'not_found'}), 404
    return jsonify(job), 200

@bp.route('/branch/<int:branch_id>', methods=['POST'])
def fetch_branch(branch_id):
    """
    Start 'sync branch' job for a specific branch.
    """
    branch = Branch.query.get_or_404(branch_id)
    job_id = start_poll_branch_job(current_app, branch_id)
    return jsonify({'job_id': job_id}), 202

@bp.route('/stop', methods=['POST'])
def stop_sync():
    """
    Stop the recurring scheduler (stops all scheduled polling).
    """
    stop_recurring_scheduler()
    return jsonify({'status': 'scheduler_stopped'}), 200
