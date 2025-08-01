#!/usr/bin/env python3
# gestor_procesamiento_las.py
import os
import sys
import logging
import argparse
from datetime import datetime
from sqlalchemy import DateTime, TEXT
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import Column, Integer, String, create_engine, update
from sqlalchemy.orm import sessionmaker, declarative_base

# Importar la función de procesamiento y los modelos necesarios
try:
    from procesamiento_las import procesar_un_solo_las, FilesImport, LogImportLas
except ImportError as e:
    logging.basicConfig(level=logging.ERROR)
    logging.error(f"Error al importar desde procesamiento_las.py: {e}.")
    sys.exit(1)


# ==========================================================================
# CONFIGURACIÓN INICIAL
# ==========================================================================
# Configuración del logging para este script gestor
# (Podrías mover la configuración de logging a un módulo común si tienes muchos scripts)
LOG_DIR_GESTOR = Path(os.getenv("LOGS_DIR_GESTOR", Path(__file__).resolve().parent.parent / "logs")) # Tomar de .env o default
LOG_DIR_GESTOR.mkdir(parents=True, exist_ok=True)
LOG_FILE_NAME_GESTOR = LOG_DIR_GESTOR / f"{Path(__file__).stem}.log"

logger_gestor_root = logging.getLogger() # Obtener el logger raíz
# Asegurar que el nivel del logger raíz sea el más bajo que se quiera manejar (ej. DEBUG)
# para que los handlers puedan filtrar más específicamente.
# El nivel aquí no debe ser más alto que el nivel de los handlers.
logger_gestor_root.setLevel(logging.DEBUG) 

# Remover handlers previos si los hay para evitar duplicación
for handler in logger_gestor_root.handlers[:]:
    logger_gestor_root.removeHandler(handler)

formatter_gestor = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s')

# Handler para archivo con rotación para el gestor
# (Asumiendo que quieres RotatingFileHandler aquí también, o puedes usar FileHandler)
from logging.handlers import RotatingFileHandler
file_handler_gestor = RotatingFileHandler(LOG_FILE_NAME_GESTOR, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
file_handler_gestor.setFormatter(formatter_gestor)
file_handler_gestor.setLevel(logging.INFO) # Nivel para el archivo de log del gestor
logger_gestor_root.addHandler(file_handler_gestor)

# Handler para consola para el gestor
console_handler_gestor = logging.StreamHandler(sys.stdout)
console_handler_gestor.setFormatter(formatter_gestor)
console_handler_gestor.setLevel(logging.INFO) # Nivel para la consola del gestor
logger_gestor_root.addHandler(console_handler_gestor)

logger = logging.getLogger(__name__) # Logger específico para este módulo gestor

# Cargar configuración de .env
# Asumimos que config.env está en el directorio padre del directorio de este script
try:
    SCRIPT_DIR_GESTOR = Path(__file__).resolve().parent
    PROJECT_ROOT_GESTOR = SCRIPT_DIR_GESTOR.parent 
except NameError: # Fallback si __file__ no está definido
    SCRIPT_DIR_GESTOR = Path(os.getcwd())
    PROJECT_ROOT_GESTOR = SCRIPT_DIR_GESTOR.parent if SCRIPT_DIR_GESTOR.name.lower() == "scripts" else SCRIPT_DIR_GESTOR

config_path_gestor = PROJECT_ROOT_GESTOR / "config.env"

if config_path_gestor.exists():
    logger.info(f"Cargando configuraciones desde: {config_path_gestor}")
    load_dotenv(config_path_gestor)
else:
    logger.error(f"❌ El archivo de configuración {config_path_gestor} no existe.")
    sys.exit(1)

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
DB_PORT = os.getenv("DB_PORT", "3306")

# Ruta donde procesar_rig.py (el descargador) guarda los archivos LAS
# Esta ruta se pasará como argumento al script
RUTA_LAS_PENDIENTES = os.getenv("RUTA_SALIDA_LAS", "/mnt/mariadb/autom_nov/data/las/activos") # Fallback por defecto

if not all([DB_HOST, DB_USER, DB_PASSWORD, DB_NAME]):
    logger.critical("Faltan variables de configuración de base de datos en .env. Saliendo.")
    sys.exit(1)

logger.info(f"Configuración de BD: {DB_HOST}:{DB_PORT}/{DB_NAME} (Usuario: {DB_USER})")


DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URL, echo=False) # echo=False para producción
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base para los modelos
Base = declarative_base()

# ==========================================================================
# SCRIPT PRINCIPAL DEL GESTOR
# ==========================================================================
def main_gestor(directorio_las_base: str):
    logger.info("--- Iniciando Gestor de Procesamiento de Archivos LAS ---")
    logger.info(f"Directorio base de archivos LAS: {directorio_las_base}")
    
    db_session = SessionLocal()
    archivos_procesados_en_sesion = 0
    archivos_fallidos_en_sesion = 0

    try:
        logger.info("Buscando archivos LAS pendientes de procesamiento en log_import_las...")
        
        # Usar el modelo LogImportLas importado de procesamiento_las.py
        pendientes = db_session.query(LogImportLas).filter(
            LogImportLas.estado == "Descarga Exitosa",
            LogImportLas.estado_procesamiento_interno.in_(["PENDIENTE", None])
        ).all()

        if not pendientes:
            logger.info("No hay archivos LAS pendientes de procesamiento en este momento.")
            return

        logger.info(f"Se encontraron {len(pendientes)} archivos LAS pendientes.")

        for log_entry in pendientes:
            # Construir ruta completa del archivo
            filepath_completa = os.path.join(directorio_las_base, log_entry.archivo_las)
            logger.info(f"--- Iniciando procesamiento para: {log_entry.archivo_las} (ID Log: {log_entry.id}) ---")
            
            # Verificar que el archivo existe
            if not os.path.exists(filepath_completa):
                logger.error(f"Archivo no encontrado: {filepath_completa}")
                log_entry.estado_procesamiento_interno = "ERROR_ARCHIVO_NO_ENCONTRADO"
                log_entry.mensaje_procesamiento_interno = f"Archivo físico no encontrado en {filepath_completa}"
                log_entry.fecha_procesamiento_interno = datetime.now()
                archivos_fallidos_en_sesion += 1
                db_session.commit()
                continue
            
            # Marcar como "PROCESANDO"
            try:
                log_entry.estado_procesamiento_interno = "PROCESANDO"
                log_entry.fecha_procesamiento_interno = datetime.now()
                db_session.commit()
            except Exception as e_update_proc:
                logger.error(f"Error al actualizar estado a PROCESANDO para log ID {log_entry.id}: {e_update_proc}")
                db_session.rollback()
                continue

            # Llamar a la función de procesamiento principal
            try:
                exito_proc, mensaje_proc, well_id, well_name, rig_id, rig_name, event_id = procesar_un_solo_las(
                    filepath_completa, db_session
                )
            except Exception as e_proc:
                logger.error(f"Excepción durante procesar_un_solo_las para {log_entry.archivo_las}: {e_proc}", exc_info=True)
                exito_proc = False
                mensaje_proc = f"Excepción: {str(e_proc)}"
            
            # Actualizar el log con el resultado del procesamiento
            if exito_proc:
                log_entry.estado_procesamiento_interno = "PROCESADO_OK"
                log_entry.mensaje_procesamiento_interno = mensaje_proc
                archivos_procesados_en_sesion += 1
                logger.info(f"Procesamiento de '{log_entry.archivo_las}' completado exitosamente.")
            else:
                log_entry.estado_procesamiento_interno = "ERROR_PROCESAMIENTO"
                log_entry.mensaje_procesamiento_interno = mensaje_proc[:1000]  # Truncar si es muy largo
                archivos_fallidos_en_sesion += 1
                logger.error(f"Error durante el procesamiento de '{log_entry.archivo_las}': {mensaje_proc}")
            
            log_entry.fecha_procesamiento_interno = datetime.now()
            try:
                db_session.commit()
            except Exception as e_commit_final:
                logger.error(f"Error al hacer commit final para log ID {log_entry.id}: {e_commit_final}")
                db_session.rollback()
    
    except Exception as e:
        logger.error(f"Error general en el gestor de procesamiento: {e}", exc_info=True)
        if db_session:
            db_session.rollback()
    finally:
        if db_session:
            db_session.close()
        logger.info("--- Gestor de Procesamiento Finalizado ---")
        logger.info(f"Resumen: Procesados OK = {archivos_procesados_en_sesion}, Fallidos = {archivos_fallidos_en_sesion}")

if __name__ == "__main__":
    # Configuración de argumentos
    parser = argparse.ArgumentParser(description="Gestor que procesa archivos LAS pendientes desde log_import_las")
    parser.add_argument(
        "directorio_las_base", 
        type=str, 
        help="Ruta al directorio base donde se encuentran los archivos LAS"
    )
    args = parser.parse_args()
    
    main_gestor(args.directorio_las_base)