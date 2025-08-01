# fechas_history.py

import os
import re
import glob
import pymysql
from dotenv import load_dotenv
from datetime import datetime

# Cargar variables desde config.env
load_dotenv('config.env')

# Configuración de la base de datos
db_config = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
    "port": 3306
}

# Carpeta donde se encuentran los archivos .las (definida en CSV_FOLDER)
las_folder = os.getenv("CSV_FOLDER")

def obtener_datos_equipos():
    """
    Realiza un SELECT en well_data y retorna una lista de diccionarios con:
      - contractor
      - rig
      - rig_name
    """
    query = """
    SELECT wd.contractor, wd.rig, r.name AS rig_name
    FROM well_data wd
    JOIN rigs_autom r ON wd.rig = r.alias
    JOIN rigs_contractors_autom rc ON wd.contractor = rc.alias
    WHERE wd.import_datetime = (
        SELECT MAX(import_datetime)
        FROM well_data
        WHERE status != 'HISTORIC'
    )
    AND wd.status != 'HISTORIC';
    """
    conn = pymysql.connect(
        host=db_config["host"],
        port=db_config["port"],
        user=db_config["user"],
        password=db_config["password"],
        database=db_config["database"],
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )
    with conn.cursor() as cursor:
        cursor.execute(query)
        resultados = cursor.fetchall()
    conn.close()

    equipos = []
    for row in resultados:
        equipos.append({
            "contractor": row["contractor"],
            "rig": row["rig"],
            "rig_name": row["rig_name"]
        })
    return equipos

def buscar_archivos(rig_name):
    """
    Busca en la carpeta los archivos .las que contengan en su nombre
    el rig_name y la cadena 'nws'.
    """
    patron_busqueda = os.path.join(las_folder, f"*{rig_name}*nws*.las")
    archivos = glob.glob(patron_busqueda)
    return archivos

def obtener_archivo_mas_reciente(archivos):
    """
    Devuelve el archivo con la fecha de modificación más reciente,
    pero solo si fue descargado hoy (a partir de las 00:00).
    Si no hay archivos descargados hoy, retorna None.
    """
    if not archivos:
        return None

    hoy = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    archivos_hoy = [archivo for archivo in archivos if os.path.getmtime(archivo) >= hoy]
    if not archivos_hoy:
        return None
    return max(archivos_hoy, key=os.path.getmtime)

def extraer_fecha_hora(archivo):
    """
    Abre el archivo .las, busca la etiqueta "~ASCII DATA AREA" y, a partir
    de la primera línea de datos, extrae la fecha y hora en el formato
    'dd/%b/%Y %H:%M:%S'. Se considera esta fecha como la fecha final.
    """
    patron = re.compile(r"(\d{1,2}/[A-Za-z]{3}/\d{4}\s+\d{2}:\d{2}:\d{2})")
    procesar_lineas = False
    with open(archivo, "r", encoding="utf-8") as f:
        for linea in f:
            if "~ascii data" in linea.lower():
                procesar_lineas = True
                continue
            if procesar_lineas:
                if not linea.strip():
                    continue
                match = patron.search(linea)
                if match:
                    return match.group(1)
                else:
                    columnas = linea.strip().split('\t')
                    if len(columnas) >= 3:
                        return f"{columnas[1]} {columnas[2]}"
                    break
    return None

def obtener_end_datos(rig_name):
    """
    Consulta en la tabla files_import para el equipo que coincida con el rig_name.
    Retorna la última fecha/hora (end_datos) registrada, que usaremos como fecha inicial.
    No se filtra por 'nws' aquí.
    """
    query = """
    SELECT MAX(end_datos) AS last_end
    FROM files_import
    WHERE name LIKE %s
    """
    params = (f"%{rig_name}%",)
    conn = pymysql.connect(
        host=db_config["host"],
        port=db_config["port"],
        user=db_config["user"],
        password=db_config["password"],
        database=db_config["database"],
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )
    with conn.cursor() as cursor:
        cursor.execute(query, params)
        resultado = cursor.fetchone()
    conn.close()
    return resultado["last_end"] if resultado and resultado["last_end"] else None

def formatear_fecha(fecha):
    """
    Convierte una fecha (str o datetime) al formato 'YYYY-MM-DD HH:MM:SS'.
    Si la fecha es None, retorna None.
    """
    if fecha is None:
        return None
    if isinstance(fecha, str):
        try:
            dt = datetime.strptime(fecha, "%d/%b/%Y %H:%M:%S")
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return fecha
    elif isinstance(fecha, datetime):
        return fecha.strftime("%Y-%m-%d %H:%M:%S")
    else:
        raise ValueError(f"Formato de fecha no válido: {fecha}")

def procesar_datos():
    """
    Para cada equipo (definido por contractor, rig y rig_name), obtiene:
      - El archivo .las más reciente (descargado hoy) que coincida con el rig_name y 'nws'.
      - La fecha final, extraída del .las (desde "~ASCII DATA AREA").
         Si no se encuentra ningún archivo descargado hoy, se asigna la fecha de hoy a las 00:00.
      - La fecha inicial, obtenida de la tabla files_import (campo end_datos) filtrada solo por rig_name.
        Si no se encuentra fecha, se asigna la fecha de hoy a las 00:00.
    Retorna un diccionario donde la clave es una tupla (contractor, rig, rig_name) y el valor es
    otro diccionario con:
      - "archivo": ruta del archivo .las (o None)
      - "fecha_inicial": fecha inicial formateada (YYYY-MM-DD HH:MM:SS)
      - "fecha_final": fecha final formateada (YYYY-MM-DD HH:MM:SS)
    """
    equipos = obtener_datos_equipos()
    datos = {}
    for equipo in equipos:
        contractor = equipo["contractor"]
        rig = equipo["rig"]
        rig_name = equipo["rig_name"]

        archivos = buscar_archivos(rig_name)
        archivo_reciente = obtener_archivo_mas_reciente(archivos) if archivos else None

        if archivo_reciente:
            fecha_final = extraer_fecha_hora(archivo_reciente)
        else:
            fecha_final = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)

        fecha_inicial = obtener_end_datos(rig_name)
        if fecha_inicial is None:
            fecha_inicial = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)

        fecha_final_formateada = formatear_fecha(fecha_final)
        fecha_inicial_formateada = formatear_fecha(fecha_inicial)

        datos[(contractor, rig, rig_name)] = {
            "archivo": archivo_reciente,
            "fecha_inicial": fecha_inicial_formateada,
            "fecha_final": fecha_final_formateada
        }
    return datos

def insertar_rigs_download(datos):
    """
    Inserta en la tabla rigs_download el rango de fechas para cada equipo.
    Cada registro contendrá:
      - contractor, rig, rig_name
      - fecha_inicial (obtenida de files_import o valor por defecto)
      - fecha_final (extraída del archivo LAS o valor por defecto)
      - archivo (ruta del archivo .las o None)
      - estado (inicializado en "PENDIENTE")
    """
    print("Iniciando inserción en rigs_download...")
    try:
        conn = pymysql.connect(
            host=db_config["host"],
            port=db_config["port"],
            user=db_config["user"],
            password=db_config["password"],
            database=db_config["database"],
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
    except Exception as e:
        print(f"✖ Error al conectar a la base de datos: {e}")
        return

    try:
        with conn.cursor() as cursor:
            query = """
            INSERT INTO rigs_download (contractor, rig, rig_name, fecha_inicial, fecha_final, archivo, estado)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
            """
            for key, value in datos.items():
                contractor, rig, rig_name = key
                fecha_inicial = value["fecha_inicial"]
                fecha_final = value["fecha_final"]
                archivo = value["archivo"]
                estado = "PENDIENTE"
                print(f"Inserción: contractor={contractor}, rig={rig}, rig_name={rig_name}, "
                      f"fecha_inicial={fecha_inicial}, fecha_final={fecha_final}, archivo={archivo}, estado={estado}")
                cursor.execute(query, (contractor, rig, rig_name, fecha_inicial, fecha_final, archivo, estado))
        conn.commit()
        print("✔ Registros insertados en rigs_download exitosamente.")
    except Exception as e:
        print(f"✖ Error durante la inserción en rigs_download: {e}")
    finally:
        conn.close()
        print("Conexión cerrada.")

if __name__ == "__main__":
    datos = procesar_datos()
    for key, value in datos.items():
        contractor, rig, rig_name = key
        print(f"Contractor: {contractor} - Rig: {rig} - Rig Name: {rig_name}")
        print(f"  Archivo .las: {value['archivo']}")
        print(f"  Fecha inicial: {value['fecha_inicial']}")
        print(f"  Fecha final: {value['fecha_final']}\n")
    insertar_rigs_download(datos)
