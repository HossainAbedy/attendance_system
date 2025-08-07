from flask import Flask
from flask_cors import CORS
from .config import Config
from .extensions import db, migrate  
from .views.devices import bp as devices_bp
from .views.logs import bp as logs_bp
from .tasks import init_scheduler

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Enable CORS for your React frontend
    CORS(app, origins=["http://localhost:3000"])

    db.init_app(app)
    migrate.init_app(app, db)

    app.register_blueprint(devices_bp, url_prefix='/api/devices')
    app.register_blueprint(logs_bp, url_prefix='/api/logs')

    init_scheduler(app)
    return app
