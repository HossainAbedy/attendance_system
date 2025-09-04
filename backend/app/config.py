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


    #END DB & Batch/behavior controls
    ENDDB_DATABASE_URI = "mysql+pymysql://test_user:test_pass@localhost:3306/test_end_db?charset=utf8mb4"
    EXPORT_BATCH_SIZE = 1500
    EXPORT_LOOKBACK_DAYS = 10

 
