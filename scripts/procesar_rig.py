#!/usr/bin/env python3
import mysql.connector
import subprocess
import os
import logging
from datetime import datetime
from dotenv import load_dotenv # Importar la librería
from pathlib import Path # Para un manejo de rutas más moderno
import time # Para el reintento del worker

# Configuración del logging
# Es buena práctica configurar el logging al principio y solo una vez.
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s')
logger = logging.getLogger(__name__)

# ==========================================================================
# CARGAR CONFIGURACIONES Y RUTAS
# ==========================================================================
try:
    SCRIPT_DIR_ORCHESTRATOR = Path(__file__).resolve().parent
    PROJECT_ROOT_ORCHESTRATOR = SCRIPT_DIR_ORCHESTRATOR.parent
except NameError:
    SCRIPT_DIR_ORCHESTRATOR = Path(os.getcwd())
    PROJECT_ROOT_ORCHESTRATOR = SCRIPT_DIR_ORCHESTRATOR.parent if SCRIPT_DIR_ORCHESTRATOR.name.lower() == "scripts" else SCRIPT_DIR_ORCHESTRATOR
    logger.warning(f"__file__ no definido, usando CWD para SCRIPT_DIR_ORCHESTRATOR: {SCRIPT_DIR_ORCHESTRATOR}")

config_path = PROJECT_ROOT_ORCHESTRATOR / "config.env"

if config_path.exists():
    logger.info(f"Cargando configuraciones desde: {config_path}")
    load_dotenv(config_path)
else:
    logger.error(f"❌ El archivo de configuración {config_path} no existe.")
    exit(1) 

try:
    DB_HOST = os.getenv("DB_HOST")
    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_NAME = os.getenv("DB_NAME")
    VENV_PYTHON = os.getenv("VENV_PYTHON")
    SCRIPT_PATH_TO_CALL = os.getenv("SCRIPT_PATH")
    FINAL_LAS_OUTPUT_DIR_WORKER = os.getenv("RUTA_SALIDA_LAS")
    LOG_LEVEL_WORKER = os.getenv("LOG_LEVEL_WORKER", "INFO")
    ORCHESTRATOR_WORKER_RETRY_ATTEMPTS = int(os.getenv("ORCHESTRATOR_WORKER_RETRY_ATTEMPTS", "0"))

    essential_vars_check = {
        "DB_HOST": DB_HOST, "DB_USER": DB_USER, "DB_PASSWORD": DB_PASSWORD,
        "DB_NAME": DB_NAME, "VENV_PYTHON": VENV_PYTHON, "SCRIPT_PATH_TO_CALL": SCRIPT_PATH_TO_CALL
    }
    missing_vars_list = [name for name, value in essential_vars_check.items() if not value]
    if missing_vars_list:
        logger.error(f"❌ Faltan variables de configuración esenciales en {config_path} o entorno: {', '.join(missing_vars_list)}")
        # Usar un código de salida definido sería mejor aquí, pero para simplificar mantenemos exit(1)
        exit(1) 

except Exception as e:
    logger.error(f"❌ Error al leer o convertir variables de configuración: {e}")
    exit(1) 

if FINAL_LAS_OUTPUT_DIR_WORKER:
    if not os.path.isabs(FINAL_LAS_OUTPUT_DIR_WORKER):
        FINAL_LAS_OUTPUT_DIR_WORKER = str(PROJECT_ROOT_ORCHESTRATOR / FINAL_LAS_OUTPUT_DIR_WORKER)
    logger.info(f"El script worker guardará los LAS en: {FINAL_LAS_OUTPUT_DIR_WORKER}")
else:
    logger.warning(f"RUTA_SALIDA_LAS no definida en config.env. El script worker {os.path.basename(SCRIPT_PATH_TO_CALL) if SCRIPT_PATH_TO_CALL else ''} usará su directorio por defecto.")

logger.info(f"Configuraciones: DB_HOST={DB_HOST}, DB_USER={DB_USER}, DB_PASSWORD={'*' * len(DB_PASSWORD) if DB_PASSWORD else 'N/A'}, DB_NAME={DB_NAME}")
logger.info(f"Python del venv: {VENV_PYTHON}")
logger.info(f"Script de automatización a llamar: {SCRIPT_PATH_TO_CALL}")
logger.info(f"Nivel de log para el worker: {LOG_LEVEL_WORKER}")
logger.info(f"Reintentos (orquestador) para el worker: {ORCHESTRATOR_WORKER_RETRY_ATTEMPTS}")

if not SCRIPT_PATH_TO_CALL or not os.path.exists(SCRIPT_PATH_TO_CALL):
    logger.error(f"❌ La ruta al script de automatización '{SCRIPT_PATH_TO_CALL}' no es válida o no existe.")
    exit(1)
if not VENV_PYTHON or not os.path.exists(VENV_PYTHON):
    logger.error(f"❌ El ejecutable de Python del VENV '{VENV_PYTHON}' no es válido o no existe.")
    exit(1)

# ==========================================================================
# FUNCIÓN PARA GUARDAR EL ESTADO DEL PROCESO EN LA BASE DE DATOS
# ==========================================================================
def guardar_estado_proceso(nombre_script_worker, archivo_las, estado_descarga_param, mensaje_descarga_param):
    """
    Guarda el estado de la FASE DE DESCARGA en la tabla log_import_las.
    """
    db_logger = logging.getLogger(__name__ + ".db_save")
    conexion = None
    cursor = None
    
    estado_proc_interno_para_insert = None
    if estado_descarga_param == "Descarga Exitosa":
        estado_proc_interno_para_insert = "PENDIENTE"
    elif estado_descarga_param == "No Descargado - Fecha":
        estado_proc_interno_para_insert = "N/A (No Descarga)"
    else: 
        estado_proc_interno_para_insert = "N/A (Fallo Descarga)"

    try:
        conexion = mysql.connector.connect(
            host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME
        )
        cursor = conexion.cursor()
        
        # IMPORTANTE: Ajusta los nombres de las columnas 'estado' y 'fecha_descarga'
        # si los tienes diferentes en tu tabla log_import_las.
        query = """
            INSERT INTO log_import_las 
                (nombre_script, archivo_las, 
                 estado,                           -- Para el estado de la descarga
                 mensaje,                          -- Para el mensaje de la descarga
                 fecha_descarga,                   -- Fecha del evento de descarga (NOW())
                 estado_procesamiento_interno,     
                 mensaje_procesamiento_interno,    
                 fecha_procesamiento_interno     
                 )
            VALUES (%s, %s, %s, %s, NOW(), %s, NULL, NULL) 
        """
        cursor.execute(query, (
            nombre_script_worker,
            archivo_las,
            estado_descarga_param,        
            mensaje_descarga_param,       
            estado_proc_interno_para_insert 
        ))
        conexion.commit()
        log_msg_preview = mensaje_descarga_param.split('\n')[0]
        if len(log_msg_preview) > 150: log_msg_preview = log_msg_preview[:147] + "..."
        db_logger.info(f"Log de descarga para '{archivo_las if archivo_las != 'N/A' else log_msg_preview}' guardado: Descarga='{estado_descarga_param}', Proc. Interno='{estado_proc_interno_para_insert}'")
    except Exception as e:
        db_logger.error(f"Error al guardar el estado del proceso en BD: {e}", exc_info=True)
    finally:
        if cursor:
            cursor.close()
        if conexion and conexion.is_connected():
            conexion.close()

# ==========================================================================
# CONECTAR A MARIADB Y OBTENER DATOS DE RIGS
# ==========================================================================
rigs_contractors = []
try:
    with mysql.connector.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME
    ) as conn:
        with conn.cursor(dictionary=True) as cursor:
            # QUERY CORREGIDA: Eliminadas las condiciones r.activo y rc.activo
            query_str = """
                SELECT wd.contractor, wd.rig, r.name AS rig_name_db, wd.well_name, r.rig_type
                FROM well_data wd
                JOIN rigs_autom r ON wd.rig = r.alias OR wd.rig = r.name 
                JOIN rigs_contractors_autom rc ON wd.contractor = rc.alias OR wd.contractor = rc.name
                WHERE wd.import_datetime = (SELECT MAX(import_datetime) FROM well_data)
                  AND wd.status <> 'HISTORIC';
            """
            cursor.execute(query_str)
            rigs_contractors_raw = cursor.fetchall()
            
            for row in rigs_contractors_raw:
                rigs_contractors.append((
                    row["contractor"], row["rig"], row["rig_name_db"],
                    row["well_name"], row["rig_type"]
                ))
    if not rigs_contractors:
        logger.warning("No se encontraron datos de rigs activos para procesar en la base de datos.")
        # Usar códigos de salida definidos al principio del script
        exit(0) # EXIT_CODE_SUCCESS podría ser apropiado si no hay trabajo que hacer.
    logger.info(f"✅ Se encontraron {len(rigs_contractors)} combinaciones de Contractor y Rig para procesar.")
except mysql.connector.Error as err:
    logger.error(f"Error de conexión a la base de datos: {err}")
    exit(1) # EXIT_CODE_DB_ERROR o similar
except Exception as e:
    logger.error(f"Error inesperado al obtener datos de la base de datos: {e}", exc_info=True)
    exit(1) # EXIT_CODE_GENERAL_ERROR o similar

# ==========================================================================
# PROCESAR CADA COMBINACIÓN
# ==========================================================================
script_worker_basename = os.path.basename(SCRIPT_PATH_TO_CALL) if SCRIPT_PATH_TO_CALL else "worker_script_desconocido"
stats = {
    "descarga_exitosa_pendiente_proc": 0, 
    "no_descargado_fecha": 0, 
    "fallo_descarga_worker": 0, 
    "error_orquestador": 0, 
    "reintentos_worker_exitosos": 0
}

for contractor, rig_alias_web, rig_name_file, well_name_file, rig_type_param in rigs_contractors:
    log_prefix = f"Contractor='{contractor}', Rig='{rig_alias_web}', Well='{well_name_file}'"
    logger.info(f"🚀 Iniciando procesamiento para: {log_prefix}, RigNameFile='{rig_name_file}', RigType='{rig_type_param}'")
    
    intentos_realizados = 0
    max_intentos_para_worker = 1 + ORCHESTRATOR_WORKER_RETRY_ATTEMPTS

    estado_descarga_final_rig = "Error Indeterminado Orquestador"
    mensaje_descarga_final_rig = f"Error inicial procesando {log_prefix}."
    archivo_las_final_rig = "N/A"

    while intentos_realizados < max_intentos_para_worker:
        intentos_realizados += 1
        if intentos_realizados > 1:
            logger.info(f"Reintento de descarga {intentos_realizados - 1}/{ORCHESTRATOR_WORKER_RETRY_ATTEMPTS} para {log_prefix}")

        estado_intento_actual = "Error Worker (default)" 
        mensaje_intento_actual = f"Salida no reconocida o error en {script_worker_basename} para {log_prefix} (Intento {intentos_realizados})."
        archivo_las_intento_actual = "N/A"

        try:
            comando = [
                VENV_PYTHON, SCRIPT_PATH_TO_CALL, 
                contractor, rig_alias_web, rig_name_file, well_name_file, rig_type_param,
                "--log-level", LOG_LEVEL_WORKER 
            ]
            if FINAL_LAS_OUTPUT_DIR_WORKER:
                comando.extend(["--las-output-dir", FINAL_LAS_OUTPUT_DIR_WORKER])
            
            logger.debug(f"Ejecutando comando (intento {intentos_realizados}): {' '.join(comando)}")
            result = subprocess.run(
                comando, capture_output=True, text=True, check=False, encoding='utf-8'
            )

            output_stdout = result.stdout.strip() if result.stdout else ""
            output_stderr = result.stderr.strip() if result.stderr else ""
            
            if output_stdout:
                logger.info(f"Salida STDOUT de {script_worker_basename} para {log_prefix} (Intento {intentos_realizados}):\n{output_stdout}")
                ultima_linea_archivo_las = ""
                for line in reversed(output_stdout.splitlines()):
                    if line.startswith("ARCHIVO_LAS:"):
                        ultima_linea_archivo_las = line
                        break
                
                if ultima_linea_archivo_las:
                    parts = ultima_linea_archivo_las.split(":", 2)
                    status_o_nombre = parts[1].strip()
                    info_adicional = parts[2].strip() if len(parts) > 2 else ""

                    if status_o_nombre == "NO_DOWNLOAD_MIN_DATE_TOO_RECENT":
                        estado_intento_actual = "No Descargado - Fecha"
                        mensaje_intento_actual = f"Razón: {status_o_nombre} para {info_adicional if info_adicional else log_prefix}."
                        archivo_las_intento_actual = "N/A"
                    elif status_o_nombre == "FALLO_DESCARGA":
                        estado_intento_actual = "Fallo Descarga (Worker)"
                        mensaje_intento_actual = f"Script worker reportó {status_o_nombre} para {info_adicional if info_adicional else log_prefix}."
                        archivo_las_intento_actual = "N/A"
                    else: 
                        archivo_las_intento_actual = status_o_nombre
                        estado_intento_actual = "Descarga Exitosa" 
                        mensaje_intento_actual = f"Descarga LAS completada para {log_prefix}. Archivo: {archivo_las_intento_actual}"
                else:
                     mensaje_intento_actual = f"No se encontró la línea ARCHIVO_LAS en la salida para {log_prefix} (Intento {intentos_realizados})."
                     estado_intento_actual = "Error Worker - Sin Salida Esperada"
            
            if result.returncode != 0:
                logging.error(f"El script {script_worker_basename} para {log_prefix} (Intento {intentos_realizados}) finalizó con código de error: {result.returncode}.")
                if estado_intento_actual not in ["No Descargado - Fecha", "Fallo Descarga (Worker)"]:
                    estado_intento_actual = "Error Worker (RC no cero)"
                
                if output_stderr:
                    logging.error(f"Salida STDERR de {script_worker_basename} para {log_prefix} (Intento {intentos_realizados}):\n{output_stderr}")
                    mensaje_intento_actual += f" (RC: {result.returncode}. Stderr: {output_stderr})"
                else:
                     mensaje_intento_actual += f" (RC: {result.returncode})"
            
            estado_descarga_final_rig = estado_intento_actual
            mensaje_descarga_final_rig = mensaje_intento_actual
            archivo_las_final_rig = archivo_las_intento_actual

            if estado_descarga_final_rig == "Descarga Exitosa" or estado_descarga_final_rig == "No Descargado - Fecha":
                if intentos_realizados > 1 and estado_descarga_final_rig == "Descarga Exitosa":
                    stats["reintentos_worker_exitosos"] += 1
                break 
            elif intentos_realizados >= max_intentos_para_worker: 
                logging.error(f"Todos los {max_intentos_para_worker} intentos de descarga fallaron para {log_prefix}.")
                break 
            else: 
                logging.warning(f"Fallo de descarga para {log_prefix} (Intento {intentos_realizados}). Esperando 5s para reintentar...")
                time.sleep(5)

        except FileNotFoundError as fnf_error: 
            mensaje_descarga_final_rig = f"Error Crítico: No se encontró ejecutable '{VENV_PYTHON}' o script '{SCRIPT_PATH_TO_CALL}'. Detalles: {fnf_error}"
            logging.error(mensaje_descarga_final_rig)
            estado_descarga_final_rig = "Error Crítico Orquestador"
            archivo_las_final_rig = "N/A"
            break 
        except Exception as e: 
            mensaje_descarga_final_rig = f"Error inesperado en orquestador al procesar {log_prefix} (Intento {intentos_realizados}): {e}"
            logging.error(mensaje_descarga_final_rig, exc_info=True)
            estado_descarga_final_rig = "Error Orquestador"
            archivo_las_final_rig = "N/A"
            if intentos_realizados >= max_intentos_para_worker:
                break 
            else:
                time.sleep(5)

    if estado_descarga_final_rig == "Descarga Exitosa":
        stats["descarga_exitosa_pendiente_proc"] += 1
    elif estado_descarga_final_rig == "No Descargado - Fecha":
        stats["no_descargado_fecha"] += 1
    elif estado_descarga_final_rig.startswith("Fallo Descarga (Worker)") or estado_descarga_final_rig.startswith("Error Worker"):
        stats["fallo_descarga_worker"] += 1
    else: 
        stats["error_orquestador"] += 1
        
    guardar_estado_proceso(
        nombre_script_worker=script_worker_basename,
        archivo_las=archivo_las_final_rig,
        estado_descarga_param=estado_descarga_final_rig, 
        mensaje_descarga_param=mensaje_descarga_final_rig
    )

logging.info("🎉 Finalizado el procesamiento de descargas de equipos.")
logging.info("Resumen de la fase de DESCargas:")
logging.info(f"  Total Rigs Procesados: {len(rigs_contractors)}")
logging.info(f"  Descargas Exitosas (Pendientes de Procesamiento Interno): {stats['descarga_exitosa_pendiente_proc']}")
logging.info(f"  No Descargados (por fecha/lógica): {stats['no_descargado_fecha']}")
logging.info(f"  Descargas Exitosas después de reintento: {stats['reintentos_worker_exitosos']}")
logging.info(f"  Fallos de Descarga (Worker): {stats['fallo_descarga_worker']}")
logging.info(f"  Fallos (Orquestador/Críticos): {stats['error_orquestador']}")

# Códigos de Salida definidos al principio del script
EXIT_CODE_SUCCESS = 0
EXIT_CODE_GENERAL_ERROR = 1
# EXIT_CODE_CONFIG_ERROR = 2 (No se usa explícitamente aquí, pero se podría)
# EXIT_CODE_DB_ERROR = ? (Podrías definir uno si la conexión a BD falla)

if __name__ == "__main__":
    final_exit_code = EXIT_CODE_SUCCESS 
    if stats['fallo_descarga_worker'] > 0 or stats['error_orquestador'] > 0:
        final_exit_code = EXIT_CODE_GENERAL_ERROR 
    
    logging.info(f"Procesar_rig.py finalizado con código: {final_exit_code}")
    exit(final_exit_code)