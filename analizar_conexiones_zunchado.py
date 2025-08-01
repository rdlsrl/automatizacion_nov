#!/usr/bin/env python3
"""
Analizar presión de zunchado SOLO durante conexiones/desconexiones
"""
import lasio
import numpy as np
from pathlib import Path

def analizar_conexiones_zunchado(archivo_las):
    """Analiza presión de zunchado solo durante operaciones de conexión"""
    print(f"\n{'='*60}")
    print(f"📂 ARCHIVO: {Path(archivo_las).name}")
    print(f"{'='*60}")
    
    try:
        las = lasio.read(archivo_las, ignore_header_errors=True)
        
        # Verificar si existe PRESION_DE_ZUNCHADO
        if 'PRESION_DE_ZUNCHADO' not in [c.mnemonic for c in las.curves]:
            print("❌ No tiene PRESION_DE_ZUNCHADO")
            return
            
        # Obtener datos principales
        presion_zunchado = las['PRESION_DE_ZUNCHADO']
        depth = las['DEPTH']
        
        # Buscar indicadores de conexión/desconexión
        # Típicamente durante conexiones: ROP=0, rotary_RPM=0, hook_load cambia
        indicadores_conexion = []
        
        # Buscar RPM (rotary)
        rpm_curves = [c for c in las.curves if 'RPM' in c.mnemonic.upper() or 'ROTARY' in c.mnemonic.upper()]
        rpm_data = None
        if rpm_curves:
            rpm_data = las[rpm_curves[0].mnemonic]
            print(f"📊 Usando {rpm_curves[0].mnemonic} para detectar conexiones")
        
        # Buscar ROP (rate of penetration)
        rop_curves = [c for c in las.curves if 'ROP' in c.mnemonic.upper() and 'BIT' in c.mnemonic.upper()]
        rop_data = None
        if rop_curves:
            rop_data = las[rop_curves[0].mnemonic]
            print(f"📊 Usando {rop_curves[0].mnemonic} para detectar conexiones")
        
        print(f"\n🔍 ANÁLISIS DE PRESIÓN DE ZUNCHADO:")
        print(f"  🏷️  Unidad declarada: '{las.curves['PRESION_DE_ZUNCHADO'].unit}'")
        
        # Filtrar datos válidos
        mask_validos = ~np.isnan(presion_zunchado)
        presion_valida = presion_zunchado[mask_validos]
        
        if len(presion_valida) == 0:
            print("❌ No hay datos válidos")
            return
            
        print(f"  📊 Total puntos válidos: {len(presion_valida):,}")
        print(f"  📈 Rango completo: {np.min(presion_valida):.1f} - {np.max(presion_valida):.1f}")
        
        # Detectar momentos de conexión (RPM ≈ 0 y ROP ≈ 0)
        if rpm_data is not None and rop_data is not None:
            mask_rpm_low = np.abs(rpm_data) < 5  # RPM casi cero
            mask_rop_low = np.abs(rop_data) < 1   # ROP casi cero
            mask_conexion = mask_validos & mask_rpm_low & mask_rop_low
            
            presion_durante_conexion = presion_zunchado[mask_conexion]
            presion_durante_conexion = presion_durante_conexion[~np.isnan(presion_durante_conexion)]
            
            if len(presion_durante_conexion) > 0:
                print(f"\n🔧 DURANTE CONEXIONES (RPM≈0, ROP≈0):")
                print(f"  📊 Puntos durante conexión: {len(presion_durante_conexion):,}")
                print(f"  📈 Rango: {np.min(presion_durante_conexion):.1f} - {np.max(presion_durante_conexion):.1f}")
                print(f"  📈 Promedio: {np.mean(presion_durante_conexion):.1f}")
                print(f"  📈 Mediana: {np.median(presion_durante_conexion):.1f}")
                
                # Contar valores significativos vs ceros
                ceros_conexion = np.sum(presion_durante_conexion < 5)
                activos_conexion = np.sum(presion_durante_conexion > 50)
                
                print(f"  🔢 Valores < 5: {ceros_conexion:,} ({100*ceros_conexion/len(presion_durante_conexion):.1f}%)")
                print(f"  🔢 Valores > 50: {activos_conexion:,} ({100*activos_conexion/len(presion_durante_conexion):.1f}%)")
                
                if activos_conexion > 0:
                    valores_activos = presion_durante_conexion[presion_durante_conexion > 50]
                    print(f"  🔥 Valores activos (>50): {np.sort(valores_activos)[:10]} ...")
                    
        # Detectar momentos con presión de zunchado activa (>10)
        mask_presion_activa = presion_valida > 10
        presion_activa = presion_valida[mask_presion_activa]
        
        print(f"\n🔥 MOMENTOS CON PRESIÓN ACTIVA (>10):")
        if len(presion_activa) > 0:
            print(f"  📊 Puntos con presión: {len(presion_activa):,} ({100*len(presion_activa)/len(presion_valida):.1f}% del total)")
            print(f"  📈 Rango activo: {np.min(presion_activa):.1f} - {np.max(presion_activa):.1f}")
            print(f"  📈 Promedio activo: {np.mean(presion_activa):.1f}")
            print(f"  🔢 Top 10 valores: {np.sort(presion_activa)[-10:]}")
            
            # Análisis de unidad basado en valores activos
            max_activo = np.max(presion_activa)
            promedio_activo = np.mean(presion_activa)
            
            print(f"\n  🎯 ANÁLISIS DE UNIDAD (valores activos):")
            if max_activo < 500 and promedio_activo < 200:
                print(f"    ✅ RANGO DE PRESIÓN (PSI) - Máx: {max_activo:.0f}, Prom: {promedio_activo:.0f}")
            elif max_activo > 1000:
                print(f"    ⚠️  PODRÍA SER TORQUE (ft.lbf) - Máx: {max_activo:.0f}, Prom: {promedio_activo:.0f}")
            else:
                print(f"    ❓ RANGO INTERMEDIO - Máx: {max_activo:.0f}, Prom: {promedio_activo:.0f}")
        else:
            print(f"  📊 Sin valores significativos (todos ≤10)")
            print(f"  ✅ COMPORTAMIENTO ESPERADO para presión de zunchado")
            
    except Exception as e:
        print(f"❌ ERROR: {e}")

if __name__ == "__main__":
    archivos = [
        "/mnt/mariadb/autom_nov/data/las/activos/DLS-083_PE-_1070_29-07-2025_16-09_2.las",
        "/mnt/mariadb/autom_nov/data/las/activos/DLS-075_PJ-_865_i_29-07-2025_16-06_2.las"
    ]
    
    print("🔧 ANÁLISIS DE PRESIÓN DE ZUNCHADO - SOLO CONEXIONES")
    print("=" * 80)
    
    for archivo in archivos:
        if Path(archivo).exists():
            analizar_conexiones_zunchado(archivo)
        else:
            print(f"❌ Archivo no encontrado: {archivo}")
    
    print(f"\n{'='*80}")
    print("✅ ANÁLISIS COMPLETADO")
