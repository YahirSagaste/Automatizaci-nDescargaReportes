import json
import os
import re
import sys
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

BASE_URL = "https://vortex-hw.ipcom.ai"
TAM_PAGINA = 50
RELLENO_REPORTE = 0  # segundo segmento del URL; confirmado que no afecta el contenido
PAGINA_FIJA = 1  # no se necesita el nombre de campaña aquí, así que basta con página 1

XPATH_CARD_INFORME_BASE = (
    "//span[contains(@class,'md-subheading') and contains(normalize-space(.),"
    " 'Informe Base')]/ancestor::div["
    "contains(concat(' ', normalize-space(@class), ' '), ' md-card ')][1]"
)

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def cargar_configuracion():
  if not os.path.exists(CONFIG_PATH):
    sys.exit(
        f"No se encontró {CONFIG_PATH}.\n"
        "Genera config.json con la página local de configuración y colócalo"
        " en esta misma carpeta."
    )
  with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

  requeridos = ["correo", "password", "id_inicio", "id_fin"]
  faltantes = [k for k in requeridos if k not in config]
  if faltantes:
    sys.exit(f"config.json no tiene los campos: {', '.join(faltantes)}")

  return config


config = cargar_configuracion()

ruta_descargas = os.path.join(os.getcwd(), "Reportes_Hoy")
if not os.path.exists(ruta_descargas):
  os.makedirs(ruta_descargas)

opciones = webdriver.ChromeOptions()
opciones.add_argument("--start-maximized")
opciones.add_experimental_option(
    "prefs",
    {
        "download.default_directory": ruta_descargas,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    },
)

servicio = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=servicio, options=opciones)
wait = WebDriverWait(driver, 15)


def url_reporte(campaign_id, pagina=PAGINA_FIJA):
  return (
      f"{BASE_URL}/admin/campaigns/{campaign_id}/reports/"
      f"{RELLENO_REPORTE}/{pagina}/{TAM_PAGINA}/"
  )


def leer_total_informe_base():
  """Devuelve el total de llamadas del bloque 'Informe Base', o None si el
  bloque no aparece (indicio de que el ID no existe)."""
  try:
    card = driver.find_element(By.XPATH, XPATH_CARD_INFORME_BASE)
  except NoSuchElementException:
    return None

  m = re.search(r"Total\s*\n?\s*([\d.,]+)", card.text)
  if not m:
    return None
  return int(m.group(1).replace(",", "").replace(".", ""))


def existe_campania(campaign_id):
  driver.get(url_reporte(campaign_id))
  try:
    wait.until(
        lambda d: len(d.find_elements(By.XPATH, XPATH_CARD_INFORME_BASE)) > 0
    )
  except TimeoutException:
    return False
  total = leer_total_informe_base()
  print(f"  (debug) ID {campaign_id}: total leído = {total}")
  return total not in (None, 0)


def descargar_reporte_actual():
  """Asume que el driver ya está posicionado en la página de un reporte."""
  boton_tres_puntos = wait.until(
      EC.presence_of_element_located(
          (By.XPATH, "//i[text()='more_vert']/ancestor::button")
      )
  )
  driver.execute_script("arguments[0].click();", boton_tres_puntos)

  opcion_descarga = wait.until(
      EC.presence_of_element_located(
          (By.XPATH, "//*[contains(text(), 'Reporte Completo')]")
      )
  )
  driver.execute_script("arguments[0].click();", opcion_descarga)
  time.sleep(2)


try:
  # 1. Iniciar sesión
  driver.get(f"{BASE_URL}/login")
  wait.until(EC.presence_of_element_located((By.ID, "formLogin")))

  campo_usuario = driver.find_element(
      By.XPATH, "//form[@id='formLogin']//input[@type='email' or @type='text']"
  )
  campo_usuario.clear()
  campo_usuario.send_keys(config["correo"])

  campo_password = driver.find_element(
      By.XPATH, "//form[@id='formLogin']//input[@type='password']"
  )
  campo_password.clear()
  campo_password.send_keys(config["password"])

  boton_entrar = driver.find_element(By.ID, "loginButton")
  driver.execute_script("arguments[0].click();", boton_entrar)
  time.sleep(4)

  # 2. Recorrer el rango de IDs indicado, descargando cada reporte existente
  id_inicio = int(config["id_inicio"])
  id_fin = int(config["id_fin"])

  total_descargados = 0
  total_omitidos = 0

  for campania_id in range(id_inicio, id_fin + 1):
    if not existe_campania(campania_id):
      print(f"ID {campania_id}: no existe o no tiene datos; se omite.")
      total_omitidos += 1
      continue

    descargar_reporte_actual()
    total_descargados += 1
    print(f"  [+] Reporte #{total_descargados} (ID {campania_id}) descargado correctamente.")

  print(
      f"\n¡Proceso finalizado! Descargados: {total_descargados}."
      f" Omitidos: {total_omitidos}."
  )
  time.sleep(5)

finally:
  driver.quit()
