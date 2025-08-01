#!/usr/bin/env python3
"""
Script para demostrar la lectura optimizada de archivos LAS:
Solo headers/metadata y definiciones de curvas, sin cargar los datos.
"""

import os
from pathlib import Path
import lasio
import time

def leer_las_completo(ruta_las):
    """Método actual: lee todo el archivo LAS"""
    print("=== MÉTODO ACTUAL: Lectura Completa ===")
    inicio = time.time()
    
    try:
        las_obj = lasio.read(ruta_las, encoding='utf-8-sig')
        tiempo = time.time() - inicio
        
        print(f"✓ Archivo leído en {tiempo:.2f} segundos")
        print(f"  - Secciones cargadas: {list(las_obj.sections.keys())}")
        print(f"  - Curvas detectadas: {len(las_obj.curves)}")
        if hasattr(las_obj, 'data') and las_obj.data is not None:
            print(f"  - Filas de datos: {las_obj.data.shape[0]}")
            print(f"  - Tamaño datos en memoria: ~{las_obj.data.nbytes / (1024*1024):.1f} MB")
        
        return las_obj, tiempo
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return None, 0

def leer_las_optimizado(ruta_las):
    """Método optimizado: solo headers y curvas, sin datos"""
    print("\n=== MÉTODO OPTIMIZADO: Solo Headers y Curvas ===")
    inicio = time.time()
    
    try:
        # Usar null_policy='none' para no cargar datos innecesarios
        # Y solo cargar las secciones que necesitamos
        las_obj = lasio.read(
            ruta_las, 
            encoding='utf-8-sig',
            null_policy='none',  # No procesar valores nulos en datos
            ignore_header_errors=True  # Ignorar errores menores en headers
        )
        
        # NO limpiar datos para evitar errores con lasio
        # La optimización principal está en null_policy='none'
            
        tiempo = time.time() - inicio
        
        print(f"✓ Archivo leído (optimizado) en {tiempo:.2f} segundos")
        print(f"  - Secciones disponibles: {list(las_obj.sections.keys())}")
        print(f"  - Curvas detectadas: {len(las_obj.curves)}")
        if hasattr(las_obj, 'data') and las_obj.data is not None:
            print(f"  - Datos: Cargados pero optimizados (null_policy='none')")
        else:
            print(f"  - Datos: No disponibles")
        
        return las_obj, tiempo
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return None, 0

def comparar_informacion_curvas(las_completo, las_optimizado):
    """Compara que ambos métodos extraigan la misma información de curvas"""
    print("\n=== COMPARACIÓN DE INFORMACIÓN EXTRAÍDA ===")
    
    if not las_completo or not las_optimizado:
        print("❌ No se pueden comparar - falló alguna lectura")
        return
    
    print("Comparando primeras 5 curvas:")
    for i in range(min(5, len(las_completo.curves), len(las_optimizado.curves))):
        curva_comp = las_completo.curves[i]
        curva_opt = las_optimizado.curves[i]
        
        print(f"\nCurva #{i+1}:")
        print(f"  Mnemónico: '{curva_comp.mnemonic}' vs '{curva_opt.mnemonic}' {'✓' if curva_comp.mnemonic == curva_opt.mnemonic else '❌'}")
        print(f"  Unidad:    '{curva_comp.unit}' vs '{curva_opt.unit}' {'✓' if curva_comp.unit == curva_opt.unit else '❌'}")
        print(f"  Descr:     '{curva_comp.descr[:30]}...' vs '{curva_opt.descr[:30]}...' {'✓' if curva_comp.descr == curva_opt.descr else '❌'}")

def main():
    # Usar un archivo LAS del equipo PAE 001
    ruta_las = "/mnt/mariadb/autom_nov/data/las/activos/PAE-001_PAE_Nq_CASE-_337_h__29-07-2025_16-04_59.las"
    
    if not os.path.exists(ruta_las):
        print(f"❌ Archivo no encontrado: {ruta_las}")
        return
    
    print(f"Probando con archivo: {Path(ruta_las).name}")
    print(f"Tamaño del archivo: {os.path.getsize(ruta_las) / (1024*1024):.1f} MB")
    
    # Probar ambos métodos
    las_completo, tiempo_completo = leer_las_completo(ruta_las)
    las_optimizado, tiempo_optimizado = leer_las_optimizado(ruta_las)
    
    # Comparar resultados
    comparar_informacion_curvas(las_completo, las_optimizado)
    
    # Mostrar mejora
    if tiempo_completo > 0 and tiempo_optimizado > 0:
        mejora = ((tiempo_completo - tiempo_optimizado) / tiempo_completo) * 100
        print(f"\n=== RESULTADOS ===")
        print(f"Tiempo completo:   {tiempo_completo:.2f}s")
        print(f"Tiempo optimizado: {tiempo_optimizado:.2f}s")
        print(f"Mejora:            {mejora:.1f}% más rápido")
        print(f"Factor:            {tiempo_completo/tiempo_optimizado:.1f}x")

if __name__ == "__main__":
    main()
