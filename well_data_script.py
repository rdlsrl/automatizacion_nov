from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from datetime import datetime
import time
import csv
import os

# Configura las opciones para ejecutar en modo headless (sin visualización)
chrome_options = Options()
chrome_options.add_argument("--headless")  # Modo sin cabeza
chrome_options.add_argument("--disable-gpu")  # Desactivar la aceleración por GPU (opcional)
chrome_options.add_argument("--no-sandbox")  # Deshabilitar el sandbox (opcional)
chrome_options.add_argument("window-size=1200x600")  # Ajusta el tamaño de la ventana si es necesario

# Configura el driver de Chrome en modo headless
service = Service(ChromeDriverManager().install())  # Usa webdriver_manager para manejar el driver
driver = webdriver.Chrome(service=service, options=chrome_options)

# Abre la página de login de WellData
driver.get("https://www.welldata.net/Login.aspx?ReturnUrl=%2f")

# Espera a que el campo de usuario esté disponible
wait = WebDriverWait(driver, 20)  # Aumentamos el tiempo de espera
usuario_input = wait.until(EC.presence_of_element_located((By.ID, "ucLogin_txtUsername")))

# Rellena los campos de usuario y contraseña
usuario_input.send_keys("mbarbieri")
driver.find_element(By.ID, "ucLogin_txtPassword").send_keys("Rdlpae2024@")

# Clic en el botón de login
driver.find_element(By.ID, "ucLogin_btnSubmit").click()

# 1. Esperamos a que el área 'Wells' sea visible y clickeable
wells_menu = wait.until(EC.element_to_be_clickable((By.XPATH, "//area[@href='/Wells/WellList.aspx']")))  # Usamos el href para identificar el área
wells_menu.click()
print("Menú 'Wells' clickeado.")

# 2. Ahora esperamos a que la opción 'Well List' cargue correctamente
wait.until(EC.title_contains("Well List"))  # Esperamos que la página cargue correctamente
print("Página 'Well List' cargada.")

# Esperar que la tabla esté visible
wait = WebDriverWait(driver, 10)
wait.until(EC.presence_of_element_located((By.ID, "ucWellList_DataGrid")))

# Encontrar todas las filas de la tabla
rows = driver.find_elements(By.XPATH, "//table[@id='ucWellList_DataGrid']/tbody/tr")

# Generamos el nombre del archivo con la fecha y hora actuales
fecha_hora = datetime.now().strftime("%d-%m-%Y_%H-%M")
filename = f"WELL_PAE_{fecha_hora}.csv"
file_path = os.path.join("/mnt/mariadb/mariadb_csv_rigs", filename)  # Ruta correcta en AlmaLinux

# Abrir un archivo CSV para escribir los datos
with open(file_path, mode='w', newline='', encoding='utf-8') as file:
    writer = csv.writer(file)
    writer.writerow(['Operator', 'Well Name', 'Contractor', 'Rig', 'Spud Date', 'Latest EDR', 'Total Depth'])
    
    # Extraer datos de cada fila
    for row in rows:
        operator = row.find_element(By.XPATH, ".//td[1]").text.strip()
        well_name = row.find_element(By.XPATH, ".//td[2]").text.strip()
        contractor = row.find_element(By.XPATH, ".//td[3]").text.strip()
        rig = row.find_element(By.XPATH, ".//td[4]").text.strip()
        spud_date = row.find_element(By.XPATH, ".//td[5]").text.strip()
        latest_edr = row.find_element(By.XPATH, ".//td[9]").text.strip()
        total_depth = row.find_element(By.XPATH, ".//td[12]").text.strip()

        # Escribir la fila de datos en el archivo CSV
        writer.writerow([operator, well_name, contractor, rig, spud_date, latest_edr, total_depth])

print(f"Datos exportados a CSV correctamente: {file_path}")

# Cerrar el navegador al finalizar
driver.quit()
