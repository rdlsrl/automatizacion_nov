from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from datetime import datetime
import csv
import os
import logging
import mysql.connector
from dotenv import load_dotenv

# Cargar las variables de entorno desde config.env
load_dotenv('/mnt/mariadb/autom_nov/config.env')

# Configurar el sistema de logs
log_folder = "/mnt/mariadb/autom_nov/logs"
if not os.path.exists(log_folder):
    os.makedirs(log_folder)

log_file = os.path.join(log_folder, "welldata_automation.log")
logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Función para guardar el estado del proceso en la base de datos
def guardar_estado_proceso(nombre_script, archivo_las, estado, mensaje):
    try:
        # Conectar a la base de datos
        conexion = mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME")
        )
        cursor = conexion.cursor()

        # Insertar el estado del proceso
        query = """
            INSERT INTO log_import_las (nombre_script, archivo_las, estado, mensaje, fecha)
            VALUES (%s, %s, %s, %s, NOW())
        """
        cursor.execute(query, (nombre_script, archivo_las, estado, mensaje))
        conexion.commit()

        cursor.close()
        conexion.close()
        logging.info("Estado del proceso guardado correctamente.")
    except Exception as e:
        logging.error(f"Error al guardar el estado del proceso: {e}")

# Función para insertar datos en WellData
def insertar_datos_en_well_data(datos):
    try:
        # Conectar a la base de datos
        conexion = mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME")
        )
        cursor = conexion.cursor()

        # Insertar los datos en WellData
        query = """
            INSERT INTO well_data (operator, well_name, contractor, rig, spud_date, latest_edr, total_depth)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(query, datos)
        conexion.commit()

        cursor.close()
        conexion.close()
        logging.info("Datos insertados correctamente en WellData.")
    except Exception as e:
        logging.error(f"Error al insertar datos en WellData: {e}")

try:
    logging.info("Iniciando el script de automatización de WellData.")

    # Configura las opciones para ejecutar en modo headless
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("window-size=1200x600")

    # Configura el driver de Chrome
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    # Abre la página de login de WellData
    driver.get(os.getenv("WD_URL"))
    logging.info("Página de login cargada.")

    # Espera a que el campo de usuario esté disponible
    wait = WebDriverWait(driver, 20)
    usuario_input = wait.until(EC.presence_of_element_located((By.ID, "ucLogin_txtUsername")))

    # Rellena los campos de usuario y contraseña
    usuario_input.send_keys(os.getenv("WD_USERNAME"))
    driver.find_element(By.ID, "ucLogin_txtPassword").send_keys(os.getenv("WD_PASSWORD"))

    # Clic en el botón de login
    driver.find_element(By.ID, "ucLogin_btnSubmit").click()
    logging.info("Login exitoso.")

    # Esperamos a que el área 'Wells' sea visible y clickeable
    wells_menu = wait.until(EC.element_to_be_clickable((By.XPATH, "//area[@href='/Wells/WellList.aspx']")))
    wells_menu.click()
    logging.info("Menú 'Wells' clickeado.")

    # Esperamos a que la opción 'Well List' cargue correctamente
    wait.until(EC.title_contains("Well List"))
    logging.info("Página 'Well List' cargada.")

    # Esperar que la tabla esté visible
    wait.until(EC.presence_of_element_located((By.ID, "ucWellList_DataGrid")))

    # Encontrar todas las filas de la tabla
    rows = driver.find_elements(By.XPATH, "//table[@id='ucWellList_DataGrid']/tbody/tr")

    # Generar el nombre del archivo CSV con la fecha y hora actuales
    fecha_hora = datetime.now().strftime("%d-%m-%Y_%H-%M")
    filename = f"WELL_PAE_{fecha_hora}.csv"

    # Ruta donde se guardará el archivo CSV
    file_path = os.path.join("/mnt/mariadb/mariadb_csv_rigs", filename)

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

            # Insertar los datos en WellData
            datos = (operator, well_name, contractor, rig, spud_date, latest_edr, total_depth)
            insertar_datos_en_well_data(datos)

    logging.info(f"Datos exportados a CSV correctamente: {file_path}")

    # Guardar el estado del proceso en la base de datos
    guardar_estado_proceso(
        nombre_script="well_data_script.py",
        archivo_las=filename,
        estado="Éxito",
        mensaje=f"Archivo CSV guardado en: {file_path}"
    )

except Exception as e:
    logging.error(f"Error durante la ejecución: {e}")

    # Guardar el estado del proceso en la base de datos en caso de error
    guardar_estado_proceso(
        nombre_script="well_data_script.py",
        archivo_las="N/A",
        estado="Error",
        mensaje=str(e)
    )

finally:
    # Cerrar el navegador al finalizar
    driver.quit()
    logging.info("Script finalizado.")
