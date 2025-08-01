#!/usr/bin/env python3
"""
Script para procesar todos los archivos LAS de la carpeta activos
usando el sistema manejador_curves_las.py corregido
"""

import os
import sys
from pathlib import Path
import logging

# Agregar el directorio de scripts al path
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_DIR))

# Importar el sistema principal
from manejador_curves_las import *

def procesar_carpeta_activos():
    """Procesa todos los archivos LAS de la carpeta activos"""
    
    # Configurar logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    logger.info("=== PROCESAMIENTO MASIVO DE ARCHIVOS LAS ACTIVOS ===")
    
    # Ruta de la carpeta activos
    carpeta_activos = Path(__file__).parent.parent / "data" / "las" / "activos"
    
    if not carpeta_activos.exists():
        logger.error(f"Carpeta no encontrada: {carpeta_activos}")
        return
    
    # Obtener todos los archivos LAS
    archivos_las = list(carpeta_activos.glob("*.las"))
    logger.info(f"Encontrados {len(archivos_las)} archivos LAS")
    
    if not archivos_las:
        logger.warning("No se encontraron archivos LAS en la carpeta")
        return
    
    # Configurar sesión de BD
    if not SessionLocal:
        logger.error("No se pudo configurar la sesión de base de datos")
        return
    
    # Contadores
    procesados_exitosos = 0
    errores = 0
    
    # Procesar cada archivo
    for i, archivo_las in enumerate(archivos_las, 1):
        logger.info(f"\n--- PROCESANDO {i}/{len(archivos_las)}: {archivo_las.name} ---")
        
        try:
            # Intentar cargar el archivo LAS
            las_obj = None
            for enc in ['utf-8-sig', 'utf-8', 'latin1', 'cp1252']:
                try:
                    las_obj = lasio.read(str(archivo_las), encoding=enc)
                    logger.info(f"✅ Archivo cargado con encoding: {enc}")
                    break
                except Exception as e:
                    continue
            
            if las_obj is None:
                logger.error(f"❌ No se pudo cargar el archivo {archivo_las.name}")
                errores += 1
                continue
            
            # ID ficticio para files_import (usaremos el índice)
            id_files_import = i + 1000  # Para evitar conflictos
            rig_id = 97  # Usamos el rig 97 que tiene configuraciones
            
            logger.info(f"📊 Curvas encontradas: {len(las_obj.curves)}")
            
            # Procesar las curvas usando la función del manejador
            with SessionLocal() as db:
                resultados = procesar_y_registrar_curvas_de_un_las(
                    db=db,
                    las_file_obj=las_obj,
                    id_files_import_actual=id_files_import,
                    rig_id_actual=rig_id
                )
            
            if resultados and resultados.get('total_curvas', 0) > 0:
                total_curvas = resultados['total_curvas']
                mapeadas = resultados.get('curvas_mapeadas', 0)
                logger.info(f"✅ {archivo_las.name} procesado exitosamente")
                logger.info(f"   📊 Total curvas: {total_curvas}, Mapeadas: {mapeadas}")
                procesados_exitosos += 1
            else:
                logger.error(f"❌ Error procesando {archivo_las.name} - sin resultados")
                errores += 1
                
        except Exception as e:
            logger.error(f"❌ Excepción procesando {archivo_las.name}: {e}")
            errores += 1
    
    # Resumen final
    logger.info(f"\n🎉 RESUMEN FINAL:")
    logger.info(f"   Total archivos: {len(archivos_las)}")
    logger.info(f"   ✅ Exitosos: {procesados_exitosos}")
    logger.info(f"   ❌ Errores: {errores}")
    logger.info(f"   📈 Tasa éxito: {(procesados_exitosos/len(archivos_las)*100):.1f}%")

if __name__ == "__main__":
    procesar_carpeta_activos()
