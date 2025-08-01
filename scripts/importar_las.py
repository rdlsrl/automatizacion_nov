import os
from datetime import datetime
import lasio
from dotenv import load_dotenv
import pymysql
import warnings
import contextlib
import io

# Importar el módulo de importación renombrado
import procesamiento_las

# Suprimir todas las advertencias
warnings.filterwarnings("ignore")

# Cargar configuración desde config.env
load_dotenv("/mnt/mariadb/autom_nov/config.env")
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

def conectar_db():
    try:
        conexion = pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        print("Conexión a la base de datos exitosa.", flush=True)
        return conexion
    except Exception as e:
        print(f"Error conectando a la base de datos: {str(e)}", flush=True)
        return None

def leer_archivo_las(ruta):
    try:
        # Redirigir stdout y stderr temporalmente para evitar mensajes de lasio
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            las = lasio.read(ruta)
        # Convertir a DataFrame sin modificar los valores
        return las.df()
    except Exception as e:
        print(f"Error leyendo el archivo LAS {ruta}: {e}", flush=True)
        return None

def extraer_metadatos(nombre_archivo):
    partes = nombre_archivo.split('_')
    if len(partes) >= 3:
        return {
            'equipo': partes[0],
            'pozo': partes[1],
            'fecha': partes[2]
        }
    return None

def verificar_equipo_pul(equipo):
    conexion = None
    try:
        conexion = conectar_db()
        if not conexion:
            return False

        with conexion.cursor() as cursor:
            sql = "SELECT name FROM rigs_autom WHERE name = %s AND rig_type = 'PUL'"
            cursor.execute(sql, (equipo,))
            resultado = cursor.fetchone()
            if resultado:
                print(f"El equipo {equipo} es de tipo PUL.", flush=True)
                return True
            else:
                print(f"El equipo {equipo} NO es de tipo PUL.", flush=True)
                return False
    except Exception as e:
        print(f"Error verificando equipo PUL: {str(e)}", flush=True)
        return False
    finally:
        if conexion:
            conexion.close()

def insertar_files_import(conexion, nombre_archivo):
    try:
        if not nombre_archivo:
            print("Error: nombre_archivo es None.", flush=True)
            return

        with conexion.cursor() as cursor:
            sql = "INSERT INTO files_import (name, date_time, event_id) VALUES (%s, NOW(), NULL)"
            cursor.execute(sql, (nombre_archivo,))
        conexion.commit()
        print(f"Insertado en files_import: {nombre_archivo}", flush=True)
    except Exception as e:
        print(f"Error insertando en files_import: {str(e)}", flush=True)

def actualizar_well_data(conexion, equipo, pozo, nombre_archivo):
    try:
        with conexion.cursor() as cursor:
            sql = """
                UPDATE well_data wd
                INNER JOIN rigs_autom ra ON wd.rig = ra.alias
                SET wd.las_name = %s
                WHERE wd.well_name = %s
                  AND ra.name = %s
                  AND DATE(wd.import_datetime) = CURDATE()
            """
            cursor.execute(sql, (nombre_archivo, pozo, equipo))
        conexion.commit()
        print(f"Actualizado well_data: {nombre_archivo} para {equipo} - {pozo}", flush=True)
    except Exception as e:
        print(f"Error actualizando well_data: {str(e)}", flush=True)

def main():
    directorio = "/mnt/mariadb/autom_nov"
    fecha_hoy = datetime.now().strftime("%d-%m-%Y")
    archivos = [os.path.join(directorio, f) for f in os.listdir(directorio) if f.endswith(".las")]

    conexion = conectar_db()
    if not conexion:
        return

    for archivo in archivos:
        nombre_archivo = os.path.basename(archivo)
        metadatos = extraer_metadatos(nombre_archivo)
        if not metadatos:
            continue

        equipo = metadatos['equipo']
        pozo = metadatos['pozo']
        fecha_archivo = metadatos['fecha']

        # Filtrar por fecha en el nombre del archivo
        if fecha_archivo != fecha_hoy:
            continue

        # Verificar si el equipo es de tipo PUL
        if not verificar_equipo_pul(equipo):
            continue

        # Leer archivo LAS (para validar que se puede leer)
        datos_las = leer_archivo_las(archivo)
        if datos_las is None:
            continue

        # Insertar en files_import y actualizar well_data en la base de datos
        insertar_files_import(conexion, nombre_archivo)
        actualizar_well_data(conexion, equipo, pozo, nombre_archivo)

        print(f"Procesado: {nombre_archivo}", flush=True)

        # Llamar al módulo de importación para procesar el contenido interno del LAS
        print(f"Iniciando importación de contenido para: {nombre_archivo}", flush=True)
        procesamiento_las.process_las_file(archivo)

    conexion.close()

if __name__ == "__main__":
    main()
