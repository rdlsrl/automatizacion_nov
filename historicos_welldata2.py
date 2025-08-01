from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from datetime import datetime
import tempfile
import os
import shutil
import time
import csv

# Configuración general de WebDriver
prefs = {
    "download.default_directory": "/mnt/mariadb/autom_nov/",  # Directorio de descarga
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

# Crear un directorio temporal único para el perfil de Chrome
temp_dir = tempfile.mkdtemp()
chrome_options.add_argument(f"--user-data-dir={temp_dir}")

service = Service("/usr/local/bin/chromedriver")
driver = webdriver.Chrome(service=service, options=chrome_options)
wait = WebDriverWait(driver, 30)  # Aumentamos el tiempo de espera a 30 segundos


def take_screenshot(name):
    """Captura una pantalla y la guarda en la carpeta 'screenshots'."""
    screenshot_dir = "screenshots"
    if not os.path.exists(screenshot_dir):
        os.makedirs(screenshot_dir)
    driver.save_screenshot(f"{screenshot_dir}/{name}.png")
    print(f"✔ Captura de pantalla guardada: {screenshot_dir}/{name}.png")


def save_page_source(name):
    """Guarda el código fuente de la página en un archivo HTML."""
    with open(f"{name}.html", "w", encoding="utf-8") as f:
        f.write(driver.page_source)
    print(f"✔ Código fuente guardado: {name}.html")


def export_table_to_html(table, name):
    """Exporta el contenido de la tabla a un archivo HTML."""
    table_html = table.get_attribute("outerHTML")
    with open(f"{name}.html", "w", encoding="utf-8") as f:
        f.write(table_html)
    print(f"✔ Tabla exportada: {name}.html")


def login_to_welldata():
    """Inicia sesión en WellData."""
    print("🌐 Iniciando sesión en WellData...")
    driver.get("https://www.welldata.net/Login.aspx?ReturnUrl=%2f")

    # Ingresar usuario
    usuario_input = wait.until(EC.presence_of_element_located((By.ID, "ucLogin_txtUsername")))
    usuario_input.send_keys("mbarbieri")
    print("✔ Usuario ingresado")

    # Ingresar contraseña
    password_input = driver.find_element(By.ID, "ucLogin_txtPassword")
    password_input.send_keys("Rdlpae2024@")
    print("✔ Contraseña ingresada")

    # Hacer clic en el botón de login
    driver.find_element(By.ID, "ucLogin_btnSubmit").click()
    print("✔ Login enviado")


def navigate_to_well_search():
    """Navega a la página de 'Well Search'."""
    print("🌐 Navegando directamente a 'Well Search'...")
    driver.get("https://www.welldata.net/Wells/WellSearch.aspx")
    print("✔ Acceso a 'Well Search' exitoso")


def select_contractor_and_rig(contractor_name, rig_name):
    """Selecciona un contractor y un rig antes de realizar la búsqueda."""
    print("🌐 Seleccionando contractor y rig...")

    # Seleccionar el contractor
    contractor_dropdown = wait.until(EC.presence_of_element_located((By.ID, "ucWellSearch_ddlContractor")))
    contractor_dropdown.click()
    contractor_option = wait.until(EC.presence_of_element_located((By.XPATH, f"//option[contains(text(), '{contractor_name}')]")))
    contractor_option.click()
    print(f"✔ Contractor seleccionado: {contractor_name}")

    # Seleccionar el rig
    rig_dropdown = wait.until(EC.presence_of_element_located((By.ID, "ucWellSearch_ddlRig")))
    rig_dropdown.click()
    
    # Buscar el rig exacto (evitar coincidencias parciales como "161" para "61")
    rig_option = wait.until(EC.presence_of_element_located((By.XPATH, f"//option[text()='{rig_name}']")))
    rig_option.click()
    print(f"✔ Rig seleccionado: {rig_name}")

    # Hacer clic en el botón de búsqueda
    search_button = driver.find_element(By.ID, "ucWellSearch_cmdSearch")
    search_button.click()
    print("✔ Búsqueda iniciada")


def sort_table_by_spud_date():
    """Ordena la tabla por la columna 'Spud Date' en orden decreciente."""
    print("🌐 Ordenando la tabla por 'Spud Date' en orden decreciente...")

    try:
        # Esperar a que el enlace de 'Spud Date' esté presente
        spud_date_link = wait.until(
            EC.presence_of_element_located((By.XPATH, "//a[contains(text(), 'Spud Date')]"))
        )
        print("✔ Enlace 'Spud Date' encontrado.")

        # Hacer clic en el enlace para ordenar
        spud_date_link.click()
        print("✔ Clic en el enlace 'Spud Date' realizado.")

        # Esperar un momento para que la tabla se ordene
        time.sleep(2)  # Ajusta este tiempo si es necesario
        print("✔ Tabla ordenada por 'Spud Date'.")
    except Exception as e:
        print(f"❌ Error al ordenar la tabla por 'Spud Date': {e}")
        take_screenshot("sort_table_error")
        save_page_source("sort_table_error_page_source")
        raise  # Relanzar la excepción para detener la ejecución


def scroll_to_bottom():
    """Desplaza la página hasta el final para cargar todos los elementos."""
    print("🌐 Desplazando la página para cargar todos los pozos...")
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        # Desplazar hacia abajo
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)  # Esperar a que se carguen nuevos elementos

        # Obtener la nueva altura después del desplazamiento
        new_height = driver.execute_script("return document.body.scrollHeight")

        # Si no hay más desplazamiento, salir del bucle
        if new_height == last_height:
            print("✔ Desplazamiento completado.")
            break
        last_height = new_height


def wait_for_table():
    """Espera a que la tabla de pozos se cargue y la devuelve."""
    print("🌐 Esperando a que la tabla de pozos se cargue...")
    try:
        table = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table#ucWellList_DataGrid"))
        )
        print("✔ Tabla encontrada.")
        return table
    except Exception as e:
        print(f"❌ No se pudo encontrar la tabla. Error: {e}")
        take_screenshot("table_not_found")
        save_page_source("table_not_found_page_source")
        raise


def extract_table_data(table):
    """Extrae los datos de la tabla y los devuelve como una lista de diccionarios."""
    print("🌐 Extrayendo datos de la tabla...")
    rows = table.find_elements(By.TAG_NAME, "tr")[1:]  # Ignorar la fila de encabezado
    data = []

    for row in rows:
        try:
            cells = row.find_elements(By.TAG_NAME, "td")
            row_data = {
                "Well Name": cells[0].text,
                "Well Number": cells[1].text,
                "Contractor": cells[2].text,
                "Rig": cells[3].text,
                "Spud Date": cells[4].text,
                "RR Date": cells[5].text,
                # Agrega más columnas si es necesario
            }
            data.append(row_data)
        except Exception as e:
            print(f"❌ Error al extraer datos de una fila: {e}")
            continue

    print(f"✔ Datos extraídos: {len(data)} filas.")
    return data


def filter_wells_by_date_range(data, start_date, end_date):
    """Filtra los pozos según el rango de fechas."""
    print("🌐 Filtrando pozos por rango de fechas...")
    filtered_data = []

    for row in data:
        try:
            # Verificar si las celdas de fecha están vacías
            if not row["Spud Date"].strip() or not row["RR Date"].strip():
                print(f"❌ Fila ignorada: Spud Date o RR Date vacío")
                continue

            # Convertir las fechas a objetos datetime
            spud_date = datetime.strptime(row["Spud Date"], "%d-%b-%y")
            rr_date = datetime.strptime(row["RR Date"], "%d-%b-%y")

            # Verificar si ambas fechas están dentro del rango
            if (start_date <= spud_date <= end_date) and (start_date <= rr_date <= end_date):
                row["Status"] = "Dentro del rango"
            else:
                row["Status"] = "Fuera del rango"

            filtered_data.append(row)
        except Exception as e:
            print(f"❌ Error al filtrar una fila: {e}")
            continue

    print(f"✔ Pozos filtrados: {len(filtered_data)} filas.")
    return filtered_data


def save_data_to_csv(data, filename):
    """Guarda los datos en un archivo CSV sin usar pandas."""
    print(f"🌐 Guardando datos en {filename}...")
    try:
        # Abrir el archivo en modo escritura
        with open(filename, mode="w", newline="", encoding="utf-8") as file:
            # Crear un escritor CSV
            writer = csv.DictWriter(file, fieldnames=data[0].keys())
            
            # Escribir el encabezado
            writer.writeheader()
            
            # Escribir las filas de datos
            writer.writerows(data)
        
        print(f"✔ Datos guardados en {filename}")
    except Exception as e:
        print(f"❌ Error al guardar el archivo CSV: {e}")


def main():
    try:
        # Iniciar sesión en WellData
        login_to_welldata()

        # Navegar a la página de 'Well Search'
        navigate_to_well_search()

        # Seleccionar contractor y rig
        select_contractor_and_rig("DLS Argentina", "61")

        # Ordenar la tabla por 'Spud Date' en orden decreciente
        sort_table_by_spud_date()

        # Desplazar la página para cargar todos los pozos
        scroll_to_bottom()

        # Obtener la tabla de pozos
        table = wait_for_table()

        # Extraer los datos de la tabla
        data = extract_table_data(table)

        # Definir el rango de fechas
        start_date = datetime.strptime("19-Feb-25", "%d-%b-%y")  # Fecha inicial
        end_date = datetime.now()  # Fecha final (hoy)

        # Filtrar los pozos según el rango de fechas
        filtered_data = filter_wells_by_date_range(data, start_date, end_date)

        # Guardar los datos en un archivo CSV
        save_data_to_csv(filtered_data, "pozos_filtrados.csv")

    except Exception as e:
        print(f"❌ Error durante la ejecución: {e}")
        take_screenshot("error")
        save_page_source("error_page_source")
    finally:
        # Cerrar el navegador y eliminar el directorio temporal
        driver.quit()
        shutil.rmtree(temp_dir)
        print("✔ Navegador cerrado y directorio temporal eliminado.")


if __name__ == "__main__":
    main()
