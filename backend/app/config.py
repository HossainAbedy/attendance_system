import os

class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL',
        'mysql+pymysql://root:root@localhost/attendance_db_test'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    POLL_INTERVAL = 5  # in seconds
    MAX_POLL_WORKERS = 10  # or whatever number of devices you want to handle in parallel
    HRBOOK_URL = os.getenv('HRBOOK_URL', 'http://localhost:8000/api')
    HRBOOK_TOKEN = os.getenv('HRBOOK_TOKEN', 'your-secret-token')
