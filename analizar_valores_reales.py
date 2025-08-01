#!/usr/bin/env python3
"""
Analizar valores reales de PRESION_DE_ZUNCHADO para detectar si realmente están en ft.lbf
"""
import lasio
import numpy as np
from pathlib import Path
import mysql.connector

def analizar_valores_reales():
    # Cargar archivos LAS
    archivos = [
        "/mnt/mariadb/autom_nov/data/las/activos/DLS-083_PE-_1070_29-07-2025_16-09_2.las",
        "/mnt/mariadb/autom_nov/data/las/activos/DLS-075_PJ-_865_i_29-07-2025_16-06_2.las"
    ]
    
    # Conectar a BD para obtener rangos esperados
    try:
        conn = mysql.connector.connect(
            host='127.0.0.1',
            user='root',
            password='Partediario20',
            database='rdl_import'
        )
        cursor = conn.cursor()
        
        # Obtener rangos configurados para presión de zunchado
        cursor.execute("""
            SELECT cvp.rig_id, cvp.rango_minimo, cvp.rango_maximo, r.nombre_rig
            FROM Config_Variables_PAE cvp
            LEFT JOIN rigs r ON cvp.rig_id = r.id
            WHERE cvp.variable_pae_id = 883
            AND cvp.rango_minimo IS NOT NULL 
            AND cvp.rango_maximo IS NOT NULL
            LIMIT 5
        """)
        rangos_config = cursor.fetchall()
        print("📊 RANGOS CONFIGURADOS EN PAE:")
        for rig_id, min_val, max_val, nombre in rangos_config:
            print(f"  Rig {rig_id} ({nombre}): {min_val} - {max_val}")
            
    except Exception as e:
        print(f"Error BD: {e}")
        rangos_config = []
    
    print("\n" + "="*80)
    
    for archivo in archivos:
        print(f"\n🔍 ANALIZANDO VALORES REALES: {Path(archivo).name}")
        print("-" * 60)
        
        try:
            las = lasio.read(archivo, ignore_header_errors=True)
            
            # Buscar la curva de presión de zunchado
            curva_zunchado = None
            for curva in las.curves:
                if 'PRESION_DE_ZUNCHADO' in curva.mnemonic.upper():
                    curva_zunchado = curva
                    break
            
            if not curva_zunchado:
                print("❌ No se encontró PRESION_DE_ZUNCHADO")
                continue
                
            # Obtener datos
            datos = las[curva_zunchado.mnemonic]
            datos_validos = datos[~np.isnan(datos)]
            
            if len(datos_validos) == 0:
                print("❌ No hay datos válidos")
                continue
                
            print(f"📈 ESTADÍSTICAS DE VALORES:")
            print(f"  Unidad declarada: {curva_zunchado.unit}")
            print(f"  Cantidad de datos: {len(datos_validos)}")
            print(f"  Mínimo: {np.min(datos_validos):.2f}")
            print(f"  Máximo: {np.max(datos_validos):.2f}")
            print(f"  Promedio: {np.mean(datos_validos):.2f}")
            print(f"  Mediana: {np.median(datos_validos):.2f}")
            
            # Mostrar algunos valores de ejemplo
            print(f"  Primeros 10 valores: {datos_validos[:10]}")
            
            # Análisis de rangos
            min_val = np.min(datos_validos)
            max_val = np.max(datos_validos)
            
            print(f"\n🔍 ANÁLISIS DE UNIDADES:")
            
            # Rangos típicos para presión (PSI): 0-5000 psi típico en drilling
            if max_val < 10000 and min_val >= 0:
                print(f"  ✅ Rango compatible con PSI (0-10000)")
            else:
                print(f"  ❌ Rango NO típico para PSI")
                
            # Rangos típicos para torque (ft.lbf): pueden ser 0-50000+ ft.lbf
            if max_val > 1000:
                print(f"  ✅ Rango compatible con ft.lbf (>1000)")
            else:
                print(f"  ❌ Rango NO típico para ft.lbf")
                
            # Comparar con rangos configurados
            if rangos_config:
                print(f"\n📋 COMPARACIÓN CON RANGOS CONFIGURADOS:")
                for rig_id, config_min, config_max, nombre in rangos_config[:2]:
                    print(f"  Config Rig {rig_id}: {config_min} - {config_max}")
                    if config_min <= min_val <= config_max and config_min <= max_val <= config_max:
                        print(f"    ✅ Valores DENTRO del rango configurado")
                    else:
                        print(f"    ❌ Valores FUERA del rango configurado")
                        
        except Exception as e:
            print(f"❌ Error procesando {archivo}: {e}")
    
    if conn:
        conn.close()

if __name__ == "__main__":
    analizar_valores_reales()
