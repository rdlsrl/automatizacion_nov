#!/usr/bin/env python3

import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import lasio

# Configuración
load_dotenv('/mnt/mariadb/autom_nov/config.env')

# Importar modelos
from modelos_bd import Config_Variables_PAE, VariablesPaeAutom, VariablesUnitsAutom

# BD
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")  
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:3306/{DB_NAME}"

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

print("=== TEST CORRECCIÓN VALIDACIÓN UNIDADES ===")

db = SessionLocal()

# Probar consulta Config_Variables_PAE
print("\n1. Probando acceso a Config_Variables_PAE...")
try:
    config_sample = db.query(Config_Variables_PAE).filter_by(rig_id=97).first()
    if config_sample:
        print(f"✅ Registro encontrado: Rig {config_sample.rig_id}, PAE {config_sample.variable_pae_id}")
        print(f"   Tiene pae_unidad_objetivo_id: {hasattr(config_sample, 'pae_unidad_objetivo_id')}")
        if hasattr(config_sample, 'pae_unidad_objetivo_id'):
            print(f"   Valor pae_unidad_objetivo_id: {config_sample.pae_unidad_objetivo_id}")
    else:
        print("❌ No se encontraron registros para Rig 97")
except Exception as e:
    print(f"❌ Error: {e}")

# Probar consulta VariablesPaeAutom
print("\n2. Probando acceso a VariablesPaeAutom...")
try:
    pae_sample = db.query(VariablesPaeAutom).filter_by(id=890).first()  # DEPTH
    if pae_sample:
        print(f"✅ PAE encontrado: {pae_sample.name_pae}")
        print(f"   Tiene unidad_estandar_pae: {hasattr(pae_sample, 'unidad_estandar_pae')}")
        if hasattr(pae_sample, 'unidad_estandar_pae'):
            print(f"   Valor: {pae_sample.unidad_estandar_pae}")
    else:
        print("❌ PAE ID 890 no encontrado")
except Exception as e:
    print(f"❌ Error: {e}")

# Probar catálogo de unidades
print("\n3. Probando catálogo de unidades...")
try:
    unidades_sample = db.query(VariablesUnitsAutom).limit(3).all()
    if unidades_sample:
        print("✅ Catálogo de unidades encontrado:")
        for u in unidades_sample:
            print(f"   ID {u.id_unidad}: '{u.nombre_unidad}' - {u.tipo_dimension}")
    else:
        print("❌ Catálogo de unidades vacío")
except Exception as e:
    print(f"❌ Error: {e}")

db.close()
print("\n=== FIN TEST ===")
