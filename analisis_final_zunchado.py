#!/usr/bin/env python3
"""
Script definitivo para analizar presión de zunchado
"""
import lasio
import numpy as np
from pathlib import Path

def analizar_presion_zunchado(archivo_las):
    """Analiza específicamente PRESION_DE_ZUNCHADO"""
    print(f"\n{'='*60}")
    print(f"📂 ARCHIVO: {Path(archivo_las).name}")
    print(f"{'='*60}")
    
    try:
        las = lasio.read(archivo_las, ignore_header_errors=True)
        
        # Buscar PRESION_DE_ZUNCHADO
        curva_encontrada = None
        for curva in las.curves:
            if curva.mnemonic == 'PRESION_DE_ZUNCHADO':
                curva_encontrada = curva
                break
        
        if curva_encontrada:
            print(f"✅ CURVA ENCONTRADA: {curva_encontrada.mnemonic}")
            print(f"📋 Descripción: {curva_encontrada.descr}")
            print(f"🏷️  Unidad declarada: '{curva_encontrada.unit}'")
            
            # Analizar datos
            datos = las[curva_encontrada.mnemonic]
            datos_validos = datos[~np.isnan(datos)]
            
            if len(datos_validos) > 0:
                min_val = np.min(datos_validos)
                max_val = np.max(datos_validos)
                promedio = np.mean(datos_validos)
                mediana = np.median(datos_validos)
                std_dev = np.std(datos_validos)
                
                print(f"\n📊 ESTADÍSTICAS:")
                print(f"  📈 Total puntos: {len(datos_validos):,}")
                print(f"  📈 Mínimo: {min_val:.2f}")
                print(f"  📈 Máximo: {max_val:.2f}")
                print(f"  📈 Promedio: {promedio:.2f}")
                print(f"  📈 Mediana: {mediana:.2f}")
                print(f"  📈 Desv. Estd: {std_dev:.2f}")
                
                print(f"\n🔢 VALORES DE MUESTRA:")
                print(f"  🔢 Primeros 10: {datos_validos[:10]}")
                print(f"  🔢 Últimos 10: {datos_validos[-10:]}")
                
                # ANÁLISIS DE UNIDAD REAL
                print(f"\n🔍 ANÁLISIS DE UNIDAD REAL:")
                
                # Rangos típicos
                if 0 <= min_val <= 500 and max_val <= 5000:
                    print(f"  ✅ RANGO TÍPICO DE PRESIÓN (PSI)")
                    print(f"    - Valores entre {min_val:.0f} - {max_val:.0f} psi")
                    print(f"    - Promedio {promedio:.0f} psi")
                    
                if max_val > 10000 or promedio > 5000:
                    print(f"  ⚠️  PODRÍA SER TORQUE (ft.lbf)")
                    print(f"    - Valores altos para presión típica")
                    
                # CONCLUSIÓN FINAL
                print(f"\n🎯 CONCLUSIÓN:")
                unidad_declarada = curva_encontrada.unit.lower()
                
                if 'psi' in unidad_declarada and max_val <= 5000:
                    print(f"  ✅ COHERENTE: Unidad 'psi' y valores de presión típicos")
                    print(f"  ✅ Los datos parecen estar correctamente en PSI")
                elif 'lbf' in unidad_declarada:
                    print(f"  ✅ COHERENTE: Unidad declara ft.lbf")
                elif 'psi' in unidad_declarada and max_val > 10000:
                    print(f"  ❌ INCOHERENTE: Dice 'psi' pero valores parecen ft.lbf")
                else:
                    print(f"  ⚠️  REVISAR: Unidad '{curva_encontrada.unit}' con rango {min_val:.0f}-{max_val:.0f}")
                
            else:
                print(f"❌ Sin datos válidos")
                
        else:
            print(f"❌ CURVA 'PRESION_DE_ZUNCHADO' NO ENCONTRADA")
            
            # Mostrar curvas similares
            print(f"\n💡 CURVAS SIMILARES:")
            for curva in las.curves:
                if 'PRESION' in curva.mnemonic and 'ZUNCHO' in curva.mnemonic:
                    print(f"  💡 {curva.mnemonic} | {curva.unit} | {curva.descr}")
            
    except Exception as e:
        print(f"❌ ERROR: {e}")

if __name__ == "__main__":
    archivos = [
        "/mnt/mariadb/autom_nov/data/las/activos/DLS-083_PE-_1070_29-07-2025_16-09_2.las",
        "/mnt/mariadb/autom_nov/data/las/activos/DLS-075_PJ-_865_i_29-07-2025_16-06_2.las"
    ]
    
    print("🎯 ANÁLISIS DEFINITIVO DE PRESIÓN DE ZUNCHADO")
    print("=" * 80)
    
    for archivo in archivos:
        if Path(archivo).exists():
            analizar_presion_zunchado(archivo)
        else:
            print(f"❌ Archivo no encontrado: {archivo}")
    
    print(f"\n{'='*80}")
    print("✅ ANÁLISIS COMPLETADO")
