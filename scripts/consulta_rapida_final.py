#!/usr/bin/env python3
"""
Consulta rápida del estado final
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
        # Conexión rápida con mysql.connector
        conn = mysql.connector.connect(
            host=os.getenv('DB_HOST', '127.0.0.1'),
            port=int(os.getenv('DB_PORT', '3306')),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            database=os.getenv('DB_NAME')
        )
        
        cursor = conn.cursor()
        
        print("=== ESTADO FINAL DE VALIDACIÓN DE UNIDADES ===\n")
        
        # Consulta rápida
        query = """
        SELECT estado_validacion_unidad, COUNT(*) as cantidad 
        FROM import_variables_las 
        WHERE estado_mapeo_curva = 'MAPEADO_EXACTO' 
        GROUP BY estado_validacion_unidad 
        ORDER BY cantidad DESC
        """
        
        cursor.execute(query)
        results = cursor.fetchall()
        
        total = 0
        for estado, cantidad in results:
            print(f"{estado}: {cantidad}")
            total += cantidad
        
        print(f"\n📊 TOTAL: {total} variables procesadas")
        
        # Calcular porcentajes
        print("\n📈 PORCENTAJES:")
        for estado, cantidad in results:
            porcentaje = (cantidad / total) * 100
            print(f"{estado}: {porcentaje:.1f}%")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
