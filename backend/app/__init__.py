# backend/app/__init__.py
import sys  
from datetime import datetime
from flask import Response
from flask import Flask, jsonify, request, current_app
from flask_cors import CORS
from .config import Config
from .extensions import db, migrate, socketio
from .views.devices import bp as devices_bp
from .views.logs import bp as logs_bp
from .views.sync import bp as sync_bp
from .logging_handler import init_socketio_logging

# scheduler controls (moved out of tasks.py)
from app.scheduler import (
    start_recurring_scheduler,
    stop_recurring_scheduler,
    start_poll_all_job,
    start_poll_branch_job,
    start_scheduler_job,
    stop_scheduler_job,
)

# keep registry/read helpers in tasks.py (so API endpoints can call them)
from app.tasks import (
    get_job_status,
    list_jobs,
)

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    origins = app.config.get("CORS_ORIGINS", ["http://localhost:3000"])
    CORS(app, resources={r"/api/*": {"origins": origins}})

    # Initialize extensions with app
    db.init_app(app)
    migrate.init_app(app, db)
    socketio.init_app(app)

    # sys.stdout = SocketIOStdout(socketio)
    # sys.stderr = SocketIOStdout(socketio)

    app.register_blueprint(devices_bp, url_prefix='/api/devices')
    app.register_blueprint(logs_bp, url_prefix='/api/logs')
    app.register_blueprint(sync_bp, url_prefix='/api/sync')

    @app.route("/")
    def home():
        return Response(f"<h1>Attendance System Scheduler<h5><h3>Backend Running ✅</h3><p>UTC: {datetime.utcnow():%Y-%m-%d %H:%M:%SZ}</p>", mimetype="text/html")

    
    @app.route("/api/sync/start", methods=["POST"])
    def start_recurring():
        body = request.get_json(silent=True) or {}
        interval = int(body.get("interval_seconds", app.config.get("POLL_INTERVAL", 3600)))
        start_recurring_scheduler(current_app, interval_seconds=interval)
        # Enqueue a job to start the recurring scheduler (returns job_id)
        job_id = start_scheduler_job(current_app, interval_seconds=interval)
        return jsonify({"job_id": job_id, "message": "Recurring scheduler started"}), 202

    @app.route("/api/sync/stop", methods=["POST"])
    def stop_recurring():
        stop_recurring_scheduler()
        # Enqueue a job to stop the recurring scheduler (returns job_id)
        job_id = stop_scheduler_job(current_app)
        return jsonify({"job_id": job_id, "message": "Recurring scheduler stopped"}), 202

    @app.route("/api/sync/one", methods=["POST"])
    def start_one_off():
        job_id = start_poll_all_job(current_app)
        return jsonify({"job_id": job_id}), 202

    @app.route("/api/sync/branch/<int:branch_id>", methods=["POST"])
    def start_branch_one_off(branch_id):
        job_id = start_poll_branch_job(current_app, branch_id)
        return jsonify({"job_id": job_id}), 202

    @app.route("/api/sync/job/<job_id>", methods=["GET"])
    def sync_job_status(job_id):
        job = get_job_status(job_id)
        if not job:
            return jsonify({"error": "not_found"}), 404
        return jsonify(job), 200

    @app.route("/api/sync/jobs", methods=["GET"])
    def sync_jobs_list():
        return jsonify({"jobs": list_jobs()}), 200

    init_socketio_logging()

    return app
