#!/usr/bin/env python3

import lasio
import os
from pathlib import Path

# Demostremos cómo detecta las unidades para TODOS los archivos
print("🔍 DEMOSTRACIÓN: Cómo detecta unidades el sistema - TODOS LOS ARCHIVOS")
print("=" * 80)

# Directorio con todos los archivos LAS
las_dir = "/mnt/mariadb/autom_nov/data/las/activos"
las_files = sorted([f for f in os.listdir(las_dir) if f.endswith('.las')])

print(f"� Directorio: {las_dir}")
print(f"📊 Total archivos encontrados: {len(las_files)}")
print()

# Estadísticas globales
total_curvas = 0
unidades_encontradas = {}

print("🔍 PROCESANDO TODOS LOS ARCHIVOS...")
print("=" * 80)

for file_idx, las_file in enumerate(las_files, 1):
    file_path = os.path.join(las_dir, las_file)
    
    try:
        print(f"\n📋 {file_idx:2d}/28: {las_file}")
        las_obj = lasio.read(file_path, encoding='utf-8-sig')
        
        file_curves = len(las_obj.curves)
        total_curvas += file_curves
        print(f"    📊 Curvas: {file_curves}")
        
        # Contar unidades únicas en este archivo
        file_units = {}
        for curve in las_obj.curves:
            unit = curve.unit or "SIN_UNIDAD"
            unit = unit.strip() if unit else "SIN_UNIDAD"
            
            # Contadores globales
            if unit in unidades_encontradas:
                unidades_encontradas[unit] += 1
            else:
                unidades_encontradas[unit] = 1
                
            # Contadores por archivo
            if unit in file_units:
                file_units[unit] += 1
            else:
                file_units[unit] = 1
        
        # Mostrar top 5 unidades de este archivo
        top_units = sorted(file_units.items(), key=lambda x: x[1], reverse=True)[:5]
        unit_summary = ", ".join([f"'{u}': {c}" for u, c in top_units])
        print(f"    🏷️  Top unidades: {unit_summary}")
        
    except Exception as e:
        print(f"    ❌ Error: {e}")

print("\n" + "=" * 80)
print("📋 RESUMEN FINAL COMPLETO:")
print(f"    📊 Total archivos procesados: {len(las_files)}")
print(f"    📈 Total curvas encontradas: {total_curvas:,}")
print(f"    🏷️  Tipos de unidades únicos: {len(unidades_encontradas)}")

print(f"\n🏷️  TOP 15 UNIDADES MÁS COMUNES:")
top_global_units = sorted(unidades_encontradas.items(), key=lambda x: x[1], reverse=True)[:15]
for unit, count in top_global_units:
    print(f"    • '{unit}': {count:,} veces")

print("\n📖 ESTRUCTURA INTERNA EJEMPLO (primer archivo):")
print("-" * 50)

# Mostrar ejemplo detallado del primer archivo
if las_files:
    first_file = os.path.join(las_dir, las_files[0])
    las_obj = lasio.read(first_file, encoding='utf-8-sig')
    
    # Tomamos las primeras 5 curvas como ejemplo
    for i, curve in enumerate(las_obj.curves[:5]):
        print(f"\nCurva #{i+1}:")
        print(f"  🔤 Mnemonic: '{curve.mnemonic}'")
        print(f"  📏 Unit: '{curve.unit}'")  # ← AQUÍ está la unidad!
        print(f"  📝 Description: '{curve.descr}'")
        print(f"  📊 Data type: {type(curve.data)}")
        
print("\n" + "=" * 80)
print("✨ MAGIA: El objeto 'curve.unit' contiene directamente la unidad!")
print()

# Proceso de detección simulado para el primer archivo
print("🧠 PROCESO DE DETECCIÓN (simulado - primer archivo):")
print("-" * 50)

if las_files:
    for i, curve in enumerate(las_obj.curves[:8]):
        unit = curve.unit or "SIN_UNIDAD"
        mnemonic = curve.mnemonic
        
        print(f"{i+1:2d}. '{mnemonic}' → Unidad detectada: '{unit}'")
        
        # Simulación del proceso interno
        if unit and unit.strip():
            print(f"    ✅ Unidad válida encontrada: '{unit}'")
        else:
            print(f"    ⚠️  Sin unidad especificada")

print("\n📋 RESUMEN DEL PROCESO COMPLETO:")
print("1. lasio.read() parsea cada archivo LAS del directorio")
print("2. Cada curve.unit contiene la unidad directamente")  
print("3. El script accede a curve.unit para cada variable")
print("4. ¡No hay procesamiento complejo, está todo en el formato LAS!")
print("5. Se analizan TODOS los 28 archivos automáticamente")

print("\n🎯 CONCLUSIÓN: La detección es DIRECTA desde TODOS los archivos LAS")
print(f"🚀 TOTAL PROCESADO: {total_curvas:,} curvas en {len(las_files)} archivos")
