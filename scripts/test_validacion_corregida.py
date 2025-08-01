#!/usr/bin/env python3

import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Configuración
load_dotenv('/mnt/mariadb/autom_nov/config.env')

# Importar modelos y funciones
from modelos_bd import Config_Variables_PAE, VariablesPaeAutom, VariablesUnitsAutom, ImportVariablesLas
from manejador_curves_las import validar_unidades_curva

# BD
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")  
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:3306/{DB_NAME}"

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

print("=== TEST VALIDACIÓN UNIDADES CORREGIDA ===")

db = SessionLocal()

# Simular un objeto ImportVariablesLas
class MockImportVariablesLas:
    def __init__(self):
        self.id_unidad_original_cat = None
        self.id_unidad_objetivo_cat = None
        self.estado_validacion_unidad = None
        self.factor_conv_aplicable = None
        self.offset_conv_aplicable = None
        self.comentarios_validacion_unidad = ""

# Test 1: Variable con unidad que SÍ existe en catálogo
print("\n1. Probando ALTURA_DEL_BLOQUE con unidad 'mm'...")
mock_obj = MockImportVariablesLas()
try:
    validar_unidades_curva(
        session=db,
        las_curve_unit="mm",
        mapped_variable_pae_id=692,  # ALTURA_DEL_BLOQUE
        rig_id=97,
        import_var_log_obj=mock_obj
    )
    print(f"✅ Estado final: {mock_obj.estado_validacion_unidad}")
    print(f"   Comentario: {mock_obj.comentarios_validacion_unidad}")
    print(f"   Unidad original ID: {mock_obj.id_unidad_original_cat}")
    print(f"   Unidad objetivo ID: {mock_obj.id_unidad_objetivo_cat}")
except Exception as e:
    print(f"❌ Error: {e}")

# Test 2: Variable con unidad que NO existe en catálogo  
print("\n2. Probando con unidad inexistente 'xyz123'...")
mock_obj2 = MockImportVariablesLas()
try:
    validar_unidades_curva(
        session=db,
        las_curve_unit="xyz123",
        mapped_variable_pae_id=692,
        rig_id=97,
        import_var_log_obj=mock_obj2
    )
    print(f"✅ Estado final: {mock_obj2.estado_validacion_unidad}")
    print(f"   Comentario: {mock_obj2.comentarios_validacion_unidad}")
except Exception as e:
    print(f"❌ Error: {e}")

# Test 3: Verificar qué unidad objetivo tiene el PAE 692
print("\n3. Verificando unidad objetivo para PAE 692...")
try:
    config = db.query(Config_Variables_PAE).filter_by(rig_id=97, variable_pae_id=692).first()
    if config and config.pae_unidad_objetivo_id:
        unidad_obj = db.query(VariablesUnitsAutom).filter_by(id_unidad=config.pae_unidad_objetivo_id).first()
        if unidad_obj:
            print(f"✅ PAE 692 espera unidad: '{unidad_obj.nombre_unidad}' ({unidad_obj.tipo_dimension})")
        else:
            print(f"⚠️ Unidad objetivo ID {config.pae_unidad_objetivo_id} no existe en catálogo")
    else:
        print("⚠️ PAE 692 no tiene unidad objetivo definida")
except Exception as e:
    print(f"❌ Error: {e}")

print("\n=== FIN TEST ===")
db.close()
