import mysql.connector

# Conectar a la base de datos
conn = mysql.connector.connect(
    host="127.0.0.1",
    user="root",
    password="Partediario20",
    database="rdl_import"
)
cursor = conn.cursor()

# Ejecutar la consulta
cursor.execute("""
    SELECT wd.contractor, wd.rig, r.name AS rig_name, wd.well_name
    FROM well_data wd
    JOIN rigs_autom r ON wd.rig = r.alias
    JOIN rigs_contractors_autom rc ON wd.contractor = rc.alias
    WHERE wd.import_datetime = (SELECT MAX(import_datetime) FROM well_data);
""")

# Obtener los resultados
rigs_data = cursor.fetchall()

# Cerrar conexión
cursor.close()
conn.close()

# Mostrar los datos obtenidos
print("📋 Lista de rigs obtenidos de la base de datos:")
for contractor, rig_number, rig_name, well_name in rigs_data:
    print(f"Contractor: {contractor}, Rig: {rig_number}, Rig Name: {rig_name}, Well Name: {well_name}")
