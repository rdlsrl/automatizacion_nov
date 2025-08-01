from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

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
chrome_options.add_argument("--headless")  # Puedes desactivar el modo headless si es necesario
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--window-size=1920,1080")

service = Service("/usr/local/bin/chromedriver")
driver = webdriver.Chrome(service=service, options=chrome_options)
wait = WebDriverWait(driver, 20)

try:
    print("🔄 Iniciando sesión en WellData...")
    driver.get("https://www.welldata.net/Login.aspx?ReturnUrl=%2f")
    
    # Ingresar usuario
    usuario_input = wait.until(EC.presence_of_element_located((By.ID, "ucLogin_txtUsername")))
    usuario_input.send_keys("mbarbieri")
    print("✅ Usuario ingresado")
    
    # Ingresar contraseña
    password_input = driver.find_element(By.ID, "ucLogin_txtPassword")
    password_input.send_keys("Rdlpae2024@")
    print("✅ Contraseña ingresada")
    
    # Hacer clic en el botón de login
    driver.find_element(By.ID, "ucLogin_btnSubmit").click()
    print("✅ Login enviado")
    
    # Navegar directamente a la URL de "Well Search"
    print("🔄 Navegando directamente a 'Well Search'...")
    driver.get("https://www.welldata.net/Wells/WellSearch.aspx")
    print("✅ Acceso a 'Well Search' exitoso")
    
    # Esperar a que la página de "Well Search" se cargue completamente
    print("🔄 Esperando a que la página de 'Well Search' se cargue...")
    wait.until(EC.title_contains("Well Search"))  # Reemplaza con el título esperado
    print("✅ Página de 'Well Search' cargada")
    
    # Escanear la tabla de Well Search para obtener la lista de pozos
    print("🔍 Escaneando la lista de pozos...")
    table = wait.until(EC.presence_of_element_located((By.ID, "ucWellList_DataGrid")))
    pozos = table.find_elements(By.XPATH, "//table[@id='ucWellList_DataGrid']//a")
    
    # Iterar sobre cada pozo para abrir su página y volver
    for pozo in pozos:
        try:
            well_name = pozo.text.strip()
            print(f"🔄 Abriendo detalles del pozo: {well_name}")
            
            # Hacer clic en el nombre del pozo
            pozo.click()
            
            # Esperar a que cargue la página de detalles
            wait.until(EC.presence_of_element_located((By.ID, "DetallePozo")))  # Ajusta ID según la estructura de la página
            print(f"✅ Pozo {well_name} abierto correctamente.")
            
            # Volver a la página de Well Search
            driver.back()
            
            # Esperar a que la tabla de resultados se recargue
            wait.until(EC.presence_of_element_located((By.ID, "ucWellList_DataGrid")))
            print(f"↩️ Regresando a la lista de pozos.")
        
        except Exception as e:
            print(f"❌ Error al procesar el pozo {well_name}: {e}")
    
    # Captura de pantalla para depuración
    driver.save_screenshot("well_search.png")
    
except Exception as e:
    print(f"❌ Error: {e}")
    driver.save_screenshot("error.png")  # Captura de pantalla para depuración
finally:
    driver.quit()
