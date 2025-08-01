#!/usr/bin/env python3
"""
Script rápido para analizar unidades de presión de zunchado en archivos LAS específicos
"""
import lasio
from pathlib import Path

def analizar_las_presion(archivo_las):
    """Analiza un archivo LAS buscando curvas de presión"""
    print(f"\n{'='*60}")
    print(f"ANALIZANDO: {Path(archivo_las).name}")
    print(f"{'='*60}")
    
    try:
        las = lasio.read(archivo_las, ignore_header_errors=True)

        # Mostrar rango de fechas/tiempos en header WELL y PARAMS
        date_keys = []
        for section_name in ('well', 'params'):
            section = getattr(las, section_name)
            for key, item in section.items():
                key_lower = key.lower()
                if any(tok in key_lower for tok in ('date', 'time', 'fecha', 'hora')):
                    date_keys.append((section_name, key, item.value))
        if date_keys:
            print("\n📅 FECHA/TIEMPO EN HEADER:")
            for sec, key, value in date_keys:
                print(f"  [{sec.upper()}] {key}: {value}")
        else:
            print("\n⚠️ No hay campos de fecha/tiempo en el header")
        
        print(f"Total de curvas en el archivo: {len(las.curves)}")
        print("\n📋 LISTA COMPLETA DE CURVAS EN EL ARCHIVO:")
        for curva in las.curves:
            print(f"  ➡️ {curva.mnemonic:<25} | Unidad: {curva.unit:<10} | Desc: {curva.descr}")

        # Buscar automáticamente la curva de presión de zunchado más probable
        print("\n🔎 Buscando curva de presión de zunchado más probable...")
        heuristicas = [
            'ZUNCH', 'CSG', 'CASING', 'PRESION', 'PRESS', 'ANNULAR', 'CIRCULACION', 'HYDRAULIC', 'TORQUE'
        ]
        candidatas = []
        for curva in las.curves:
            nombre = curva.mnemonic.upper()
            desc = (curva.descr or '').upper()
            if any(h in nombre or h in desc for h in heuristicas):
                candidatas.append(curva)
        if candidatas:
            print(f"\nCandidatas encontradas ({len(candidatas)}):")
            for curva in candidatas:
                print(f"  🏷️ {curva.mnemonic:<25} | Unidad: {curva.unit:<10} | Desc: {curva.descr}")
            # Elegir la más específica
            preferidas = [c for c in candidatas if 'ZUNCH' in c.mnemonic.upper() or 'ZUNCH' in (c.descr or '').upper()]
            if not preferidas:
                preferidas = [c for c in candidatas if 'PRESION' in c.mnemonic.upper() or 'PRESION' in (c.descr or '').upper()]
            if preferidas:
                curva_obj = preferidas[0]
            else:
                curva_obj = candidatas[0]
            print(f"\n🎯 Analizando curva seleccionada: {curva_obj.mnemonic} ({curva_obj.unit})")
            try:
                import numpy as np
                datos = las[curva_obj.mnemonic]
                datos_validos = datos[~np.isnan(datos)] if hasattr(datos, '__getitem__') else datos
                if len(datos_validos) > 0:
                    print(f"  📊 Total de puntos: {len(datos_validos)}")
                    print(f"  📈 Mínimo: {np.min(datos_validos):.2f}")
                    print(f"  📈 Máximo: {np.max(datos_validos):.2f}")
                    print(f"  📈 Promedio: {np.mean(datos_validos):.2f}")
                    print(f"  📈 Mediana: {np.median(datos_validos):.2f}")
                    print(f"  📈 Desv. Estándar: {np.std(datos_validos):.2f}")
                else:
                    print(f"  ❌ No hay datos válidos en la curva")
            except Exception as e:
                print(f"  ❌ Error al analizar datos: {e}")
        else:
            print("❌ No se encontró ninguna curva candidata a presión de zunchado")
        return

        # Buscar curvas relacionadas con presión
        curvas_presion = []
        keywords_presion = ['PRES', 'PRESS', 'PSI', 'BAR', 'KPA', 'PASCAL', 'ATM']
        
        for curva in las.curves:
            mnemonic_upper = curva.mnemonic.upper()
            if any(keyword in mnemonic_upper for keyword in keywords_presion):
                curvas_presion.append(curva)
        
        print(f"\n🔍 CURVAS DE PRESIÓN ENCONTRADAS ({len(curvas_presion)}):")
        if curvas_presion:
            for curva in curvas_presion:
                print(f"  📊 {curva.mnemonic:<20} | Unidad: {curva.unit:<10} | Desc: {curva.descr}")
        else:
            print("  ❌ No se encontraron curvas de presión con keywords obvios")
        
        # Buscar curvas relacionadas con zunchado/casing
        curvas_zunchado = []
        keywords_zunchado = ['CASING', 'CSG', 'ZUNCHO', 'ANNU', 'TUBULAR', 'REVESTIMIENTO']
        
        for curva in las.curves:
            mnemonic_upper = curva.mnemonic.upper()
            desc_upper = (curva.descr or '').upper()
            if any(keyword in mnemonic_upper or keyword in desc_upper for keyword in keywords_zunchado):
                curvas_zunchado.append(curva)
        
        print(f"\n🔧 CURVAS DE ZUNCHADO/CASING ENCONTRADAS ({len(curvas_zunchado)}):")
        if curvas_zunchado:
            for curva in curvas_zunchado:
                print(f"  🔧 {curva.mnemonic:<20} | Unidad: {curva.unit:<10} | Desc: {curva.descr}")
        else:
            print("  ❌ No se encontraron curvas de zunchado con keywords obvios")
        
        # Buscar combinaciones de presión + zunchado
        curvas_presion_zunchado = []
        for curva in las.curves:
            mnemonic_upper = curva.mnemonic.upper()
            desc_upper = (curva.descr or '').upper()
            
            tiene_presion = any(keyword in mnemonic_upper or keyword in desc_upper for keyword in keywords_presion)
            tiene_zunchado = any(keyword in mnemonic_upper or keyword in desc_upper for keyword in keywords_zunchado)
            
            if tiene_presion and tiene_zunchado:
                curvas_presion_zunchado.append(curva)
        
        print(f"\n🎯 CURVAS DE PRESIÓN DE ZUNCHADO ({len(curvas_presion_zunchado)}):")
        if curvas_presion_zunchado:
            for curva in curvas_presion_zunchado:
                print(f"  🎯 {curva.mnemonic:<20} | Unidad: {curva.unit:<10} | Desc: {curva.descr}")
        else:
            print("  ❌ No se encontraron curvas que combinen presión + zunchado")
        
        # Buscar específicamente PRESION_DE_ZUNCHADO y analizar valores
        import numpy as np
        curva_zunchado_encontrada = None
        for curva in las.curves:
            if curva.mnemonic == 'PRESION_DE_ZUNCHADO':
                curva_zunchado_encontrada = curva
                break
        
        if curva_zunchado_encontrada:
            print(f"\n🎯 ANÁLISIS DETALLADO DE {curva_zunchado_encontrada.mnemonic}:")
            print(f"  📋 Descripción: {curva_zunchado_encontrada.descr}")
            print(f"  🏷️  Unidad declarada: {curva_zunchado_encontrada.unit}")
            
            # Obtener datos reales
            try:
                datos = las[curva_zunchado_encontrada.mnemonic]
                datos_validos = datos[~np.isnan(datos)]
                
                if len(datos_validos) > 0:
                    print(f"  📊 Total de puntos: {len(datos_validos)}")
                    print(f"  📈 Mínimo: {np.min(datos_validos):.2f}")
                    print(f"  📈 Máximo: {np.max(datos_validos):.2f}")
                    print(f"  📈 Promedio: {np.mean(datos_validos):.2f}")
                    print(f"  📈 Mediana: {np.median(datos_validos):.2f}")
                    print(f"  📈 Desv. Estándar: {np.std(datos_validos):.2f}")
                    
                    # Mostrar más valores de ejemplo
                    print(f"  🔢 Primeros 20 valores: {datos_validos[:20]}")
                    print(f"  🔢 Últimos 10 valores: {datos_validos[-10:]}")
                    
                    # Análisis de rangos para detectar unidad real
                    min_val = np.min(datos_validos)
                    max_val = np.max(datos_validos)
                    promedio = np.mean(datos_validos)
                    
                    print(f"\n  🔍 ANÁLISIS DE UNIDAD REAL:")
                    
                    # Si los valores son típicos de PSI (presión)
                    if 0 <= min_val < 100 and max_val < 5000:
                        print(f"    ✅ Rango típico de PRESIÓN en PSI (0-5000)")
                    elif max_val > 5000:
                        print(f"    ⚠️  Valores altos para PSI típico (>5000)")
                    
                    # Si los valores son típicos de ft.lbf (torque)
                    if max_val > 10000 or promedio > 5000:
                        print(f"    ✅ Rango típico de TORQUE en ft.lbf (>10000)")
                    elif max_val > 1000:
                        print(f"    ⚠️  Podría ser torque en ft.lbf (1000-10000)")
                    
                    # Conclusión
                    print(f"\n  🎯 CONCLUSIÓN:")
                    if curva_zunchado_encontrada.unit == 'psi' and max_val > 10000:
                        print(f"    ❌ PROBABLE ERROR: Unidad dice 'psi' pero valores parecen ft.lbf")
                    elif curva_zunchado_encontrada.unit == 'psi' and max_val < 5000:
                        print(f"    ✅ CORRECTO: Unidad 'psi' y valores coherentes")
                    elif 'lbf' in str(curva_zunchado_encontrada.unit).lower():
                        print(f"    ✅ CORRECTO: Unidad ft.lbf declarada")
                    else:
                        print(f"    ⚠️  REVISAR: Unidad '{curva_zunchado_encontrada.unit}' con valores {min_val:.0f}-{max_val:.0f}")
                        
                else:
                    print(f"  ❌ No hay datos válidos en la curva")
            except Exception as e:
                print(f"  ❌ Error al analizar datos: {e}")
        else:
            print(f"\n❌ No se encontró curva de PRESION_DE_ZUNCHADO")
        
        # Mostrar algunas curvas que podrían ser de interés (que contengan P)
        print(f"\n💡 OTRAS CURVAS QUE CONTIENEN 'P' (primeras 15):")
        curvas_con_p = [c for c in las.curves if 'P' in c.mnemonic.upper()][:15]
        for curva in curvas_con_p:
            print(f"  💡 {curva.mnemonic:<25} | Unidad: {curva.unit:<12} | Desc: {curva.descr}")
        
        return curvas_presion, curvas_zunchado, curvas_presion_zunchado
        
    except Exception as e:
        print(f"❌ ERROR al leer el archivo: {e}")
        return [], [], []

if __name__ == "__main__":
    # Archivos a analizar
    archivos_a_analizar = [
        "/mnt/mariadb/autom_nov/data/las/activos/SAI-225_PO-_825_29-07-2025_16-20_3.las"
    ]
    
    print("🔍 ANÁLISIS DE PRESIÓN DE ZUNCHADO EN ARCHIVOS LAS")
    print("=" * 80)
    
    for archivo in archivos_a_analizar:
        if Path(archivo).exists():
            analizar_las_presion(archivo)
        else:
            print(f"❌ Archivo no encontrado: {archivo}")
    
    print(f"\n{'='*80}")
    print("✅ ANÁLISIS COMPLETADO")
