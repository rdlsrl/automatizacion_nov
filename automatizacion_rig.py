import mysql.connector
import subprocess

# ========================================================================== 
# CONECTAR A MARIADB Y OBTENER CONTRACTOR, RIG, RIG NAME Y WELL NAME
# ========================================================================== 
conn = mysql.connector.connect(
    host="127.0.0.1",
    user="root",
    password="Partediario20",
    database="rdl_import"
)
cursor = conn.cursor()
cursor.execute(
    """
    SELECT wd.contractor, wd.rig, r.name AS rig_name, wd.well_name
    FROM well_data wd
    JOIN rigs_autom r ON wd.rig = r.alias
    JOIN rigs_contractors_autom rc ON wd.contractor = rc.alias
    WHERE wd.import_datetime = (SELECT MAX(import_datetime) FROM well_data);
    """
)
rigs_contractors = cursor.fetchall()
cursor.close()
conn.close()

print(f"🔍 Se encontraron {len(rigs_contractors)} combinaciones de Contractor y Rig.")

# ========================================================================== 
# PROCESAR CADA CONTRACTOR Y RIG Y LLAMAR A automatizacion_welldata.py
# ========================================================================== 
for contractor, rig, rig_name, well_name in rigs_contractors:
    print(f"🚀 Procesando Contractor: {contractor}, Rig: {rig}, Well: {well_name}")

    try:
        # Llamada al script de automatización con los parámetros necesarios
        command = [
            "python3", "/mnt/mariadb/autom_nov/automatizacion_welldata.py",
            contractor, rig, rig_name, well_name
        ]
        subprocess.run(command, check=True)
        print(f"✅ Automatización completada para {contractor} - {rig}")
    
    except subprocess.CalledProcessError as e:
        print(f"❌ Error ejecutando el script para {contractor} - {rig}: {e}")

print("✅ Finalizado el procesamiento de todos los equipos.")
