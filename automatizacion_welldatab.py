from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from datetime import datetime, timedelta
from selenium.webdriver.common.keys import Keys
import time
import os
import sys

# ========================================================================== 
# CONFIGURACIÓN GENERAL
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
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--window-size=1920,1080")

service = Service("/usr/local/bin/chromedriver")
driver = webdriver.Chrome(service=service, options=chrome_options)
wait = WebDriverWait(driver, 20)

# ========================================================================== 
# VALIDAR PARÁMETROS RECIBIDOS
# ========================================================================== 
if len(sys.argv) != 5:
    print("❌ Error: Debes proporcionar Contractor, Rig, Rig Name y Well Name.")
    sys.exit(1)

contractor = sys.argv[1]
rig = sys.argv[2]
rig_name = sys.argv[3]
well_name = sys.argv[4]

print(f"🚀 Ejecutando automatización para: Contractor={contractor}, Rig={rig}, Rig Name={rig_name}, Well Name={well_name}")

try:
    # ========================================================================== 
    # LOGIN A WELLDATA
    # ========================================================================== 
    driver.get("https://www.welldata.net/Login.aspx?ReturnUrl=%2f")
    usuario_input = wait.until(EC.presence_of_element_located((By.ID, "ucLogin_txtUsername")))
    usuario_input.send_keys("mbarbieri")
    driver.find_element(By.ID, "ucLogin_txtPassword").send_keys("Rdlpae2024@")
    driver.find_element(By.ID, "ucLogin_btnSubmit").click()

    # ========================================================================== 
    # NAVEGAR A LA LISTA DE RIGS
    # ========================================================================== 
    wells_menu = wait.until(EC.element_to_be_clickable((By.XPATH, "//area[@href='/Wells/WellList.aspx']")))
    wells_menu.click()
    print("✅ Clic en 'Wells' exitoso")
    wait.until(EC.title_contains("Well List"))

    # ========================================================================== 
    # BUSCAR EL RIG Y CONTRACTOR EN LA TABLA
    # ========================================================================== 
    wait.until(EC.presence_of_element_located((By.ID, "ucWellList_DataGrid")))
    rows = driver.find_elements(By.XPATH, "//table[@id='ucWellList_DataGrid']/tbody/tr")
    found = False

    for row in rows:
        cols = row.find_elements(By.TAG_NAME, "td")
        if len(cols) >= 4:
            web_contractor = cols[2].text.strip().lower()
            web_rig = cols[3].text.strip().lower()
            print(f"🔍 Comparando: {web_contractor} - {web_rig} con {contractor.lower()} - {rig.lower()}")
            
            if web_contractor == contractor.lower() and web_rig == rig.lower():
                found = True
                print(f"✅ Encontrado: {contractor} - {rig}")
                cols[3].find_element(By.TAG_NAME, "a").click()
                break

    if not found:
        print(f"❌ No encontrado: {contractor} - {rig}, terminando ejecución...")
        driver.quit()
        sys.exit(1)

    wait.until(lambda d: d.execute_script('return document.readyState') == 'complete')

    # ========================================================================== 
    # IFRAME Y PRIMER 'SAVE'
    # ========================================================================== 
    iframe = wait.until(EC.presence_of_element_located((By.ID, "Frame1")))
    driver.switch_to.frame(iframe)

    save_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[@id='ucDrillingRecorderUV_HyperLink1']")))
    save_button.click()
    driver.switch_to.default_content()

    # ========================================================================== 
    # 'ADD ALL' + '5 sec'
    # ========================================================================== 
    add_all_button = wait.until(EC.element_to_be_clickable((By.ID, "ucDrillingRecorder_btnAddAll")))
    add_all_button.click()

    select_element = wait.until(EC.presence_of_element_located((By.ID, "ucDrillingRecorder_ddlResolutionTime")))
    select = Select(select_element)
    select.select_by_visible_text("5 sec")

    # ========================================================================== 
    # FECHA DE INICIO Y FIN = AYER Y HOY (Forzado con JS + Selección de Horas)
    # ========================================================================== 

    # Obtener las fechas de ayer y hoy en el formato requerido por la web
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%d-%B-%y")  
    today_str = datetime.now().strftime("%d-%B-%y")  

    # Seleccionar el checkbox "Range Date" si es necesario
    try:
        range_checkbox = driver.find_element(By.ID, "ucDrillingRecorder_chkDateRange")
        if not range_checkbox.is_selected():
            range_checkbox.click()
            time.sleep(1)
    except Exception as e:
        print(f"⚠️ No se encontró o no se necesitó seleccionar 'Range Date': {e}")

    # Ingresar la fecha de inicio (ayer)
    start_date_input = driver.find_element(By.ID, "ucDrillingRecorder_calStartDate_txtDate")
    driver.execute_script("arguments[0].value = '';", start_date_input)
    time.sleep(1)
    driver.execute_script(f"arguments[0].value = '{yesterday_str}';", start_date_input)
    start_date_input.send_keys(Keys.TAB)
    time.sleep(2)

    # Ingresar la fecha de fin (hoy)
    end_date_input = driver.find_element(By.ID, "ucDrillingRecorder_calEndDate_txtDate")
    driver.execute_script("arguments[0].value = '';", end_date_input)
    time.sleep(1)
    driver.execute_script(f"arguments[0].value = '{today_str}';", end_date_input)
    end_date_input.send_keys(Keys.TAB)
    time.sleep(2)

    print("✅ Fechas y horas establecidas correctamente.")

    # ========================================================================== 
    # SAVE FINAL
    # ========================================================================== 
    save_button_final = wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@name='ucDrillingRecorder$btnSave']")))
    save_button_final.click()
    print("✅ Clic final en 'Save' exitoso")

    time.sleep(3)

except Exception as e:
    print(f"❌ Error en la ejecución: {e}")

# Cerrar navegador al final
driver.quit()
