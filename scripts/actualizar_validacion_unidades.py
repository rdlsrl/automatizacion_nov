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

print("=== ACTUALIZAR VALIDACIÓN DE UNIDADES ===")

db = SessionLocal()

# Obtener registros con OBJETIVO_NO_DEFINIDO que tienen mapeo
registros_pendientes = db.query(ImportVariablesLas)\
    .filter(ImportVariablesLas.fecha_registro_curva >= '2025-07-31 17:00:00')\
    .filter(ImportVariablesLas.mapeado_a_variable_pae_id.isnot(None))\
    .filter(ImportVariablesLas.estado_validacion_unidad == 'OBJETIVO_NO_DEFINIDO')\
    .all()

print(f"Encontrados {len(registros_pendientes)} registros para actualizar...")

contador_actualizados = 0
for registro in registros_pendientes:
    print(f"\nActualizando: {registro.mnemonic_original_las} ({registro.unidad_original_las}) → PAE {registro.mapeado_a_variable_pae_id}")
    
    try:
        # Volver a ejecutar la validación con el código corregido
        validar_unidades_curva(
            session=db,
            las_curve_unit=registro.unidad_original_las,
            mapped_variable_pae_id=registro.mapeado_a_variable_pae_id,
            rig_id=97,  # Asumiendo rig_id 97
            import_var_log_obj=registro
        )
        contador_actualizados += 1
        print(f"✅ Nuevo estado: {registro.estado_validacion_unidad}")
        
    except Exception as e:
        print(f"❌ Error: {e}")

# Guardar cambios
try:
    db.commit()
    print(f"\n🎉 {contador_actualizados} registros actualizados y guardados en BD")
except Exception as e:
    print(f"❌ Error al guardar: {e}")
    db.rollback()

# Mostrar resumen final
print("\n=== RESUMEN DESPUÉS DE ACTUALIZAR ===")
resumen = db.query(ImportVariablesLas.estado_validacion_unidad, db.func.count().label('cantidad'))\
    .filter(ImportVariablesLas.fecha_registro_curva >= '2025-07-31 17:00:00')\
    .filter(ImportVariablesLas.mapeado_a_variable_pae_id.isnot(None))\
    .group_by(ImportVariablesLas.estado_validacion_unidad)\
    .all()

for estado, cantidad in resumen:
    print(f"{estado}: {cantidad}")

db.close()
