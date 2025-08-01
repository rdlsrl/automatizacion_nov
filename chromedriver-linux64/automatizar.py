from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

# Configuración del navegador en modo headless
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

# Inicia el navegador
driver = webdriver.Chrome(options=chrome_options)

# URL inicial de la página de login
driver.get("https://www.welldata.net/Login.aspx?ReturnUrl=%2f")

# Espera para asegurarse de que la página haya cargado completamente
wait = WebDriverWait(driver, 10)

# Login con usuario y contraseña
usuario_input = wait.until(EC.presence_of_element_located((By.ID, "ucLogin_txtUsername")))
usuario_input.send_keys("aottasso")
driver.find_element(By.ID, "ucLogin_txtPassword").send_keys("Rdlpae2025")
driver.find_element(By.ID, "ucLogin_btnSubmit").click()

# Espera a que cargue la página de la lista de pozos
wait.until(EC.title_contains("My Well List"))

# Localiza y hace clic en el primer rig de la lista
first_rig_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//tr[1]//td/a")))
first_rig_button.click()

# Espera que se cargue la página del primer rig
wait.until(EC.title_contains("WellData"))

# Ahora que estamos dentro del primer rig, buscamos el enlace del botón Save
save_button = wait.until(EC.element_to_be_clickable((By.ID, "ucDrillingRecorderUV_HyperLink1")))

# Clic en el botón Save
save_button.click()

# Espera un poco para asegurarse de que el clic se haya realizado
time.sleep(3)

# Verifica si el clic fue exitoso
print("Ingreso al primer Rig OK y clic en Save realizado.")

# Cierra el navegador
driver.quit()
