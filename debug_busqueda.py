#!/usr/bin/env python3
import lasio

archivo = "/mnt/mariadb/autom_nov/data/las/activos/DLS-083_PE-_1070_29-07-2025_16-09_2.las"
las = lasio.read(archivo, ignore_header_errors=True)

print("🔍 BUSCANDO PRESION_DE_ZUNCHADO:")
encontrada = False

for i, curva in enumerate(las.curves):
    if 'PRESION_DE_ZUNCHADO' in curva.mnemonic:
        print(f"  ✅ ENCONTRADA #{i}: '{curva.mnemonic}' | Unidad: '{curva.unit}' | Desc: {curva.descr}")
        encontrada = True
        
        # Probar acceso a datos
        try:
            datos = las[curva.mnemonic]
            print(f"    📊 Datos accesibles: {len(datos)} puntos")
            print(f"    📊 Primeros 5 valores: {datos[:5]}")
        except Exception as e:
            print(f"    ❌ Error accediendo datos: {e}")

if not encontrada:
    print("❌ NO ENCONTRADA")
    
    # Listar todos los mnemónicos que contengan 'PRESION'
    print("\n🔍 Todos los mnemónicos que contienen 'PRESION':")
    for i, curva in enumerate(las.curves):
        if 'PRESION' in curva.mnemonic:
            print(f"  {i}: '{curva.mnemonic}' | Repr: {repr(curva.mnemonic)}")
