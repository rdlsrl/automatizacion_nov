#!/usr/bin/env python3
"""
Consulta muy simple y directa
"""

import mysql.connector
import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar configuración
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
CONFIG_PATH = PROJECT_ROOT / "config.env"
load_dotenv(CONFIG_PATH)

def main():
    try:
        conn = mysql.connector.connect(
            host=os.getenv('DB_HOST', '127.0.0.1'),
            port=int(os.getenv('DB_PORT', '3306')),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            database=os.getenv('DB_NAME')
        )
        
        cursor = conn.cursor()
        
        print("=== RESULTADOS SIMPLES ===\n")
        
        # Contar total de variables
        cursor.execute("SELECT COUNT(*) FROM import_variables_las")
        total = cursor.fetchone()[0]
        print(f"Total variables en BD: {total}")
        
        # Estados de validación
        cursor.execute("""
        SELECT estado_validacion_unidad, COUNT(*) 
        FROM import_variables_las 
        GROUP BY estado_validacion_unidad
        """)
        
        print("\nEstados de validación:")
        for estado, cantidad in cursor.fetchall():
            estado_str = estado if estado else 'NULL'
            print(f"  {estado_str}: {cantidad}")
        
        # Variables con OBJETIVO_NO_DEFINIDO
        cursor.execute("""
        SELECT COUNT(*) 
        FROM import_variables_las 
        WHERE estado_validacion_unidad = 'OBJETIVO_NO_DEFINIDO'
        """)
        no_definido = cursor.fetchone()[0]
        print(f"\n❌ OBJETIVO_NO_DEFINIDO: {no_definido}")
        
        # Variables con VALIDA_MISMA_UNIDAD
        cursor.execute("""
        SELECT COUNT(*) 
        FROM import_variables_las 
        WHERE estado_validacion_unidad = 'VALIDA_MISMA_UNIDAD'
        """)
        validas = cursor.fetchone()[0]
        print(f"✅ VALIDA_MISMA_UNIDAD: {validas}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
