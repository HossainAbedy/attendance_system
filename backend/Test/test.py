import pyodbc

access_db_path = r"E:\ShareME\SBAC TAO\NewYear25\attendance-system\backend\att2000.mdb"

conn_str = (
    rf"DRIVER={{Microsoft Access Driver (*.mdb, *.accdb)}};"
    rf"DBQ={access_db_path};"
)

try:
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    cursor.execute("SELECT TOP 5 * FROM CHECKINOUT")
    rows = cursor.fetchall()
    for row in rows:
        print(row)
    cursor.close()
    conn.close()
except Exception as e:
    print("❌ Error:", e)
