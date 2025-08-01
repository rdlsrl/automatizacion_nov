#!/usr/bin/env python3
import os
import sys
import time
from pathlib import Path
import logging
import argparse
from datetime import datetime, timedelta
from typing import Optional, Tuple, Callable, Any
import functools 
from logging.handlers import RotatingFileHandler 

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchWindowException, ElementClickInterceptedException, StaleElementReferenceException

# ---- Tiempos y Parámetros Configurables (valores por defecto iniciales) ----
POPUP_TRANSITION_SLEEP_SEC = 2.5
DOWNLOAD_START_WAIT_SEC = 10
DOWNLOAD_FALLBACK_WAIT_SEC = 15
DOWNLOAD_COMPLETE_TIMEOUT_SEC = 180 
DOWNLOAD_CHECK_INTERVAL_SEC = 3     
DOWNLOAD_SIZE_STABILITY_CHECKS = 2  
DOWNLOAD_SIZE_STABILITY_INTERVAL_SEC = 2.0 
RETRY_ATTEMPTS = 2 
RETRY_DELAY_SEC = 5 
CHANNEL_CONFIG_ACTION_SLEEP_SEC = 3 
MIN_LAS_FILE_SIZE_BYTES = 100 

# ---- Códigos de Salida (Completos) ----
EXIT_CODE_SUCCESS = 0
EXIT_CODE_GENERAL_ERROR = 1
EXIT_CODE_CONFIG_ERROR = 2
EXIT_CODE_SELENIUM_ERROR = 3
EXIT_CODE_DOWNLOAD_ERROR = 4

# ==========================================================================
# CONFIGURACIÓN DE RUTAS BASE
# ==========================================================================
_SCRIPT_DIR_DEFAULT = Path(__file__).resolve().parent
_BASE_DIR_DEFAULT = _SCRIPT_DIR_DEFAULT.parent

_ENV_PATH_DEFAULT = _BASE_DIR_DEFAULT / "config.env"
_LAS_OUTPUT_DIR_DEFAULT = _BASE_DIR_DEFAULT / "data" / "las" / "activos"
_LOGS_DIR_DEFAULT = _BASE_DIR_DEFAULT / "logs"

# ==========================================================================
# PARSEO DE ARGUMENTOS Y CONFIG INICIAL
# ==========================================================================
parser = argparse.ArgumentParser(description="Automatiza la descarga de archivos LAS desde WellData.")
parser.add_argument("contractor", type=str, help="Nombre del Contractor.")
parser.add_argument("rig", type=str, help="Nombre del Rig/Equipo.")
parser.add_argument("rig_name", type=str, help="Nombre del Rig para el nombre del archivo LAS.")
parser.add_argument("well_name", type=str, help="Nombre del Pozo para el nombre del archivo LAS.")
parser.add_argument("rig_type", type=str, choices=["PER", "WO", "PUL"], help="Tipo de Rig (PER, WO, PUL) para la resolución de descarga.")
parser.add_argument("--env-file", type=Path, default=str(_ENV_PATH_DEFAULT), help=f"Ruta al archivo .env (def: {_ENV_PATH_DEFAULT})")
parser.add_argument("--las-output-dir", type=Path, default=str(_LAS_OUTPUT_DIR_DEFAULT), help=f"Directorio de salida para archivos LAS (def: {_LAS_OUTPUT_DIR_DEFAULT})")
parser.add_argument("--log-dir", type=Path, default=str(_LOGS_DIR_DEFAULT), help=f"Directorio para archivos de log (def: {_LOGS_DIR_DEFAULT})")
parser.add_argument("--log-level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], help="Nivel de logging (def: INFO)")
parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True, help="Ejecutar Chrome en modo headless. Usar --no-headless para modo visual.")
args = parser.parse_args()

ENV_PATH = Path(args.env_file)
LAS_OUTPUT_DIR = Path(args.las_output_dir)
LOGS_DIR = Path(args.log_dir)
LOG_LEVEL_STR = args.log_level.upper()
HEADLESS_MODE = args.headless
numeric_log_level = getattr(logging, LOG_LEVEL_STR, logging.INFO)

LAS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ==========================================================================
# CONFIGURACIÓN DE LOGGING
# ==========================================================================
LOG_FILE_NAME = LOGS_DIR / f"{Path(__file__).stem}.log" 
logger_root = logging.getLogger()
logger_root.setLevel(numeric_log_level)
for handler in logger_root.handlers[:]:
    logger_root.removeHandler(handler)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s')
file_handler = RotatingFileHandler(LOG_FILE_NAME, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
file_handler.setFormatter(formatter)
logger_root.addHandler(file_handler)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger_root.addHandler(console_handler)
logger = logging.getLogger(__name__) 

logger.info(f"Script '{Path(__file__).name}' iniciado.")
logger.info(f"  Argumentos parseados:")
logger.info(f"    Contractor: {args.contractor}")
logger.info(f"    Rig: {args.rig}")
logger.info(f"    Rig Name (archivo): {args.rig_name}")
logger.info(f"    Well Name (archivo): {args.well_name}")
logger.info(f"    Rig Type: {args.rig_type}")
logger.info(f"    Archivo .env: {ENV_PATH}")
logger.info(f"    Directorio Salida LAS: {LAS_OUTPUT_DIR}")
logger.info(f"    Directorio Logs: {LOGS_DIR}")
logger.info(f"    Nivel de Log: {LOG_LEVEL_STR}")
logger.info(f"    Modo Headless: {HEADLESS_MODE}")
logger.info(f"  Archivo de log actual: {LOG_FILE_NAME}")
logger.info(f"  Tiempos (defaults ANTES de .env): POPUP_TRANSITION_SLEEP_SEC={POPUP_TRANSITION_SLEEP_SEC}, RETRY_ATTEMPTS={RETRY_ATTEMPTS}, CHANNEL_CONFIG_ACTION_SLEEP_SEC={CHANNEL_CONFIG_ACTION_SLEEP_SEC}, MIN_LAS_FILE_SIZE_BYTES={MIN_LAS_FILE_SIZE_BYTES}, etc.")

WD_URL, WD_USERNAME, WD_PASSWORD = None, None, None

def retry_on_exception(attempts: int = RETRY_ATTEMPTS, delay_sec: int = RETRY_DELAY_SEC, 
                       exceptions_to_catch: Tuple[type[Exception], ...] = (TimeoutException, ElementClickInterceptedException, StaleElementReferenceException)):
    """Decorador para reintentar una función si lanza una de las excepciones especificadas."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            for i in range(attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions_to_catch as e:
                    logger.warning(f"Intento {i + 1}/{attempts} fallido para {func.__name__}: {type(e).__name__} - {str(e).splitlines()[0] if str(e) else 'Sin mensaje'}")
                    if i + 1 == attempts:
                        logger.error(f"Todos los {attempts} intentos fallaron para {func.__name__}.")
                        raise 
                    actual_delay = delay_sec * (i + 1) 
                    logger.info(f"Reintentando {func.__name__} en {actual_delay} segundos...")
                    time.sleep(actual_delay)
            return None # Debería ser inalcanzable si raise funciona, pero es bueno para el linter
        return wrapper
    return decorator

def load_wd_configuration(env_file_path: Path) -> bool:
    """Carga la configuración de WellData y parámetros de script desde un archivo .env."""
    global WD_URL, WD_USERNAME, WD_PASSWORD, POPUP_TRANSITION_SLEEP_SEC, DOWNLOAD_START_WAIT_SEC, \
           DOWNLOAD_FALLBACK_WAIT_SEC, DOWNLOAD_COMPLETE_TIMEOUT_SEC, DOWNLOAD_CHECK_INTERVAL_SEC, \
           DOWNLOAD_SIZE_STABILITY_CHECKS, DOWNLOAD_SIZE_STABILITY_INTERVAL_SEC, \
           RETRY_ATTEMPTS, RETRY_DELAY_SEC, CHANNEL_CONFIG_ACTION_SLEEP_SEC, MIN_LAS_FILE_SIZE_BYTES

    logger.info(f"Cargando configuración y parámetros desde: {env_file_path}")
    if not env_file_path.exists():
        logger.warning(f"Archivo .env no encontrado en: {env_file_path}. Usando valores por defecto para parámetros.")
    else:
        load_dotenv(env_file_path) 
    
    WD_URL = os.getenv("WD_URL")
    WD_USERNAME = os.getenv("WD_USERNAME")
    WD_PASSWORD = os.getenv("WD_PASSWORD")

    POPUP_TRANSITION_SLEEP_SEC = float(os.getenv("POPUP_TRANSITION_SLEEP_SEC", POPUP_TRANSITION_SLEEP_SEC))
    DOWNLOAD_START_WAIT_SEC = int(os.getenv("DOWNLOAD_START_WAIT_SEC", DOWNLOAD_START_WAIT_SEC))
    DOWNLOAD_FALLBACK_WAIT_SEC = int(os.getenv("DOWNLOAD_FALLBACK_WAIT_SEC", DOWNLOAD_FALLBACK_WAIT_SEC))
    DOWNLOAD_COMPLETE_TIMEOUT_SEC = int(os.getenv("DOWNLOAD_COMPLETE_TIMEOUT_SEC", DOWNLOAD_COMPLETE_TIMEOUT_SEC))
    DOWNLOAD_CHECK_INTERVAL_SEC = int(os.getenv("DOWNLOAD_CHECK_INTERVAL_SEC", DOWNLOAD_CHECK_INTERVAL_SEC))
    DOWNLOAD_SIZE_STABILITY_CHECKS = int(os.getenv("DOWNLOAD_SIZE_STABILITY_CHECKS", DOWNLOAD_SIZE_STABILITY_CHECKS))
    DOWNLOAD_SIZE_STABILITY_INTERVAL_SEC = float(os.getenv("DOWNLOAD_SIZE_STABILITY_INTERVAL_SEC", DOWNLOAD_SIZE_STABILITY_INTERVAL_SEC))
    RETRY_ATTEMPTS = int(os.getenv("RETRY_ATTEMPTS", RETRY_ATTEMPTS))
    RETRY_DELAY_SEC = int(os.getenv("RETRY_DELAY_SEC", RETRY_DELAY_SEC))
    CHANNEL_CONFIG_ACTION_SLEEP_SEC = float(os.getenv("CHANNEL_CONFIG_ACTION_SLEEP_SEC", CHANNEL_CONFIG_ACTION_SLEEP_SEC))
    MIN_LAS_FILE_SIZE_BYTES = int(os.getenv("MIN_LAS_FILE_SIZE_BYTES", MIN_LAS_FILE_SIZE_BYTES))
    
    logger.info(f"  Valores de parámetros (después de cargar .env):")
    logger.info(f"    POPUP_TRANSITION_SLEEP_SEC = {POPUP_TRANSITION_SLEEP_SEC}")
    logger.info(f"    DOWNLOAD_START_WAIT_SEC = {DOWNLOAD_START_WAIT_SEC}")
    logger.info(f"    DOWNLOAD_FALLBACK_WAIT_SEC = {DOWNLOAD_FALLBACK_WAIT_SEC}")
    logger.info(f"    DOWNLOAD_COMPLETE_TIMEOUT_SEC = {DOWNLOAD_COMPLETE_TIMEOUT_SEC}")
    logger.info(f"    DOWNLOAD_CHECK_INTERVAL_SEC = {DOWNLOAD_CHECK_INTERVAL_SEC}")
    logger.info(f"    DOWNLOAD_SIZE_STABILITY_CHECKS = {DOWNLOAD_SIZE_STABILITY_CHECKS}")
    logger.info(f"    DOWNLOAD_SIZE_STABILITY_INTERVAL_SEC = {DOWNLOAD_SIZE_STABILITY_INTERVAL_SEC}")
    logger.info(f"    RETRY_ATTEMPTS = {RETRY_ATTEMPTS}, RETRY_DELAY_SEC = {RETRY_DELAY_SEC}")
    logger.info(f"    CHANNEL_CONFIG_ACTION_SLEEP_SEC = {CHANNEL_CONFIG_ACTION_SLEEP_SEC}")
    logger.info(f"    MIN_LAS_FILE_SIZE_BYTES = {MIN_LAS_FILE_SIZE_BYTES}")

    if not all([WD_URL, WD_USERNAME, WD_PASSWORD]):
        logger.critical("Faltan variables WD_URL, WD_USERNAME o WD_PASSWORD. Verificar .env o variables de entorno.")
        return False
    logger.info("Configuración de WellData (URL/Usuario) cargada exitosamente.")
    return True

def _configurar_webdriver(download_dir_arg: Path, headless_arg: bool) -> Tuple[Optional[webdriver.Chrome], Optional[WebDriverWait]]:
    """Configura e inicializa el WebDriver de Chrome con las opciones especificadas."""
    logger.info(f"Configurando WebDriver. Headless: {headless_arg}. Descargas a: {download_dir_arg}.")
    prefs = {
        "download.default_directory": str(download_dir_arg),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "profile.default_content_settings.popups": 0, 
        "safeBrowse.enabled": True,
        "plugins.always_open_pdf_externally": True
    }
    chrome_options = Options()
    if headless_arg:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu") 
    chrome_options.add_argument("window-size=1920,1080")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--start-maximized") 
    chrome_options.add_experimental_option("prefs", prefs)
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
    chrome_options.add_argument('--log-level=1')

    try:
        logger.info("Intentando configurar ChromeDriver usando webdriver-manager...")
        service = Service(ChromeDriverManager().install())
        logger.info("ChromeDriver configurado/actualizado mediante webdriver-manager.")
        
        driver = webdriver.Chrome(service=service, options=chrome_options)
        wait = WebDriverWait(driver, 60) 
        logger.info("WebDriver creado y configurado exitosamente.")
        return driver, wait
    except Exception as e:
        logger.error(f"Error crítico configurando WebDriver: {e}", exc_info=True)
        return None, None

@retry_on_exception()
def _login_welldata(driver: webdriver.Chrome, wait: WebDriverWait, url: str, username: str, password: str) -> bool:
    """Realiza el proceso de login en la plataforma WellData."""
    logger.info(f"Accediendo a {url} para login...")
    try:
        driver.get(url)
        wait.until(EC.presence_of_element_located((By.ID, "ucLogin_txtUsername"))).send_keys(username)
        driver.find_element(By.ID, "ucLogin_txtPassword").send_keys(password)
        driver.find_element(By.ID, "ucLogin_btnSubmit").click()
        
        WebDriverWait(driver, 20).until_not(EC.url_contains("Login.aspx"))
        if "Login.aspx" in driver.current_url.lower():
            logger.error("Login fallido, aún en la página de login. Verificar credenciales o CAPTCHA.")
            return False 
        logger.info("Login en WellData exitoso.")
        return True
    except TimeoutException as te: 
        logger.error(f"Timeout durante el login: {str(te).splitlines()[0] if str(te) else 'Sin mensaje'}")
        if driver and "Login.aspx" in driver.current_url.lower():
             logger.error("Login fallido (timeout), aún en la página de login.")
        raise 
    except Exception as e: 
        logger.error(f"Error no-Timeout durante el login en WellData: {e}", exc_info=True)
        raise 

@retry_on_exception()
def _navegar_y_seleccionar_rig(driver: webdriver.Chrome, wait: WebDriverWait, contractor: str, rig: str) -> bool:
    """Navega a la lista de pozos/rigs y selecciona el rig especificado."""
    logger.info(f"Navegando a Well List para seleccionar Contractor: '{contractor}', Rig: '{rig}'...")
    try:
        wells_menu_xpath = "//area[@href='/Wells/WellList.aspx']"
        logger.debug(f"Esperando por el menú 'Wells': {wells_menu_xpath}")
        
        wells_menu_element = wait.until(EC.element_to_be_clickable((By.XPATH, wells_menu_xpath)))
        driver.execute_script("arguments[0].click();", wells_menu_element)
        
        logger.debug("Esperando que el título contenga 'Well List'")
        wait.until(EC.title_contains("Well List"))
        logger.info("Página 'Well List' cargada.")

        logger.debug("Esperando por la tabla de datos 'ucWellList_DataGrid'")
        wait.until(EC.presence_of_element_located((By.ID, "ucWellList_DataGrid")))
        rows = driver.find_elements(By.XPATH, "//table[@id='ucWellList_DataGrid']/tbody/tr")
        found = False
        for row_idx, row in enumerate(rows[1:], start=1): 
            cols = row.find_elements(By.TAG_NAME, "td")
            if len(cols) >= 4:
                web_contractor = cols[2].text.strip()
                web_rig = cols[3].text.strip()
                logger.debug(f"Fila {row_idx}: Web='{web_contractor} - {web_rig}' vs Args='{contractor} - {rig}'")
                if web_contractor.lower() == contractor.lower() and web_rig.lower() == rig.lower():
                    logger.info(f"Rig encontrado: {contractor} - {rig}. Haciendo clic...")
                    link_element = cols[3].find_element(By.TAG_NAME, "a")
                    driver.execute_script("arguments[0].click();", link_element)
                    found = True
                    break
        if not found:
            logger.error(f"No se encontró la combinación Contractor '{contractor}' y Rig '{rig}' en la lista.")
            return False
        
        logger.debug("Esperando por iframe 'Frame1' en la página de detalles del Rig/Pozo.")
        wait.until(EC.presence_of_element_located((By.ID, "Frame1")))
        logger.info("Página de detalles del Rig/Pozo cargada (iframe detectado).")
        return True
    except (TimeoutException, ElementClickInterceptedException, StaleElementReferenceException) as e:
        logger.error(f"Excepción reintentable navegando o seleccionando rig: {type(e).__name__} - {str(e).splitlines()[0] if str(e) else 'Sin mensaje'}")
        raise
    except Exception as e:
        logger.error(f"Error no reintentable navegando o seleccionando el rig: {e}", exc_info=True)
        return False

@retry_on_exception() # Aplicar reintentos aquí también
def _configurar_parametros_descarga_las(driver: webdriver.Chrome, wait: WebDriverWait, rig_type: str) -> bool:
    """Configura los parámetros para la descarga del LAS (canales, resolución)."""
    logger.info("Configurando parámetros para descarga LAS...")
    try:
        logger.debug("Cambiando a iframe 'Frame1'...")
        wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, "Frame1")))
        
        logger.debug("Haciendo clic en el primer botón 'Save' (HyperLink1) para abrir opciones de descarga...")
        save_button_initial = wait.until(EC.element_to_be_clickable((By.ID, "ucDrillingRecorderUV_HyperLink1")))
        save_button_initial.click()
        
        logger.debug("Saliendo del iframe para interactuar con la página principal...")
        driver.switch_to.default_content()
        
        logger.info("Configurando canales: Remove All, desmarcar Active, Add All.")
        
        wait.until(EC.element_to_be_clickable((By.ID, "ucDrillingRecorder_btnRemoveAll"))).click()
        logger.debug(f"Clic en 'Remove All'. Esperando {CHANNEL_CONFIG_ACTION_SLEEP_SEC}s para que la UI procese...")
        time.sleep(CHANNEL_CONFIG_ACTION_SLEEP_SEC) 

        cb_only_active = wait.until(EC.element_to_be_clickable((By.ID, "ucDrillingRecorder_cbOnlyShowActiveChannels")))
        if cb_only_active.is_selected():
            cb_only_active.click()
            logger.debug("Checkbox 'OnlyShowActiveChannels' desmarcado.")
        
        wait.until(EC.element_to_be_clickable((By.ID, "ucDrillingRecorder_btnAddAll"))).click()
        logger.debug(f"Clic en 'Add All'. Esperando {CHANNEL_CONFIG_ACTION_SLEEP_SEC}s para que la UI procese...")
        time.sleep(CHANNEL_CONFIG_ACTION_SLEEP_SEC)

        logger.info(f"Configurando resolución de tiempo para Rig Type '{rig_type}'...")
        select_resolution_element = wait.until(EC.presence_of_element_located((By.ID, "ucDrillingRecorder_ddlResolutionTime")))
        select_resolution = Select(select_resolution_element)
        
        if rig_type in ["PER", "WO"]:
            select_resolution.select_by_visible_text("30 sec")
            logger.info("Resolución establecida a '30 sec'.")
        elif rig_type == "PUL":
            select_resolution.select_by_visible_text("5 sec")
            logger.info("Resolución establecida a '5 sec'.")
        else:
            select_resolution.select_by_visible_text("5 sec") 
            logger.warning(f"Rig Type '{rig_type}' no reconocido, usando '5 sec' por defecto.")
        return True
    except (TimeoutException, ElementClickInterceptedException, StaleElementReferenceException) as e_retry: 
        logger.error(f"Excepción reintentable en _configurar_parametros_descarga_las: {type(e_retry).__name__} - {str(e_retry).splitlines()[0] if str(e_retry) else 'Sin mensaje'}")
        raise 
    except Exception as e:
        logger.error(f"Error no reintentable configurando parámetros de descarga LAS: {e}", exc_info=True)
        try:
            driver.switch_to.default_content() 
        except: pass
        return False


def _establecer_rango_fechas_y_calcular_sufijo(driver: webdriver.Chrome, wait: WebDriverWait) -> Optional[str]:
    """Establece el rango de fechas para la descarga y calcula el sufijo para el nombre del archivo."""
    logger.info("Estableciendo rango de fechas para la descarga...")
    try:
        wait.until(EC.element_to_be_clickable((By.ID, "ucDrillingRecorder_rbRangeDate"))).click()
        logger.debug("Radio button 'Range Date' seleccionado.")

        min_date_input_id = "ucDrillingRecorder_calStartDate_txtDate"
        max_date_input_id = "ucDrillingRecorder_calEndDate_txtDate"

        min_date_input = wait.until(EC.visibility_of_element_located((By.ID, min_date_input_id)))
        max_date_input = driver.find_element(By.ID, max_date_input_id)
        
        min_date_str_from_page = min_date_input.get_attribute("value")
        if not min_date_str_from_page:
            logger.error("No se pudo obtener la fecha mínima de la página (campo vacío).")
            return None

        try:
            min_date_page = datetime.strptime(min_date_str_from_page, "%d-%B-%y")
        except ValueError:
            logger.error(f"Formato de fecha inesperado en la página: '{min_date_str_from_page}'. No se pudo parsear.")
            return None

        today = datetime.now()
        yesterday = today - timedelta(days=1)
        
        sufijo_calculado = ""

        if min_date_page.date() > yesterday.date():
            logger.warning(f"La fecha mínima del pozo en la web ({min_date_page.date()}) es posterior a ayer ({yesterday.date()}). No se descargará.")
            return "NO_DOWNLOAD_MIN_DATE_TOO_RECENT"
        elif min_date_page.date() == yesterday.date():
            sufijo_calculado = "_nws"
            logger.info(f"Fecha mínima del pozo ({min_date_page.date()}) es ayer. Usando sufijo '{sufijo_calculado}'.")
        else: 
            num_dias_diff = (yesterday.date() - min_date_page.date()).days
            sufijo_calculado = f"_{num_dias_diff}"
            logger.info(f"Fecha mínima del pozo ({min_date_page.date()}) es {num_dias_diff} días antes de ayer. Usando sufijo '{sufijo_calculado}'.")

        Select(driver.find_element(By.ID, "ucDrillingRecorder_tsRangeDateStartTime_DropDownListHour")).select_by_value("0")
        Select(driver.find_element(By.ID, "ucDrillingRecorder_tsRangeDateStartTime_DropDownListMinute")).select_by_value("00")
        Select(driver.find_element(By.ID, "ucDrillingRecorder_tsRangeDateEndTime_DropDownListHour")).select_by_value("0")
        Select(driver.find_element(By.ID, "ucDrillingRecorder_tsRangeDateEndTime_DropDownListMinute")).select_by_value("00")
        logger.debug("Horas de inicio y fin establecidas a '0:00'.")

        yesterday_str_formatted = yesterday.strftime("%d-%B-%y")
        today_str_formatted = today.strftime("%d-%B-%y")

        driver.execute_script(f"document.getElementById('{min_date_input_id}').value = '';")
        driver.execute_script(f"document.getElementById('{min_date_input_id}').value = '{yesterday_str_formatted}';")
        min_date_input.send_keys(Keys.TAB) 
        time.sleep(0.5) 

        driver.execute_script(f"document.getElementById('{max_date_input_id}').value = '';")
        driver.execute_script(f"document.getElementById('{max_date_input_id}').value = '{today_str_formatted}';")
        max_date_input.send_keys(Keys.TAB)
        time.sleep(0.5) 
        
        logger.info(f"Rango de fechas establecido en la web: Inicio={yesterday_str_formatted}, Fin={today_str_formatted}")
        return sufijo_calculado
    except Exception as e:
        logger.error(f"Error estableciendo rango de fechas o calculando sufijo: {e}", exc_info=True)
        return None

def _iniciar_descarga_y_manejar_popups(driver: webdriver.Chrome, wait: WebDriverWait) -> bool:
    """Inicia la descarga del archivo LAS y maneja las ventanas emergentes de confirmación."""
    logger.info("Iniciando descarga final (clic en 'Save')...")
    main_window_handle = driver.current_window_handle
    initial_handles = {main_window_handle} 
    descarga_iniciada_correctamente = False

    try:
        save_button_final = wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@name='ucDrillingRecorder$btnSave']")))
        save_button_final.click()
        logger.debug("Clic en botón 'Save' final realizado.")

        popup_1_handle = None 
        popup_2_handle = None 

        # --- Fase 1: Popup con botón "Yes" ---
        try:
            WebDriverWait(driver, 20).until(EC.number_of_windows_to_be(len(initial_handles) + 1))
            current_handles_after_save = set(driver.window_handles)
            new_handles = current_handles_after_save - initial_handles
            if not new_handles:
                logger.error("No se detectó la primera ventana emergente (para 'Yes') después de hacer clic en 'Save'.")
                return False
            
            popup_1_handle = new_handles.pop()
            driver.switch_to.window(popup_1_handle)
            logger.info(f"Ventana emergente 1 ('{driver.title}') detectada. Foco cambiado.")

            yes_button_xpath = "//input[@name='butYes']"
            yes_button = wait.until(EC.element_to_be_clickable((By.XPATH, yes_button_xpath)))
            yes_button.click() 
            logger.info("Clic en 'Yes' en la ventana emergente 1 realizado.")
            
        except TimeoutException:
            logger.error("Timeout esperando la primera ventana emergente ('Yes') o el botón 'Yes' dentro de ella.")
            return False 
        except NoSuchWindowException:
            logger.error("NoSuchWindowException al intentar manejar el primer popup ('Yes'). La ventana desapareció prematuramente.")
            return False

        # --- Fase 2: Popup con botón "Save File Now" (o descarga directa) ---
        logger.debug(f"Esperando {POPUP_TRANSITION_SLEEP_SEC}s para transición de popups...")
        time.sleep(POPUP_TRANSITION_SLEEP_SEC)

        try:
            all_current_handles = set(driver.window_handles)
            potential_popup_2_handles = all_current_handles - {main_window_handle}

            if potential_popup_2_handles:
                popup_2_handle = potential_popup_2_handles.pop()
                driver.switch_to.window(popup_2_handle) 
                logger.info(f"Ventana emergente 2 ('{driver.title}') detectada. Foco cambiado.")

                save_file_now_xpath = "//input[@value='Save File Now']"
                save_file_now_button = WebDriverWait(driver, 30).until(
                    EC.element_to_be_clickable((By.XPATH, save_file_now_xpath))
                )
                save_file_now_button.click()
                logger.info("Clic en 'Save File Now' realizado.")
                descarga_iniciada_correctamente = True
                logger.debug(f"Esperando {DOWNLOAD_START_WAIT_SEC}s para que la descarga inicie...")
                time.sleep(DOWNLOAD_START_WAIT_SEC) 
            else:
                logger.info("No se detectó una segunda ventana emergente. Se asume que la descarga inició después del clic en 'Yes'.")
                if main_window_handle in all_current_handles:
                    if driver.current_window_handle != main_window_handle:
                         driver.switch_to.window(main_window_handle)
                elif all_current_handles: 
                     if driver.current_window_handle != list(all_current_handles)[0]:
                         driver.switch_to.window(list(all_current_handles)[0])
                
                logger.debug(f"Esperando {DOWNLOAD_FALLBACK_WAIT_SEC}s (fallback) para que la descarga inicie...")
                time.sleep(DOWNLOAD_FALLBACK_WAIT_SEC) 
                descarga_iniciada_correctamente = True

        except TimeoutException: 
            logger.warning("Timeout esperando el botón 'Save File Now' en la segunda ventana emergente.")
            logger.info("Se asume que la descarga pudo haber comenzado. Esperando...")
            time.sleep(DOWNLOAD_FALLBACK_WAIT_SEC)
            descarga_iniciada_correctamente = True
        except NoSuchWindowException:
            logger.error("NoSuchWindowException al intentar manejar la segunda fase de popups. La ventana objetivo se cerró. Asumiendo descarga iniciada.")
            time.sleep(DOWNLOAD_FALLBACK_WAIT_SEC)
            descarga_iniciada_correctamente = True 
            
        return descarga_iniciada_correctamente

    except Exception as e: 
        logger.error(f"Error crítico no esperado en _iniciar_descarga_y_manejar_popups: {e}", exc_info=True)
        return False
    finally:
        try:
            all_handles_at_end = driver.window_handles 
            active_main_handle = main_window_handle
            if main_window_handle not in all_handles_at_end:
                logger.warning(f"La ventana principal original ('{main_window_handle}') ya no existe.")
                if all_handles_at_end: 
                    active_main_handle = all_handles_at_end[0] 
                    logger.info(f"Usando handle '{active_main_handle}' como referencia para la ventana principal.")
                else:
                    logger.error("No quedan ventanas abiertas para controlar en el finally.")

            for handle_to_check in list(driver.window_handles): 
                if handle_to_check != active_main_handle:
                    try:
                        driver.switch_to.window(handle_to_check)
                        logger.debug(f"Cerrando ventana popup residual: '{driver.title}' (handle: {handle_to_check})")
                        driver.close()
                    except NoSuchWindowException:
                        logger.debug(f"Ventana {handle_to_check} ya estaba cerrada al intentar cerrarla en finally.")
                    except Exception as e_close:
                        logger.warning(f"No se pudo cerrar una ventana popup residual '{handle_to_check}': {e_close}", exc_info=False)
            
            if active_main_handle in driver.window_handles:
                 if driver.current_window_handle != active_main_handle: 
                    driver.switch_to.window(active_main_handle)
                 logger.debug(f"Foco final en la ventana principal: '{driver.title}' (handle: {active_main_handle})")
            elif driver.window_handles: 
                if driver.current_window_handle != driver.window_handles[0]: 
                    driver.switch_to.window(driver.window_handles[0]) 
                logger.warning(f"Ventana principal original no encontrada. Foco final en: '{driver.title}'.")

        except NoSuchWindowException:
             logger.warning("Alguna ventana (posiblemente la principal de referencia) ya no existía al intentar finalizar el manejo de popups.")
        except Exception as e_final_switch:
            logger.error(f"Error en el bloque finally de manejo de popups: {e_final_switch}", exc_info=True)

def _wait_for_download_completion(download_dir: Path, timeout_sec: int) -> Optional[Path]:
    """
    Espera a que una descarga en el directorio especificado se complete.
    Busca la desaparición de archivos .crdownload y la estabilización del tamaño del archivo .las.
    """
    logger.info(f"Esperando descarga completa en {download_dir} (timeout: {timeout_sec}s)")
    start_time = time.monotonic()
    last_found_las: Optional[Path] = None

    while time.monotonic() - start_time < timeout_sec:
        crdownload_files = list(download_dir.glob("*.crdownload"))
        if crdownload_files:
            logger.debug(f"Descarga en progreso, detectados: {[f.name for f in crdownload_files]}")
            time.sleep(DOWNLOAD_CHECK_INTERVAL_SEC)
            continue

        las_files = sorted(download_dir.glob("*.las"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not las_files:
            logger.debug("No hay .crdownload ni .las. Esperando...")
            time.sleep(DOWNLOAD_CHECK_INTERVAL_SEC)
            continue
        
        current_las_file = las_files[0]
        
        previous_size = -1
        consecutive_stable_checks = 0 
        is_stable_and_valid = False

        for check_num in range(DOWNLOAD_SIZE_STABILITY_CHECKS):
            try:
                if not current_las_file.exists():
                    logger.debug(f"Archivo {current_las_file.name} desapareció durante chequeo de estabilidad {check_num + 1}.")
                    consecutive_stable_checks = 0 
                    break 
                
                current_size = current_las_file.stat().st_size
                if check_num == 0: 
                    previous_size = current_size
                    logger.debug(f"Archivo LAS potencial: {current_las_file.name}. Chequeo {check_num + 1}/{DOWNLOAD_SIZE_STABILITY_CHECKS}. Tamaño: {current_size}")
                elif current_size > 0 and current_size == previous_size:
                    consecutive_stable_checks += 1
                    logger.debug(f"Archivo LAS: {current_las_file.name}. Chequeo {check_num + 1}/{DOWNLOAD_SIZE_STABILITY_CHECKS}. Tamaño {current_size} estable. Checks estables consecutivos: {consecutive_stable_checks +1 }")
                else: 
                    logger.debug(f"Archivo LAS: {current_las_file.name}. Chequeo {check_num + 1}/{DOWNLOAD_SIZE_STABILITY_CHECKS}. Tamaño cambió de {previous_size} a {current_size}. Reseteando checks.")
                    previous_size = current_size 
                    consecutive_stable_checks = 0 
                
                if consecutive_stable_checks >= (DOWNLOAD_SIZE_STABILITY_CHECKS - 1) and current_size > 0 : 
                    is_stable_and_valid = True
                    logger.info(f"Archivo {current_las_file.name} considerado estable y válido con tamaño {current_size}.")
                    break 
                
                if check_num < DOWNLOAD_SIZE_STABILITY_CHECKS - 1: 
                    time.sleep(DOWNLOAD_SIZE_STABILITY_INTERVAL_SEC)

            except FileNotFoundError:
                logger.debug(f"FileNotFoundError para {current_las_file.name} durante chequeo {check_num + 1}.")
                consecutive_stable_checks = 0 
                break 
        
        if is_stable_and_valid:
            return current_las_file 
        else: 
            last_found_las = current_las_file 
            logger.debug(f"Archivo {current_las_file.name} (tamaño: {previous_size}) no se consideró estable tras {DOWNLOAD_SIZE_STABILITY_CHECKS} chequeos. Continuando espera en bucle principal...")
            time.sleep(DOWNLOAD_CHECK_INTERVAL_SEC) 
            
    if last_found_las and last_found_las.exists() and last_found_las.stat().st_size > 0 :
         logger.warning(f"Timeout esperando estabilidad del archivo ({timeout_sec}s). Usando el último archivo encontrado con tamaño > 0: {last_found_las.name} (tamaño: {last_found_las.stat().st_size})")
         return last_found_las

    logger.error(f"Timeout ({timeout_sec}s) o fallo esperando la descarga completa y estable del archivo LAS en {download_dir}.")
    return None

def _renombrar_archivo_descargado(download_dir: Path, rig_name_file: str, well_name_file: str, sufijo_nombre: str) -> Optional[str]:
    """Espera la descarga, encuentra el archivo .las más reciente y lo renombra."""
    logger.info(f"Iniciando proceso de espera y renombrado en: {download_dir}")
    latest_file = _wait_for_download_completion(download_dir, DOWNLOAD_COMPLETE_TIMEOUT_SEC)

    if not latest_file:
        return None

    file_size = latest_file.stat().st_size
    logger.info(f"Archivo .las final detectado: {latest_file.name} (Tamaño: {file_size} bytes)")
    if file_size < MIN_LAS_FILE_SIZE_BYTES: 
        logger.warning(f"Archivo .las encontrado ({latest_file.name}) es muy pequeño ({file_size} bytes, umbral: {MIN_LAS_FILE_SIZE_BYTES} bytes). Podría estar corrupto o vacío.")

    safe_rig_name = "".join(c if c.isalnum() or c in ['_', '-'] else "_" for c in rig_name_file)
    safe_well_name = "".join(c if c.isalnum() or c in ['_', '-'] else "_" for c in well_name_file)
    
    fecha_hora_actual = datetime.now().strftime("%d-%m-%Y_%H-%M")
    new_filename_stem = f"{safe_rig_name}_{safe_well_name}_{fecha_hora_actual}{sufijo_nombre}"
    new_filename = new_filename_stem + ".las"
    new_file_path = download_dir / new_filename

    try:
        logger.debug(f"Intentando renombrar '{latest_file.name}' a '{new_filename}'")
        latest_file.rename(new_file_path)
        logger.info(f"Archivo LAS renombrado exitosamente a: {new_filename}")
        return new_filename
    except OSError as e:
        logger.error(f"Error de OS al renombrar el archivo '{latest_file.name}' a '{new_filename}'. Puede estar en uso o permisos incorrectos.", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Error inesperado al renombrar el archivo '{latest_file.name}' a '{new_filename}'.", exc_info=True)
        return None

def descargar_las_para_rig(
    contractor_arg: str, rig_arg: str, rig_name_file_arg: str, well_name_file_arg: str, rig_type_arg: str,
    las_output_dir_arg: Path, headless_mode_arg: bool
) -> Optional[str]:
    """
    Orquesta el proceso completo de descarga de un archivo LAS para un rig específico.
    """
    driver, wait = _configurar_webdriver(las_output_dir_arg, headless_mode_arg)
    if not driver or not wait:
        logger.error("Fallo en la configuración inicial del WebDriver. No se puede continuar.")
        return None

    final_las_filename_or_status = None
    try:
        if not _login_welldata(driver, wait, WD_URL, WD_USERNAME, WD_PASSWORD): return None 
        if not _navegar_y_seleccionar_rig(driver, wait, contractor_arg, rig_arg): return None
        if not _configurar_parametros_descarga_las(driver, wait, rig_type_arg): return None
        
        sufijo_para_nombre = _establecer_rango_fechas_y_calcular_sufijo(driver, wait)
        if sufijo_para_nombre is None: 
            logger.error("No se pudo determinar el sufijo o establecer el rango de fechas críticamente.")
            return None
        if sufijo_para_nombre in ["NO_DOWNLOAD_MIN_DATE_TOO_RECENT"]: 
            logger.info(f"Descarga omitida para {contractor_arg} - {rig_arg} (Razón: {sufijo_para_nombre}).")
            final_las_filename_or_status = sufijo_para_nombre
            return final_las_filename_or_status

        if not _iniciar_descarga_y_manejar_popups(driver, wait):
            logger.warning("El proceso de iniciar la descarga y manejar popups reportó un fallo o no pudo confirmar el inicio. Se intentará renombrar de todas formas.")
        
        final_las_filename_or_status = _renombrar_archivo_descargado(
            las_output_dir_arg, rig_name_file_arg, well_name_file_arg, sufijo_para_nombre
        )
        if final_las_filename_or_status:
            logger.info(f"Proceso de descarga y renombrado para {contractor_arg}-{rig_arg} finalizado con archivo: {final_las_filename_or_status}")
        else:
            logger.error(f"Falló el renombrado del archivo LAS para {contractor_arg}-{rig_arg} o no se encontró el archivo después de la descarga.")
        return final_las_filename_or_status

    except Exception as e: 
        logger.error(f"Excepción no controlada en el flujo principal de descarga para el rig: {e}", exc_info=True)
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_contractor = "".join(c if c.isalnum() else "_" for c in contractor_arg)
            safe_rig = "".join(c if c.isalnum() else "_" for c in rig_arg)
            error_screenshot_path = LOGS_DIR / f"error_screenshot_{Path(__file__).stem}_{safe_contractor}_{safe_rig}_{timestamp}.png"
            if driver: 
                driver.save_screenshot(str(error_screenshot_path))
                logger.info(f"Captura de pantalla de error guardada en: {error_screenshot_path}")
        except Exception as e_ss:
            logger.error(f"No se pudo guardar captura de pantalla de error: {e_ss}")
        return None 
    finally:
        if driver:
            logger.debug("Cerrando WebDriver en descargar_las_para_rig...")
            try:
                driver.quit()
                logger.info("WebDriver cerrado.")
            except Exception as e_quit: 
                logger.error(f"Error al intentar cerrar WebDriver: {e_quit}", exc_info=True)
    
    return final_las_filename_or_status

def main():
    """Función principal que ejecuta el script."""
    if not load_wd_configuration(ENV_PATH): 
        sys.exit(EXIT_CODE_CONFIG_ERROR)

    logger.info(f"Iniciando proceso de descarga LAS para: C='{args.contractor}', R='{args.rig}', RN='{args.rig_name}', WN='{args.well_name}', T='{args.rig_type}'")
    
    nombre_final_o_estado = descargar_las_para_rig(
        args.contractor, args.rig, args.rig_name, args.well_name, args.rig_type,
        LAS_OUTPUT_DIR, HEADLESS_MODE
    )

    final_status_code = EXIT_CODE_GENERAL_ERROR 

    if nombre_final_o_estado:
        if nombre_final_o_estado in ["NO_DOWNLOAD_MIN_DATE_TOO_RECENT"]: 
            logger.info(f"Proceso completado con estado de no descarga: {nombre_final_o_estado}")
            print(f"ARCHIVO_LAS:{nombre_final_o_estado}:{args.contractor}-{args.rig}") 
            final_status_code = EXIT_CODE_SUCCESS
        else: 
            logger.info(f"Proceso completado exitosamente. Archivo LAS generado: {nombre_final_o_estado}")
            print(f"ARCHIVO_LAS:{nombre_final_o_estado}") 
            final_status_code = EXIT_CODE_SUCCESS
    else: 
        logger.error("El proceso de descarga del archivo LAS falló o no produjo un archivo/estado válido.")
        print(f"ARCHIVO_LAS:FALLO_DESCARGA:{args.contractor}-{args.rig}") 
        final_status_code = EXIT_CODE_DOWNLOAD_ERROR 

    logger.info(f"Finalizando script '{Path(__file__).name}' con código de salida: {final_status_code}")
    sys.exit(final_status_code)

if __name__ == "__main__":
    main()