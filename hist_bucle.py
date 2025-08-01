from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime, timedelta
import tempfile
import os
import shutil
import time
import pymysql
from dotenv import load_dotenv

# Importamos las funciones necesarias desde fechas_history
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

# Cargar variables desde config.env
load_dotenv('config.env')

# Configuración de la base de datos
db_config = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
    "port": 3306
}

# Configuración general de WebDriver
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

def take_screenshot(name):
    screenshot_dir = "screenshots"
    if not os.path.exists(screenshot_dir):
        os.makedirs(screenshot_dir)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    screenshot_path = f"{screenshot_dir}/{name}_{timestamp}.png"
    driver.save_screenshot(screenshot_path)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✓ Captura de pantalla guardada: {screenshot_path}")

def save_page_source(name):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    page_source_path = f"{name}_{timestamp}.html"
    with open(page_source_path, "w", encoding="utf-8") as f:
        f.write(driver.page_source)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✓ Código fuente guardado: {page_source_path}")

def login_to_welldata():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔍 Iniciando sesión en WellData...")
    driver.get("https://www.welldata.net/Login.aspx?ReturnUrl=%2f")
    usuario_input = wait.until(EC.presence_of_element_located((By.ID, "ucLogin_txtUsername")))
    usuario_input.send_keys("mbarbieri")
    password_input = driver.find_element(By.ID, "ucLogin_txtPassword")
    password_input.send_keys("Rdlpae2024@")
    driver.find_element(By.ID, "ucLogin_btnSubmit").click()
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✓ Login enviado")

def navigate_to_well_search():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔍 Navegando a 'Well Search'...")
    driver.get("https://www.welldata.net/Wells/WellSearch.aspx")
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✓ Acceso a 'Well Search' exitoso")

def select_contractor_and_rig(contractor, rig):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔍 Seleccionando contractor y rig...")
    contractor_dropdown = wait.until(EC.presence_of_element_located((By.ID, "ucWellSearch_ddlContractor")))
    contractor_dropdown.click()
    contractor_option = wait.until(EC.presence_of_element_located(
        (By.XPATH, f"//option[contains(text(), '{contractor}')]")))
    contractor_option.click()
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✓ Contractor seleccionado: {contractor}")

    rig_dropdown = wait.until(EC.presence_of_element_located((By.ID, "ucWellSearch_ddlRig")))
    rig_dropdown.click()
    rig_option = wait.until(EC.presence_of_element_located(
        (By.XPATH, f"//option[text()='{rig}']")))
    rig_option.click()
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✓ Rig seleccionado: {rig}")

    driver.find_element(By.ID, "ucWellSearch_cmdSearch").click()
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✓ Búsqueda iniciada")

def sort_table_by_spud_date():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔍 Ordenando tabla por 'Spud Date'...")
    try:
        spud_date_link = wait.until(EC.presence_of_element_located(
            (By.XPATH, "//a[contains(text(), 'Spud Date')]")))
        spud_date_link.click()
        time.sleep(2)
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✓ Tabla ordenada.")
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✗ Error al ordenar la tabla: {e}")
        take_screenshot("sort_table_error")
        save_page_source("sort_table_error_page_source")
        raise

def scroll_to_bottom():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔍 Desplazando página...")
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✓ Desplazamiento completado.")
            break
        last_height = new_height

def wait_for_table():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔍 Esperando a que se cargue la tabla...")
    try:
        table = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "table#ucWellList_DataGrid")))
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✓ Tabla encontrada.")
        return table
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✗ No se encontró la tabla. Error: {e}")
        take_screenshot("table_not_found")
        save_page_source("table_not_found_page_source")
        raise

def extract_table_data(table):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔍 Extrayendo datos de la tabla...")
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
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✗ Error al extraer una fila: {e}")
            continue
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✓ Datos extraídos: {len(data)} filas.")
    return data

def filter_wells_by_date_range(data, start_date, end_date):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔍 Filtrando pozos por rango de fechas...")
    filtered_data = []
    for row in data:
        try:
            if not row["Spud Date"] or not row["RR Date"]:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✗ Fila omitida: Fechas vacías en {row}")
                continue
            spud_date = datetime.strptime(row["Spud Date"], "%d-%b-%y")
            rr_date = datetime.strptime(row["RR Date"], "%d-%b-%y")
            if (start_date <= spud_date <= end_date) or (start_date <= rr_date <= end_date):
                row["Spud Date Status"] = "Dentro del rango" if start_date <= spud_date <= end_date else "Fuera del rango"
                row["RR Date Status"] = "Dentro del rango" if start_date <= rr_date <= end_date else "Fuera del rango"
                filtered_data.append(row)
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✗ Error al filtrar una fila: {e}")
            continue
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✓ Pozos filtrados: {len(filtered_data)} filas.")
    return filtered_data

def convert_date(date_str):
    if not date_str:
        return None
    try:
        date_obj = datetime.strptime(date_str, "%d-%b-%y")
        return date_obj.strftime("%Y-%m-%d")
    except Exception as e:
        print(f"Error al convertir la fecha {date_str}: {e}")
        return None

def insertar_well_data(data):
    """
    Inserta en la tabla well_data cada registro del resultado filtrado.
    Se insertan los siguientes campos:
      - operator, well_name, contractor, rig
      - spud_date: se convierte a date
      - latest_edr: se toma el valor de 'RR Date' convertido a datetime
      - import_datetime: fecha y hora actual
      - status: se fija en "HISTORIC"
      - event_id y files_import_id se dejan como NULL
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
        print(f"✗ Error al conectar a la base de datos: {e}")
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
                    print(f"Error al convertir Spud Date '{row.get('Spud Date')}': {e}")
                    spud_date_obj = None
                try:
                    latest_edr_obj = datetime.strptime(row.get("RR Date"), "%d-%b-%y")
                except Exception as e:
                    print(f"Error al convertir RR Date '{row.get('RR Date')}': {e}")
                    latest_edr_obj = None

                import_datetime = datetime.now()
                status = "HISTORIC"
                cursor.execute(query, (operator, well_name, contractor, rig, spud_date_obj, latest_edr_obj, import_datetime, status, None, None))
        conn.commit()
        print("✓ Registros insertados en well_data exitosamente.")
    except Exception as e:
        print(f"✗ Error durante la inserción en well_data: {e}")
    finally:
        conn.close()
        print("Conexión cerrada a la base de datos.")

def main():
    try:
        # Primera parte: Ingresar a WellData y obtener datos históricos
        login_to_welldata()
        
        # Se obtienen los datos históricos de cada equipo (fechas, archivos, etc.)
        equipos_datos = procesar_datos()  # Diccionario con claves (contractor, rig, rig_name)
        print("Datos de equipos obtenidos:")
        for key, info in equipos_datos.items():
            contractor, rig, rig_name = key
            print(f"Contractor: {contractor} - Rig: {rig} - Rig Name: {rig_name}")
            print(f"  Fecha inicial: {info['fecha_inicial']}")
            print(f"  Fecha final: {info['fecha_final']}\n")
        
        # Primero, insertamos en rigs_download los datos históricos
        print("\nInsertando datos históricos en rigs_download...")
        insertar_rigs_download(equipos_datos)
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✓ Datos insertados en rigs_download exitosamente.")
        
        # Luego, para cada equipo, se procesa la información en WellData
        for key, info in equipos_datos.items():
            contractor, rig, rig_name = key
            print(f"\nProcesando WellData para el equipo: {rig_name}")
            navigate_to_well_search()
            select_contractor_and_rig(contractor, rig)
            sort_table_by_spud_date()
            scroll_to_bottom()
            table = wait_for_table()
            data = extract_table_data(table)
            
            # Convertir las fechas para filtrar la tabla
            start_date = datetime.strptime(info["fecha_inicial"], "%Y-%m-%d %H:%M:%S")
            end_date = datetime.strptime(info["fecha_final"], "%Y-%m-%d %H:%M:%S")
            filtered_data = filter_wells_by_date_range(data, start_date, end_date)
            
            print(f"Datos filtrados para {rig_name}:")
            for row in filtered_data:
                print(row)
            
            # Inserción en la tabla well_data de cada registro filtrado
            insertar_well_data(filtered_data)
            
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✗ Error durante la ejecución: {e}")
        take_screenshot("error")
        save_page_source("error_page_source")
    finally:
        driver.quit()
        shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✓ Navegador cerrado y directorio temporal eliminado.")

if __name__ == '__main__':
    main()
