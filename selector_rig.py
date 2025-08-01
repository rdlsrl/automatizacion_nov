import time
import mysql.connector
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Configuración de Selenium sin interfaz gráfica
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

# Iniciar el navegador
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)

# Conectar a la base de datos
conn = mysql.connector.connect(
    host="127.0.0.1",
    user="root",
    password="Partediario20",
    database="rdl_import"
)
cursor = conn.cursor()

# Obtener los rigs y contractors desde la base de datos con el último import_datetime
cursor.execute("""
    SELECT LOWER(TRIM(wd.contractor)), LOWER(TRIM(wd.rig))
    FROM well_data wd
    WHERE wd.import_datetime = (SELECT MAX(import_datetime) FROM well_data);
""")
db_data = cursor.fetchall()

cursor.close()
conn.close()

# Abrir la página de login de WellData
driver.get("https://www.welldata.net/Login.aspx?ReturnUrl=%2f")

# Esperar e ingresar credenciales
wait = WebDriverWait(driver, 20)
usuario_input = wait.until(EC.presence_of_element_located((By.ID, "ucLogin_txtUsername")))
usuario_input.send_keys("mbarbieri")
driver.find_element(By.ID, "ucLogin_txtPassword").send_keys("Rdlpae2024@")
driver.find_element(By.ID, "ucLogin_btnSubmit").click()

# Acceder a la tabla de Well List
wells_menu = wait.until(EC.element_to_be_clickable((By.XPATH, "//area[@href='/Wells/WellList.aspx']")))
wells_menu.click()
wait.until(EC.presence_of_element_located((By.ID, "ucWellList_DataGrid")))

# Extraer datos de la tabla de la web
rows = driver.find_elements(By.XPATH, "//table[@id='ucWellList_DataGrid']/tbody/tr")
web_data = []

for row in rows[1:]:  # Omitimos el encabezado
    cols = row.find_elements(By.TAG_NAME, "td")
    if len(cols) >= 4:
        contractor = cols[2].text.strip().lower()
        rig = cols[3].text.strip().lower()
        web_data.append((contractor, rig))

# Comparar datos de la web con la base de datos y mostrar resultados en bucle
print("📊 RESULTADO DE LA BÚSQUEDA DE RIGS:")
for db_contractor, db_rig in db_data:
    found = False
    for web_contractor, web_rig in web_data:
        if db_contractor == web_contractor and db_rig == web_rig:
            print(f"✅ ENCONTRADO - Contractor: {db_contractor}, Rig: {db_rig}")
            found = True
            break
    if not found:
        print(f"❌ NO ENCONTRADO - Contractor: {db_contractor}, Rig: {db_rig}")

# Cerrar Selenium
driver.quit()
