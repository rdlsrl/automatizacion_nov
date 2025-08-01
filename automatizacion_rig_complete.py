from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from datetime import datetime, timedelta
from selenium.webdriver.common.keys import Keys
import mysql.connector
import time
import os

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
# CONECTAR A MARIADB Y OBTENER CONTRACTOR Y RIG
# ==========================================================================
conn = mysql.connector.connect(
    host="localhost",
    user="tu_usuario",
    password="tu_password",
    database="tu_base_de_datos"
)
cursor = conn.cursor()
cursor.execute("SELECT DISTINCT contractor, rig FROM well_data")
rigs_contractors = cursor.fetchall()
cursor.close()
conn.close()

print(f"🔄 Se encontraron {len(rigs_contractors)} combinaciones de Contractor y Rig")

# ==========================================================================
# PROCESAR CADA CONTRACTOR Y RIG
# ==========================================================================
for contractor, rig_number in rigs_contractors:
    print(f"🚀 Procesando Contractor: {contractor}, Rig: {rig_number}")

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
        # BUSCAR Y SELECCIONAR EL RIG
        # ==========================================================================
        try:
            rig_button = wait.until(EC.element_to_be_clickable((By.XPATH, f"//a[contains(text(), '{rig_number}')]")))
            rig_button.click()
            print(f"✅ Clic en el rig {rig_number} exitoso")
        except:
            print(f"⚠️ Rig {rig_number} NO encontrado en la página. Pasando al siguiente...")
            continue  # Saltar al siguiente contractor/rig

        wait.until(lambda d: d.execute_script('return document.readyState') == 'complete')

        # ==========================================================================
        # IFRAME Y PRIMER 'SAVE'
        # ==========================================================================
        iframe = wait.until(EC.presence_of_element_located((By.ID, "Frame1")))
        driver.switch_to.frame(iframe)

        save_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[@id='ucDrillingRecorderUV_HyperLink1']")))
        save_button.click()
        print("✅ Clic en 'Save' exitoso")

        driver.switch_to.default_content()

        # ==========================================================================
        # 'ADD ALL' + '5 sec'
        # ==========================================================================
        add_all_button = wait.until(EC.element_to_be_clickable((By.ID, "ucDrillingRecorder_btnAddAll")))
        add_all_button.click()
        print("✅ Clic en 'Add All' exitoso")

        select_element = wait.until(EC.presence_of_element_located((By.ID, "ucDrillingRecorder_ddlResolutionTime")))
        select = Select(select_element)
        select.select_by_visible_text("5 sec")
        print("✅ Opción '5 sec' seleccionada exitosamente")

        # ==========================================================================
        # FECHA DE INICIO Y FIN (19-20 FEBRERO 2025)
        # ==========================================================================
        start_date_input = driver.find_element(By.ID, "ucDrillingRecorder_calStartDate_txtDate")
        driver.execute_script("arguments[0].value = '19-February-25';", start_date_input)
        start_date_input.send_keys(Keys.TAB)

        end_date_input = driver.find_element(By.ID, "ucDrillingRecorder_calEndDate_txtDate")
        driver.execute_script("arguments[0].value = '20-February-25';", end_date_input)
        end_date_input.send_keys(Keys.TAB)

        print("✅ Fechas establecidas: Inicio = 19-February-25, Fin = 20-February-25")

        # ==========================================================================
        # SAVE FINAL
        # ==========================================================================
        save_button_final = wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@name='ucDrillingRecorder$btnSave']")))
        save_button_final.click()
        print("✅ Clic final en 'Save' exitoso")

        time.sleep(3)
        windows_before = driver.window_handles
        print(f"🪟 Ventanas antes del clic: {len(windows_before)}")

        if len(windows_before) > 1:
            driver.switch_to.window(windows_before[1])
            yes_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//input[@name='butYes']"))
            )
            yes_button.click()
            print("✅ Clic en 'Yes' realizado.")

            time.sleep(3)
            windows_after = driver.window_handles
            driver.switch_to.window(windows_after[-1])
            print("✅ Cambiado a la ventana de progreso.")

            save_file_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//input[@value='Save File Now']"))
            )
            save_file_button.click()
            print("✅ Clic en 'Save File Now' realizado.")
            time.sleep(5)

            # Renombrar archivo con Contractor y Rig
            download_path = "/mnt/mariadb/autom_nov/"
            files = os.listdir(download_path)
            if files:
                latest_file = max([os.path.join(download_path, f) for f in files], key=os.path.getctime)
                new_filename = f"{contractor}_{rig_number}_19_20_February_25.las"
                os.rename(latest_file, os.path.join(download_path, new_filename))
                print(f"✅ Archivo renombrado como: {new_filename}")

        else:
            print("⚠️ No apareció ventana emergente de 'Yes'. Posible error en la web.")

    except Exception as e:
        print(f"❌ Error con {contractor} - {rig_number}: {e}")

# Cerrar navegador al final
driver.quit()
