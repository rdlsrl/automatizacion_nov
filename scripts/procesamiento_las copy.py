#!/usr/bin/env python3
import os
import lasio
import datetime
import re
from import_las_autom2 import buscar_pozo_general, buscar_pozo_por_uwi
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

print("Iniciando procesamiento de LAS...")

# Cargar configuración de base de datos
load_dotenv("/mnt/mariadb/autom_nov/config.env")
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
DB_PORT = os.getenv("DB_PORT", 3306)
DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
print("DATABASE_URL =", DATABASE_URL)

Base = declarative_base()

class FilesImport(Base):
    __tablename__ = 'files_import'
    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    date_time = Column(DateTime)
    STRT = Column(String(50))
    STOP = Column(String(50))
    STEP = Column(String(10))
    NULL = Column(String(20))
    COMP = Column(String(100))
    WELL = Column(String(100))
    FLD = Column(String(100))
    LOC = Column(String(100))
    SRVC = Column(String(100))
    CTRY = Column(String(50))
    DATE = Column(String(20))
    UWI = Column(String(50))
    LIC = Column(String(50))
    LATI = Column(String(50))
    LONG = Column(String(50))
    GDAT = Column(String(50))
    variables_las = Column(Integer)
    step = Column(Integer)
    process_time_seg = Column(String(50))

class Event(Base):
    __tablename__ = 'events'
    id = Column(Integer, primary_key=True)
    well_id = Column(Integer)
    activate = Column(Integer)
    date_end = Column(DateTime)
    date_start = Column(DateTime)

class InfoProd(Base):
    __tablename__ = 'info_prod'
    id = Column(Integer, primary_key=True)
    DATE_REPORT = Column(String(50))
    UWI = Column(String(20))
    WELL = Column(String(255))
    EVENT_ID = Column(String(50))
    EVENT_CODE = Column(String(255))
    START_DATE = Column(String(50))
    RIG = Column(String(255))
    obs = Column(String(255))

engine = create_engine(DATABASE_URL, echo=True)
Session = sessionmaker(bind=engine)
session = Session()

def extraer_valor(header_item):
    if hasattr(header_item, "value"):
        return header_item.value.strip() if isinstance(header_item.value, str) else str(header_item.value).strip()
    return str(header_item).strip()

def process_las_file(filepath):
    try:
        las = lasio.read(filepath)
        print("Archivo LAS leído:", filepath)
    except Exception as e:
        print("Error al leer el archivo LAS:", e)
        return None
    header_lower = {k.lower(): v for k, v in las.header.items()}
    well = header_lower.get("well")
    well_info = {}
    if well:
        for key, header_item in well.items():
            well_info[key.strip()] = extraer_valor(header_item)
    else:
        print("No se encontró el bloque WELL en el archivo LAS.")
    return {"WI": well_info, "LAS_obj": las}

def process_va(las):
    va_data = []
    orders = []
    for curve in las.curves:
        mnemonic = curve.mnemonic.strip() if curve.mnemonic else ""
        unit = curve.unit.strip() if curve.unit else ""
        description = curve.description.strip() if hasattr(curve, "description") and curve.description else ""
        m = re.match(r'(\d+)', description)
        order = int(m.group(1)) if m else None
        if order is not None:
            orders.append(order)
        va_data.append({
            "mnemonic": mnemonic,
            "unit": unit,
            "description": description,
            "order": order
        })
    var_nom = [item["mnemonic"] for item in va_data if item["mnemonic"]]
    var_unit = [item["unit"] for item in va_data if item["mnemonic"]]
    var_inter = []
    for i, item in enumerate(va_data):
        if item["mnemonic"]:
            pos = item.get("order") if item.get("order") is not None else i
            var_inter.append({
                "position": pos,
                "variable": item["mnemonic"],
                "unit": item["unit"]
            })
    total_variables = max(orders) if orders else len(var_nom)
    return {"var_nom": var_nom, "var_unit": var_unit, "var_inter": var_inter, "total_variables": total_variables}

from datetime import datetime

def update_files_import_db(archivo_id, well_info):
    registro = session.query(FilesImport).filter(FilesImport.id == archivo_id).first()
    if not registro:
        print("No se encontró el registro con id", archivo_id)
        return

    formato_original = '%d/%b/%Y %H:%M:%S'
    formato_nuevo = '%Y-%m-%d %H:%M:%S'

    for key, valor in well_info.items():
        valor_final = valor.split(" : ")[0].strip() if " : " in valor else valor.strip()

        if key in ('STRT', 'STOP') and valor_final:
            try:
                fecha_obj = datetime.strptime(valor_final, formato_original)
                valor_final = fecha_obj.strftime(formato_nuevo)
            except ValueError as ve:
                print(f"⚠️ Error parseando fecha {key}: {valor_final}", ve)
                continue

        setattr(registro, key, valor_final)

    registro.step = 5
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        print("Error actualizando files_import:", e)

def update_variables_las(archivo_id, va_info):
    total_vars = va_info.get("total_variables", 0)
    registro = session.query(FilesImport).filter(FilesImport.id == archivo_id).first()
    if not registro:
        print("No se encontró el registro con id", archivo_id)
        return
    registro.variables_las = total_vars
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        print("Error actualizando variables_las:", e)

filepath = "/mnt/mariadb/autom_nov/DLS-074_PCG- 1299*D_05-04-2025_04-32_2.las"
archivo_id = 126440

if not os.path.exists(filepath):
    print("El archivo LAS no existe en la ruta:", filepath)
    exit(1)

datos = process_las_file(filepath)
if datos is None:
    print("Error en la lectura del LAS.")
    exit(1)

well_info = datos.get("WI")
nombre_pozo = well_info.get("WELL")
uwi = well_info.get("UWI")

pozo = None
if uwi:
    pozo = buscar_pozo_por_uwi(uwi)
    if pozo:
        print("✅ Pozo encontrado por UWI:", pozo.name, "(ID:", pozo.id, ")")

if not pozo:
    pozo = buscar_pozo_general(nombre_pozo, None)
    if pozo:
        print("✅ Pozo encontrado por nombre:", pozo.name, "(ID:", pozo.id, ")")

if pozo:
    # Verificar si el pozo encontrado es el activo último
    evento_activo_ultimo = session.query(Event).filter(
        Event.well_id == pozo.id,
        Event.activate == 1
    ).order_by(Event.date_end.desc(), Event.date_start.desc()).first()

    if evento_activo_ultimo:
        print("El pozo encontrado ES el activo último.")
    else:
        print("El pozo encontrado NO es el activo último.")

        # Si no es el activo último, buscarlo en info_prod
        infoprod_pozo = session.query(InfoProd).filter(
            InfoProd.WELL == pozo.name  # Usar el nombre del pozo encontrado
        ).first()

        if infoprod_pozo:
            print("Pozo encontrado en info_prod:", infoprod_pozo.WELL, "(ID:", infoprod_pozo.id, ")")

    update_files_import_db(archivo_id, well_info)
    las_obj = datos.get("LAS_obj")
    va_info = process_va(las_obj)
    update_variables_las(archivo_id, va_info)
    print("Procesamiento finalizado.")
else:
    print("⚠️ Pozo no encontrado en la base de datos.")
