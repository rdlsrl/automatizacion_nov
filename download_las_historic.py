#!/usr/bin/env python3
import os
import sys
import time
import glob
import shutil
import tempfile
from datetime import datetime, timedelta

import pymysql
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
import logging
# Cargar variables de entorno desde config.env
load_dotenv('config.env')

# Configuración de la base de datos
db_config = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
    "port": int(os.getenv("DB_PORT", 3306))
}

def obtener_registros_welldata():
    """
    Consulta la tabla well_data para obtener, del día de hoy y con status 'HISTORIC',
    cada registro individual, retornando contractor, rig, well_name, spud_date y latest_edr.
    Se formatea spud_date y latest_edr en el query para que tengan el formato '%d-%b-%y'.
    """
    query = """
    SELECT contractor, rig, well_name, 
           DATE_FORMAT(spud_date, '%d-%b-%y') AS spud_date,
           DATE_FORMAT(latest_edr, '%d-%b-%y') AS latest_edr
    FROM well_data
    WHERE status = 'HISTORIC'
      AND DATE(import_datetime) = CURDATE();
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
        with conn.cursor() as cursor:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Consultando well_data...")
            cursor.execute(query)
            registros = cursor.fetchall()
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Registros consultados: {len(registros)}.\n")
        conn.close()
        for rec in registros:
            rec['contractor'] = rec['contractor'].strip().upper()
            rec['rig'] = rec['rig'].strip().upper()
        return registros
    except Exception as e:
        print(f"Error al obtener registros de well_data: {e}")
        sys.exit(1)

def obtener_rigs_download_ultimos():
    """
    Consulta la tabla rigs_download para obtener los registros del día de hoy (según fecha_proceso)
    y, para cada equipo (contractor, rig), conserva el registro con fecha_proceso más reciente.
    """
    query = """
    SELECT contractor, rig, rig_name, fecha_inicial, fecha_final, archivo, estado, fecha_proceso
    FROM rigs_download
    WHERE DATE(fecha_proceso) = CURDATE()
    ORDER BY contractor, rig, fecha_proceso DESC;
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
        with conn.cursor() as cursor:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Consultando rigs_download...")
            cursor.execute(query)
            registros = cursor.fetchall()
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Registros consultados: {len(registros)}.\n")
        conn.close()
        for reg in registros:
            reg['contractor'] = reg['contractor'].strip().upper()
            reg['rig'] = reg['rig'].strip().upper()
        rigs_dict = {}
        for reg in registros:
            key = (reg['contractor'], reg['rig'])
            if key not in rigs_dict:
                rigs_dict[key] = reg
        return rigs_dict
    except Exception as e:
        print(f"Error al obtener rigs_download: {e}")
        sys.exit(1)

# ==========================================================================
# CONFIGURACIÓN GENERAL DE DESCARGAS
# ==========================================================================
prefs = {
    "download.default_directory": "/mnt/mariadb/autom_nov/",
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "safebrowsing.enabled": False,
    "plugins.always_open_pdf_externally": True
}
chrome_options = webdriver.ChromeOptions()
chrome_options.add_experimental_option("prefs", prefs)
chrome_options.add_argument("--headless")  # Quita headless para ver la navegación si lo prefieres
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--window-size=1920,1080")
temp_dir = tempfile.mkdtemp()
chrome_options.add_argument(f"--user-data-dir={temp_dir}")
service = Service("/usr/local/bin/chromedriver")
driver = webdriver.Chrome(service=service, options=chrome_options)
wait = WebDriverWait(driver, 20)

def take_screenshot(name):
    screenshot_dir = "screenshots"
    if not os.path.exists(screenshot_dir):
        os.makedirs(screenshot_dir)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(screenshot_dir, f"{name}_{timestamp}.png")
    driver.save_screenshot(path)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Captura guardada.")

def save_page_source(name):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = f"{name}_{timestamp}.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(driver.page_source)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Código fuente guardado.")

def login_to_welldata():
    # Obtener las variables de WellData desde config.env
    wd_url = os.getenv("WD_URL")
    wd_username = os.getenv("WD_USERNAME")
    wd_password = os.getenv("WD_PASSWORD")
    
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Iniciando sesión en WellData...")
    driver.get(wd_url)
    usuario_input = wait.until(EC.presence_of_element_located((By.ID, "ucLogin_txtUsername")))
    usuario_input.send_keys(wd_username)
    password_input = driver.find_element(By.ID, "ucLogin_txtPassword")
    password_input.send_keys(wd_password)
    driver.find_element(By.ID, "ucLogin_btnSubmit").click()
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Sesión iniciada.")

def navigate_to_well_search():
    driver.get("https://www.welldata.net/Wells/WellSearch.aspx")
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Acceso a 'Well Search' confirmado.")

def select_contractor_and_rig(contractor, rig):
    try:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Seleccionando equipo.")
        contractor_dropdown = wait.until(EC.presence_of_element_located((By.ID, "ucWellSearch_ddlContractor")))
        driver.execute_script("arguments[0].scrollIntoView(true);", contractor_dropdown)
        contractor_dropdown.click()
        contractor_option = wait.until(EC.presence_of_element_located(
            (By.XPATH, f"//option[contains(translate(text(), 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), '{contractor}')]")
        ))
        contractor_option.click()
        
        rig_dropdown = wait.until(EC.presence_of_element_located((By.ID, "ucWellSearch_ddlRig")))
        driver.execute_script("arguments[0].scrollIntoView(true);", rig_dropdown)
        rig_dropdown.click()
        rig_option = wait.until(EC.presence_of_element_located((By.XPATH, f"//option[text()='{rig}']")))
        rig_option.click()
        
        driver.find_element(By.ID, "ucWellSearch_cmdSearch").click()
    except Exception as e:
        print("Error en la selección de equipo.")
        raise

def scroll_to_bottom():
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

def extract_table_data():
    table = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table#ucWellList_DataGrid")))
    rows = table.find_elements(By.TAG_NAME, "tr")
    return rows[1:]

def click_matching_well(rows, expected_well, expected_spud_date, expected_rr):
    print(f"Buscando pozo con: Well = '{expected_well}', Spud Date = '{expected_spud_date}', RR = '{expected_rr}'")
    for row in rows:
        try:
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) < 6:
                continue
            well_name = cells[1].text.strip()
            spud_date = cells[4].text.strip()
            rr_date = cells[5].text.strip()
            print(f"Fila: Well = '{well_name}', Spud Date = '{spud_date}', RR = '{rr_date}'")
            if well_name == expected_well and spud_date == expected_spud_date and rr_date == expected_rr:
                link = cells[1].find_element(By.TAG_NAME, "a")
                link.click()
                print("Criterios coinciden. Se hizo click en el pozo.")
                return True
        except Exception as e:
            print("Error al verificar fila.")
    print("No se encontró ningún pozo que coincida con los criterios.")
    return False

def procesar_descarga(expected_well, rig_name, fecha_inicial_download, fecha_final_download):
    # Guardar la ventana principal para volver luego
    main_window = driver.current_window_handle

    # IFRAME Y PRIMER 'SAVE'
    iframe = wait.until(EC.presence_of_element_located((By.ID, "Frame1")))
    driver.switch_to.frame(iframe)
    save_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[@id='ucDrillingRecorderUV_HyperLink1']")))
    save_button.click()
    driver.switch_to.default_content()

    # 'ADD ALL' y configuración de resolución de tiempo
    try:
        print("Buscando botón 'Add All'...")
        add_all_button = wait.until(EC.element_to_be_clickable((By.ID, "ucDrillingRecorder_btnAddAll")))
        add_all_button.click()
        print("Se hizo clic en 'Add All'.")
        
        print("Configurando resolución de tiempo...")
        select_element = wait.until(EC.presence_of_element_located((By.ID, "ucDrillingRecorder_ddlResolutionTime")))
        select = Select(select_element)
        rig_type = "DEFAULT"  # Ajustar según necesidad
        if rig_type == "PER":
            select.select_by_visible_text("10 sec")
            print("Resolución configurada a '10 sec'.")
        elif rig_type in ["PUL", "WO"]:
            select.select_by_visible_text("5 sec")
            print("Resolución configurada a '5 sec'.")
        else:
            select.select_by_visible_text("5 sec")
            print("Resolución configurada a '5 sec' por defecto.")
    except Exception as e:
        print(f"Error al configurar 'Add All' o la resolución: {e}")
        driver.quit()
        sys.exit(1)

    # Seleccionar radio button "Range Date"
    range_date_radio = wait.until(EC.element_to_be_clickable((By.ID, "ucDrillingRecorder_rbRangeDate")))
    range_date_radio.click()
    print("Radio button 'Range Date' seleccionado.")

    # Obtener fechas actuales del pozo
    min_date_input = driver.find_element(By.ID, "ucDrillingRecorder_calStartDate_txtDate")
    max_date_input = driver.find_element(By.ID, "ucDrillingRecorder_calEndDate_txtDate")
    min_date_str = min_date_input.get_attribute("value")
    max_date_str = max_date_input.get_attribute("value")
    try:
        min_date = datetime.strptime(min_date_str, "%d-%B-%y")
        max_date = datetime.strptime(max_date_str, "%d-%B-%y")
    except Exception as e:
        print(f"Error al convertir las fechas del pozo: {e}")
        driver.quit()
        sys.exit(1)

    # Convertir fechas de rigs_download a datetime (si es necesario)
    try:
        if isinstance(fecha_inicial_download, datetime):
            fecha_inicial_download_dt = fecha_inicial_download
        else:
            fecha_inicial_download_dt = datetime.strptime(fecha_inicial_download, "%Y-%m-%d %H:%M:%S")
        if isinstance(fecha_final_download, datetime):
            fecha_final_download_dt = fecha_final_download
        else:
            fecha_final_download_dt = datetime.strptime(fecha_final_download, "%Y-%m-%d %H:%M:%S")
    except Exception as e:
        print(f"Error al convertir las fechas de rigs_download: {e}")
        driver.quit()
        sys.exit(1)

    # Ajustar fechas del pozo según rigs_download:
    if min_date < fecha_inicial_download_dt:
        min_date = fecha_inicial_download_dt
    if max_date > fecha_final_download_dt:
        max_date = fecha_final_download_dt

    print(f"Fecha mínima ajustada: {min_date.strftime('%d-%B-%y')}")
    print(f"Fecha máxima ajustada: {max_date.strftime('%d-%B-%y')}")

    # Determinar sufijo para el LAS:
    if min_date == fecha_inicial_download_dt:
        suffix = "_end"
    else:
        suffix = "_all"
    print(f"Sufijo para el LAS: {suffix}")

    # Establecer la hora de inicio en "0:00" (la hora final se deja sin modificar)
    Select(driver.find_element(By.ID, "ucDrillingRecorder_tsRangeDateStartTime_DropDownListHour")).select_by_value("0")
    Select(driver.find_element(By.ID, "ucDrillingRecorder_tsRangeDateStartTime_DropDownListMinute")).select_by_value("00")
    print("Hora de inicio establecida en '0:00'.")

    # Escribir la fecha mínima ajustada en el input (la fecha final se deja sin modificar)
    min_date_str_formatted = min_date.strftime("%d-%B-%y")
    driver.execute_script("arguments[0].value = '';", min_date_input)
    time.sleep(1)
    driver.execute_script("arguments[0].value = arguments[1];", min_date_input, min_date_str_formatted)
    min_date_input.send_keys(Keys.TAB)
    time.sleep(2)
    print(f"Fecha de inicio establecida: {min_date_str_formatted}")
    print(f"Fecha de fin (sin modificar): {max_date_str}")

    # Click final en Save
    save_button_final = wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@name='ucDrillingRecorder$btnSave']")))
    save_button_final.click()
    print("Clic final en 'Save' realizado.")
    time.sleep(5)

    # Manejo de ventana emergente: Si aparece, hacer clic en 'Yes' y luego en 'Save File Now'
    windows_before = driver.window_handles
    print(f"Ventanas antes del manejo de popup: {len(windows_before)}")
    if len(windows_before) > 1:
        driver.switch_to.window(windows_before[1])
        try:
            yes_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//input[@name='butYes']"))
            )
            yes_button.click()
            print("Clic en 'Yes' realizado.")
        except Exception as e:
            print("Error al hacer clic en 'Yes'.")
        time.sleep(10)
        windows_after = driver.window_handles
        driver.switch_to.window(windows_after[-1])
        print("Cambiado a la ventana de progreso.")
        try:
            save_file_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//input[@value='Save File Now']"))
            )
            save_file_button.click()
            print("Clic en 'Save File Now' realizado.")
        except Exception as e:
            print("Error al hacer clic en 'Save File Now'.")
        time.sleep(5)
    else:
        print("No apareció ventana emergente de 'Yes'.")
    
    # Volver a la ventana principal para renombrar
    driver.switch_to.window(main_window)
    driver.switch_to.default_content()

    # Renombrar archivo descargado
    download_dir = "/mnt/mariadb/autom_nov/"
    las_files = glob.glob(os.path.join(download_dir, "*.las"))
    if las_files:
        latest_file = max(las_files, key=os.path.getctime)
        fecha_hora = datetime.now().strftime("%d-%m-%Y_%H-%M")
        new_filename = f"{rig_name}_{expected_well}_{fecha_hora}{suffix}.las"
        os.rename(latest_file, os.path.join(download_dir, new_filename))
        print(f"Archivo descargado renombrado a: {new_filename}")
    else:
        print("No se encontró archivo LAS descargado.")
    
    # Cerrar ventanas emergentes adicionales después de renombrar
    main_window = driver.current_window_handle
    for handle in driver.window_handles:
        if handle != main_window:
            driver.switch_to.window(handle)
            driver.close()
    driver.switch_to.window(main_window)
    driver.switch_to.default_content()

def procesar_equipo(contractor, rig, expected_well, expected_spud_date, expected_rr, rig_name, fecha_inicial_download, fecha_final_download):
    try:
        navigate_to_well_search()
        select_contractor_and_rig(contractor, rig)
        scroll_to_bottom()
        rows = extract_table_data()
        if click_matching_well(rows, expected_well, expected_spud_date, expected_rr):
            procesar_descarga(expected_well, rig_name, fecha_inicial_download, fecha_final_download)
        else:
            print("No se encontró el pozo con los criterios establecidos.")
    except Exception as e:
        print("Error procesando el equipo.")
        take_screenshot("error_equipo")
        save_page_source("error_equipo_source")
    finally:
        navigate_to_well_search()
        time.sleep(2)

def main():
    try:
        login_to_welldata()
        time.sleep(3)
        rigs_dict = obtener_rigs_download_ultimos()
        registros_wd = obtener_registros_welldata()
        well_keys = set((rec['contractor'], rec['rig']) for rec in registros_wd)
        rigs_filtrados = {k: v for k, v in rigs_dict.items() if k in well_keys}

        print("Iniciando procesamiento de equipos...\n")
        for rec in registros_wd:
            contractor = rec['contractor']
            rig = rec['rig']
            expected_well = rec['well_name'].strip()
            expected_spud_date = rec['spud_date'] if rec['spud_date'] else ""
            expected_rr = rec['latest_edr'] if rec['latest_edr'] else ""

            key = (contractor, rig)
            if key not in rigs_filtrados:
                continue

            rig_rec = rigs_filtrados[key]
            fecha_inicial = rig_rec.get('fecha_inicial', 'N/D')
            fecha_final = rig_rec.get('fecha_final', 'N/D')
            rig_name = rig_rec.get('rig_name', '').strip()

            print(f"Equipo procesado: {contractor} - {rig}")
            print(f"Fechas de rigs_download: Inicio: {fecha_inicial}, Final: {fecha_final}")
            print(f"Criterios de búsqueda: Well = {expected_well}, Spud Date = {expected_spud_date}, RR = {expected_rr}\n")
            procesar_equipo(contractor, rig, expected_well, expected_spud_date, expected_rr, rig_name, fecha_inicial, fecha_final)
            print("-----------------------------------------------------\n")
    except Exception as e:
        print("Error en el proceso global.")
    finally:
        driver.quit()
        shutil.rmtree(temp_dir)
        print("Navegador cerrado y directorio temporal eliminado.")

if __name__ == '__main__':
    main()
