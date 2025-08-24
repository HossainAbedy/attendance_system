# seed_devices.py

from app.extensions import db
from app.models import Device, Branch
from flask import Flask
from datetime import datetime
from sqlalchemy import text

def seed_devices():
    app = Flask(__name__)
    app.config.from_object("app.config.Config")

    with app.app_context():
        db.init_app(app)

        # # 🚨 Use raw connection to disable FK checks immediately
        # with db.engine.connect() as conn:
        #     conn.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))
        #     Branch.__table__.drop(bind=conn, checkfirst=True)
        #     Branch.__table__.create(bind=conn)
        #     conn.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))

        # Fetch existing branches by name
        gulshan_branch = Branch.query.filter_by(name="Gulshan Branch").first()
        uttara_branch = Branch.query.filter_by(name="Uttara Branch").first()

        devices = [
            Device(name="K40 Lobby Gulshan Branch", ip_address="172.19.110.231", port=4370, serial_no="CQQC225261110", branch_id=gulshan_branch.id),
            # Device(name="K40 Lobby Uttara Branch", ip_address="172.19.109.231", port=4370, serial_no="CQQC225261109", branch=uttara_branch),
            # Add more as needed
        ]

        db.session.add_all(devices)
        db.session.commit()
        print("✅ Devices seeded.")

if __name__ == "__main__":
    seed_devices()
