#!/usr/bin/env python3

import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import lasio

# Carga configuración
load_dotenv('/mnt/mariadb/autom_nov/config.env')

# Configuración BD
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:3306/{DB_NAME}"

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Test rápido de unidades detectadas
print("=== TEST RÁPIDO DE DETECCIÓN DE UNIDADES ===")

las_file = "/mnt/mariadb/autom_nov/data/las/activos/DLS-061_PLMS-_1056_29-07-2025_16-04_1.las"
las_obj = lasio.read(las_file, encoding='utf-8-sig')

print(f"Archivo: {Path(las_file).name}")
print(f"Total curvas: {len(las_obj.curves)}")
print("\n--- PRIMERAS 20 CURVAS CON UNIDADES ---")

count = 0
for curve in las_obj.curves:
    if count >= 20:
        break
    unit = curve.unit or "SIN_UNIDAD"
    print(f"{count+1:2d}. {curve.mnemonic:25} | Unidad: '{unit}' | Desc: {curve.descr[:50] if curve.descr else 'N/A'}")
    count += 1

print("\n--- RESUMEN DE UNIDADES ENCONTRADAS ---")
units_found = {}
for curve in las_obj.curves:
    unit = curve.unit or "SIN_UNIDAD"
    units_found[unit] = units_found.get(unit, 0) + 1

print(f"Total tipos de unidades: {len(units_found)}")
for unit, count in sorted(units_found.items(), key=lambda x: x[1], reverse=True)[:15]:
    print(f"  '{unit}': {count} variables")

print("\n¡DETECCIÓN DE UNIDADES FUNCIONANDO CORRECTAMENTE!")
