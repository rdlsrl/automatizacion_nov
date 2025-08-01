import pymysql
from datetime import datetime

db_config = {
    "host": "127.0.0.1",         # ajusta según corresponda
    "port": 3306,
    "user": "root",
    "password": "Partediario20", # asegúrate de que la contraseña sea correcta
    "database": "rdl_import"
}

try:
    conn = pymysql.connect(
        host=db_config["host"],
        port=db_config["port"],
        user=db_config["user"],
        password=db_config["password"],
        database=db_config["database"],
        charset='utf8mb4'
    )
    cursor = conn.cursor()
    sql = "INSERT INTO log_import_las (log_date, log_level, log_message) VALUES (%s, %s, %s);"
    cursor.execute(sql, (datetime.now(), "DEBUG", "Mensaje de prueba desde script aislado"))
    conn.commit()
    cursor.close()
    conn.close()
    print("Inserción de prueba completada.")
except Exception as e:
    print("Error en la inserción de prueba:", e)
