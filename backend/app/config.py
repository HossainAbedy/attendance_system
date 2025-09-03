import os

class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL',
        'mysql+pymysql://root:root@localhost/attendance_db_test'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    POLL_INTERVAL = 5  # in seconds
    MAX_POLL_WORKERS = 10  # or whatever number of devices you want to handle in parallel
    SCHEDULER_LOG_DIR = os.environ.get("SCHEDULER_LOG_DIR", "logs")  # Scheduler logs
    # ACCESS_LOCK_DIR = os.environ.get("ACCESS_LOCK_DIR")  # optional, defaults shown below
    # ACCESS_LOCK_TIMEOUT = int(os.environ.get("ACCESS_LOCK_TIMEOUT", "15"))
    # ACCESS_LOCK_STALE_SECONDS = int(os.environ.get("ACCESS_LOCK_STALE_SECONDS", "60"))
    # HRBOOK_URL = os.getenv('HRBOOK_URL', 'http://localhost:8000/api')
    # HRBOOK_TOKEN = os.getenv('HRBOOK_TOKEN', 'your-secret-token')


    #END DB & Batch/behavior controls
    ENDDB_DATABASE_URI = "mysql+pymysql://test_user:test_pass@localhost:3306/test_end_db?charset=utf8mb4"
    EXPORT_BATCH_SIZE = 1500
    EXPORT_LOOKBACK_DAYS = 10

    # Insert source label (optional)
    # END_INSERT_SOURCE = "flask_exporter_test"
    # EXPORT_DRY_RUN = False  # set True for dry-run
    # EXPORT_UNMAPPED_CSV_DIR = "logs"  # optional; writes unmapped_badges_*.csv
    # END_INSERT_BATCH_VALUE = ""  # batch column value ('' by default)

