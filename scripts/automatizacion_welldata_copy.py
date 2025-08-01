from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from datetime import datetime, timedelta
from selenium.webdriver.common.keys import Keys
import sys
import time
import os
from dotenv import load_dotenv

# Cargar variables de entorno desde config.env
load_dotenv("/mnt/mariadb/autom_nov/config.env")

# ==========================================================================
# VALIDACIÓN DE PARÁMETROS DE ENTRADA
# ==========================================================================
if len(sys.argv) != 6:  # Ahora esperamos 6 parámetros
    print("✖ Error: Debes proporcionar Contractor, Rig, Rig Name, Well Name y Rig Type.")
    sys.exit(1)

contractor = sys.argv[1]
rig = sys.argv[2]
rig_name = sys.argv[3]
well_name = sys.argv[4]
rig_type = sys.argv[5]  # Nuevo parámetro: Rig Type

print(f"🚀 Ejecutando automatización para: Contractor={contractor}, Rig={rig}, Rig Name={rig_name}, Well Name={well_name}, Rig Type={rig_type}")

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
chrome_options.add_argument("--headless")  # Modo headless
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--window-size=1920,1080")

service = Service("/usr/local/bin/chromedriver")
driver = webdriver.Chrome(service=service, options=chrome_options)
wait = WebDriverWait(driver, 30)  # Aumentamos el tiempo de espera

try:
    # ==========================================================================
    # LOGIN A WELLDATA (CON DATOS DE config.env)
    # ==========================================================================
    print("🌐 Navegando a la URL de WellData...")
    driver.get(os.getenv("WD_URL"))  # URL de WellData desde config.env

    print("🔑 Ingresando credenciales...")
    usuario_input = wait.until(EC.presence_of_element_located((By.ID, "ucLogin_txtUsername")))
    usuario_input.send_keys(os.getenv("WD_USERNAME"))  # Usuario desde config.env
    driver.find_element(By.ID, "ucLogin_txtPassword").send_keys(os.getenv("WD_PASSWORD"))  # Contraseña desde config.env
    driver.find_element(By.ID, "ucLogin_btnSubmit").click()
    print("✔ Login exitoso.")

    # Esperar a que la página se cargue completamente
    wait.until(lambda d: d.execute_script('return document.readyState') == 'complete')
    print("🔄 Página de inicio cargada completamente.")

    # ==========================================================================
    # NAVEGAR A LA LISTA DE RIGS
    # ==========================================================================
    print("🔍 Buscando el menú 'Wells'...")
    wells_menu = wait.until(EC.visibility_of_element_located((By.XPATH, "//area[@href='/Wells/WellList.aspx']")))
    wells_menu.click()
    print("✔ Clic en 'Wells' exitoso")

    # Esperar a que la página de la lista de Rigs se cargue completamente
    wait.until(EC.title_contains("Well List"))
    print("🔄 Página de lista de Rigs cargada completamente.")

    # ==========================================================================
    # BUSCAR EL RIG Y CONTRACTOR EN LA TABLA
    # ==========================================================================
    print("🔍 Buscando el Rig y Contractor en la tabla...")
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
                print(f"✔ Encontrado: {contractor} - {rig}")
                cols[3].find_element(By.TAG_NAME, "a").click()
                break

    if not found:
        print(f"✖ No encontrado: {contractor} - {rig}, terminando ejecución...")
        driver.quit()
        sys.exit(1)

    # Esperar a que la página se cargue completamente
    wait.until(lambda d: d.execute_script('return document.readyState') == 'complete')
    print("🔄 Página del Rig seleccionado cargada completamente.")

    # ==========================================================================
    # IFRAME Y PRIMER 'SAVE'
    # ==========================================================================
    print("🖼 Cambiando al iframe...")
    iframe = wait.until(EC.presence_of_element_located((By.ID, "Frame1")))
    driver.switch_to.frame(iframe)

    print("💾 Haciendo clic en 'Save'...")
    save_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[@id='ucDrillingRecorderUV_HyperLink1']")))
    save_button.click()
    driver.switch_to.default_content()
    print("✔ Clic en 'Save' exitoso")

    # ==========================================================================
    # 'ADD ALL' + SETEO DE RESOLUCIÓN DE TIEMPO
    # ==========================================================================
    try:
        print("⚙ Configurando canales...")

        # 1. Remove All
        print("➖ Ejecutando Remove All...")
        remove_btn = wait.until(EC.element_to_be_clickable((By.ID, "ucDrillingRecorder_btnRemoveAll")))
        remove_btn.click()
        time.sleep(2)  # Espera para que se complete
        print("✔ Remove All ejecutado")

        # 2. Desmarcar checkbox
        print("🔘 Desmarcando checkbox...")
        checkbox = wait.until(EC.element_to_be_clickable((By.ID, "ucDrillingRecorder_cbOnlyShowActiveChannels")))
        if checkbox.is_selected():
            checkbox.click()
            print("✔ Checkbox desmarcado")

        # 3. Add All
        print("➕ Ejecutando Add All...")
        add_btn = wait.until(EC.element_to_be_clickable((By.ID, "ucDrillingRecorder_btnAddAll")))
        add_btn.click()
        time.sleep(2)  # Espera para que se complete
        print("✔ Add All ejecutado")

        # 4. Configurar resolución
        print("⏱ Configurando resolución...")
        select = Select(wait.until(EC.presence_of_element_located((By.ID, "ucDrillingRecorder_ddlResolutionTime"))))
        if rig_type in ["PER", "WO"]:
            select.select_by_visible_text("30 sec")
            print("✔ Resolución: 30 sec")
        elif rig_type == "PUL":
            select.select_by_visible_text("5 sec")
            print("✔ Resolución: 5 sec")
        else:
            select.select_by_visible_text("5 sec")  # Valor por defecto
            print("⚠ rig_type no reconocido. Se usa 5 sec por defecto.")

    except Exception as e:
        print(f"✖ Error al configurar canales: {e}")
        driver.save_screenshot("/mnt/mariadb/autom_nov/error_canales.png")
        raise

    # ==========================================================================
    # SELECCIONAR RADIO BUTTON "RANGE DATE"
    # ==========================================================================
    print("📅 Seleccionando 'Range Date'...")
    range_date_radio = wait.until(EC.element_to_be_clickable((By.ID, "ucDrillingRecorder_rbRangeDate")))
    range_date_radio.click()
    print("✔ Radio button 'Range Date' seleccionado.")

    # ==========================================================================
    # OBTENER FECHAS MÍNIMA Y MÁXIMA DEL POZO
    # ==========================================================================
    print("📆 Obteniendo fechas mínima y máxima...")
    min_date_input = driver.find_element(By.ID, "ucDrillingRecorder_calStartDate_txtDate")
    max_date_input = driver.find_element(By.ID, "ucDrillingRecorder_calEndDate_txtDate")

    min_date_str = min_date_input.get_attribute("value")
    max_date_str = max_date_input.get_attribute("value")

    # Convertir fechas a objetos datetime
    min_date = datetime.strptime(min_date_str, "%d-%B-%y")
    today = datetime.now()
    yesterday = today - timedelta(days=1)

    # Validar si la fecha mínima es hoy
    if min_date.date() == today.date():
        print("⚠ La fecha mínima es hoy. No se descargará ningún archivo.")
        driver.quit()
        sys.exit(0)

    # Calcular diferencia en días
    diferencia_dias = (yesterday - min_date).days

    # Si la fecha de ayer es igual a la fecha mínima, agregar "_nws"
    if diferencia_dias == 0:
        print("📌 La fecha de ayer es igual a la fecha mínima. Se agregará '_nws' al nombre del archivo.")
        diferencia_dias = "nws"
    else:
        diferencia_dias = str(diferencia_dias)  # Sin restar 1

    print(f"📌 Diferencia en días (ayer - fecha mínima): {diferencia_dias}")

    # ==========================================================================
    # ESTABLECER HORAS DE INICIO Y FIN EN "0:00"
    # ==========================================================================
    print("⏰ Estableciendo horas de inicio y fin en '0:00'...")
    Select(driver.find_element(By.ID, "ucDrillingRecorder_tsRangeDateStartTime_DropDownListHour")).select_by_value("0")
    Select(driver.find_element(By.ID, "ucDrillingRecorder_tsRangeDateStartTime_DropDownListMinute")).select_by_value("00")
    Select(driver.find_element(By.ID, "ucDrillingRecorder_tsRangeDateEndTime_DropDownListHour")).select_by_value("0")
    Select(driver.find_element(By.ID, "ucDrillingRecorder_tsRangeDateEndTime_DropDownListMinute")).select_by_value("00")
    print("✔ Horas establecidas en '0:00'.")

    # ==========================================================================
    # ESTABLECER FECHAS DE AYER Y HOY
    # ==========================================================================
    print("📅 Estableciendo fechas de ayer y hoy...")
    yesterday_str = yesterday.strftime("%d-%B-%y")
    today_str = today.strftime("%d-%B-%y")

    driver.execute_script("arguments[0].value = '';", min_date_input)
    time.sleep(1)
    driver.execute_script(f"arguments[0].value = '{yesterday_str}';", min_date_input)
    min_date_input.send_keys(Keys.TAB)
    time.sleep(2)

    driver.execute_script("arguments[0].value = '';", max_date_input)
    time.sleep(1)
    driver.execute_script(f"arguments[0].value = '{today_str}';", max_date_input)
    max_date_input.send_keys(Keys.TAB)
    time.sleep(2)

    print(f"📌 Fechas establecidas: Inicio={yesterday_str}, Fin={today_str}")

    # ==========================================================================
    # SAVE FINAL
    # ==========================================================================
    print("💾 Haciendo clic en 'Save' final...")
    save_button_final = wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@name='ucDrillingRecorder$btnSave']")))
    save_button_final.click()
    print("✔ Clic final en 'Save' exitoso")

    # Manejo de ventanas emergentes
    print("🪟 Verificando ventanas emergentes...")
    windows_before = driver.window_handles
    print(f"📂 Ventanas antes del clic: {len(windows_before)}")

    if len(windows_before) > 1:
        driver.switch_to.window(windows_before[1])
        yes_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//input[@name='butYes']"))
        )
        yes_button.click()
        print("✔ Clic en 'Yes' realizado.")

        time.sleep(10)
        windows_after = driver.window_handles
        driver.switch_to.window(windows_after[-1])
        print("✔ Cambiado a la ventana de progreso.")

        save_file_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//input[@value='Save File Now']"))
        )
        save_file_button.click()
        print("✔ Clic en 'Save File Now' realizado.")
        time.sleep(5)

        # Renombrar archivo descargado
        download_path = "/mnt/mariadb/autom_nov/"
        files = os.listdir(download_path)
        if files:
            latest_file = max([os.path.join(download_path, f) for f in files], key=os.path.getctime)
            fecha_hora = datetime.now().strftime("%d-%m-%Y_%H-%M")

            if diferencia_dias == "nws":
                new_filename = f"{rig_name}_{well_name}_{fecha_hora}_nws.las"
            else:
                new_filename = f"{rig_name}_{well_name}_{fecha_hora}_{diferencia_dias}.las"

            os.rename(latest_file, os.path.join(download_path, new_filename))
            print(f"✔ Archivo renombrado como: {new_filename}")
        else:
            print("⚠ No se encontraron archivos descargados.")

    else:
        print("⚠ No aparecieron ventanas emergentes de 'Yes'. Posible error en la web.")

except Exception as e:
    print(f"✖ Error en la ejecución: {e}")
    driver.save_screenshot("/mnt/mariadb/autom_nov/error_general.png")  # Guardar captura de pantalla en caso de error

finally:
    # Cerrar navegador al final
    driver.quit()
    print("🛑 Navegador cerrado.")
print(f"ARCHIVO_LAS:{new_filename}")
