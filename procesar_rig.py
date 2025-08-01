import mysql.connector
import subprocess
import os
import logging
from datetime import datetime
from dotenv import load_dotenv # Importar la librería

# Configuración del logging
# Es buena práctica configurar el logging al principio y solo una vez.
# Si otros módulos importados también configuran logging, podría haber interacciones.
# Para un script principal, esto está bien.
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s')
logger = logging.getLogger(__name__) # Usar un logger específico para este módulo

# ==========================================================================
# CARGAR CONFIGURACIONES Y RUTAS
# ==========================================================================
try:
    SCRIPT_DIR_ORCHESTRATOR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT_ORCHESTRATOR = os.path.dirname(SCRIPT_DIR_ORCHESTRATOR)
except NameError: 
    SCRIPT_DIR_ORCHESTRATOR = os.getcwd()
    PROJECT_ROOT_ORCHESTRATOR = os.path.dirname(SCRIPT_DIR_ORCHESTRATOR)
    logger.warning(f"__file__ no definido, usando CWD para SCRIPT_DIR_ORCHESTRATOR: {SCRIPT_DIR_ORCHESTRATOR}")

config_path = os.path.join(PROJECT_ROOT_ORCHESTRATOR, "config.env")

if os.path.exists(config_path):
    logger.info(f"Cargando configuraciones desde: {config_path}")
    load_dotenv(config_path) # Carga variables de .env al entorno del OS
else:
    logger.error(f"❌ El archivo de configuración {config_path} no existe.")
    exit(1)

# Leer variables del entorno (cargadas desde .env o ya existentes)
try:
    DB_HOST = os.getenv("DB_HOST")
    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_NAME = os.getenv("DB_NAME")
    VENV_PYTHON = os.getenv("VENV_PYTHON")
    
    # SCRIPT_PATH_FROM_ENV es la ruta completa al script worker
    SCRIPT_PATH_TO_CALL = os.getenv("SCRIPT_PATH") 
    
    # RUTA_SALIDA_LAS es la ruta donde el worker debe guardar los archivos
    FINAL_LAS_OUTPUT_DIR_WORKER = os.getenv("RUTA_SALIDA_LAS")

    LOG_LEVEL_WORKER = os.getenv("LOG_LEVEL_WORKER", "INFO") 
    ORCHESTRATOR_WORKER_RETRY_ATTEMPTS = int(os.getenv("ORCHESTRATOR_WORKER_RETRY_ATTEMPTS", "0"))

    # Validar variables esenciales
    essential_vars = {
        "DB_HOST": DB_HOST, "DB_USER": DB_USER, "DB_PASSWORD": DB_PASSWORD, 
        "DB_NAME": DB_NAME, "VENV_PYTHON": VENV_PYTHON, "SCRIPT_PATH_TO_CALL": SCRIPT_PATH_TO_CALL
    }
    missing_vars = [name for name, value in essential_vars.items() if not value]
    if missing_vars:
        logger.error(f"❌ Faltan variables de configuración esenciales en {config_path} o entorno: {', '.join(missing_vars)}")
        exit(1)

except Exception as e:
    logger.error(f"❌ Error al leer o convertir variables de configuración: {e}")
    exit(1)

if FINAL_LAS_OUTPUT_DIR_WORKER:
    # Asegurar que la ruta sea absoluta (si no lo es, asumirla relativa al proyecto)
    if not os.path.isabs(FINAL_LAS_OUTPUT_DIR_WORKER):
        FINAL_LAS_OUTPUT_DIR_WORKER = os.path.join(PROJECT_ROOT_ORCHESTRATOR, FINAL_LAS_OUTPUT_DIR_WORKER)
    logger.info(f"El script worker guardará los LAS en: {FINAL_LAS_OUTPUT_DIR_WORKER}")
else:
    logger.warning(f"RUTA_SALIDA_LAS no definida en config.env. El script worker usará su directorio por defecto.")

logger.info(f"Configuraciones: DB_HOST={DB_HOST}, DB_USER={DB_USER}, DB_PASSWORD={'*' * len(DB_PASSWORD) if DB_PASSWORD else 'N/A'}, DB_NAME={DB_NAME}")
logger.info(f"Python del venv: {VENV_PYTHON}")
logger.info(f"Script de automatización a llamar: {SCRIPT_PATH_TO_CALL}")
logger.info(f"Nivel de log para el worker: {LOG_LEVEL_WORKER}")
logger.info(f"Reintentos (orquestador) para el worker: {ORCHESTRATOR_WORKER_RETRY_ATTEMPTS}")

if not os.path.exists(SCRIPT_PATH_TO_CALL):
    logger.error(f"❌ El script de automatización no existe en la ruta: {SCRIPT_PATH_TO_CALL}")
    exit(1)
if not os.path.exists(VENV_PYTHON):
    logger.error(f"❌ El ejecutable de Python del VENV no existe en la ruta: {VENV_PYTHON}")
    exit(1)

# ==========================================================================
# FUNCIÓN PARA GUARDAR EL ESTADO DEL PROCESO EN LA BASE DE DATOS
# ==========================================================================
def guardar_estado_proceso(nombre_script_worker, archivo_las, estado, mensaje):
    """Guarda el estado del proceso en la tabla de logs de la base de datos."""
    try:
        # Usar un nuevo logger para esta función para evitar confusión si el logger global cambia
        db_logger = logging.getLogger(__name__ + ".db")
        conexion = mysql.connector.connect(
            host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME
        )
        cursor = conexion.cursor()
        query = """
            INSERT INTO log_import_las (nombre_script, archivo_las, estado, mensaje, fecha)
            VALUES (%s, %s, %s, %s, NOW())
        """
        cursor.execute(query, (nombre_script_worker, archivo_las, estado, mensaje))
        conexion.commit()
        db_logger.info(f"Estado para '{archivo_las if archivo_las != 'N/A' else mensaje.split(':')[0]}' guardado en BD: {estado}")
    except Exception as e:
        db_logger.error(f"Error al guardar el estado del proceso en BD: {e}")
    finally:
        if 'conexion' in locals() and conexion.is_connected():
            if 'cursor' in locals() and cursor:
                cursor.close()
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
            query_str = """
                SELECT wd.contractor, wd.rig, r.name AS rig_name_db, wd.well_name, r.rig_type
                FROM well_data wd
                JOIN rigs_autom r ON wd.rig = r.alias OR wd.rig = r.name 
                JOIN rigs_contractors_autom rc ON wd.contractor = rc.alias OR wd.contractor = rc.name
                WHERE wd.import_datetime = (SELECT MAX(import_datetime) FROM well_data)
                  AND wd.status <> 'HISTORIC'
                  AND r.activo = 1 
                  AND rc.activo = 1;
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
        exit(0)
    logger.info(f"✅ Se encontraron {len(rigs_contractors)} combinaciones de Contractor y Rig para procesar.")
except mysql.connector.Error as err:
    logger.error(f"Error de conexión a la base de datos: {err}")
    exit(1)
except Exception as e:
    logger.error(f"Error inesperado al obtener datos de la base de datos: {e}", exc_info=True)
    exit(1)

# ==========================================================================
# PROCESAR CADA COMBINACIÓN
# ==========================================================================
script_worker_basename = os.path.basename(SCRIPT_PATH_TO_CALL)
stats = {"exito": 0, "no_descargado": 0, "error_script_worker": 0, "error_orquestador": 0, "reintentos_worker_exitosos": 0}

for contractor, rig_alias_web, rig_name_file, well_name_file, rig_type_param in rigs_contractors:
    log_prefix = f"Contractor='{contractor}', Rig='{rig_alias_web}', Well='{well_name_file}'"
    logger.info(f"🚀 Iniciando procesamiento para: {log_prefix}, RigNameFile='{rig_name_file}', RigType='{rig_type_param}'")
    
    intentos_realizados = 0
    max_intentos_para_worker = 1 + ORCHESTRATOR_WORKER_RETRY_ATTEMPTS

    # Loop de reintentos para el worker actual
    while intentos_realizados < max_intentos_para_worker:
        intentos_realizados += 1
        if intentos_realizados > 1:
            logger.info(f"Reintento {intentos_realizados - 1}/{ORCHESTRATOR_WORKER_RETRY_ATTEMPTS} para {log_prefix}")

        # Estado por defecto para esta iteración/reintento
        estado_proceso_intento = "Error Indeterminado"
        mensaje_detalle_intento = f"Salida no reconocida o error en {script_worker_basename} para {log_prefix} (Intento {intentos_realizados})."
        archivo_las_obtenido_intento = "N/A"

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
                        estado_proceso_intento = "No Descargado"
                        mensaje_detalle_intento = f"Razón: {status_o_nombre} para {info_adicional if info_adicional else log_prefix}."
                    elif status_o_nombre == "FALLO_DESCARGA":
                        estado_proceso_intento = "Error Script Worker"
                        mensaje_detalle_intento = f"Script worker reportó fallo para {info_adicional if info_adicional else log_prefix}."
                    else: 
                        archivo_las_obtenido_intento = status_o_nombre
                        estado_proceso_intento = "Éxito"
                        mensaje_detalle_intento = f"Procesamiento completado para {log_prefix}."
                else:
                     mensaje_detalle_intento = f"No se encontró la línea ARCHIVO_LAS en la salida para {log_prefix} (Intento {intentos_realizados})."
            
            if result.returncode != 0:
                logging.error(f"El script {script_worker_basename} para {log_prefix} (Intento {intentos_realizados}) finalizó con código de error: {result.returncode}.")
                if estado_proceso_intento == "Éxito": 
                    estado_proceso_intento = "Error Worker Inesperado" # Corregir estado si parecía éxito
                elif estado_proceso_intento == "Error Indeterminado" and not output_stdout and not output_stderr:
                     mensaje_detalle_intento = f"Script worker finalizó con RC: {result.returncode} sin salida stdout/stderr para {log_prefix}."

                if output_stderr:
                    logging.error(f"Salida STDERR de {script_worker_basename} para {log_prefix} (Intento {intentos_realizados}):\n{output_stderr}")
                    mensaje_detalle_intento += f" (RC: {result.returncode}. Stderr: {output_stderr})"
                else:
                     mensaje_detalle_intento += f" (RC: {result.returncode})"
            
            # Decidir si salir del bucle de reintentos
            if estado_proceso_intento == "Éxito" or estado_proceso_intento == "No Descargado":
                if intentos_realizados > 1 and estado_proceso_intento == "Éxito":
                    stats["reintentos_worker_exitosos"] += 1
                break # Salir del bucle de reintentos para este rig
            elif intentos_realizados >= max_intentos_para_worker: # Último intento fallido
                logging.error(f"Todos los {max_intentos_para_worker} intentos fallaron para {log_prefix}.")
                break # Salir del bucle de reintentos
            else: # Error y quedan reintentos
                logging.warning(f"Fallo para {log_prefix} (Intento {intentos_realizados}). Esperando 5s para reintentar...")
                time.sleep(5)

        except FileNotFoundError as fnf_error: # Error al intentar ejecutar el subproceso
            mensaje_detalle_intento = f"Error Crítico: No se encontró ejecutable '{VENV_PYTHON}' o script '{SCRIPT_PATH_TO_CALL}'. Detalles: {fnf_error}"
            logging.error(mensaje_detalle_intento)
            estado_proceso_intento = "Error Crítico Orquestador"
            break 
        except Exception as e: # Otro error inesperado en el orquestador al manejar este rig
            mensaje_detalle_intento = f"Error inesperado en orquestador al procesar {log_prefix} (Intento {intentos_realizados}): {e}"
            logging.error(mensaje_detalle_intento, exc_info=True)
            estado_proceso_intento = "Error Orquestador"
            if intentos_realizados >= max_intentos_para_worker:
                break 
            else:
                time.sleep(5)


    # Actualizar estadísticas finales después de todos los reintentos para este rig
    if estado_proceso_intento == "Éxito":
        stats["exito"] += 1
    elif estado_proceso_intento == "No Descargado":
        stats["no_descargado"] += 1
    elif estado_proceso_intento.startswith("Error Script Worker") or estado_proceso_intento.startswith("Error Worker Inesperado"):
        stats["error_script_worker"] += 1
    else: # Error Crítico Orquestador, Error Orquestador, Error Indeterminado
        stats["error_orquestador"] += 1
        
    guardar_estado_proceso(
        nombre_script_worker=script_worker_basename,
        archivo_las=archivo_las_obtenido_intento,
        estado=estado_proceso_intento,
        mensaje=mensaje_detalle_intento
    )

logging.info("🎉 Finalizado el procesamiento de todos los equipos.")
logging.info("Resumen del procesamiento:")
logging.info(f"  Total Rigs Procesados: {len(rigs_contractors)}")
logging.info(f"  Éxitos (descargas o confirmación de no descarga necesaria): {stats['exito'] + stats['no_descargado']}")
logging.info(f"    - Descargas Exitosas: {stats['exito']}")
logging.info(f"    - No Descargados (por fecha/lógica): {stats['no_descargado']}")
logging.info(f"    - Éxitos después de reintento del worker: {stats['reintentos_worker_exitosos']}")
logging.info(f"  Fallos (Script Worker): {stats['error_script_worker']}")
logging.info(f"  Fallos (Orquestador/Críticos): {stats['error_orquestador']}")