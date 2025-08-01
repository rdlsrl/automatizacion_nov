import logging
import os
import tempfile
import shutil
import time
from datetime import datetime, timedelta
import pymysql
import mysql.connector
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Importar funciones de fechas_history.py
from fechas_history import (
    procesar_datos,
    formatear_fecha,
    insertar_rigs_download,
    obtener_datos_equipos,
    buscar_archivos,
    obtener_archivo_mas_reciente,
    extraer_fecha_hora,
    obtener_end_datos
)

# Configurar logging básico
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Cargar variables desde config.env
load_dotenv('config.env')

# Configuración de la base de datos (se usará tanto para la operación normal como para los logs)
db_config = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
    "port": 3306
}

# =============================================================================
# FUNCIÓN PARA GUARDAR EL ESTADO DEL PROCESO EN LA TABLA DE LOGS (log_import_las)
# =============================================================================
def guardar_estado_proceso(nombre_script, archivo_las, estado, mensaje):
    """
    Inserta un registro en la tabla log_import_las con el estado del proceso.
    """
    try:
        conexion = mysql.connector.connect(
            host=db_config["host"],
            user=db_config["user"],
            password=db_config["password"],
            database=db_config["database"]
        )
        cursor = conexion.cursor()
        query = """
            INSERT INTO log_import_las (nombre_script, archivo_las, estado, mensaje, fecha)
            VALUES (%s, %s, %s, %s, NOW())
        """
        cursor.execute(query, (nombre_script, archivo_las, estado, mensaje))
        conexion.commit()
        cursor.close()
        conexion.close()
        logging.info("Estado del proceso guardado en log_import_las.")
    except Exception as e:
        logging.error(f"Error al guardar el estado del proceso en la base de datos: {e}")

# =============================================================================
# Configuración de WebDriver
# =============================================================================
prefs = {
    "download.default_directory": "/mnt/mariadb/autom_nov/",
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "safebrowsing.enabled": False,
    "plugins.always_open_pdf_externally": True
}

chrome_options = webdriver.ChromeOptions()
chrome_options.add_experimental_option("prefs", prefs)
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--window-size=1920,1080")

temp_dir = tempfile.mkdtemp()
chrome_options.add_argument(f"--user-data-dir={temp_dir}")

service = Service("/usr/local/bin/chromedriver")
driver = webdriver.Chrome(service=service, options=chrome_options)
wait = WebDriverWait(driver, 30)

# =============================================================================
# Funciones de operación con Selenium y procesamiento de datos
# =============================================================================
def take_screenshot(name):
    screenshot_dir = "screenshots"
    if not os.path.exists(screenshot_dir):
        os.makedirs(screenshot_dir)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    screenshot_path = f"{screenshot_dir}/{name}_{timestamp}.png"
    driver.save_screenshot(screenshot_path)
    logging.info(f"Captura de pantalla guardada: {screenshot_path}")

def save_page_source(name):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    page_source_path = f"{name}_{timestamp}.html"
    with open(page_source_path, "w", encoding="utf-8") as f:
        f.write(driver.page_source)
    logging.info(f"Código fuente guardado: {page_source_path}")

def login_to_welldata():
    logging.info("Iniciando sesión en WellData...")
    driver.get("https://www.welldata.net/Login.aspx?ReturnUrl=%2f")
    usuario_input = wait.until(EC.presence_of_element_located((By.ID, "ucLogin_txtUsername")))
    usuario_input.send_keys("mbarbieri")
    password_input = driver.find_element(By.ID, "ucLogin_txtPassword")
    password_input.send_keys("Rdlpae2024@")
    driver.find_element(By.ID, "ucLogin_btnSubmit").click()
    logging.info("Login enviado")

def navigate_to_well_search():
    logging.info("Navegando a 'Well Search'...")
    driver.get("https://www.welldata.net/Wells/WellSearch.aspx")
    logging.info("Acceso a 'Well Search' exitoso")

def select_contractor_and_rig(contractor, rig):
    logging.info("Seleccionando contractor y rig...")
    contractor_dropdown = wait.until(EC.presence_of_element_located((By.ID, "ucWellSearch_ddlContractor")))
    contractor_dropdown.click()
    contractor_option = wait.until(EC.presence_of_element_located(
        (By.XPATH, f"//option[contains(text(), '{contractor}')]")))
    contractor_option.click()
    logging.info(f"Contractor seleccionado: {contractor}")

    rig_dropdown = wait.until(EC.presence_of_element_located((By.ID, "ucWellSearch_ddlRig")))
    rig_dropdown.click()
    rig_option = wait.until(EC.presence_of_element_located(
        (By.XPATH, f"//option[text()='{rig}']")))
    rig_option.click()
    logging.info(f"Rig seleccionado: {rig}")

    driver.find_element(By.ID, "ucWellSearch_cmdSearch").click()
    logging.info("Búsqueda iniciada")

def sort_table_by_spud_date():
    logging.info("Ordenando tabla por 'Spud Date'...")
    try:
        spud_date_link = wait.until(EC.presence_of_element_located(
            (By.XPATH, "//a[contains(text(), 'Spud Date')]")))
        spud_date_link.click()
        time.sleep(2)
        logging.info("Tabla ordenada")
    except Exception as e:
        logging.error(f"Error al ordenar la tabla: {e}")
        take_screenshot("sort_table_error")
        save_page_source("sort_table_error_page_source")
        raise

def scroll_to_bottom():
    logging.info("Desplazando página...")
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            logging.info("Desplazamiento completado")
            break
        last_height = new_height

def wait_for_table():
    logging.info("Esperando a que se cargue la tabla...")
    try:
        table = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table#ucWellList_DataGrid")))
        logging.info("Tabla encontrada")
        return table
    except Exception as e:
        logging.error(f"No se encontró la tabla. Error: {e}")
        take_screenshot("table_not_found")
        save_page_source("table_not_found_page_source")
        raise

def extract_table_data(table):
    logging.info("Extrayendo datos de la tabla...")
    rows = table.find_elements(By.TAG_NAME, "tr")[1:]
    data = []
    for row in rows:
        try:
            cells = row.find_elements(By.TAG_NAME, "td")
            row_data = {
                "Operator": cells[0].text,
                "Well Name": cells[1].text,
                "Contractor": cells[2].text,
                "Rig": cells[3].text,
                "Spud Date": cells[4].text,
                "RR Date": cells[5].text,
            }
            data.append(row_data)
        except Exception as e:
            logging.error(f"Error al extraer una fila: {e}")
            continue
    logging.info(f"Datos extraídos: {len(data)} filas")
    return data

def filter_wells_by_date_range(data, start_date, end_date):
    logging.info("Filtrando pozos por rango de fechas...")
    filtered_data = []
    for row in data:
        try:
            if not row["Spud Date"] or not row["RR Date"]:
                logging.error(f"Fila omitida: Fechas vacías en {row}")
                continue
            spud_date = datetime.strptime(row["Spud Date"], "%d-%b-%y")
            rr_date = datetime.strptime(row["RR Date"], "%d-%b-%y")
            if (start_date <= spud_date <= end_date) or (start_date <= rr_date <= end_date):
                row["Spud Date Status"] = "Dentro del rango" if start_date <= spud_date <= end_date else "Fuera del rango"
                row["RR Date Status"] = "Dentro del rango" if start_date <= rr_date <= end_date else "Fuera del rango"
                filtered_data.append(row)
        except Exception as e:
            logging.error(f"Error al filtrar una fila: {e}")
            continue
    logging.info(f"Pozos filtrados: {len(filtered_data)} filas")
    return filtered_data

def insertar_well_data(data):
    """
    Inserta en la tabla well_data cada registro del resultado filtrado.
    """
    try:
        conn = pymysql.connect(
            host=db_config["host"],
            port=db_config["port"],
            user=db_config["user"],
            password=db_config["password"],
            database=db_config["database"],
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
    except Exception as e:
        logging.error(f"Error al conectar a la base de datos: {e}")
        return

    try:
        with conn.cursor() as cursor:
            query = """
            INSERT INTO well_data (operator, well_name, contractor, rig, spud_date, latest_edr, import_datetime, status, event_id, files_import_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """
            for row in data:
                operator = row.get("Operator")
                well_name = row.get("Well Name")
                contractor = row.get("Contractor")
                rig = row.get("Rig")
                try:
                    spud_date_obj = datetime.strptime(row.get("Spud Date"), "%d-%b-%y").date()
                except Exception as e:
                    logging.error(f"Error al convertir Spud Date '{row.get('Spud Date')}': {e}")
                    spud_date_obj = None
                try:
                    latest_edr_obj = datetime.strptime(row.get("RR Date"), "%d-%b-%y")
                except Exception as e:
                    logging.error(f"Error al convertir RR Date '{row.get('RR Date')}': {e}")
                    latest_edr_obj = None
                import_datetime = datetime.now()
                status = "HISTORIC"
                cursor.execute(query, (
                    operator, well_name, contractor, rig,
                    spud_date_obj, latest_edr_obj, import_datetime,
                    status, None, None
                ))
                logging.info(f"Insertado: {operator}, {well_name}, {contractor}, {rig}")
        conn.commit()
        logging.info("Registros insertados en well_data exitosamente.")
    except Exception as e:
        logging.error(f"Error durante la inserción en well_data: {e}")
    finally:
        conn.close()
        logging.info("Conexión cerrada a la base de datos.")

# =============================================================================
# Función principal
# =============================================================================
def main():
    script_name = "hist_bucle.py"  # Nombre del script para los logs
    try:
        # Primera parte: Ingresar a WellData y obtener datos históricos
        login_to_welldata()

        equipos_datos = procesar_datos()  # Diccionario con claves (contractor, rig, rig_name)
        logging.info("Datos de equipos obtenidos:")
        for key, info in equipos_datos.items():
            contractor, rig, rig_name = key
            logging.info(f"Contractor: {contractor} - Rig: {rig} - Rig Name: {rig_name}")
            logging.info(f"  Fecha inicial: {info['fecha_inicial']}")
            logging.info(f"  Fecha final: {info['fecha_final']}")

        logging.info("Insertando datos históricos en rigs_download...")
        insertar_rigs_download(equipos_datos)
        logging.info("Datos insertados en rigs_download exitosamente.")

        # Procesar cada equipo
        for key, info in equipos_datos.items():
            contractor, rig, rig_name = key
            try:
                logging.info(f"Procesando WellData para el equipo: {rig_name}")
                navigate_to_well_search()
                select_contractor_and_rig(contractor, rig)
                sort_table_by_spud_date()
                scroll_to_bottom()
                table = wait_for_table()
                data = extract_table_data(table)
                start_date = datetime.strptime(info["fecha_inicial"], "%Y-%m-%d %H:%M:%S")
                end_date = datetime.strptime(info["fecha_final"], "%Y-%m-%d %H:%M:%S")
                filtered_data = filter_wells_by_date_range(data, start_date, end_date)
                logging.info(f"Datos filtrados para {rig_name}: {filtered_data}")

                if filtered_data:
                    insertar_well_data(filtered_data)
                    guardar_estado_proceso(script_name, "N/A", "Éxito",
                        f"Procesamiento completado para {contractor} - {rig} - {rig_name}.")
                else:
                    guardar_estado_proceso(script_name, "N/A", "No Procesado",
                        f"No hay datos filtrados para {rig_name}.")
            except Exception as e:
                guardar_estado_proceso(script_name, "N/A", "Error",
                    f"Error al procesar {contractor} - {rig} - {rig_name}: {e}")
                logging.error(f"Error al procesar {contractor} - {rig} - {rig_name}: {e}")

    except Exception as e:
        guardar_estado_proceso(script_name, "N/A", "Error",
            f"Error en la ejecución principal: {e}")
        logging.error(f"Error en la ejecución principal: {e}")
    finally:
        driver.quit()
        shutil.rmtree(temp_dir, ignore_errors=True)
        logging.info("Navegador cerrado y directorio temporal eliminado.")

if __name__ == '__main__':
    main()
