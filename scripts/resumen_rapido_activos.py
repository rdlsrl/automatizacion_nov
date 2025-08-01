#!/usr/bin/env python3
"""
Script para hacer un resumen rápido de todos los archivos LAS activos
sin procesamiento completo - solo para ver el estado general
"""

import os
import logging
from pathlib import Path
import lasio
from collections import Counter

# Configurar logging básico
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def resumen_rapido_activos():
    """Hace un resumen rápido de todos los archivos LAS sin procesamiento completo."""
    
    logger.info("🚀 RESUMEN RÁPIDO - ARCHIVOS LAS ACTIVOS")
    logger.info("=" * 60)
    
    # Directorio de archivos LAS
    directorio_las = Path("/mnt/mariadb/autom_nov/data/las/activos")
    archivos_las = list(directorio_las.glob("*.las"))
    
    logger.info(f"📁 Directorio: {directorio_las}")
    logger.info(f"📊 Total archivos encontrados: {len(archivos_las)}")
    
    if not archivos_las:
        logger.error("❌ No se encontraron archivos LAS")
        return
    
    # Estadísticas generales
    total_archivos = len(archivos_las)
    archivos_procesados = 0
    archivos_con_error = 0
    total_curvas = 0
    
    # Contadores de unidades más comunes
    unidades_encontradas = Counter()
    
    logger.info("\n🔍 ANALIZANDO ARCHIVOS (MUESTRA RÁPIDA)...")
    logger.info("-" * 50)
    
    for i, archivo_las in enumerate(archivos_las[:10], 1):  # Solo primeros 10 para ser rápido
        try:
            logger.info(f"\n📋 {i:2d}/10: {archivo_las.name}")
            
            # Cargar archivo LAS
            las_obj = lasio.read(str(archivo_las), encoding='utf-8-sig')
            num_curvas = len(las_obj.curves)
            total_curvas += num_curvas
            
            logger.info(f"   📊 Curvas: {num_curvas}")
            
            # Recopilar unidades (solo primeras 20 curvas para ser rápido)
            for curve in las_obj.curves[:20]:
                if curve.unit and curve.unit.strip():
                    unidades_encontradas[curve.unit] += 1
            
            archivos_procesados += 1
            
        except Exception as e:
            logger.error(f"   ❌ Error: {str(e)[:100]}...")
            archivos_con_error += 1
    
    # Estadísticas del resto de archivos (solo conteo rápido)
    logger.info(f"\n📈 CONTANDO ARCHIVOS RESTANTES...")
    archivos_restantes = len(archivos_las) - 10
    if archivos_restantes > 0:
        logger.info(f"   📁 Archivos restantes sin análisis detallado: {archivos_restantes}")
    
    # Resumen final
    logger.info("\n" + "=" * 60)
    logger.info("📋 RESUMEN FINAL:")
    logger.info(f"   📊 Total archivos LAS: {total_archivos}")
    logger.info(f"   ✅ Analizados (muestra): {archivos_procesados}/10")
    logger.info(f"   ❌ Con errores: {archivos_con_error}")
    logger.info(f"   📈 Total curvas (muestra): {total_curvas}")
    
    if unidades_encontradas:
        logger.info(f"\n🏷️  TOP 10 UNIDADES MÁS COMUNES:")
        for unidad, cantidad in unidades_encontradas.most_common(10):
            logger.info(f"   • '{unidad}': {cantidad} veces")
    
    logger.info("\n💡 RECOMENDACIÓN:")
    if archivos_con_error == 0:
        logger.info("   ✅ Todos los archivos se pueden leer correctamente")
        logger.info("   🚀 Listo para procesamiento completo con 'procesar_todos_activos.py'")
    else:
        logger.info(f"   ⚠️  {archivos_con_error} archivos tienen problemas de lectura")
        logger.info("   🔧 Revisar archivos con errores antes del procesamiento completo")

if __name__ == "__main__":
    resumen_rapido_activos()
