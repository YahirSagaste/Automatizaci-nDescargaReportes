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

XPATH_NOMBRE_CAMPANIA = "//span[small[contains(@class,'md-primary')]]"
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

  requeridos = ["correo", "password", "id_inicio", "id_fin", "pagina"]
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


def url_reporte(campaign_id, pagina):
  return (
      f"{BASE_URL}/admin/campaigns/{campaign_id}/reports/"
      f"{RELLENO_REPORTE}/{pagina}/{TAM_PAGINA}/"
  )


def leer_datos_reporte():
  """Lee de la página actual: nombre de campaña (o None si viene vacío o es
  solo un guion) y el total de llamadas del bloque 'Informe Base' (o None si
  no se encuentra)."""
  nombre = None
  try:
    span_nombre = driver.find_element(By.XPATH, XPATH_NOMBRE_CAMPANIA)
    texto = span_nombre.text.strip()
    texto = re.sub(r"\(id\s*\d+\)", "", texto).strip(" -").strip()
    nombre = texto or None
  except NoSuchElementException:
    nombre = None

  total = None
  try:
    card = driver.find_element(By.XPATH, XPATH_CARD_INFORME_BASE)
    m = re.search(r"Total\s*\n?\s*([\d.,]+)", card.text)
    if m:
      total = int(m.group(1).replace(",", "").replace(".", ""))
  except NoSuchElementException:
    total = None

  return nombre, total


def obtener_estado_reporte(campaign_id, pagina):
  driver.get(url_reporte(campaign_id, pagina))
  try:
    wait.until(
        lambda d: len(d.find_elements(By.XPATH, XPATH_CARD_INFORME_BASE)) > 0
    )
  except TimeoutException:
    return None, None
  return leer_datos_reporte()


def validar_campania(campaign_id, pagina_inicial):
  """Devuelve (es_valida, nombre, pagina_usada). Es válida solo si tiene
  nombre de campaña Y un total de llamadas mayor a cero. Si hay datos pero
  el nombre sale vacío, retrocede de página en página (asumiendo que la
  campaña quedó en una página anterior del listado)."""
  pagina = pagina_inicial
  nombre, total = obtener_estado_reporte(campaign_id, pagina)
  print(f"  (Validación) ID {campaign_id} página {pagina}: nombre={nombre!r} total={total}")

  if total in (None, 0):
    return False, None, pagina

  while not nombre and pagina > 1:
    pagina -= 1
    nombre, total_reintento = obtener_estado_reporte(campaign_id, pagina)
    print(
        f"  (debug) ID {campaign_id} reintento página {pagina}:"
        f" nombre={nombre!r} total={total_reintento}"
    )
    if total_reintento not in (None, 0):
      total = total_reintento

  es_valida = bool(nombre) and total not in (None, 0)
  return es_valida, nombre, pagina


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

  # 2. Recorrer el rango de IDs indicado, descargando cada reporte válido
  id_inicio = int(config["id_inicio"])
  id_fin = int(config["id_fin"])
  pagina_actual = int(config["pagina"])

  total_descargados = 0
  total_omitidos = 0

  for campania_id in range(id_inicio, id_fin + 1):
    es_valida, nombre, pagina_usada = validar_campania(campania_id, pagina_actual)

    if not es_valida:
      print(f"ID {campania_id}: no existe o no tiene nombre de campaña; se omite.")
      total_omitidos += 1
      continue

    # El driver ya quedó posicionado en la página correcta tras validar_campania
    pagina_actual = pagina_usada
    descargar_reporte_actual()
    total_descargados += 1
    print(
        f"  [+] Reporte #{total_descargados} (ID {campania_id}, '{nombre}')"
        " descargado correctamente."
    )

  print(
      f"\n¡Proceso finalizado! Descargados: {total_descargados}."
      f" Omitidos: {total_omitidos}."
  )
  time.sleep(5)

finally:
  driver.quit()
