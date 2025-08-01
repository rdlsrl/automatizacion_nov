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
import subprocess

# ========================================================================== 
# CONFIGURACIÓN DE SELENIUM PARA DESCARGAR EL CSV
# ========================================================================== 
def descargar_csv():
    # Configura las opciones para ejecutar en modo headless (sin visualización)
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Modo sin cabeza
    chrome_options.add_argument("--disable-gpu")  # Desactivar la aceleración por GPU (opcional)
    chrome_options.add_argument("--no-sandbox")  # Deshabilitar el sandbox (opcional)
    chrome_options.add_argument("window-size=1200x600")  # Ajusta el tamaño de la ventana si es necesario

    # Configura el driver de Chrome en modo headless
    service = Service(ChromeDriverManager().install())  # Usa webdriver_manager para manejar el driver
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
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
        return file_path

    except Exception as e:
        print(f"Error durante la descarga del CSV: {e}")
        return None

    finally:
        # Cerrar el navegador al finalizar
        driver.quit()

# ========================================================================== 
# IMPORTAR CSV A MARIADB
# ========================================================================== 
def importar_csv_a_mariadb(file_path):
    if not file_path:
        print("No se puede importar el CSV: Ruta no válida.")
        return

    # Cargar variables de entorno desde el archivo de configuración
    if os.path.exists("config.env"):
        from dotenv import load_dotenv
        load_dotenv("config.env")
    else:
        print("Error: No se encontró el archivo de configuración 'config.env'.")
        return

    # Variables de conexión a MariaDB
    DB_USER = os.getenv("DB_USER")
    DB_PASS = os.getenv("DB_PASS")
    DB_NAME = os.getenv("DB_NAME")

    if not all([DB_USER, DB_PASS, DB_NAME]):
        print("Error: Faltan credenciales en el archivo de configuración.")
        return

    try:
        # Limpiar el archivo CSV
        print("Limpiando el archivo CSV...")
        subprocess.run(["sed", "-i", 's/M\$//g; s/"//g; s/\("[^"]*\),\([^"]*"\)/\1\2/g; /^$/d', file_path], check=True)

        # Cargar el archivo CSV en MariaDB
        print("Cargando datos en MariaDB...")
        subprocess.run([
            "mysql", "-u", DB_USER, f"-p{DB_PASS}", DB_NAME, "-e",
            f"""
            LOAD DATA LOCAL INFILE '{file_path}'
            INTO TABLE well_data
            FIELDS TERMINATED BY ',' ENCLOSED BY '\"'
            LINES TERMINATED BY '\n'
            IGNORE 1 ROWS
            (@operator, @well_name, @contractor, @rig, @spud_date, @latest_edr, @total_depth)
            SET 
                operator = @operator,
                well_name = @well_name,
                contractor = @contractor,
                rig = @rig,
                spud_date = STR_TO_DATE(@spud_date, '%d-%b-%y'),
                latest_edr = CASE 
                    WHEN @latest_edr REGEXP '^[0-9]{2}:[0-9]{2}$' 
                    THEN STR_TO_DATE(CONCAT(CURDATE(), ' ', @latest_edr), '%Y-%m-%d %H:%i')
                    ELSE STR_TO_DATE(@latest_edr, '%d-%b-%y')
                END,
                import_datetime = CURRENT_TIMESTAMP, 
                status = CASE
                    WHEN TIMESTAMPDIFF(HOUR, STR_TO_DATE(CONCAT(CURDATE(), ' ', @latest_edr), '%Y-%m-%d %H:%i'), NOW()) < 6 THEN 'online'
                    ELSE 'offline'
                END
            """
        ], check=True)
        print("Datos cargados exitosamente en MariaDB.")

        # Eliminar registros no válidos
        print("Eliminando registros no válidos...")
        subprocess.run([
            "mysql", "-u", DB_USER, f"-p{DB_PASS}", DB_NAME, "-e",
            """
            DELETE FROM well_data 
            WHERE 
                (contractor, rig) NOT IN (
                    SELECT contractor_alias.alias, 
                           CASE 
                               WHEN rig_alias.alias LIKE 'FB%' THEN REPLACE(rig_alias.alias, '-', ' ')  
                               WHEN rig_alias.alias LIKE 'PAE%' THEN REPLACE(rig_alias.alias, '-', ' ')  
                               ELSE rig_alias.alias 
                           END AS normalized_rig
                    FROM rigs_contractors_autom contractor_alias
                    JOIN rigs_autom rig_alias 
                    ON rig_alias.contractor_id = contractor_alias.id
                    WHERE rig_alias.alias = well_data.rig 
                    AND contractor_alias.alias = well_data.contractor
                )
                AND rig NOT IN ('PAE 001', 'FB-01');
            """
        ], check=True)
        print("Registros no válidos eliminados exitosamente.")

    except subprocess.CalledProcessError as e:
        print(f"Error durante la importación a MariaDB: {e}")

# ========================================================================== 
# EJECUCIÓN PRINCIPAL
# ========================================================================== 
if __name__ == "__main__":
    # Descargar el CSV
    csv_file_path = descargar_csv()

    # Importar el CSV a MariaDB
    if csv_file_path:
        importar_csv_a_mariadb(csv_file_path)
    else:
        print("No se pudo descargar el CSV. Verifica el error anterior.")
