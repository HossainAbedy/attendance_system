# tools/exporter_runner.py
"""
Test runner for app/exporter.py

Creates:
  - small Flask app using sqlite files for the app DB and for the 'end' DB
  - creates tables (models.create_all())
  - seeds sample device, access_userinfo and access_checkinout rows
  - creates att_raw_data_old table in the end DB
  - runs export_to_enddb and prints outcome
"""

import os
import shutil
from datetime import datetime, timedelta

from flask import Flask
from sqlalchemy import create_engine, text

# Adjust imports to match your project layout
from .extensions import db
from .models import Branch, Device, AccessUserInfo, CheckinOut

# importer of exporter
from .exporter import export_to_enddb

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
TEST_FLASK_DB = os.path.join(BASE_DIR, "test_flask.db")
TEST_ENDDB   = os.path.join(BASE_DIR, "test_end.db")

def _remove_if_exists(p):
    try:
        if os.path.exists(p):
            os.remove(p)
    except Exception:
        pass

def make_app():
    app = Flask("test_exporter_app")
    # use separate sqlite files for the app DB and the end DB
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + TEST_FLASK_DB
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    # end DB URI used by exporter
    app.config["ENDDB_DATABASE_URI"] = "sqlite:///" + TEST_ENDDB
    # make exporter lookback small for testing
    app.config["EXPORT_LOOKBACK_DAYS"] = 10
    return app

def create_end_table_if_missing(engine):
    # Create a compatible att_raw_data_old table for sqlite (simple schema)
    create_sql = """
    CREATE TABLE IF NOT EXISTS att_raw_data_old (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      log_date DATE NOT NULL,
      badge TEXT,
      badge_dup TEXT,
      placeholder TEXT,
      log_time TIME,
      flag INTEGER DEFAULT 0,
      access_door TEXT,
      batch TEXT,
      access_device TEXT,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      source TEXT DEFAULT 'php_old'
    );
    """
    with engine.begin() as conn:
        conn.execute(text(create_sql))

def seed_sample_data(app):
    with app.app_context():
        # ensure tables exist in the flask DB
        db.create_all()

        # create a branch and a device
        br = Branch(name="Test Branch", ip_range="127.0.0.1/32")
        db.session.add(br)
        db.session.commit()

        dev = Device(branch_id=br.id, name="ZK-1", ip_address="127.0.0.1", serial_no="A8N5232360049")
        db.session.add(dev)
        db.session.commit()

        # seed AccessUserInfo mapping: device-local USERID -> Badgenumber
        now = datetime.utcnow()
        # create mapping for USERID '122'
        a1 = AccessUserInfo(USERID='122', Badgenumber='122', Name='Alice', sn=dev.serial_no)
        # create mapping for another user '311' (to show multiple)
        a2 = AccessUserInfo(USERID='311', Badgenumber='311', Name='Bob', sn=dev.serial_no)
        db.session.add_all([a1, a2])
        db.session.commit()

        # create CheckinOut rows (replica of device logs)
        # Two rows: one that will be exported, and one duplicate we pre-create in end DB to test skipping.
        t1 = datetime.utcnow()
        t2 = datetime.utcnow() - timedelta(minutes=1)
        c1 = CheckinOut(USERID='122', CHECKTIME=t1, CHECKTYPE='IN', WorkCode='FLASK', sn=dev.serial_no)
        c2 = CheckinOut(USERID='311', CHECKTIME=t2, CHECKTYPE='IN', WorkCode='FLASK', sn=dev.serial_no)
        db.session.add_all([c1, c2])
        db.session.commit()

def main():
    # cleanup previous test dbs
    _remove_if_exists(TEST_FLASK_DB)
    _remove_if_exists(TEST_ENDDB)

    app = make_app()
    # init db extension BEFORE seeding / using models
    db.init_app(app)

    # seed data into the app DB
    seed_sample_data(app)

    # prepare end-db table
    end_engine = create_engine_from_uri(app.config["ENDDB_DATABASE_URI"])
    create_end_table_if_missing(end_engine)

    # Pre-insert a row identical to one of the checkins to test skip.
    with end_engine.begin() as conn:
        # find a checkin time to duplicate (we will fetch from app db)
        with app.app_context():
            row = CheckinOut.query.order_by(CheckinOut.CHECKTIME.desc()).first()
            if row:
                # Attempt to get the matching device row in app DB by serial_no (sn)
                device_row = Device.query.filter_by(serial_no=row.sn).first()
                if device_row:
                    # exporter will map to device_row.serial_no -> access_door and device_row.name -> access_device
                    door_val = device_row.serial_no
                    device_ident = device_row.name
                else:
                    # fallback to legacy behaviour (what exporter also falls back to)
                    door_val = row.sn
                    device_ident = f"FLASK-ZKT-{row.sn or ''}"

                # prepare parameters (same transformation exporter uses)
                conn.execute(text("""
                    INSERT INTO att_raw_data_old (log_date, badge, badge_dup, placeholder, log_time, flag, access_door, batch, access_device, source)
                    VALUES (:log_date, :badge, :badge_dup, :ph, :log_time, :flag, :door, :batch, :device, :source)
                """), {
                    "log_date": row.CHECKTIME.date(),
                    "badge": row.USERID,
                    "badge_dup": row.USERID,
                    "ph": "",
                    "log_time": row.CHECKTIME.time(),
                    "flag": 0,
                    "door": door_val,
                    "batch": "",
                    "device": device_ident,
                    "source": "preseed"
                })

    # Now run exporter (not dry run)
    print("Running exporter...")
    result = export_to_enddb(app=app, lookback_days=7, dry_run=False, batch_size=100)
    print("Export result:", result)

    # show contents of end DB
    with end_engine.connect() as conn:
        rows = conn.execute(text("SELECT id, log_date, badge, access_device, access_door, created_at, source FROM att_raw_data_old ORDER BY id")).fetchall()
        print("End DB rows:")
        for r in rows:
            # convert row proxy to dict-like for nicer printing
            try:
                print(dict(r))
            except Exception:
                print(tuple(r))

def create_engine_from_uri(uri):
    from sqlalchemy import create_engine
    return create_engine(uri, pool_pre_ping=True)

if __name__ == "__main__":
    main()
