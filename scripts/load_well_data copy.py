#!/usr/bin/env python3
import os
import csv
import subprocess
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from datetime import datetime
from dotenv import load_dotenv

# ==========================================================================
# CONFIGURACIÓN INICIAL - CARGA DE CREDENCIALES
# ==========================================================================

# Cargar variables de entorno usando ruta absoluta
env_path = "/mnt/mariadb/autom_nov/config.env"
load_dotenv(env_path)

# Debug: Verificar carga de variables
print(f"\n{'='*50}")
print(f"Cargando variables de entorno desde: {env_path}")
print(f"Archivo existe: {os.path.exists(env_path)}")

# Obtener credenciales
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

WD_USERNAME = os.getenv("WD_USERNAME")
WD_PASSWORD = os.getenv("WD_PASSWORD")
WD_URL = os.getenv("WD_URL")

# Mostrar valores cargados (sin contraseñas para seguridad)
print("\nVariables cargadas:")
print(f"DB_HOST: {DB_HOST}")
print(f"DB_USER: {DB_USER}")
print(f"DB_NAME: {DB_NAME}")
print(f"WD_USERNAME: {WD_USERNAME}")
print(f"WD_URL: {WD_URL}")
print(f"{'='*50}\n")

# Verificar que todas las credenciales estén presentes
if not all([DB_HOST, DB_USER, DB_PASS, DB_NAME, WD_USERNAME, WD_PASSWORD, WD_URL]):
    print("ERROR: Faltan credenciales en el archivo de configuración.")
    print("Verifica que config.env contenga todas estas variables:")
    print("DB_HOST, DB_USER, DB_PASSWORD, DB_NAME")
    print("WD_USERNAME, WD_PASSWORD, WD_URL")
    exit(1)

# ========================================================================== 
# FUNCIONES DE TRANSFORMACIÓN DE DATOS
# ========================================================================== 

def transformar_latest_edr(latest_edr):
    """Transforma el campo latest_edr a formato datetime válido"""
    try:
        if not latest_edr or latest_edr.strip() == "":
            return None
            
        if ":" in latest_edr and len(latest_edr) <= 5:  # Formato HH:MM
            hora, minutos = latest_edr.split(":")
            fecha_actual = datetime.now().strftime("%Y-%m-%d")
            return f"{fecha_actual} {hora}:{minutos}:00"
        elif "-" in latest_edr:  # Formato d-mmm-yy
            return datetime.strptime(latest_edr, "%d-%b-%y").strftime("%Y-%m-%d %H:%M:%S")
        return None
    except Exception as e:
        print(f"Error transformando latest_edr '{latest_edr}': {e}")
        return None

def transformar_spud_date(spud_date):
    """Transforma el campo spud_date a formato YYYY-MM-DD"""
    try:
        if not spud_date or spud_date.strip() == "":
            return None
            
        if "-" in spud_date:  # Formato d-mmm-yy
            return datetime.strptime(spud_date, "%d-%b-%y").strftime("%Y-%m-%d")
        return None
    except Exception as e:
        print(f"Error transformando spud_date '{spud_date}': {e}")
        return None

# ========================================================================== 
# FUNCIÓN PARA DESCARGAR CSV DESDE WELLDATA
# ========================================================================== 

def descargar_csv():
    print("Iniciando descarga desde WellData...")
    
    # Configuración de Chrome en modo headless
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("window-size=1200x600")

    try:
        # Inicializar WebDriver
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        wait = WebDriverWait(driver, 20)

        # Navegación a WellData
        print(f"Accediendo a {WD_URL}...")
        driver.get(WD_URL)

        # Login
        print("Realizando login...")
        wait.until(EC.presence_of_element_located((By.ID, "ucLogin_txtUsername"))).send_keys(WD_USERNAME)
        driver.find_element(By.ID, "ucLogin_txtPassword").send_keys(WD_PASSWORD)
        driver.find_element(By.ID, "ucLogin_btnSubmit").click()

        # Navegación a Well List
        print("Navegando a Well List...")
        wait.until(EC.element_to_be_clickable((By.XPATH, "//area[@href='/Wells/WellList.aspx']"))).click()
        wait.until(EC.title_contains("Well List"))

        # Extracción de datos
        print("Extrayendo datos de la tabla...")
        wait.until(EC.presence_of_element_located((By.ID, "ucWellList_DataGrid")))
        rows = driver.find_elements(By.XPATH, "//table[@id='ucWellList_DataGrid']/tbody/tr")

        # Crear archivo CSV
        fecha_hora = datetime.now().strftime("%d-%m-%Y_%H-%M")
        filename = f"WELL_PAE_{fecha_hora}.csv"
        file_path = os.path.join("/mnt/mariadb/mariadb_csv_rigs", filename)
        
        print(f"Creando archivo CSV en {file_path}...")
        with open(file_path, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(['Operator', 'Well Name', 'Contractor', 'Rig', 'Spud Date', 'Latest EDR'])
            
            for row in rows:
                cells = [td.text.strip() for td in row.find_elements(By.XPATH, ".//td")]
                if len(cells) >= 9:  # Asegurarse que la fila tiene suficientes columnas
                    writer.writerow([
                        cells[0],  # Operator
                        cells[1],  # Well Name
                        cells[2],  # Contractor
                        cells[3],  # Rig
                        transformar_spud_date(cells[4]),  # Spud Date
                        transformar_latest_edr(cells[8])   # Latest EDR
                    ])

        print("Descarga completada exitosamente!")
        return file_path

    except Exception as e:
        print(f"ERROR durante la descarga: {str(e)}")
        return None
    finally:
        if 'driver' in locals():
            driver.quit()

# ========================================================================== 
# FUNCIONES PARA IMPORTAR A MARIADB (VERSIÓN CORREGIDA)
# ========================================================================== 

def importar_csv_a_mariadb(file_path):
    if not file_path or not os.path.exists(file_path):
        print("ERROR: Archivo CSV no válido o no encontrado")
        return False

    try:
        # Limpieza del CSV
        print("Limpiando archivo CSV...")
        subprocess.run([
            "sed", "-i",
            's/M\$//g; s/"//g; s/\("[^"]*\),\([^"]*"\)/\1\2/g; /^$/d',
            file_path
        ], check=True)

        # Importación a MariaDB - VERSIÓN CORREGIDA
        mysql_cmd = f"""
        LOAD DATA LOCAL INFILE '{file_path}'
        INTO TABLE well_data
        FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '\"'
        LINES TERMINATED BY '\\n'
        IGNORE 1 ROWS
        (operator, well_name, contractor, rig, @spud_date, @latest_edr)
        SET 
            import_datetime = CURRENT_TIMESTAMP,
            spud_date = NULLIF(STR_TO_DATE(@spud_date, '%Y-%m-%d'), '0000-00-00'),
            latest_edr = NULLIF(STR_TO_DATE(@latest_edr, '%Y-%m-%d %H:%i:%s'), '0000-00-00 00:00:00'),
            status = CASE
                WHEN TIMESTAMPDIFF(HOUR, STR_TO_DATE(@latest_edr, '%Y-%m-%d %H:%i:%s'), NOW()) < 6 THEN 'online'
                ELSE 'offline'
            END;
        """

        print("Ejecutando comando MySQL...")
        subprocess.run([
            "mysql",
            "--local-infile=1",
            "-h", DB_HOST,
            "-u", DB_USER,
            f"-p{DB_PASS}",
            DB_NAME,
            "-e",
            mysql_cmd
        ], check=True)
        print("Importación a MariaDB completada!")
        return True

    except subprocess.CalledProcessError as e:
        print(f"ERROR en importación a MariaDB: {e}")
        print(f"Comando ejecutado: {mysql_cmd}")
        return False
    except Exception as e:
        print(f"ERROR inesperado: {e}")
        return False

def eliminar_registros_no_validos():
    try:
        print("Limpiando registros no válidos...")
        subprocess.run([
            "mysql",
            "-h", DB_HOST,
            "-u", DB_USER,
            f"-p{DB_PASS}",
            DB_NAME,
            "-e",
            """
            DELETE FROM well_data 
            WHERE 
                (contractor, rig) NOT IN (
                    SELECT contractor_alias.alias, 
                           CASE 
                               WHEN rig_alias.alias LIKE 'FB%' THEN REPLACE(rig_alias.alias, '-', ' ')  
                               WHEN rig_alias.alias LIKE 'PAE%' THEN REPLACE(rig_alias.alias, '-', ' ')  
                               ELSE rig_alias.alias 
                           END
                    FROM rigs_contractors_autom contractor_alias
                    JOIN rigs_autom rig_alias ON rig_alias.contractor_id = contractor_alias.id
                )
                AND rig NOT IN ('PAE 001', 'FB-01');
            """
        ], check=True)
        print("Limpieza de registros completada!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"ERROR limpiando registros: {e}")
        return False

# ========================================================================== 
# EJECUCIÓN PRINCIPAL
# ========================================================================== 

if __name__ == "__main__":
    print("\n" + "="*50)
    print("INICIANDO PROCESO DE ACTUALIZACIÓN DE DATOS")
    print("="*50 + "\n")

    # Paso 1: Descargar datos desde WellData
    csv_file = descargar_csv()
    
    if csv_file:
        # Paso 2: Importar a MariaDB
        if importar_csv_a_mariadb(csv_file):
            # Paso 3: Limpiar registros no válidos
            eliminar_registros_no_validos()
    else:
        print("No se pudo completar el proceso debido a errores en la descarga")

    print("\n" + "="*50)
    print("PROCESO FINALIZADO")
    print("="*50)
