#!/usr/bin/env python3
import os
import csv
# import subprocess # Comentado ya que sed fue reemplazado
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from datetime import datetime
from dotenv import load_dotenv

from pathlib import Path
import logging
import argparse
from typing import Optional, List 

from sqlalchemy import create_engine, text, exc as sqlalchemy_exc
import pandas as pd
import tempfile # Para las pruebas de _escribir_csv

# ---- Códigos de Salida ----
EXIT_CODE_SUCCESS = 0
EXIT_CODE_GENERAL_ERROR = 1 
EXIT_CODE_CONFIG_ERROR = 2    
EXIT_CODE_DOWNLOAD_ERROR = 3  
EXIT_CODE_DB_IMPORT_ERROR = 4 
EXIT_CODE_DB_CLEANUP_ERROR = 5
# ---- FIN Códigos de Salida ----

# ==========================================================================
# CONFIGURACIÓN DE RUTAS BASE (Valores por defecto para argparse)
# ==========================================================================
_SCRIPT_DIR_DEFAULT = Path(__file__).resolve().parent
_BASE_DIR_DEFAULT = _SCRIPT_DIR_DEFAULT.parent

_ENV_PATH_DEFAULT = _BASE_DIR_DEFAULT / "config.env"
_CSV_ACTIVOS_DIR_DEFAULT = _BASE_DIR_DEFAULT / "data" / "csv" / "activos"
_LOGS_DIR_DEFAULT = _BASE_DIR_DEFAULT / "logs"

# ==========================================================================
# PARSEO DE ARGUMENTOS DE LÍNEA DE COMANDOS
# ==========================================================================
parser = argparse.ArgumentParser(description="Script para descargar datos de WellData e importarlos a MariaDB.")
parser.add_argument(
    "--env-file", type=Path, default=_ENV_PATH_DEFAULT,
    help=f"Ruta al archivo de configuración .env (def: {_ENV_PATH_DEFAULT})"
)
parser.add_argument(
    "--csv-dir", type=Path, default=_CSV_ACTIVOS_DIR_DEFAULT,
    help=f"Directorio CSV (def: {_CSV_ACTIVOS_DIR_DEFAULT})"
)
parser.add_argument(
    "--log-dir", type=Path, default=_LOGS_DIR_DEFAULT,
    help=f"Directorio de Logs (def: {_LOGS_DIR_DEFAULT})"
)
parser.add_argument(
    "--log-level", type=str, default="INFO",
    choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    help="Nivel de logging (def: INFO)"
)

# Evitar que argparse intente parsear si el módulo es importado (ej. por pytest)
# a menos que se esté ejecutando como script principal.
# sys.modules es una forma de chequear si pytest está activo.
import sys
if __name__ == "__main__" or "pytest" not in sys.modules:
    args = parser.parse_args()
else: 
    args = parser.parse_args([]) # Permite a pytest importar sin error de argumentos


ENV_PATH = args.env_file
CSV_ACTIVOS_DIR = args.csv_dir
LOGS_DIR = args.log_dir
LOG_LEVEL_STR = args.log_level.upper()
numeric_log_level = getattr(logging, LOG_LEVEL_STR, logging.INFO)

CSV_ACTIVOS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ==========================================================================
# CONFIGURACIÓN DE LOGGING
# ==========================================================================
LOG_FILE_PATH = LOGS_DIR / "load_well_data.log"
for handler in logging.root.handlers[:]: logging.root.removeHandler(handler)
logging.basicConfig(
    level=numeric_log_level,
    format='%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s - %(message)s',
    handlers=[logging.FileHandler(LOG_FILE_PATH), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

if __name__ == "__main__": # Solo loguear esto si se ejecuta como script principal
    logger.info(f"Script iniciado. Args: .env={ENV_PATH}, CSVs={CSV_ACTIVOS_DIR}, Logs={LOGS_DIR}, LogLvl={LOG_LEVEL_STR}")
    logger.info(f"Archivo de log: {LOG_FILE_PATH}")

# ==========================================================================
# CARGA DE CREDENCIALES y CREACIÓN DEL MOTOR SQLAlchemy
# ==========================================================================
DB_HOST, DB_USER, DB_PASS, DB_NAME = None, None, None, None
WD_USERNAME, WD_PASSWORD, WD_URL = None, None, None
DB_ENGINE = None

def cargar_credenciales_y_crear_engine() -> bool:
    global DB_HOST, DB_USER, DB_PASS, DB_NAME, WD_USERNAME, WD_PASSWORD, WD_URL, DB_ENGINE
    logger.info(f"{'='*50}\nCargando variables de entorno desde: {ENV_PATH}")
    if not ENV_PATH.exists():
        logger.critical(f"ERROR CRÍTICO: {ENV_PATH} no existe."); return False
    logger.info(f"Archivo {ENV_PATH.name} encontrado."); load_dotenv(ENV_PATH)
    
    DB_HOST, DB_USER, DB_PASS, DB_NAME = os.getenv("DB_HOST"), os.getenv("DB_USER"), os.getenv("DB_PASSWORD"), os.getenv("DB_NAME")
    WD_USERNAME, WD_PASSWORD, WD_URL = os.getenv("WD_USERNAME"), os.getenv("WD_PASSWORD"), os.getenv("WD_URL")

    env_vars_status = {
        "DB_HOST": DB_HOST, "DB_USER": DB_USER, "DB_NAME": DB_NAME,
        "WD_USERNAME": WD_USERNAME, "WD_URL": WD_URL
    }
    logger.info("Variables cargadas del .env:")
    for var, val in env_vars_status.items(): logger.info(f"  {var}: {'Presente' if val else 'NO PRESENTE'}")
    
    if not all([DB_HOST, DB_USER, DB_PASS, DB_NAME, WD_USERNAME, WD_PASSWORD, WD_URL]):
        logger.error("Faltan credenciales/configuraciones esenciales en .env."); return False
    logger.info(f"{'='*50}")
    try:
        db_url = f"mysql+mysqlconnector://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}?charset=utf8mb4"
        connect_args = {'allow_local_infile': True}
        DB_ENGINE = create_engine(db_url, connect_args=connect_args, echo=(LOG_LEVEL_STR == "DEBUG"))
        with DB_ENGINE.connect() as connection: # Prueba de conexión
            logger.info(f"Motor SQLAlchemy creado y conexión a BD '{DB_NAME}' exitosa.")
    except Exception:
        logger.critical("No se pudo crear motor SQLAlchemy o conectar a BD.", exc_info=True); return False
    return True

# ==========================================================================
# FUNCIONES DE TRANSFORMACIÓN DE DATOS (Adaptadas para Pandas)
# ==========================================================================
def transformar_spud_date_pandas(date_series: pd.Series) -> Optional[pd.Series]:
    logger.debug(f"Transformando Serie de Spud Dates ({len(date_series)} elementos)...")
    if date_series.empty: return pd.Series(dtype=object) # Devolver serie vacía si la entrada es vacía
    try:
        transformed_series = pd.to_datetime(date_series, format='%d-%b-%y', errors='coerce')
        return transformed_series.dt.strftime('%Y-%m-%d').where(transformed_series.notna(), None)
    except Exception:
        logger.error("Error en transformar_spud_date_pandas.", exc_info=True)
        return pd.Series([None] * len(date_series), dtype=object)


def _transformar_latest_edr_celda(cell_value):
    if pd.isna(cell_value) or str(cell_value).strip() == "": return None
    cell_str = str(cell_value).strip()
    try:
        if ":" in cell_str and len(cell_str) <= 5: # HH:MM
            hora, minutos = cell_str.split(":")
            fecha_actual = datetime.now().strftime("%Y-%m-%d") # Usa la fecha del momento de ejecución
            return f"{fecha_actual} {hora}:{minutos}:00"
        elif "-" in cell_str: # d-mmm-yy
            dt_obj = datetime.strptime(cell_str, "%d-%b-%y")
            return dt_obj.strftime("%Y-%m-%d %H:%M:%S")
        return None # Formato no reconocido
    except ValueError: # Error específico de parsing
        return None
    except Exception: # Otros errores inesperados
        logger.warning(f"Error inesperado transformando celda latest_edr '{cell_str}'.", exc_info=True)
        return None

def transformar_latest_edr_pandas(date_series: pd.Series) -> Optional[pd.Series]:
    logger.debug(f"Transformando Serie de Latest EDR Dates ({len(date_series)} elementos) usando apply...")
    if date_series.empty: return pd.Series(dtype=object)
    try:
        return date_series.apply(_transformar_latest_edr_celda)
    except Exception:
        logger.error("Error en transformar_latest_edr_pandas.", exc_info=True)
        return pd.Series([None] * len(date_series), dtype=object)

# ---- Funciones auxiliares para el proceso de descarga ----
def _configurar_webdriver(headless=True):
    logger.debug(f"Configurando WebDriver. Headless: {headless}")
    chrome_options = Options();
    if headless: chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu"); chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--dns-prefetch-disable"); # Podría ayudar en algunos entornos de red
    chrome_options.add_argument("window-size=1200x600"); chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    logger.debug("Instalando/configurando ChromeDriver..."); service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options); wait = WebDriverWait(driver, 30)
    logger.debug("WebDriver configurado exitosamente."); return driver, wait

def _login_welldata(driver, wait, url, username, password):
    logger.info(f"Accediendo a {url} para login..."); driver.get(url)
    logger.info("Realizando login...")
    wait.until(EC.presence_of_element_located((By.ID, "ucLogin_txtUsername"))).send_keys(username)
    driver.find_element(By.ID, "ucLogin_txtPassword").send_keys(password)
    driver.find_element(By.ID, "ucLogin_btnSubmit").click()
    # Considerar verificación de login exitoso aquí (ej. título de página o elemento esperado)
    logger.info("Login aparentemente exitoso.")

def _navegar_a_well_list(driver, wait):
    logger.info("Navegando a Well List...")
    wait.until(EC.element_to_be_clickable((By.XPATH, "//area[@href='/Wells/WellList.aspx']"))).click()
    wait.until(EC.title_contains("Well List")); logger.info("Navegación a Well List completada.")

def _extraer_datos_tabla(driver, wait) -> List[List[str]]:
    logger.info("Extrayendo datos de la tabla...")
    wait.until(EC.presence_of_element_located((By.ID, "ucWellList_DataGrid")))
    tabla_rows_elements = driver.find_elements(By.XPATH, "//table[@id='ucWellList_DataGrid']/tbody/tr")
    if not tabla_rows_elements: logger.warning("No se encontraron filas de datos en la tabla de WellData."); return []
    
    datos_extraidos = [[td.text.strip() for td in row_element.find_elements(By.XPATH, ".//td")] for row_element in tabla_rows_elements]
    logger.info(f"Se extrajeron {len(datos_extraidos)} filas de la tabla.")
    return datos_extraidos

def _escribir_csv_desde_dataframe(df: pd.DataFrame, file_path: Path) -> bool:
    logger.info(f"Escribiendo DataFrame en el archivo CSV: {file_path}")
    try:
        columnas_finales = ['Operator', 'Well Name', 'Contractor', 'Rig', 'Spud Date', 'Latest EDR']
        df_to_write = df.reindex(columns=columnas_finales)
        df_to_write.to_csv(file_path, index=False, header=True, quoting=csv.QUOTE_MINIMAL)
        logger.info(f"DataFrame escrito exitosamente en '{file_path.name}'. Filas: {len(df_to_write)}")
        return True
    except Exception:
        logger.error(f"Error inesperado al escribir el DataFrame en CSV {file_path}.", exc_info=True)
        return False

# ==========================================================================
# FUNCIÓN PARA DESCARGAR CSV DESDE WELLDATA (Refactorizada con Pandas)
# ==========================================================================
def descargar_csv_y_procesar_con_pandas() -> Optional[Path]:
    logger.info("Iniciando proceso de descarga y procesamiento con Pandas...")
    driver = None
    try:
        driver, wait = _configurar_webdriver()
        _login_welldata(driver, wait, WD_URL, WD_USERNAME, WD_PASSWORD)
        _navegar_a_well_list(driver, wait)
        datos_tabla_crudos = _extraer_datos_tabla(driver, wait)

        if not datos_tabla_crudos:
            logger.warning("No se extrajeron datos de la tabla, no se generará archivo CSV.")
            return None

        logger.info("Convirtiendo datos extraídos a DataFrame de Pandas...")
        df_data_list = []
        # Columnas que esperamos en el CSV final, y sus correspondientes índices en datos_tabla_crudos
        column_setup = {
            'Operator': 0, 'Well Name': 1, 'Contractor': 2, 'Rig': 3,
            'Spud Date_raw': 4, 'Latest EDR_raw': 8
        }
        
        for row_cells in datos_tabla_crudos:
            if len(row_cells) > max(column_setup.values()): # Asegurar que la fila tenga suficientes celdas
                record = {key: row_cells[idx] for key, idx in column_setup.items()}
                df_data_list.append(record)
            else:
                logger.warning(f"Fila de Selenium ignorada por celdas insuficientes ({len(row_cells)}). Contenido: {row_cells}")
        
        if not df_data_list:
            logger.warning("No quedaron filas válidas para crear el DataFrame."); return None
        
        df = pd.DataFrame(df_data_list)
        logger.info(f"DataFrame creado con {len(df)} filas y {len(df.columns)} columnas.")
        logger.debug(f"Primeras filas del DataFrame inicial:\n{df.head()}")

        logger.info("Limpiando 'M$' del DataFrame...")
        string_columns_to_clean = ['Operator', 'Well Name', 'Contractor', 'Rig']
        for col in string_columns_to_clean:
             if col in df.columns: # Chequear si la columna existe (fue creada desde column_setup)
                df.loc[:, col] = df[col].astype(str).str.replace('M\$', '', regex=True)
        
        logger.info("Transformando columnas de fechas...")
        df_spud_transformed = transformar_spud_date_pandas(df['Spud Date_raw'])
        df_latest_transformed = transformar_latest_edr_pandas(df['Latest EDR_raw'])

        df.loc[:, 'Spud Date'] = df_spud_transformed
        df.loc[:, 'Latest EDR'] = df_latest_transformed
            
        logger.debug(f"Primeras filas del DataFrame después de transformar fechas:\n{df.head()}")

        logger.info("Eliminando filas completamente vacías (basado en columnas de texto originales)...")
        cols_for_empty_text_check = ['Operator', 'Well Name', 'Contractor', 'Rig']
        df_check_empty = df[cols_for_empty_text_check].copy()
        for col in df_check_empty.columns:
            if df_check_empty[col].dtype == 'object': # o str, si pandas infiere así
                df_check_empty[col] = df_check_empty[col].astype(str).str.strip().replace('', pd.NA)
        
        is_empty_row = df_check_empty.isna().all(axis=1)
        df = df[~is_empty_row].reset_index(drop=True)
        logger.info(f"DataFrame después de eliminar filas vacías: {len(df)} filas.")

        df.drop(columns=['Spud Date_raw', 'Latest EDR_raw'], inplace=True, errors='ignore')

        fecha_hora = datetime.now().strftime("%Y-%m-%d_%H-%M-%S"); filename = f"WELL_PAE_{fecha_hora}.csv"
        file_path_final_csv = CSV_ACTIVOS_DIR / filename

        if _escribir_csv_desde_dataframe(df, file_path_final_csv):
            logger.info(f"Archivo CSV procesado '{filename}' guardado exitosamente en {CSV_ACTIVOS_DIR}.")
            return file_path_final_csv
        else: logger.error("Falló la escritura del archivo CSV procesado."); return None

    except Exception: 
        logger.error("Error crítico durante el proceso de descarga y procesamiento con Pandas.", exc_info=True)
        return None
    finally:
        if driver: logger.debug("Cerrando WebDriver principal..."); driver.quit(); logger.debug("WebDriver principal cerrado.")

# ==========================================================================
# FUNCIONES PARA IMPORTAR A MARIADB (Usando SQLAlchemy)
# ==========================================================================
def importar_csv_a_mariadb(csv_a_importar_path: Path) -> bool:
    if not csv_a_importar_path or not csv_a_importar_path.exists():
        logger.error(f"Archivo CSV a importar no válido o no encontrado: {csv_a_importar_path}"); return False
    if not DB_ENGINE: logger.error("Motor DB (DB_ENGINE) no inicializado."); return False

    escaped_file_path_for_sql = str(csv_a_importar_path).replace("\\", "\\\\")
    mysql_load_cmd_str = f"""
    LOAD DATA LOCAL INFILE '{escaped_file_path_for_sql}' INTO TABLE well_data
    FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' LINES TERMINATED BY '\\n' IGNORE 1 ROWS
    (operator, well_name, contractor, rig, @spud_date, @latest_edr)
    SET import_datetime = CURRENT_TIMESTAMP,
        spud_date = NULLIF(STR_TO_DATE(NULLIF(TRIM(@spud_date), ''), '%Y-%m-%d'), '0000-00-00'),
        latest_edr = NULLIF(STR_TO_DATE(NULLIF(TRIM(@latest_edr), ''), '%Y-%m-%d %H:%i:%s'), '0000-00-00 00:00:00'),
        status = CASE WHEN TIMESTAMPDIFF(HOUR, STR_TO_DATE(NULLIF(TRIM(@latest_edr), ''), '%Y-%m-%d %H:%i:%s'), NOW()) < 6 THEN 'online' ELSE 'offline' END;
    """
    try:
        with DB_ENGINE.connect() as connection:
            logger.info(f"Ejecutando LOAD DATA INFILE para: {csv_a_importar_path} usando SQLAlchemy...")
            with connection.begin(): result = connection.execute(text(mysql_load_cmd_str))
            logger.info(f"LOAD DATA INFILE ejecutado. (SQLAlchemy rowcount: {result.rowcount if result else 'N/A'})")
        return True
    except sqlalchemy_exc.SQLAlchemyError: logger.error(f"Error SQLAlchemy importando '{csv_a_importar_path}'.", exc_info=True); return False
    except Exception: logger.error(f"Error inesperado importando a MariaDB '{csv_a_importar_path}'.", exc_info=True); return False

def eliminar_registros_no_validos() -> bool:
    if not DB_ENGINE: logger.error("Motor DB (DB_ENGINE) no inicializado."); return False
    sql_delete_cmd_str = """
    DELETE FROM well_data WHERE (contractor, rig) NOT IN (
        SELECT ca.alias, CASE WHEN ra.alias LIKE 'FB%' THEN REPLACE(ra.alias, '-', ' ')
                               WHEN ra.alias LIKE 'PAE%' THEN REPLACE(ra.alias, '-', ' ')
                               ELSE ra.alias END
        FROM rigs_contractors_autom ca JOIN rigs_autom ra ON ra.contractor_id = ca.id
    ) AND rig NOT IN ('PAE 001', 'FB-01');
    """
    try:
        with DB_ENGINE.connect() as connection:
            logger.info("Ejecutando DELETE para limpiar registros no válidos (SQLAlchemy)...")
            with connection.begin(): result = connection.execute(text(sql_delete_cmd_str))
            logger.info(f"Limpieza de registros completada! (SQLAlchemy rowcount: {result.rowcount if result else 'N/A'})")
        return True
    except sqlalchemy_exc.SQLAlchemyError: logger.error(f"Error SQLAlchemy durante limpieza de registros.", exc_info=True); return False
    except Exception: logger.error(f"Error inesperado durante limpieza de registros.", exc_info=True); return False

# ==========================================================================
# EJECUCIÓN PRINCIPAL
# ==========================================================================
def main():
    final_exit_code = EXIT_CODE_SUCCESS
    if not cargar_credenciales_y_crear_engine():
        sys.exit(EXIT_CODE_CONFIG_ERROR) 
    
    logger.info(f"{'='*50}"); logger.info("INICIANDO PROCESO DE ACTUALIZACIÓN DE DATOS"); logger.info(f"{'='*50}")
    path_csv_procesado = descargar_csv_y_procesar_con_pandas() 
    
    if path_csv_procesado:
        if importar_csv_a_mariadb(path_csv_procesado):
            if not eliminar_registros_no_validos():
                logger.error("Fallo durante la eliminación de registros no válidos en la BD.")
                final_exit_code = EXIT_CODE_DB_CLEANUP_ERROR
            else: # Solo borrar si importación y limpieza BD fueron exitosas
                try:
                    logger.debug(f"Intentando eliminar archivo CSV procesado: {path_csv_procesado}")
                    os.remove(path_csv_procesado)
                    logger.info(f"Archivo CSV procesado '{path_csv_procesado.name}' eliminado tras operaciones exitosas.")
                except OSError:
                    logger.warning(f"No se pudo eliminar el CSV procesado: {path_csv_procesado}", exc_info=True)
        else: 
            logger.error("Fallo durante la importación del CSV a MariaDB.")
            final_exit_code = EXIT_CODE_DB_IMPORT_ERROR
    else: 
        logger.error("Proceso detenido: no se pudo descargar o procesar el archivo CSV.")
        final_exit_code = EXIT_CODE_DOWNLOAD_ERROR
    
    logger.info(f"{'='*50}")
    if final_exit_code == EXIT_CODE_SUCCESS:
        logger.info("PROCESO FINALIZADO EXITOSAMENTE")
    else:
        logger.error(f"PROCESO FINALIZADO CON ERRORES. Código de salida: {final_exit_code}")
    logger.info(f"{'='*50}")
    sys.exit(final_exit_code)

if __name__ == "__main__":
    main()

# ==========================================================================
# PRUEBAS UNITARIAS (Integradas en el mismo archivo)
# Para ejecutar:
# 1. Asegúrate de tener pytest instalado: pip install pytest
# 2. Desde la terminal, en la carpeta 'scripts/', ejecuta: pytest load_well_data.py
# ==========================================================================
# Nota: Normalmente, las pruebas se colocan en archivos separados en un directorio 'tests'.

def test_transformar_spud_date_pandas_validos():
    """Prueba transformar_spud_date_pandas con fechas válidas."""
    serie_entrada = pd.Series(["15-Jan-23", "01-Dec-22", "20-Feb-24"])
    serie_esperada = pd.Series(["2023-01-15", "2022-12-01", "2024-02-20"], dtype=object) # dtype=object para Nones
    serie_resultado = transformar_spud_date_pandas(serie_entrada)
    pd.testing.assert_series_equal(serie_resultado, serie_esperada, check_dtype=False)

def test_transformar_spud_date_pandas_invalidos_y_vacios():
    """Prueba transformar_spud_date_pandas con valores inválidos, None o vacíos."""
    serie_entrada = pd.Series(["invalido", None, "", "25/12/2023", "30-Mar-21"])
    serie_esperada = pd.Series([None, None, None, None, "2021-03-30"], dtype=object)
    serie_resultado = transformar_spud_date_pandas(serie_entrada)
    pd.testing.assert_series_equal(serie_resultado, serie_esperada, check_dtype=False)

def test_transformar_latest_edr_pandas_varios_casos():
    """Prueba transformar_latest_edr_pandas con diferentes formatos y casos."""
    # Mockear datetime.now() sería ideal para pruebas deterministas.
    # Aquí, aceptaremos que la fecha puede cambiar si la prueba se ejecuta en diferentes días.
    # Nos enfocaremos en la correcta transformación de la hora y el formato.
    
    # Obtener la fecha actual una vez para usarla en las aserciones de HH:MM
    # Esto no mockea la función, solo la captura para la aserción.
    # La función _transformar_latest_edr_celda seguirá usando datetime.now() en tiempo real.
    fecha_para_comparacion_hhmm = datetime.now().strftime("%Y-%m-%d")

    serie_entrada = pd.Series([
        "14:30", "08:05", "15-Jan-23", "01-Dec-22",
        "", None, "invalido", "22:70" 
    ])
    serie_esperada = pd.Series([
        f"{fecha_para_comparacion_hhmm} 14:30:00",
        f"{fecha_para_comparacion_hhmm} 08:05:00",
        "2023-01-15 00:00:00",
        "2022-12-01 00:00:00",
        None, None, None, None
    ], dtype=object)
    
    serie_resultado = transformar_latest_edr_pandas(serie_entrada)
    
    # Comparamos elemento a elemento para la parte de HH:MM
    # ya que la fecha_actual podría ser diferente entre la llamada a la función y la creación de serie_esperada
    # si la prueba cruza la medianoche (muy improbable pero posible).
    # Una forma más simple es solo verificar la parte de la hora para esos casos.
    for i in range(len(serie_entrada)):
        if ":" in str(serie_entrada[i]) and len(str(serie_entrada[i])) <= 5 and serie_resultado[i] is not None:
            # Verificar que la parte de la hora y minutos sea correcta
            assert str(serie_entrada[i]) + ":00" in serie_resultado[i] 
        else:
            assert serie_resultado[i] == serie_esperada[i]


def test_escribir_csv_desde_dataframe_basico():
    """Prueba básica de _escribir_csv_desde_dataframe."""
    datos_ejemplo = {
        'Operator': ['OpA', 'OpB'], 'Well Name': ['Well1', 'Well2'],
        'Contractor': ['Contr1', 'Contr2'], 'Rig': ['RigA', 'RigB'],
        'Spud Date': ['2023-01-10', '2023-02-15'],
        'Latest EDR': ['2023-01-10 08:00:00', '2023-02-15 09:30:00']
    }
    df_ejemplo = pd.DataFrame(datos_ejemplo)
    
    with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.csv', newline='', encoding='utf-8') as tmp_csv_file:
        temp_csv_path = Path(tmp_csv_file.name)

    try:
        resultado_escritura = _escribir_csv_desde_dataframe(df_ejemplo, temp_csv_path)
        assert resultado_escritura is True
        assert temp_csv_path.exists()

        with open(temp_csv_path, mode='r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            contenido_csv = list(reader)
            
        assert len(contenido_csv) == 3 
        assert contenido_csv[0] == ['Operator', 'Well Name', 'Contractor', 'Rig', 'Spud Date', 'Latest EDR']
        assert contenido_csv[1] == ['OpA', 'Well1', 'Contr1', 'RigA', '2023-01-10', '2023-01-10 08:00:00']
        assert contenido_csv[2] == ['OpB', 'Well2', 'Contr2', 'RigB', '2023-02-15', '2023-02-15 09:30:00']
    finally:
        if temp_csv_path.exists(): os.remove(temp_csv_path)

def test_escribir_csv_desde_dataframe_columnas_reordenadas_y_faltantes():
    """Prueba _escribir_csv_desde_dataframe con columnas en desorden o faltantes."""
    datos_ejemplo = { # Spud Date y Latest EDR ya están como strings en el formato esperado
        'Well Name': ['WellX'], 'Latest EDR': ['2023-03-01 10:00:00'], 
        'Operator': ['OpX'], 'ExtraCol': ['ExtraVal']
    } # Faltan Contractor, Rig, Spud Date
    df_ejemplo = pd.DataFrame(datos_ejemplo)
    
    with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.csv', newline='', encoding='utf-8') as tmp_csv_file:
        temp_csv_path = Path(tmp_csv_file.name)
    
    try:
        _escribir_csv_desde_dataframe(df_ejemplo, temp_csv_path)
        with open(temp_csv_path, mode='r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            contenido_csv = list(reader)
        
        assert len(contenido_csv) == 2
        assert contenido_csv[0] == ['Operator', 'Well Name', 'Contractor', 'Rig', 'Spud Date', 'Latest EDR']
        # .to_csv escribe strings vacíos para NaN por defecto.
        assert contenido_csv[1] == ['OpX', 'WellX', '', '', '', '2023-03-01 10:00:00']
    finally:
        if temp_csv_path.exists(): os.remove(temp_csv_path)