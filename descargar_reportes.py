import os
import time
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

# 1. Directorio de descargas
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

# Fechas de referencia
fecha_hoy_str = datetime.now().strftime("%m/%d/%Y")

try:
  # 2. Iniciar sesión
  driver.get("https://vortex-hw.ipcom.ai/login")
  wait.until(EC.presence_of_element_located((By.ID, "formLogin")))

  campo_usuario = driver.find_element(
      By.XPATH, "//form[@id='formLogin']//input[@type='email' or @type='text']"
  )
  campo_usuario.clear()
  campo_usuario.send_keys("bancoppel_cdmx_cat_cobranza_02@ipcom.mx")

  campo_password = driver.find_element(
      By.XPATH, "//form[@id='formLogin']//input[@type='password']"
  )
  campo_password.clear()
  campo_password.send_keys("DY*E$&VTdy8v")

  boton_entrar = driver.find_element(By.ID, "loginButton")
  driver.execute_script("arguments[0].click();", boton_entrar)
  time.sleep(4)

  # 3. Ir a Campañas
  driver.get("https://vortex-hw.ipcom.ai/admin/campaigns")
  time.sleep(3)

  # 4. FASE 1: Avanzar páginas hasta encontrar registros de ayer / días anteriores
  print("Buscando el límite de los reportes del día de hoy...")
  llegado_al_final = False

  while not llegado_al_final:
    # Contar filas en la página actual que NO sean de hoy
    filas_anteriores = driver.find_elements(
        By.XPATH, f"//tr[not(contains(., 'Creada: {fecha_hoy_str}'))]"
    )

    # Si hay filas que no pertenecen a hoy, encontramos el límite
    if len(filas_anteriores) > 0:
      print("Se detectaron registros anteriores a hoy en esta página.")
      llegado_al_final = True
    else:
      # Intentar avanzar a la siguiente página usando el botón con clase md-table-pagination-next
      try:
        boton_siguiente = driver.find_element(
            By.XPATH,
            "//button[contains(@class, 'md-table-pagination-next') or"
            " .//i[text()='keyboard_arrow_right']]",
        )

        if boton_siguiente.is_enabled():
          print("Avanzando a la siguiente página...")
          driver.execute_script("arguments[0].click();", boton_siguiente)
          time.sleep(3)
        else:
          print("Llegaste a la última página disponible.")
          llegado_al_final = True
      except Exception:
        print("No se encontró el botón de siguiente página.")
        llegado_al_final = True

  # 5. FASE 2: Procesar los reportes de HOY de la página actual en orden inverso
  procesando_paginas = True
  total_descargados = 0

  while procesando_paginas:
    xpath_filas_hoy = f"//tr[contains(., 'Creada: {fecha_hoy_str}')]"
    filas_hoy = driver.find_elements(By.XPATH, xpath_filas_hoy)

    if len(filas_hoy) > 0:
      print(
          f"Procesando {len(filas_hoy)} reportes de hoy en la página actual..."
      )

      # Recorrer de ABAJO hacia ARRIBA (en orden inverso)
      for idx in range(len(filas_hoy) - 1, -1, -1):
        filas_actuales = driver.find_elements(By.XPATH, xpath_filas_hoy)
        fila = filas_actuales[idx]

        # Entrar al detalle del reporte (insert_chart)
        boton_grafica = fila.find_element(
            By.XPATH, ".//i[text()='insert_chart']/ancestor::button"
        )
        driver.execute_script("arguments[0].click();", boton_grafica)

        # Esperar vista del reporte
        wait.until(EC.url_contains("/reports/"))
        time.sleep(2)

        # Clic en los tres puntos (more_vert)
        boton_tres_puntos = wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "//i[text()='more_vert']/ancestor::button")
            )
        )
        driver.execute_script("arguments[0].click();", boton_tres_puntos)

        # Clic en Reporte Completo
        opcion_descarga = wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "//*[contains(text(), 'Reporte Completo')]")
            )
        )
        driver.execute_script("arguments[0].click();", opcion_descarga)

        total_descargados += 1
        print(f"Reporte #{total_descargados} descargado correctamente.")
        time.sleep(2)

        # Regresar a campañas
        driver.get("https://vortex-hw.ipcom.ai/admin/campaigns")
        time.sleep(3)

    # 6. Intentar retroceder a la página anterior (hacia atrás)
    try:
      boton_anterior = driver.find_element(
          By.XPATH,
          "//button[contains(@class, 'md-table-pagination-previous') or"
          " .//i[text()='keyboard_arrow_left']]",
      )

      if boton_anterior.is_enabled():
        print("Retrocediendo a la página anterior...")
        driver.execute_script("arguments[0].click();", boton_anterior)
        time.sleep(3)
      else:
        print("Se ha llegado al inicio de la tabla (Página 1).")
        procesando_paginas = False
    except Exception:
      print("No hay más páginas anteriores.")
      procesando_paginas = False

  print(
      f"\n¡Proceso finalizado con éxito! Total de reportes descargados:"
      f" {total_descargados}"
  )
  time.sleep(5)

finally:
  driver.quit()