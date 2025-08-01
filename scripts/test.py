#!/usr/bin/env python3
"""
SCRIPT DE DIAGNÓSTICO SIMPLIFICADO
"""

import os
import sys

# --------------------------------------------------
# PASO 1: Verificaciones básicas del sistema
# --------------------------------------------------
print("\n[PASO 1] Verificando sistema básico...")
print(f"Python version: {sys.version}")
print(f"Directorio actual: {os.getcwd()}")

# --------------------------------------------------
# PASO 2: Verificar archivo LAS
# --------------------------------------------------
print("\n[PASO 2] Verificando archivo LAS...")
archivo_las = "/mnt/mariadb/autom_nov/DLS-075_ESCORIAL PE-932_05-04-2025_05-09_end.las"
print(f"Ruta del archivo: {archivo_las}")

if os.path.exists(archivo_las):
    print("✅ El archivo existe")
    print(f"Tamaño: {os.path.getsize(archivo_las)} bytes")
else:
    print("❌ El archivo NO existe")
    sys.exit(1)

# --------------------------------------------------
# PASO 3: Verificar módulo lasio
# --------------------------------------------------
print("\n[PASO 3] Verificando módulo lasio...")
try:
    import lasio
    print("✅ lasio está instalado")
    # Intentar leer el archivo
    try:
        las = lasio.read(archivo_las)
        print("✅ Archivo LAS leído correctamente")
        print(f"Primeras 5 curvas: {las.curves[:5]}")
    except Exception as e:
        print(f"❌ Error leyendo LAS: {str(e)}")
except ImportError:
    print("❌ lasio NO está instalado")
    print("Instala con: pip install lasio")

# --------------------------------------------------
# PASO 4: Verificar conexión a base de datos
# --------------------------------------------------
print("\n[PASO 4] Verificando base de datos...")
try:
    from sqlalchemy import create_engine
    print("✅ SQLAlchemy está instalado")
    
    # Verificar archivo de configuración
    config_path = "/mnt/mariadb/autom_nov/config.env"
    if os.path.exists(config_path):
        print(f"✅ Archivo config encontrado: {config_path}")
        from dotenv import load_dotenv
        load_dotenv(config_path)
        
        # Verificar variables
        required_vars = ['DB_HOST', 'DB_USER', 'DB_PASSWORD', 'DB_NAME']
        missing = [var for var in required_vars if not os.getenv(var)]
        
        if missing:
            print(f"❌ Faltan variables: {missing}")
        else:
            print("✅ Todas las variables están presentes")
            print("Probando conexión...")
            try:
                engine = create_engine(
                    f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}/{os.getenv('DB_NAME')}"
                )
                with engine.connect() as conn:
                    print("✅ Conexión exitosa a la base de datos")
            except Exception as e:
                print(f"❌ Error de conexión: {str(e)}")
    else:
        print(f"❌ Archivo config NO encontrado: {config_path}")
except ImportError:
    print("❌ SQLAlchemy NO está instalado")
    print("Instala con: pip install sqlalchemy pymysql python-dotenv")

# --------------------------------------------------
# FINAL
# --------------------------------------------------
print("\n[RESUMEN]")
print("1. Sistema Python: OK" if "✅" in sys.version else "1. Sistema Python: PROBLEMA")
print("2. Archivo LAS: OK" if os.path.exists(archivo_las) else "2. Archivo LAS: NO EXISTE")
print("3. Módulo lasio: OK" if "lasio" in sys.modules else "3. Módulo lasio: NO INSTALADO")
print("4. Conexión BD: OK" if "✅ Conexión exitosa" in locals() else "4. Conexión BD: PROBLEMA")

print("\nSi ves algún ❌, ese es tu problema principal a resolver.")
