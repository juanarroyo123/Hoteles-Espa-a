#!/usr/bin/env python3
"""
Hotel Monitor — Scraper local con cache acumulativo
Portales activos: ThinkSpain, Lucas Fox
"""
import json, re, time, os, subprocess, random, unicodedata, shutil
from datetime import date, datetime, timedelta
from html import unescape

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
import requests as req_mod
from bs4 import BeautifulSoup

TODAY      = date.today().strftime('%d/%m/%Y')
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hoteles_cache.json')
# Historico PERMANENTE de anuncios retirados. Nunca se borra: acumula cada
# anuncio que se retira, aunque la cache se resetee o cambiemos de scraper.
# Sirve de comparables historicos (precios de activos que ya no estan a la venta).
RETIRADOS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'retirados_historico.json')

# ── Licencias turísticas oficiales (scraper aparte, 1 vez/semana) ──
# La tarea programada de Windows dispara ESTE scraper.py todos los días,
# pero el de licencias (17 CCAA, Cantabria 552 páginas, Asturias 11 PDF...)
# tarda varios minutos y las fuentes oficiales casi nunca cambian a
# diario. Por eso no lo corremos cada vez: guardamos la fecha de la
# última ejecución en un archivo de estado, y solo lo repetimos si han
# pasado 7+ días desde la última vez — así la tarea diaria de Windows
# puede llamar a este script sin cambios, y licencias se actualiza solo
# semanalmente por dentro.
LICENCIAS_ESTADO_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'licencias_ultima_ejecucion.txt')
LICENCIAS_INTERVALO_DIAS = 7


def ejecutar_licencias_si_toca():
    """Corre el scraper de licencias (scraper_licencias.py, en la misma
    carpeta) solo si han pasado 7+ días desde la última vez, o si nunca
    se ha corrido. Nunca deja que un fallo aquí tumbe el scraper
    principal de anuncios — se captura cualquier excepción y se sigue."""
    try:
        ultima_vez = None
        if os.path.exists(LICENCIAS_ESTADO_FILE):
            with open(LICENCIAS_ESTADO_FILE, 'r', encoding='utf-8') as f:
                texto = f.read().strip()
            try:
                ultima_vez = datetime.strptime(texto, '%Y-%m-%d').date()
            except ValueError:
                ultima_vez = None  # archivo de estado corrupto -> tratamos como "nunca"

        hoy = date.today()
        if ultima_vez is not None:
            dias_pasados = (hoy - ultima_vez).days
            if dias_pasados < LICENCIAS_INTERVALO_DIAS:
                print(f'\nLicencias: última actualización hace {dias_pasados} día(s) '
                      f'— toca cada {LICENCIAS_INTERVALO_DIAS}, no se repite hoy.')
                return

        print(f'\n{"="*50}')
        print('Actualizando licencias turísticas oficiales (toca esta semana)...')
        print('='*50)

        import sys
        carpeta_actual = os.path.dirname(os.path.abspath(__file__))
        if carpeta_actual not in sys.path:
            sys.path.insert(0, carpeta_actual)

        import scraper_licencias
        scraper_licencias.main()

        with open(LICENCIAS_ESTADO_FILE, 'w', encoding='utf-8') as f:
            f.write(hoy.strftime('%Y-%m-%d'))
        print('Licencias actualizadas correctamente — próxima actualización en '
              f'{LICENCIAS_INTERVALO_DIAS} días.')

    except Exception as e:
        print(f'\n⚠️  Error actualizando licencias (no afecta a los anuncios): {e}')
        print('   Se reintentará en la próxima ejecución de todas formas, ya que')
        print('   no se ha actualizado la fecha de estado.')


def cruzar_licencias_con_activos(todos_activos):
    """Cruza cada anuncio activo con el registro oficial de licencias
    turísticas (licencias_completo.json), usando EXACTAMENTE la misma
    función (cruzarLicencia, y sus ayudantes) que usa el botón "Descargar
    Excel" de la web -- no es una reimplementación aparte: se extrae en
    caliente de index_template.html y se ejecuta con Node.js
    (cruzar_licencias.js), así que la web y este cruce automático nunca
    pueden divergir ni hay que mantener la lógica dos veces.

    Escribe 'licencia_texto' y 'licencia_motivo' directamente en cada dict
    de todos_activos -- como son los MISMOS objetos que ya están dentro de
    cache_nuevo (todos_activos = filtro de list(cache_nuevo.values())), con
    modificarlos aquí basta para que el siguiente save_cache() los persista
    en hoteles_cache.json, y para que __LISTINGS_JSON__ los lleve también a
    index.html.

    Se recalcula desde cero en cada ejecución (nunca se fía de un
    licencia_texto/motivo ya guardado de un día anterior), para que las
    licencias nuevas de la actualización semanal, o cualquier mejora en la
    lógica de cruce, se reflejen enseguida. Cualquier fallo aquí (Node no
    instalado, template cambiado, JSON corrupto...) se registra y se
    ignora: nunca debe tumbar el scraper de anuncios."""
    carpeta = os.path.dirname(os.path.abspath(__file__))
    ruta_licencias = os.path.join(carpeta, 'licencias_completo.json')
    ruta_template = os.path.join(carpeta, 'index_template.html')
    ruta_script = os.path.join(carpeta, 'cruzar_licencias.js')

    if not os.path.exists(ruta_licencias):
        print('\nCruce de licencias: no existe licencias_completo.json todavía -- se omite.')
        return
    if not os.path.exists(ruta_script):
        print('\n⚠️  Cruce de licencias: falta cruzar_licencias.js -- se omite.')
        return
    if shutil.which('node') is None:
        print('\n⚠️  Cruce de licencias: Node.js no está disponible en este entorno -- se omite '
              '(en GitHub Actions, comprueba que el workflow tenga instalado Node).')
        return

    print(f'\n{"="*50}')
    print('Cruzando anuncios con licencias turísticas oficiales...')
    print('='*50)

    tmp_activos = os.path.join(carpeta, '_tmp_cruce_activos.json')
    tmp_salida = os.path.join(carpeta, '_tmp_cruce_resultado.json')
    try:
        with open(tmp_activos, 'w', encoding='utf-8') as f:
            json.dump(todos_activos, f, ensure_ascii=False)

        resultado = subprocess.run(
            ['node', ruta_script, ruta_template, ruta_licencias, tmp_activos, tmp_salida],
            cwd=carpeta, capture_output=True, text=True, timeout=900,
        )
        if resultado.stdout:
            print(resultado.stdout.strip())
        if resultado.returncode != 0:
            print(f'⚠️  Cruce de licencias: cruzar_licencias.js terminó con error '
                  f'(código {resultado.returncode}) -- se omite esta vez, no se toca ningún dato.')
            if resultado.stderr:
                print(resultado.stderr.strip())
            return

        with open(tmp_salida, 'r', encoding='utf-8') as f:
            por_url = json.load(f)

        aplicados = 0
        for h in todos_activos:
            info = por_url.get(h.get('url'))
            if info is None:
                continue
            h['licencia_texto'] = info.get('licencia_texto', '') or ''
            h['licencia_motivo'] = info.get('licencia_motivo', '') or ''
            aplicados += 1
        print(f'Cruce de licencias aplicado a {aplicados} anuncios activos.')
    except Exception as e:
        print(f'⚠️  Error en el cruce de licencias (no afecta a los anuncios): {e}')
    finally:
        for p in (tmp_activos, tmp_salida):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass


HOTEL_KW = ['hotel','hostal','hostel','pensión','pension','aparthotel',
            'posada','parador','fonda','casa rural','alojamiento turístico',
            'albergue','resort','casa de huespedes','bed and breakfast',
            'hotel boutique','boutique hotel','complejo hotelero','negocio hotelero',
            'guesthouse','b&b','inn ','lodge','rural house',
            'apartamento turístico','apartamentos turísticos','edificio turístico']

SPAM_KW = ['404','página no encontrada','page not found','i want to advertise',
           'advertise on think','sign up','register','login','cookie',
           'privacy policy','terms of use','contact us','about us']

def es_hotel(texto):
    t = (texto or '').lower()
    if any(s in t for s in SPAM_KW): return False
    return any(k in t for k in HOTEL_KW)

def clean(s):
    if not s: return ''
    s = re.sub(r'<[^>]+>', ' ', str(s))
    s = unescape(s)
    return re.sub(r'\s+', ' ', s).strip()

def clean_desc(elemento_o_texto):
    """Como clean(), pero para DESCRIPCIONES: en vez de aplastar todo en
    una sola linea, conserva los saltos de parrafo/linea REALES -- los que
    vienen de <br>, </p>, </div>, </li> en el HTML original de la ficha, o
    de un '\n' de verdad si ya nos llega como texto plano (p.ej. de un
    JSON de la propia web) -- para que se lea completo y con los mismos
    puntos y aparte que en el anuncio de verdad.
    Recibe el elemento de BeautifulSoup TAL CUAL (sin haberle sacado ya el
    texto con get_text()) para no perder donde estaban los saltos de
    bloque; el resto de etiquetas en linea (negrita, enlaces...) se quitan
    sin cortar la frase en trozos sueltos.
    """
    if not elemento_o_texto: return ''
    s = str(elemento_o_texto)
    s = re.sub(r'<br\b[^>]*>', '\n', s, flags=re.I)
    s = re.sub(r'</p\s*>', '\n\n', s, flags=re.I)
    s = re.sub(r'</div\s*>', '\n', s, flags=re.I)
    # Titulos (Inmo Olaya usa <h3>/<h5> como subtitulos dentro de la
    # propia descripcion, p.ej. 'HOTEL BOUTIQUE - ACTIVO CONSOLIDADO') --
    # los tratamos como un parrafo aparte, igual que un </p>.
    s = re.sub(r'</h[1-6]\s*>', '\n\n', s, flags=re.I)
    # Listas (<ul><li>...): cada <li> se convierte en una linea con guion
    # delante, para que no queden pegadas unas a otras -- CONFIRMADO que
    # hace falta con las listas de caracteristicas reales de Inmo Olaya
    # ('Reforma integral: 2017', '6 habitaciones: 4 dobles + 2 suites'...).
    s = re.sub(r'<li\b[^>]*>', '- ', s, flags=re.I)
    s = re.sub(r'</li\s*>', '\n', s, flags=re.I)
    s = re.sub(r'</(?:ul|ol)\s*>', '\n', s, flags=re.I)
    s = re.sub(r'<[^>]+>', '', s)
    s = unescape(s)
    lineas = [re.sub(r'[ \t]+', ' ', l).strip() for l in s.split('\n')]
    out = []
    en_blanco = False
    for l in lineas:
        if l == '':
            if not en_blanco and out:
                out.append('')
            en_blanco = True
        else:
            out.append(l)
            en_blanco = False
    while out and out[-1] == '':
        out.pop()
    return '\n'.join(out)

def parsear_fecha(texto):
    if not texto: return TODAY
    t = texto.lower().strip()
    meses = {
        'ene':1,'feb':2,'mar':3,'abr':4,'may':5,'jun':6,
        'jul':7,'ago':8,'sep':9,'oct':10,'nov':11,'dic':12,
        'enero':1,'febrero':2,'marzo':3,'abril':4,'mayo':5,'junio':6,
        'julio':7,'agosto':8,'septiembre':9,'octubre':10,'noviembre':11,'diciembre':12,
        'jan':1,'apr':4,'aug':8,'dec':12,
    }
    hoy = date.today()
    if 'hoy' in t or 'today' in t: return TODAY
    if 'ayer' in t or 'yesterday' in t:
        return (hoy - timedelta(days=1)).strftime('%d/%m/%Y')
    m = re.search(r'hace\s+(\d+)\s+(día|isemana|mes|año|ano)', t)
    if not m: m = re.search(r'(\d+)\s+(day|week|month|year)', t)
    if m:
        num = int(m.group(1)); u = m.group(2)
        if   'día' in u or 'dia' in u or 'day' in u: d = hoy - timedelta(days=num)
        elif 'semana' in u or 'week' in u: d = hoy - timedelta(weeks=num)
        elif 'mes' in u or 'month' in u:
            mes = hoy.month - num; año = hoy.year
            while mes <= 0: mes += 12; año -= 1
            d = date(año, mes, min(hoy.day, 28))
        elif 'año' in u or 'ano' in u or 'year' in u:
            d = date(hoy.year - num, hoy.month, hoy.day)
        else: d = hoy
        return d.strftime('%d/%m/%Y')
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', t)
    if m: return f'{m.group(3)}/{m.group(2)}/{m.group(1)}'
    m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', t)
    if m: return f'{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}'
    m = re.search(r'(\d{1,2})\s+(?:de\s+)?([a-záéíóúñ]+)(?:\s+(?:de\s+)?(\d{4}))?', t)
    if m:
        dia = int(m.group(1)); mes_txt = m.group(2)[:3]
        año = int(m.group(3)) if m.group(3) else hoy.year
        mes_num = meses.get(mes_txt, 0)
        if mes_num: return f'{dia:02d}/{mes_num:02d}/{año}'
    return TODAY

# ─── cache ────────────────────────────────────────────
def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f'Cache cargado: {len(data)} anuncios previos.')
            return {item['url']: item for item in data}
        except Exception as e:
            print(f'Cache corrupto ({e}), empezando desde cero.')
    print('Cache vacío — primera ejecución.')
    return {}

def save_cache(cache_dict):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(cache_dict.values()), f, ensure_ascii=False, indent=2)

# ─── driver ───────────────────────────────────────────
def _chrome_major():
    """Versión mayor de Chrome instalada (Windows, vía registro). int o None."""
    try:
        import winreg
        for hive, path in [
            (winreg.HKEY_CURRENT_USER,  r'Software\Google\Chrome\BLBeacon'),
            (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Google\Chrome\BLBeacon'),
        ]:
            try:
                k = winreg.OpenKey(hive, path)
                v, _ = winreg.QueryValueEx(k, 'version')
                winreg.CloseKey(k)
                if v:
                    return int(str(v).split('.')[0])
            except OSError:
                continue
    except Exception:
        pass
    return None

def _uc_chrome(build_opts):
    """Crea uc.Chrome fijando la versión de Chrome INSTALADA (evita el fallo
    'ChromeDriver only supports Chrome version X / current is Y'). Si aun así
    falla por desajuste, reintenta con la versión exacta que reporta el error,
    así se autoarregla cuando Chrome se actualiza."""
    # Si hay un chromedriver.exe local (misma carpeta que el scraper), usarlo y
    # NO descargar nada — evita el fallo de red al bajar el driver (WinError 10065).
    _local = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chromedriver.exe')
    if os.path.exists(_local):
        print(f'  Usando chromedriver local: {_local}')
        return uc.Chrome(options=build_opts(), use_subprocess=True, driver_executable_path=_local)
    mv = _chrome_major()
    try:
        kw = {'use_subprocess': True}
        if mv:
            kw['version_main'] = mv
        return uc.Chrome(options=build_opts(), **kw)
    except Exception as e:
        m = re.search(r'Current browser version is (\d+)', str(e))
        if not m:
            raise
        ver = int(m.group(1))
        print(f'  Ajustando ChromeDriver a Chrome {ver} y reintentando...')
        return uc.Chrome(options=build_opts(), use_subprocess=True, version_main=ver)

def init_driver():
    print('Iniciando Chrome...')
    def _mk():
        o = uc.ChromeOptions()
        o.add_argument('--window-size=1920,1080')
        o.add_argument('--lang=es-ES')
        return o
    if os.environ.get('GITHUB_ACTIONS'):
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        opts2 = Options()
        opts2.add_argument('--headless=new')
        opts2.add_argument('--no-sandbox')
        opts2.add_argument('--disable-dev-shm-usage')
        opts2.add_argument('--disable-gpu')
        opts2.add_argument('--window-size=1920,1080')
        driver = webdriver.Chrome(options=opts2)
    else:
        driver = _uc_chrome(_mk)
    print('Chrome listo.\n')
    return driver

def init_driver_stealth():
    """Driver anti-detección para Idealista — usa undetected_chromedriver siempre."""
    print('Iniciando Chrome stealth para Idealista...')
    _ci = bool(os.environ.get('GITHUB_ACTIONS'))
    def _mk():
        o = uc.ChromeOptions()
        o.add_argument('--window-size=1920,1080')
        o.add_argument('--lang=es-ES')
        o.add_argument('--no-first-run')
        o.add_argument('--no-default-browser-check')
        if _ci:
            o.add_argument('--headless=new')
            o.add_argument('--no-sandbox')
            o.add_argument('--disable-dev-shm-usage')
            o.add_argument('--disable-gpu')
            o.add_argument('--disable-blink-features=AutomationControlled')
            o.add_argument('--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36')
        return o
    try:
        driver = _uc_chrome(_mk)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    except Exception as e:
        print(f'  Stealth driver falló ({e}), usando driver estándar')
        driver = init_driver()
    print('Chrome stealth listo.\n')
    return driver

def accept_cookies(driver):
    for bid in ['didomi-notice-agree-button','onetrust-accept-btn-handler',
                'acceptAllButton','accept-cookies']:
        try: driver.find_element(By.ID, bid).click(); time.sleep(0.3); return
        except: pass
    for txt in ['Aceptar todo','Aceptar todas','Aceptar','Accept all']:
        try:
            driver.find_element(By.XPATH, f'//button[contains(.,"{txt}")]').click()
            time.sleep(0.3); return
        except: pass

def get_page(driver, url, wait=3):
    try:
        driver.get(url); time.sleep(wait)
        accept_cookies(driver)
        return driver.page_source
    except Exception as e:
        print(f'  ERROR {url[:70]}: {e}')
        return None

# ─── listings ─────────────────────────────────────────
found_listings = []
seen_urls = set()

def normalizar_titulo(s):
    s = (s or '').lower().strip()
    s = re.sub(r'[^\w\s]', '', s)
    for w in ['hotel','hostal','en','venta','de','la','el','las','los','un','una',
              'lujo','boutique','para','sale','for','luxury','the']:
        s = re.sub(rf'\b{w}\b', '', s)
    return re.sub(r'\s+', ' ', s).strip()

def es_duplicado(item, lista=None):
    """Detecta duplicados por precio + título similar"""
    from difflib import SequenceMatcher
    if lista is None: lista = found_listings
    precio = re.sub(r'[^\d]', '', item.get('price',''))
    titulo = normalizar_titulo(item.get('title',''))
    if not precio or not titulo: return False
    for ex in lista:
        if re.sub(r'[^\d]', '', ex.get('price','')) == precio:
            if SequenceMatcher(None, titulo, normalizar_titulo(ex.get('title',''))).ratio() >= 0.72:
                return True
    return False


# ─── región y limpieza de ubicación ──────────────────
def _norm(s):
    if not s: return ''
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = s.lower()
    s = re.sub(r'[^\w\s]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()

_REGION_MAP = {
    'madrid':'Madrid','alcala de henares':'Madrid','getafe':'Madrid','mostoles':'Madrid',
    'alcobendas':'Madrid','pozuelo':'Madrid','majadahonda':'Madrid','cercedilla':'Madrid',
    'aranjuez':'Madrid','soto del real':'Madrid','rascafria':'Madrid','valdemoro':'Madrid',
    'guadarrama':'Madrid','villacastin':'Madrid',
    'barcelona':'Cataluña','girona':'Cataluña','tarragona':'Cataluña','lleida':'Cataluña',
    'sitges':'Cataluña','lloret':'Cataluña','roses':'Cataluña','calella':'Cataluña',
    'palamos':'Cataluña','creixell':'Cataluña','salou':'Cataluña','cambrils':'Cataluña',
    'reus':'Cataluña','tortosa':'Cataluña','platja daro':'Cataluña','vidreres':'Cataluña',
    'sant feliu de guixols':'Cataluña','badalona':'Cataluña','sabadell':'Cataluña',
    'terrassa':'Cataluña','manresa':'Cataluña','mataro':'Cataluña','vic':'Cataluña',
    'figueres':'Cataluña','tordera':'Cataluña','mora la nova':'Cataluña',
    'calafell':'Cataluña','empuriabrava':'Cataluña','blanes':'Cataluña',
    'malgrat de mar':'Cataluña','castelldefels':'Cataluña','montblanc':'Cataluña',
    'granollers':'Cataluña','costa brava':'Cataluña','costa dorada':'Cataluña',
    'cataluña':'Cataluña','catalonia':'Cataluña','vielha':'Cataluña',
    'sevilla':'Andalucía','malaga':'Andalucía','granada':'Andalucía',
    'cadiz':'Andalucía','huelva':'Andalucía','almeria':'Andalucía',
    'cordoba':'Andalucía','jaen':'Andalucía','marbella':'Andalucía',
    'torremolinos':'Andalucía','benalmadena':'Andalucía','nerja':'Andalucía',
    'fuengirola':'Andalucía','ronda':'Andalucía','tarifa':'Andalucía',
    'velez malaga':'Andalucía','aguadulce':'Andalucía','estepona':'Andalucía',
    'mijas':'Andalucía','motril':'Andalucía','almunecar':'Andalucía',
    'salobrena':'Andalucía','gaucin':'Andalucía','mojacar':'Andalucía',
    'antequera':'Andalucía','competa':'Andalucía','torrox':'Andalucía',
    'frigiliana':'Andalucía','sotogrande':'Andalucía','carmona':'Andalucía',
    'aracena':'Andalucía','linares':'Andalucía','ubeda':'Andalucía',
    'costa del sol':'Andalucía','andalucia':'Andalucía','andalusia':'Andalucía',
    'pizarra':'Andalucía','tolox':'Andalucía','alhaurin':'Andalucía',
    'orgiva':'Andalucía','zahara':'Andalucía','sedella':'Andalucía',
    'baza':'Andalucía','coin':'Andalucía','rute':'Andalucía','chiclana':'Andalucía',
    'jerez':'Andalucía','algeciras':'Andalucía','san roque':'Andalucía',
    'arcos de la frontera':'Andalucía','medina sidonia':'Andalucía',
    'alhama de granada':'Andalucía','alcala la real':'Andalucía',
    'galaroza':'Andalucía','busquistar':'Andalucía','guejar sierra':'Andalucía',
    'alora':'Andalucía','diezma':'Andalucía','iznate':'Andalucía',
    'la zubia':'Andalucía','lecrin':'Andalucía','mondujar':'Andalucía',
    'pinos genil':'Andalucía','vejer':'Andalucía','seville':'Andalucía',
    'villanueva de la concepcion':'Andalucía','macharaviaya':'Andalucía',
    'casariche':'Andalucía','montejaque':'Andalucía','moclin':'Andalucía',
    'calahonda':'Andalucía','tabernas':'Andalucía','carboneras':'Andalucía',
    'turre':'Andalucía','laroles':'Andalucía','gualchos':'Andalucía',
    'iznajar':'Andalucía','baena':'Andalucía','constantina':'Andalucía',
    'la iruela':'Andalucía','lanjaron':'Andalucía','albolote':'Andalucía',
    'casarabonela':'Andalucía','benajarafe':'Andalucía','vinuela':'Andalucía',
    'almayate':'Andalucía','villanueva de tapia':'Andalucía','arriate':'Andalucía',
    'mijas costa':'Andalucía','playa granada':'Andalucía',
    'valencia':'C. Valenciana','alicante':'C. Valenciana','castellon':'C. Valenciana',
    'benidorm':'C. Valenciana','denia':'C. Valenciana','javea':'C. Valenciana',
    'calpe':'C. Valenciana','altea':'C. Valenciana','benissa':'C. Valenciana',
    'orihuela':'C. Valenciana','torrevieja':'C. Valenciana','santa pola':'C. Valenciana',
    'elche':'C. Valenciana','gandia':'C. Valenciana','peniscola':'C. Valenciana',
    'costa blanca':'C. Valenciana','beniali':'C. Valenciana','palomar':'C. Valenciana',
    'bocairente':'C. Valenciana','finestrat':'C. Valenciana','alfaz del pi':'C. Valenciana',
    'el campello':'C. Valenciana','villajoyosa':'C. Valenciana',
    'playas de orihuela':'C. Valenciana','vall de gallinera':'C. Valenciana',
    'calig':'C. Valenciana','oliva':'C. Valenciana','vinaros':'C. Valenciana',
    'parcent':'C. Valenciana','jalon':'C. Valenciana','rojales':'C. Valenciana',
    'moraira':'C. Valenciana','orba':'C. Valenciana','alcoy':'C. Valenciana',
    'xativa':'C. Valenciana','alzira':'C. Valenciana','burriana':'C. Valenciana',
    'enguera':'C. Valenciana','chulilla':'C. Valenciana','tarbena':'C. Valenciana',
    'ondara':'C. Valenciana','guardamar del segura':'C. Valenciana',
    'guadalest':'C. Valenciana','la nucia':'C. Valenciana','lliber':'C. Valenciana',
    'san vicente del raspeig':'C. Valenciana','orihuela costa':'C. Valenciana',
    'albir':'C. Valenciana','villanueva de san carlos':'C. Valenciana',
    'mallorca':'Baleares','menorca':'Baleares','ibiza':'Baleares',
    'formentera':'Baleares','palma':'Baleares','baleares':'Baleares',
    'balears':'Baleares','islas baleares':'Baleares','illes balears':'Baleares',
    'balearic islands':'Baleares','eivissa':'Baleares','manacor':'Baleares',
    'pollensa':'Baleares','alcudia':'Baleares','soller':'Baleares',
    'estellenchs':'Baleares','ses salines':'Baleares','capdepera':'Baleares',
    'magaluf':'Baleares','porto cristo':'Baleares','cala millor':'Baleares',
    'sineu':'Baleares','arta':'Baleares','peguera':'Baleares','portocolom':'Baleares',
    'inca':'Baleares','arenal':'Baleares','llucmajor':'Baleares','campos':'Baleares',
    'felanitx':'Baleares','santanyi':'Baleares','ciutadella':'Baleares',
    'mahon':'Baleares','mao':'Baleares','son servera':'Baleares',
    'can picafort':'Baleares','cala ratjada':'Baleares','valldemosa':'Baleares',
    'sencelles':'Baleares','alaro':'Baleares','bunyola':'Baleares','muro':'Baleares',
    'calvia':'Baleares','santa ponsa':'Baleares','colonia de sant jordi':'Baleares',
    'portals nous':'Baleares','ferreries':'Baleares','es mercadal':'Baleares',
    'tenerife':'Canarias','las palmas':'Canarias','gran canaria':'Canarias',
    'lanzarote':'Canarias','fuerteventura':'Canarias','la palma':'Canarias',
    'el hierro':'Canarias','la gomera':'Canarias',
    'santa cruz de tenerife':'Canarias','adeje':'Canarias','arona':'Canarias',
    'mogan':'Canarias','macher':'Canarias','costa adeje':'Canarias',
    'islas canarias':'Canarias','canarias':'Canarias','maspalomas':'Canarias',
    'los realejos':'Canarias','la orotava':'Canarias','teguise':'Canarias',
    'yaiza':'Canarias','santa brigida':'Canarias','puerto de la cruz':'Canarias',
    'bilbao':'País Vasco','donostia':'País Vasco','vitoria':'País Vasco',
    'san sebastian':'País Vasco','bizkaia':'País Vasco','oiartzun':'País Vasco',
    'pamplona':'Navarra','navarra':'Navarra',
    'santander':'Cantabria','cantabria':'Cantabria','reinosa':'Cantabria',
    'oviedo':'Asturias','gijon':'Asturias','asturias':'Asturias',
    'cangas de onis':'Asturias','llanes':'Asturias','cudillero':'Asturias',
    'a coruna':'Galicia','coruna':'Galicia','vigo':'Galicia','pontevedra':'Galicia',
    'santiago':'Galicia','lugo':'Galicia','ourense':'Galicia','galicia':'Galicia',
    'a guarda':'Galicia','cuntis':'Galicia','moana':'Galicia','ribadeo':'Galicia',
    'ames':'Galicia','ordes':'Galicia','catoira':'Galicia','lalin':'Galicia',
    'o porrino':'Galicia','arzua':'Galicia','bueu':'Galicia','marin':'Galicia',
    'salamanca':'Castilla y León','burgos':'Castilla y León',
    'valladolid':'Castilla y León','segovia':'Castilla y León',
    'avila':'Castilla y León','soria':'Castilla y León','zamora':'Castilla y León',
    'palencia':'Castilla y León','leon':'Castilla y León','ponferrada':'Castilla y León',
    'ciudad rodrigo':'Castilla y León','bejar':'Castilla y León',
    'puebla de sanabria':'Castilla y León',
    'toledo':'Castilla-La Mancha','ciudad real':'Castilla-La Mancha',
    'albacete':'Castilla-La Mancha','cuenca':'Castilla-La Mancha',
    'guadalajara':'Castilla-La Mancha','castilla la mancha':'Castilla-La Mancha',
    'consuegra':'Castilla-La Mancha','almagro':'Castilla-La Mancha',
    'villarrobledo':'Castilla-La Mancha','yeste':'Castilla-La Mancha',
    'caceres':'Extremadura','badajoz':'Extremadura','merida':'Extremadura',
    'trujillo':'Extremadura','zafra':'Extremadura','extremadura':'Extremadura',
    'zaragoza':'Aragón','huesca':'Aragón','teruel':'Aragón','jaca':'Aragón',
    'benasque':'Aragón','aragon':'Aragón','graus':'Aragón',
    'murcia':'Murcia','cartagena':'Murcia','lorca':'Murcia','san javier':'Murcia',
    'mazarron':'Murcia','caravaca':'Murcia','calabardina':'Murcia',
    'san pedro del pinatar':'Murcia','alhama de murcia':'Murcia',
    'aguilas':'Murcia','jumilla':'Murcia','los alcazares':'Murcia',
    'la manga':'Murcia','vera':'Murcia',
    'logrono':'La Rioja','la rioja':'La Rioja','rioja':'La Rioja',
    # Nombres cortos que colisionan con una comarca/pedania de OTRA
    # comunidad -- confirmado con datos reales de Inmo Olaya: 'vera'
    # (pueblo de Almeria/Murcia) aparece tambien dentro de 'La Vera'
    # (comarca de Caceres, Extremadura); 'santiago' (Galicia) aparece
    # dentro de 'Santiago de la Ribera' (pedania de Murcia); y 'san
    # sebastian' (Pais Vasco) aparece dentro de 'San Sebastian de la
    # Gomera' (Canarias). Al ser mas largas que esas claves genericas,
    # infer_region() ya las revisa antes (ordena por longitud).
    'la vera':'Extremadura','santiago de la ribera':'Murcia',
    'san sebastian de la gomera':'Canarias',
}

def infer_region(texto):
    """Infiere la comunidad autónoma a partir de cualquier texto de ubicación.

    IMPORTANTE (bug real encontrado probando Inmo Olaya, 21/09/2026): antes
    se comprobaba "key in t" (subcadena suelta), lo que hacia que un
    municipio corto quedara escondido DENTRO de otra palabra sin ninguna
    relacion -- p.ej. 'Villafames' contiene literalmente 'ames' (clave de
    un pueblo de Galicia) y se colaba como "Galicia" en vez de caer, ya
    en el titulo/descripcion, en Castellon/C. Valenciana. Ahora se exige
    que la clave aparezca como palabra(s) completa(s) (limites \\b), no
    como fragmento de otra palabra.
    """
    t = _norm(texto or '')
    for key in sorted(_REGION_MAP.keys(), key=len, reverse=True):
        if re.search(r'\b' + re.escape(key) + r'\b', t):
            return _REGION_MAP[key]
    return None

def limpiar_location(loc):
    """Limpia ubicaciones con basura pegada (ThinkSpain principalmente)."""
    if not loc: return loc
    # Engel & Völkers pega el texto del botón "Añadir a favoritos" delante
    # del municipio real, sin espacio (ej. "Añadir a favoritosEl Prat de
    # Llobregat") -- comprobado en hoteles_cache.json: 8 anuncios así, todos
    # de ese portal. Lo quitamos para que la ubicación mostrada (y el cruce
    # de licencias, que depende de ella) usen el municipio real.
    loc = re.sub(r'^\s*añadir a favoritos\s*', '', loc, flags=re.I)
    # Algún portal antepone el código postal al municipio (ej. "14979
    # Iznajar") -- lo quitamos igual que el resto de basura pegada.
    loc = re.sub(r'^\d{5}\s+', '', loc)
    loc = re.sub(r'â[\x00-\xff]{0,2}', '', loc)
    loc = re.sub(r'€.*', '', loc)
    loc = re.sub(r'\s+with\b.*', '', loc, flags=re.I)
    loc = re.sub(r'\bgarage\b.*', '', loc, flags=re.I)
    loc = re.sub(r'\bpool\b.*', '', loc, flags=re.I)
    loc = re.sub(r'\s*-\s*\d.*', '', loc)
    loc = re.sub(r'\s*/\s*.+', '', loc)
    loc = re.sub(r'\s+city\b.*', '', loc, flags=re.I)
    m = re.match(r'([^,]{3,40}),\s*.{4,}', loc)
    if m: loc = m.group(1)
    return loc.strip()

def clasificar_tipo(title, description=''):
    """
    Clasifica un anuncio según la misma taxonomía que ya usas en tu Excel
    (columna 'Tipología'), por orden de especificidad (el primero que
    encuentra, gana). Devuelve un string listo para esa misma columna.
    """
    texto = (title or '') + ' ' + (description or '')
    t = texto.lower()

    # Estrellas, si las menciona (para adjuntar al tipo, ej. "Hotel boutique 4*")
    estrellas = ''
    m_estrellas = re.search(r'(\d)\s*(?:\*|estrellas?|★)', t)
    if m_estrellas:
        estrellas = f' {m_estrellas.group(1)}*'

    # Orden de prioridad: de lo más específico a lo más genérico
    if 'hotel boutique' in t or 'boutique hotel' in t:
        return f'Hotel boutique{estrellas}'
    if 'hotel rural' in t:
        return f'Hotel Rural{estrellas}'
    if 'hostal' in t:
        return f'Hostal{estrellas}'
    if 'albergue' in t or 'hostel' in t:
        return 'Albergue/Hostel'
    if 'apartahotel' in t or 'apart-hotel' in t or 'apart hotel' in t:
        return f'Apartahotel{estrellas}'
    if 'casa rural' in t:
        return 'Casa Rural'
    if 'casa de huéspedes' in t or 'casa de huespedes' in t or 'guesthouse' in t or 'guest house' in t:
        return 'Casa de huéspedes'
    if 'pensión' in t or 'pension' in t:
        return 'Pensión'
    if 'b&b' in t or 'bed and breakfast' in t or 'bed & breakfast' in t:
        return 'B&B'
    # ── Apartamentos/edificios turísticos: la categoría nueva que pediste ──
    if 'apartamentos turísticos' in t or 'apartamentos turisticos' in t or \
       'apartamento turístico' in t or 'apartamento turistico' in t:
        return 'Apartamento turístico'
    if 'edificio turístico' in t or 'edificio turistico' in t:
        return 'Edificio turístico'
    if 'parador' in t:
        return 'Parador'
    if 'resort' in t:
        return 'Resort'
    if 'hotel' in t:
        return f'Hotel{estrellas}'
    return 'Alojamiento (n.d.)'  # mismo texto que ya usas tú para los ambiguos


def add_listing(item):
    url = item.get('url','').strip().split('?')[0].rstrip('/')
    if not url or url in seen_urls: return False
    if not item.get('title') or len(item['title']) < 8: return False
    if es_duplicado(item, found_listings): return False
    seen_urls.add(url)
    item['url']         = url
    item['title']       = item['title'][:120]
    item['description'] = item.get('description','')[:3000]
    # Tipología (columna "Tipología" en tu Excel) — igual para todos los
    # portales, sea cual sea el que lo haya encontrado.
    item['tipo'] = clasificar_tipo(item.get('title',''), item.get('description',''))
    # Estado: todo anuncio nuevo entra como "Activo" — se marcará "Retirado"
    # más adelante en limpiar_bajas() si deja de aparecer.
    item['estado'] = 'Activo'
    # Limpiar ubicación y asignar región automáticamente
    if item.get('location'):
        item['location'] = limpiar_location(item['location'])
    if not item.get('location_region'):
        fuentes = [item.get('location',''), item.get('title',''), item.get('description','')[:300]]
        for t in fuentes:
            r = infer_region(t)
            if r:
                item['location_region'] = r
                break
    # ── Sanear precio: descartar valores basura (parsing erroneo) ──
    # CONFIRMADO: esto antes solo arreglaba precios con dígitos raros
    # (demasiado pequeños/grandes) -- si el precio venía VACÍO desde el
    # principio (portal sin precio, o parsing que no encontró nada), se
    # quedaba tal cual en vez de caer a "Precio a consultar". Ahora
    # cubre los dos casos, para TODOS los portales por igual (este es el
    # único sitio por el que pasan todos los anuncios antes de guardarse).
    _pnum = re.sub(r'[^\d]', '', item.get('price','') or '')
    if _pnum:
        _pv = int(_pnum)
        if _pv < 1000 or _pv > 100_000_000:
            item['price'] = 'Precio a consultar'
    else:
        item['price'] = 'Precio a consultar'
    # ── Habitaciones: si el portal no las dio, sacarlas del texto ──
    # CONFIRMADO: faltaba "quartos" (portugués) -- Casa Sapo nunca se
    # beneficiaba de este respaldo porque solo buscaba términos en
    # español/inglés. Añadido sin quitar nada de lo que ya funcionaba.
    if not item.get('rooms'):
        _blob = (item.get('title','') or '') + ' ' + (item.get('description','') or '')
        _m = re.search(r'(\d{1,4})\s*(?:habitaciones|habitacion|habs?\b|dormitorios|rooms?|bedrooms?|llaves|quartos?)', _blob, re.I)
        if _m:
            _rv = int(_m.group(1))
            if 1 <= _rv <= 2000:
                item['rooms'] = _rv
    # ── m²: NO existía ningún respaldo general para esto -- cada portal
    # lo sacaba (o no) con su propio código. Añadimos uno común, igual
    # que el de habitaciones, para que cualquier portal que no lo saque
    # ya (como Casa Sapo) al menos lo intente desde el texto libre.
    if not item.get('m2'):
        # BUG REAL encontrado con un test de verdad: clean() (aplicada al
        # título, pero NO a la descripción) convierte \xa0 en un espacio
        # normal -- así que el título trae el número YA ROTO ("1 176m²"
        # con espacio normal, imposible de unir) mientras la descripción
        # sí conserva el \xa0 real. Antes buscábamos en título+descripción
        # PEGADOS, y al encontrar antes el título roto, nos quedábamos
        # con "176" en vez de "1176". Ahora miramos la descripción
        # PRIMERO (más fiable, sin procesar) y el título solo como plan B.
        _mm = None
        for _fuente in (item.get('description','') or '', item.get('title','') or ''):
            _mm = re.search(r'([\d][\d.,\xa0]*)\s*m[\u00b22]\b', _fuente, re.I)
            if _mm:
                break
        if _mm:
            try:
                _m2v = int(float(_mm.group(1).replace('\xa0', '').replace('.', '').replace(',', '.')))
                if 5 <= _m2v <= 1_000_000:  # descarta ruido (0 m² o cifras absurdas)
                    item['m2'] = _m2v
            except ValueError:
                pass
    found_listings.append(item)
    return True

# ══════════════════════════════════════════════════════
# 1. THINKSPAIN — requests + JSON-LD
# ══════════════════════════════════════════════════════
def scrape_thinkspain(driver):
    print('\u2192 ThinkSpain...')
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
        'Referer': 'https://www.thinkspain.com/property-for-sale',
        'Upgrade-Insecure-Requests': '1',
    }
    # ThinkSpain elimin\u00f3 las rutas regionales (/andalucia/hotels\u2026 ahora dan 404).
    # Las nacionales siguen vivas y ya devuelven TODOS los hoteles paginando con ?numpag=N.
    BASE_URLS = [
        'https://www.thinkspain.com/property-for-sale/hotels',
        'https://www.thinkspain.com/property-for-sale/guest-houses-bed-breakfasts',
    ]

    session = req_mod.Session()
    session.headers.update(HEADERS)

    def fetch_html(url):
        # requests primero (r\u00e1pido); si el runner est\u00e1 bloqueado (no llega ItemList),
        # cae al navegador stealth que ya tenemos abierto.
        try:
            r = session.get(url, timeout=20)
            # CONFIRMADO con datos reales: sin esto, el euro salia roto
            # como "a-brevecent" (mojibake clasico de 'requests' -- si el
            # servidor no manda el charset exacto en la cabecera, requests
            # asume Latin-1 en vez de UTF-8 aunque el contenido SI sea
            # UTF-8). Eso rompia el regex que limpia el precio del titulo
            # porque buscaba un simbolo euro de verdad y no lo encontraba
            # mal codificado. Forzamos UTF-8 explicitamente, que es lo
            # que ThinkSpain manda de verdad.
            r.encoding = 'utf-8'
            if r.status_code == 200 and 'ItemList' in r.text:
                return r.text
        except Exception as e:
            print(f'  requests KO {url[-45:]}: {e}')
        html = get_page(driver, url, wait=3)
        return html or ''

    def parsear_titulo_ts(name):
        t = re.sub(r'^[\d][\d.,]*\s*€\s*', '', name).strip()
        t = re.sub(r'^€\s*[\d][\d.,]*\s*', '', t).strip()
        t = re.sub(r'\s*\(Ref:.*?\)', '', t)
        t = re.sub(r'\s*-\s*€.*', '', t).strip()
        words = t.split()
        if len(words) >= 8:
            mid = len(words) // 2
            p1 = ' '.join(words[:mid]); p2 = ' '.join(words[mid:])
            if p1.lower()[:20] == p2.lower()[:20]: t = p1
        t = re.sub(r'\bfor sale\b', 'en venta', t, flags=re.IGNORECASE)
        t = re.sub(r'(\d+)\s+bedroom\s+', r'\1 habitaciones ', t, flags=re.IGNORECASE)
        t = t.strip()
        m = re.search(r'(?:en venta en|in)\s+(.+?)(?:\s+Hotel|\s+Guesthouse|$)', t, re.IGNORECASE)
        loc = m.group(1).strip().rstrip(',').strip() if m else 'España'
        return t, loc

    def extraer_precio_ts(name):
        m = re.search(r'^([\d][\d.,]+)\s*€', name.strip())
        if m: return m.group(1) + ' €'
        m = re.search(r'€\s*([\d][\d.,]+)', name)
        if m: return m.group(1) + ' €'
        m = re.search(r'([\d][\d.,]+)\s*€', name)
        if m: return m.group(1) + ' €'
        return 'Precio a consultar'

    def enriquecer_ficha_ts(url_ficha):
        # CONFIRMADO con la ficha real (property/9383731): la descripcion
        # del listado (el 'description' del JSON-LD ItemList) viene
        # TRUNCADA por el propio ThinkSpain -- acaba literal en '...'. La
        # descripcion COMPLETA solo esta en la ficha individual, dentro de
        # <p class="property-description"> (contenedor #property-description).
        # OJO: le pasamos el elemento de BeautifulSoup TAL CUAL a clean_desc(),
        # nunca su .get_text() -- clean_desc necesita ver los <br><br> reales
        # del HTML para poder reconstruir los puntos y aparte; si le llega ya
        # como texto plano, todo el parrafo queda pegado en una sola linea.
        # Fotos: viven en el slider principal (div.twc__property--slider-
        # primary img) -- la primera imagen trae 'src' real, las siguientes
        # son lazy-load y el src real esta en 'data-src' (el 'src' que tienen
        # puesto de entrada es un gif placeholder en base64). Confirmado con
        # la ficha real -- no hay ninguna galeria mas grande escondida en JSON.
        try:
            r = session.get(url_ficha, timeout=15)
            if r.status_code != 200:
                return None, []
            r.encoding = 'utf-8'
            soup_ficha = BeautifulSoup(r.text, 'lxml')
            desc_el = soup_ficha.find('p', class_='property-description')
            descripcion = clean_desc(desc_el) if desc_el else None

            # ThinkSpain es un portal en ingles, pero cada ficha tiene un
            # selector de idioma (arriba de la descripcion) que carga la
            # traduccion via un endpoint propio de la web -- confirmado
            # viendo la peticion real que dispara ese desplegable:
            #   GET /load-property-description?id=<ID>&requestedLanguage=es&preview=0
            # con la cabecera 'X-Requested-With: XMLHttpRequest' (sin ella
            # devuelve un 404 en HTML en vez del JSON). No hace falta sesion
            # ni login -- confirmado que funciona igual sin cookies. El <ID>
            # es el mismo numero que ya llevamos en la URL de la ficha
            # (.../property-for-sale/9383731 -> id=9383731). Pedimos la
            # version en español para que TODAS las descripciones de
            # ThinkSpain queden en español como el resto de la web, en vez
            # de mezclado con ingles.
            m_id = re.search(r'/property-for-sale/(\d+)', url_ficha)
            if m_id:
                try:
                    r_es = session.get(
                        'https://www.thinkspain.com/load-property-description',
                        params={'id': m_id.group(1), 'requestedLanguage': 'es', 'preview': '0'},
                        headers={'X-Requested-With': 'XMLHttpRequest'},
                        timeout=15,
                    )
                    if r_es.status_code == 200:
                        data_es = r_es.json()
                        if data_es.get('success') and data_es.get('content'):
                            soup_es = BeautifulSoup(data_es['content'], 'lxml')
                            desc_es_el = soup_es.find('p', class_='property-description')
                            desc_es = clean_desc(desc_es_el) if desc_es_el else clean_desc(data_es['content'])
                            # Solo la usamos si de verdad trajo texto -- si no,
                            # mejor quedarnos con la version en ingles que ya
                            # teniamos que dejar el anuncio en blanco.
                            if desc_es and len(desc_es) > 20:
                                descripcion = desc_es
                except Exception as e:
                    print(f'  ThinkSpain traduccion KO {url_ficha[-45:]}: {e}')

            fotos = []
            for img in soup_ficha.select('div.twc__property--slider-primary img'):
                src = img.get('src') or ''
                if not src or src.startswith('data:'):
                    src = img.get('data-src') or ''
                if src and src.startswith('http') and src not in fotos:
                    fotos.append(src)
            return descripcion, fotos
        except Exception as e:
            print(f'  ThinkSpain ficha KO {url_ficha[-45:]}: {e}')
            return None, []

    seen_ts = set()
    total_ts = 0
    for base_url in BASE_URLS:
        region = base_url.split('/')[-1]
        paginas_vacias = 0
        for numpag in range(1, 60):
            url = base_url if numpag == 1 else f'{base_url}?numpag={numpag}'
            html = fetch_html(url)
            if not html:
                break
            soup = BeautifulSoup(html, 'lxml')

            # CONFIRMADO con diagnóstico real (07/09/2026): el JSON-LD
            # (ItemList) NUNCA trajo habitaciones/baños/m² -- solo
            # título/precio-en-texto/descripción/url. Esos datos están
            # en un sitio totalmente distinto: cada <article> de la
            # tarjeta lleva un atributo 'data-base-twc-analytic-event-
            # parameters' (pensado para analítica interna de la propia
            # web) con un JSON limpio: {"propertyID":..., "price":...,
            # "beds":..., "baths":..., "buildSqm":...}. Lo cruzamos con
            # el JSON-LD por 'propertyID' == 'productID' -- mismo
            # identificador en los dos sitios, confirmado con datos
            # reales. Esto es MUCHO más fiable que sacar el precio y
            # las habitaciones a base de regex sobre el texto del título
            # (que es justo lo que se estaba haciendo antes, y fallaba
            # para la mayoría de anuncios en cuanto el título no seguía
            # el patrón exacto esperado).
            stats_por_id = {}
            for article in soup.find_all('article', attrs={'data-base-twc-analytic-event-parameters': True}):
                try:
                    stats = json.loads(article['data-base-twc-analytic-event-parameters'])
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue
                pid = str(stats.get('propertyID', '')).strip()
                # Fallback: si el JSON de la ficha no trae buildSqm, lo leemos
                # del texto visible de la tarjeta ("1253 m2 Build"/"1253 m² Build").
                if not stats.get('buildSqm'):
                    _txt = article.get_text(' ', strip=True)
                    _mb = re.search(r'([\d][\d.,\xa0]*)\s*m\s*(?:²|2)\s*Build', _txt, re.I)
                    if _mb:
                        try:
                            _bv = int(re.sub(r'[^\d]', '', _mb.group(1)))
                            if 5 <= _bv <= 1_000_000:
                                stats['buildSqm'] = _bv
                        except ValueError:
                            pass
                if pid:
                    stats_por_id[pid] = stats

            enc = 0
            for s in soup.find_all('script', type='application/ld+json'):
                try:
                    data = json.loads(s.get_text())
                except Exception:
                    continue
                for d in (data if isinstance(data, list) else [data]):
                    if not isinstance(d, dict) or d.get('@type') != 'ItemList':
                        continue
                    for item in d.get('itemListElement', []):
                        prod = item.get('item', {}) if isinstance(item, dict) else {}
                        url_a = (prod.get('url') or prod.get('@id') or '').split('?')[0].rstrip('/')
                        if not url_a or url_a in seen_ts:
                            continue
                        name = prod.get('name', '')
                        if not name:
                            continue
                        titulo, loc = parsear_titulo_ts(name)
                        seen_ts.add(url_a)

                        # Cruce con las stats reales de la tarjeta (ver arriba)
                        product_id = str(prod.get('productID', '')).strip()
                        stats = stats_por_id.get(product_id, {})

                        precio_num = stats.get('price')
                        if isinstance(precio_num, (int, float)) and precio_num > 0:
                            precio = f'{precio_num:,.0f} €'.replace(',', '.')
                        else:
                            precio = extraer_precio_ts(name)  # fallback: el regex de siempre

                        listing = {'title': titulo, 'price': precio, 'location': loc,
                                   'description': clean_desc(prod.get('description', '')),
                                   'url': url_a, 'source': 'ThinkSpain'}
                        if isinstance(stats.get('beds'), (int, float)) and stats['beds'] > 0:
                            listing['rooms'] = int(stats['beds'])
                        if isinstance(stats.get('baths'), (int, float)) and stats['baths'] > 0:
                            listing['bathrooms'] = int(stats['baths'])
                        if isinstance(stats.get('buildSqm'), (int, float)) and stats['buildSqm'] > 0:
                            listing['m2'] = int(stats['buildSqm'])

                        # Visitamos la ficha real para sacar la descripcion
                        # COMPLETA (la del listado viene truncada por el propio
                        # ThinkSpain) y las fotos de la galeria.
                        desc_completa, fotos_ts = enriquecer_ficha_ts(url_a)
                        if desc_completa and len(desc_completa) > len(listing['description']):
                            listing['description'] = desc_completa
                        if fotos_ts:
                            listing['fotos_url'] = fotos_ts
                        time.sleep(0.25)

                        added = add_listing(listing)
                        if added: enc += 1
            total_ts += enc
            if enc > 0:
                print(f'  {region} p{numpag}: {enc} nuevos | Total TS: {total_ts}')
                paginas_vacias = 0
            else:
                paginas_vacias += 1
            if paginas_vacias >= 2: break
            time.sleep(0.4)
    print(f'  ThinkSpain TOTAL: {total_ts}')

# ══════════════════════════════════════════════════════
# 2. LUCAS FOX — requests
# ══════════════════════════════════════════════════════
def scrape_lucasfox(driver):
    print('\n→ Lucas Fox...')
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept-Language': 'es-ES,es;q=0.9',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Referer': 'https://www.lucasfox.es/',
    }
    BASE = 'https://www.lucasfox.es/comprar-vivienda/hoteles.html'
    session = req_mod.Session()
    seen_lf = set()
    total_lf = 0
    for page in range(1, 10):
        url = BASE if page == 1 else f'{BASE}?page={page}'
        try:
            time.sleep(random.uniform(2, 4))
            r = session.get(url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                print(f'  LucasFox p{page}: status {r.status_code}, parando'); break
            soup = BeautifulSoup(r.text, 'lxml')
            items = soup.find_all('a', href=re.compile(r'/comprar-vivienda/espana/.*\.html$'))
            if not items:
                print(f'  LucasFox p{page}: sin anuncios, fin'); break
            enc = 0
            for a in items:
                href = a.get('href','')
                if not href: continue
                if not href.startswith('http'): href = 'https://www.lucasfox.es' + href
                href_clean = href.split('?')[0]
                if href_clean in seen_lf: continue
                seen_lf.add(href_clean)
                li = a.find_parent('li') or a
                price_el = li.find(class_=re.compile(r'price|precio', re.I))
                title_el = li.find(class_=re.compile(r'title|heading|name', re.I)) or li.find('h2') or li.find('h3')
                title_txt = clean(title_el.get_text()) if title_el else clean(a.get_text())
                if len(title_txt) < 5: continue
                loc_el = li.find(class_=re.compile(r'location|localidad|zone|area', re.I))
                add_listing({'title': title_txt,
                             'price': clean(price_el.get_text()) if price_el else 'Precio a consultar',
                             'location': clean(loc_el.get_text()) if loc_el else 'España',
                             'description': '', 'url': href_clean, 'source': 'Lucas Fox'})
                enc += 1; total_lf += 1
            print(f'  LucasFox p{page}: {enc} | Total LF: {total_lf}')
            if enc == 0: break
        except Exception as e:
            print(f'  LucasFox error p{page}: {e}'); break
    print(f'  Lucas Fox TOTAL: {total_lf}')

# ══════════════════════════════════════════════════════
# sistema de baja
# ══════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════
# sistema de baja
# ══════════════════════════════════════════════════════
def limpiar_bajas(cache, urls_encontradas, portales_fallidos=None):
    """
    ANTES: los anuncios que llevaban 3+ ejecuciones sin aparecer se
    BORRABAN del todo (se perdía el histórico).

    AHORA: se marcan como 'Retirado' (igual que tu columna Estado en el
    Excel) y se quedan en el cache — así, cuando exportes/descargues,
    puedes ver qué ha desaparecido de la oferta sin perder el dato.
    Si un anuncio "Retirado" vuelve a aparecer en un scraping posterior
    (algunos portales reactivan anuncios), vuelve a "Activo" solo.

    portales_fallidos: nombres de 'source' (ej. {'Idealista'}) para los que
    ESTA ejecución no ha conseguido resultados de verdad (bloqueo de IP,
    captcha, caída del portal...). Un anuncio de uno de estos portales que
    no aparece hoy NO suma ausencia: no es que se haya vendido o retirado,
    es que no hemos podido comprobarlo. Sin esto, un portal bloqueado 3
    días seguidos (p.ej. Idealista tras varios días desde la misma IP)
    marcaba como "Retirado" TODOS sus anuncios de golpe, aunque siguieran
    perfectamente activos -- visto en producción: 82/82 de Idealista y
    139/350 de Milanuncios acabaron así.
    """
    portales_fallidos = portales_fallidos or set()
    marcados_retirado = 0
    reactivados = 0
    protegidos = 0
    for url, item in cache.items():
        if url not in urls_encontradas:
            if item.get('source') in portales_fallidos:
                protegidos += 1
                continue
            ausencias = item.get('ausencias', 0) + 1
            item['ausencias'] = ausencias
            if ausencias >= 3 and item.get('estado') != 'Retirado':
                item['estado'] = 'Retirado'
                marcados_retirado += 1
        else:
            item['ausencias'] = 0
            if item.get('estado') == 'Retirado':
                reactivados += 1
            item['estado'] = 'Activo'
    if marcados_retirado:
        print(f'  Marcados como Retirado: {marcados_retirado} anuncios (3+ ejecuciones sin aparecer).')
    if reactivados:
        print(f'  Reactivados (volvieron a aparecer): {reactivados} anuncios.')
    if protegidos:
        print(f'  Protegidos de baja por fallo/bloqueo del portal esta ejecucion: {protegidos} anuncios (no se les cuenta ausencia).')
    return cache

# ══════════════════════════════════════════════════════
# Historico permanente de RETIRADOS (comparables)
# ══════════════════════════════════════════════════════
def cargar_retirados():
    if os.path.exists(RETIRADOS_FILE):
        try:
            with open(RETIRADOS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                return {x.get('url'): x for x in data if x.get('url')}
            if isinstance(data, dict):
                return data
        except Exception as e:
            print(f'  Aviso: no se pudo leer retirados_historico.json ({e}); empiezo vacio.')
    return {}

def guardar_retirados(hist):
    with open(RETIRADOS_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(hist.values()), f, ensure_ascii=False, indent=1)

def actualizar_historico_retirados(cache):
    """Acumula en retirados_historico.json TODO anuncio marcado 'Retirado'.
    NUNCA borra: sobrevive a resets de cache y cambios de scraper. Guarda la
    fecha de retirada la primera vez y rellena datos utiles (m2/hab/precio) si
    faltaban. Devuelve el dict {url: item} completo del historico."""
    hist = cargar_retirados()
    nuevos = 0
    for url, item in cache.items():
        if not url or item.get('estado') != 'Retirado':
            continue
        if url not in hist:
            snap = dict(item)
            snap['fecha_retirado'] = snap.get('fecha_retirado') or TODAY
            hist[url] = snap
            nuevos += 1
        else:
            prev = hist[url]
            if not prev.get('fecha_retirado'):
                prev['fecha_retirado'] = TODAY
            for k in ('price', 'rooms', 'm2', 'beds', 'location', 'location_region',
                      'tipo', 'title', 'source', 'description'):
                if not prev.get(k) and item.get(k):
                    prev[k] = item[k]
    guardar_retirados(hist)
    print(f'  Historico de retirados: +{nuevos} nuevos (total acumulado {len(hist)}).')
    return hist

# ══════════════════════════════════════════════════════
# git push
# ══════════════════════════════════════════════════════
def subir_github(total):
    print('\nSubiendo a GitHub...')
    try:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        subprocess.run(['git','stash'], capture_output=True)
        subprocess.run(['git','pull','origin','main','--rebase'], check=True)
        subprocess.run(['git','stash','pop'], capture_output=True)

        # CONFIRMADO — riesgo real detectado antes de que pasara: si
        # 'licencias_completo.json' no existe todavía (primera vez, o
        # esa semana en concreto falló), 'git add' con un archivo
        # inexistente falla ENTERO y ni siquiera se suben index.html ni
        # hoteles_cache.json ese día. Por eso comprobamos qué archivos
        # existen de verdad antes de añadirlos, uno a uno.
        archivos_candidatos = ['index.html', 'hoteles_cache.json',
                                'index_template.html', 'licencias_completo.json',
                                'retirados_historico.json',
                                'scraper.py', 'scraper_licencias.py', 'cruzar_licencias.js',
                                'comprobar_licencias.py', 'comprobar_licencias.bat']
        archivos_a_subir = [a for a in archivos_candidatos if os.path.exists(a)]
        faltantes = [a for a in archivos_candidatos if a not in archivos_a_subir]
        if faltantes:
            print(f'  Aviso: no encontrados (se omiten esta vez): {faltantes}')
        subprocess.run(['git','add'] + archivos_a_subir, check=True)

        result = subprocess.run(['git','diff','--cached','--quiet'], capture_output=True)
        if result.returncode != 0:
            subprocess.run(['git','commit','-m',f'Actualizacion {TODAY} — {total} hoteles'], check=True)
            subprocess.run(['git','push','origin','main'], check=True)
            print(f'Subido OK: https://juanarroyo123.github.io/Hoteles-Espa-a/')
        else:
            print('Sin cambios nuevos que subir.')
    except Exception as e:
        print(f'Error git: {e}')

# ══════════════════════════════════════════════════════
# 3. LUXURYESTATE — hoteles en venta España
# ══════════════════════════════════════════════════════
def _le_enrich_ficha(driver, href):
    """Entra en la ficha de LuxuryEstate y extrae rooms, beds, m2, location y descripción."""
    resultado = {}
    try:
        driver.get(href)
        time.sleep(2.5)
        page_source = driver.page_source

        # ── Detección de bloqueo/captcha ──
        # LuxuryEstate a veces devuelve una página de verificación/error en vez
        # de la ficha real. Si no detectamos esto, el h1 de esa página ("403 ERROR",
        # "Let's confirm you are human"...) se guarda como si fuera el título del hotel.
        BLOCK_INDICATORS = [
            'confirm you are human', 'are you a robot', 'access denied',
            '403 error', '403 forbidden', 'checking your browser',
            'attention required', 'cloudflare', 'captcha',
        ]
        lower_source = page_source.lower()
        if any(ind in lower_source for ind in BLOCK_INDICATORS) or len(page_source) < 2000:
            print(f'    [LE ficha] Bloqueada/captcha en {href[:60]} — uso solo datos del listado')
            time.sleep(4)  # backoff extra para no insistir agresivamente
            return resultado  # dict vacío: el llamador usará title_fallback/desc_fallback

        soup = BeautifulSoup(page_source, 'lxml')

        # ── Título desde h1 ──
        h1 = soup.find('h1')
        if h1:
            title_h1 = clean(h1.get_text())
            # Salvaguarda extra: nunca aceptar un h1 que sea uno de los mensajes de bloqueo
            if not any(ind in title_h1.lower() for ind in BLOCK_INDICATORS) and len(title_h1) > 3:
                resultado['title_ficha'] = title_h1

        # ── Ubicación desde h1: "Hotel de lujo de 950 m2 en venta Siétamo, España"
        #    O desde el breadcrumb / texto de localización
        if h1:
            txt_h1 = clean(h1.get_text())
            # "...en venta Siétamo, España" → "Siétamo"
            m = re.search(r'en venta\s+([^,]+)', txt_h1, re.I)
            if m:
                loc = m.group(1).strip().split(',')[0].strip()
                if len(loc) > 2:
                    resultado['location'] = loc

        # Si no salió del h1, intentar breadcrumb
        if 'location' not in resultado:
            breadcrumb = soup.find('nav', attrs={'aria-label': re.compile(r'bread', re.I)})
            if not breadcrumb:
                breadcrumb = soup.find(class_=re.compile(r'breadcrumb', re.I))
            if breadcrumb:
                crumbs = [clean(a.get_text()) for a in breadcrumb.find_all('a')]
                # El último crumb antes de "España" suele ser la ciudad
                for crumb in reversed(crumbs):
                    if crumb and crumb.lower() not in ('españa', 'hoteles', 'inicio', 'home'):
                        resultado['location'] = crumb
                        break

        # ── Descripción ──
        desc_el = soup.find(class_=re.compile(r'description|descrip', re.I))
        if not desc_el:
            desc_el = soup.find('div', class_=re.compile(r'text|content|body', re.I))
        if desc_el:
            resultado['description'] = clean(desc_el.get_text()).replace('~', ' ')[:1500]

        # ── Datos estructurados: sección DETALLES ──
        # Buscar todos los pares "Label: Valor" en la sección de detalles
        # Estructura: <dt>Dormitorios</dt><dd>12</dd> o <span>Dormitorios: 12</span>
        full_text = soup.get_text(' ', strip=True)

        # Dormitorios / habitaciones — campo principal
        for pat in [
            r'Dormitorios[:\s]+(\d+)',
            r'Habitaciones[:\s]+(\d+)',
            r'Estancias[:\s]+(\d+)',
            r'Rooms?[:\s]+(\d+)',
            r'Bedrooms?[:\s]+(\d+)',
        ]:
            m = re.search(pat, full_text, re.I)
            if m:
                resultado['rooms'] = int(m.group(1))
                break

        # Camas / beds
        for pat in [
            r'Camas[:\s]+(\d+)',
            r'Beds?[:\s]+(\d+)',
        ]:
            m = re.search(pat, full_text, re.I)
            if m:
                resultado['beds'] = int(m.group(1))
                break

        # M² — superficie
        for pat in [
            r'Superficie[:\s]+([\d.,]+)\s*m',
            r'([\d.,]+)\s*m[\u00b22]\b',
        ]:
            m = re.search(pat, full_text, re.I)
            if m:
                val = m.group(1).replace('.', '').replace(',', '.')
                try:
                    resultado['m2'] = int(float(val))
                except:
                    pass
                break

        # Baños
        m = re.search(r'Ba[ñn]os?[:\s]+(\d+)', full_text, re.I)
        if m:
            resultado['bathrooms'] = int(m.group(1))

        # Estrellas — raro en LE pero por si acaso
        m = re.search(r'(\d)\s*estrellas?', full_text, re.I)
        if m:
            resultado['stars'] = int(m.group(1))

    except Exception as e:
        print(f'    [LE ficha] Error {href[:60]}: {e}')

    return resultado


def scrape_luxuryestate(driver):
    print('\n→ LuxuryEstate...')
    BASE = 'https://www.luxuryestate.com/es/hotels-spain'
    total_le = 0
    paginas_vacias = 0
    fichas_pendientes = []  # (href, price, loc_fallback, title_fallback, desc_fallback)

    # ── PASO 1: Recorrer páginas de listado y recopilar URLs nuevas ──
    for pagina in range(1, 40):
        url = BASE if pagina == 1 else f'{BASE}?pag={pagina}'
        try:
            driver.get(url)
            time.sleep(3)
            soup = BeautifulSoup(driver.page_source, 'lxml')

            cards = soup.find_all('li', class_=re.compile(r'search-list__item'))
            if not cards:
                paginas_vacias += 1
                if paginas_vacias >= 2: break
                continue

            paginas_vacias = 0

            for card in cards:
                # URL
                a = card.find('a', href=re.compile(r'/es/p\d+'))
                if not a: continue
                href = a.get('href', '')
                if not href.startswith('http'): href = 'https://www.luxuryestate.com' + href
                href = href.split('?')[0].rstrip('/')
                if href in seen_urls: continue

                # Precio del listado
                price_el = card.find('div', class_=re.compile(r'price'))
                price_raw = clean(price_el.get_text()) if price_el else ''
                price = re.sub(r'€\s*([\d.,]+)', r'\1 €', price_raw.replace(' ', '')).strip()
                # CONFIRMADO como fallo real: si el texto del precio no
                # tenía el símbolo € (p.ej. "Price on request", o la
                # tarjeta está vacía), el regex de arriba no encontraba
                # nada que sustituir y nos quedábamos con basura sin
                # espacios ("Priceonrequest") en vez de cae a "Precio a
                # consultar". Ahora validamos el resultado FINAL: si no
                # tiene pinta de verdad de "NÚMERO €", se descarta.
                if not re.match(r'^[\d.,]+\s*€$', price):
                    price = 'Precio a consultar'

                # CONFIRMADO con HTML real (07/09/2026): el listado SÍ
                # trae m²/baños/habitaciones limpios en un bloque
                # <div class="specs">, cada uno junto a un icono SVG
                # propio (#size, #bath, #bed). El código anterior los
                # sacaba con un regex posicional que ASUMÍA el orden
                # "m² - habitaciones - baños", pero el orden real en la
                # web es "m² - BAÑOS - HABITACIONES" -- estaban
                # intercambiados. Además, depender del orden es frágil
                # (si a un anuncio le falta un dato, todo se desplaza).
                # Ahora identificamos cada número por su ICONO asociado,
                # no por su posición -- no puede confundirse aunque
                # cambie el orden o falte algún dato.
                m2_le = None
                rooms_le = None
                bathrooms_le = None
                specs_div = card.find('div', class_=re.compile(r'\bspecs\b'))
                if specs_div:
                    for svg in specs_div.find_all('svg'):
                        use_tag = svg.find('use')
                        if not use_tag:
                            continue
                        # BUG REAL encontrado con un test de verdad: esta
                        # variable se llamaba 'href' antes, igual que la
                        # URL del anuncio ya calculada más arriba (línea
                        # ~la del 'a = card.find(...)'). Al reutilizar el
                        # mismo nombre dentro de este bucle, SOBRESCRIBÍA
                        # la URL real del anuncio con el href del icono
                        # SVG (p.ej. '...sprite.svg#bed') -- y como varios
                        # anuncios distintos acababan con el mismo
                        # fragmento repetido, el sistema los trataba como
                        # duplicados entre sí y descartaba casi todos
                        # (de 452 fichas solo pasaban 12). Ahora con un
                        # nombre de variable distinto no puede volver a
                        # pasar.
                        href_icono = use_tag.get('xlink:href', '') or use_tag.get('href', '') or ''

                        valor_texto = ''
                        nodo = svg.next_sibling
                        while nodo and not (hasattr(nodo, 'name') and nodo.name == 'svg'):
                            if isinstance(nodo, str):
                                valor_texto += nodo
                            nodo = nodo.next_sibling
                        valor_texto = valor_texto.strip()

                        if '#size' in href_icono:
                            m = re.search(r'([\d][\d.,]*)', valor_texto)
                            if m:
                                try:
                                    m2_le = int(float(m.group(1).replace('.', '').replace(',', '.')))
                                except ValueError:
                                    pass
                        elif '#bath' in href_icono:
                            m = re.search(r'(\d+)', valor_texto)
                            if m:
                                bathrooms_le = int(m.group(1))
                        elif '#bed' in href_icono:
                            m = re.search(r'(\d+)', valor_texto)
                            if m:
                                rooms_le = int(m.group(1))

                # Ubicación fallback desde URL
                loc_fallback = ''
                m = re.search(r'hotel-for-sale-(.+)$', href)
                if m: loc_fallback = m.group(1).replace('-', ' ').title()

                # Título fallback
                title_el = card.find(['h2', 'h3', 'h4'])
                title_fallback = clean(title_el.get_text()) if title_el else f'Hotel en venta en {loc_fallback or "España"}'

                # Descripción fallback del listado
                desc_el = card.find('p')
                desc_fallback = clean(desc_el.get_text()).replace('~', ' ')[:1500] if desc_el else ''

                fichas_pendientes.append((href, price, loc_fallback, title_fallback, desc_fallback, m2_le, rooms_le, bathrooms_le))

            if paginas_vacias == 0:
                print(f'  LE listado p{pagina}: {len([f for f in fichas_pendientes])} fichas acumuladas')
            time.sleep(1)

        except Exception as e:
            print(f'  Error listado p{pagina}: {e}')
            break

    print(f'  LE: {len(fichas_pendientes)} fichas nuevas.')

    # ── PASO 2: Entrar en cada ficha ──
    # DESACTIVADO temporalmente (01/09/2026): LuxuryEstate está bloqueando
    # el 100% de las visitas a fichas individuales (captcha/403). Entrar en
    # cada una solo para que falle tira ~50 minutos a la basura y quema
    # peticiones contra el bloqueo sin sacar ningún dato extra.
    # Nos quedamos con lo que ya sacamos del listado (título, precio,
    # ubicación, descripción corta) — es peor que con datos completos,
    # pero real y rápido. Cuando LuxuryEstate deje de bloquear (o metamos
    # proxies), se puede reactivar poniendo ENRIQUECER_FICHAS_LE = True.
    ENRIQUECER_FICHAS_LE = False

    for i, (href, price, loc_fallback, title_fallback, desc_fallback, m2_le, rooms_le, bathrooms_le) in enumerate(fichas_pendientes):
        if ENRIQUECER_FICHAS_LE:
            ficha = _le_enrich_ficha(driver, href)
        else:
            ficha = {}

        title     = ficha.get('title_ficha') or title_fallback
        loc       = ficha.get('location') or loc_fallback or 'España'
        desc      = ficha.get('description') or desc_fallback
        # m²/habitaciones/baños: preferimos los de la ficha si los tenemos
        # (más fiables), y si no, los que ya sacamos del propio listado.
        rooms     = ficha.get('rooms') or rooms_le
        m2        = ficha.get('m2') or m2_le
        bathrooms = ficha.get('bathrooms') or bathrooms_le

        item = {
            'title':           title,
            'price':           price,
            'location':        loc,
            'description':     desc,
            'url':             href,
            'source':          'LuxuryEstate',
            'date':            TODAY,
        }
        # Campos estructurados — solo si se encontraron
        if rooms:                    item['rooms']      = rooms
        if ficha.get('beds'):        item['beds']       = ficha['beds']
        if m2:                       item['m2']         = m2
        if bathrooms:                item['bathrooms']  = bathrooms
        if ficha.get('stars'):       item['stars']      = ficha['stars']

        added = add_listing(item)
        if added:
            total_le += 1
            datos = []
            if rooms: datos.append(f"{rooms} hab")
            if m2:    datos.append(f"{m2} m²")
            print(f'  [{i+1}/{len(fichas_pendientes)}] ✅ {loc} — {" | ".join(datos) or "sin datos extra"}')
        # Solo hace falta esperar entre peticiones si de verdad hicimos una
        # petición (visita a la ficha). Sin visita, no hay razón para frenar.
        if ENRIQUECER_FICHAS_LE:
            time.sleep(1.5)

    print(f'  LuxuryEstate TOTAL: {total_le}')

# ══════════════════════════════════════════════════════
# 4. OI REAL ESTATE — hoteles en venta España
# ══════════════════════════════════════════════════════
def scrape_oirealestate(driver):
    print('\n→ Oi Real Estate...')
    import requests as req_mod
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept-Language': 'es-ES,es;q=0.9',
    }
    BASE = 'https://www.oirealestate.net'
    pages = [
        f'{BASE}/venta/hoteles',
        f'{BASE}/venta/hoteles/page-2',
        f'{BASE}/venta/hoteles/page-3',
    ]
    seen_oi = set()
    total_oi = 0

    for page_url in pages:
        try:
            r = req_mod.get(page_url, headers=HEADERS, timeout=15)
            if r.status_code != 200: continue
            soup = BeautifulSoup(r.text, 'lxml')
            links = list(set([
                a.get('href') for a in soup.find_all('a', href=re.compile(r'/propiedad/\d+'))
                if a.get('href')
            ]))
            for link in links:
                full = BASE + link if link.startswith('/') else link
                full = full.split('?')[0].rstrip('/')
                if full in seen_oi or full in seen_urls: continue
                seen_oi.add(full)
                try:
                    r2 = req_mod.get(full, headers=HEADERS, timeout=15)
                    if r2.status_code != 200: continue
                    soup2 = BeautifulSoup(r2.text, 'lxml')

                    # Título
                    h1 = soup2.find('h1')
                    title = clean(h1.get_text()) if h1 else ''
                    if not title or len(title) < 8: continue

                    # Precio
                    price_el = soup2.find(string=re.compile(r'[\d.,]+\s*€'))
                    price = clean(str(price_el)) if price_el else 'Precio a consultar'

                    # Ubicación — extraer de la URL
                    m = re.search(r'/propiedad/\d+/[^/]+-en-venta-en-(.+)$', link)
                    loc = m.group(1).replace('-', ' ').title() if m else 'España'

                    # Descripción
                    desc_el = soup2.find('div', class_=re.compile(r'desc|content|text|body', re.I))
                    description = clean_desc(desc_el) if desc_el else ''

                    added = add_listing({
                        'title': title,
                        'price': price,
                        'location': loc,
                        'description': description,
                        'url': full,
                        'source': 'Oi Real Estate',
                        'date': TODAY
                    })
                    if added: total_oi += 1
                    time.sleep(0.5)
                except Exception as e:
                    print(f'  Error ficha {full[:60]}: {e}')
        except Exception as e:
            print(f'  Error página {page_url}: {e}')

    print(f'  Oi Real Estate TOTAL: {total_oi}')

# ══════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════
# 5. NEGOCIOSENVENTA — hoteles en venta España
# ══════════════════════════════════════════════════════
# Ficha individual de NegociosEnVenta -- REUTILIZADA por scrape_negociosenventa()
# y scrape_negociosenventa_traspasos(). CONFIRMADO con una ficha real
# (hotel-en-el-camino-de-santiago-en-burgos-8175): la descripcion que se
# saca del LISTADO (container.find('p') en la tarjeta de busqueda) es solo
# un resumen corto de 1-2 frases -- la descripcion COMPLETA (habitaciones,
# servicios, cifras del negocio, ubicacion...) esta en la ficha individual,
# en el <p> que viene justo despues de <span class="titleInfo">Informacion
# sobre este anuncio</span>. Las FOTOS reales de la galeria tampoco estan
# en el listado (que solo trae la foto de portada) -- estan en la ficha,
# en los <a data-lightbox="advert-image-..."><img src="/img/original/
# {ID}_....webp"></a> del carrusel. Es HTML servido tal cual (confirmado
# con un fetch() de verdad -- no hace falta Selenium/JS para verlo), asi
# que basta con 'requests' normal, mas rapido que abrir el navegador otra vez.
def enriquecer_ficha_nv(url_ficha, session):
    try:
        r = session.get(url_ficha, timeout=15)
        if r.status_code != 200:
            return None, []
        r.encoding = 'utf-8'
        soup = BeautifulSoup(r.text, 'lxml')
        titulo_info = soup.find('span', class_='titleInfo')
        desc_el = titulo_info.find_next_sibling('p') if titulo_info else None
        descripcion = clean_desc(desc_el) if desc_el else None
        fotos = []
        for a in soup.select('a[data-lightbox]'):
            src = a.get('href') or ''
            if not src:
                img = a.find('img')
                src = img.get('src') if img else ''
            if src and not src.startswith('http'):
                src = 'https://www.negociosenventa.es' + src
            if src and src.startswith('http') and src not in fotos:
                fotos.append(src)
        return descripcion, fotos
    except Exception as e:
        print(f'  NegociosEnVenta ficha KO {url_ficha[-45:]}: {e}')
        return None, []


def scrape_negociosenventa(driver):
    print('\n→ NegociosEnVenta...')
    import requests as req_mod
    BASE = 'https://www.negociosenventa.es'
    session = req_mod.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'})
    pages = [f'{BASE}/venta/hosteleria/hoteles', f'{BASE}/venta/hosteleria/hoteles?page=2']
    total_nv = 0
    seen_nv = set()
    for page_url in pages:
        try:
            html = get_page(driver, page_url, wait=4)
            if not html: continue
            soup = BeautifulSoup(html, 'lxml')
            # Cada anuncio tiene h2.listviewtitle con link dentro
            h2s = soup.find_all('h2', class_='listviewtitle')
            for h in h2s:
                a = h.find('a', href=True)
                if not a: continue
                href = a.get('href','')
                if not href.startswith('http'): href = BASE + href
                href = href.split('?')[0].rstrip('/')
                if href in seen_nv or href in seen_urls: continue
                seen_nv.add(href)
                title = clean(h.get_text())
                if not title or len(title) < 5: continue
                # Contenedor padre para precio y ciudad
                container = h.parent  # div.newslisttext
                loc_el = container.find('span', class_='textintro') if container else None
                loc = clean(loc_el.get_text()) if loc_el else 'España'
                desc_el = container.find('p') if container else None
                description = clean(desc_el.get_text()) if desc_el else ''
                # Precio — subir niveles hasta encontrar numPrice
                price = 'Precio a consultar'
                el = h
                for _ in range(8):
                    el = el.parent
                    if not el: break
                    p = el.find('span', class_='numPrice')
                    if p:
                        precio_txt = clean(p.get_text())
                        if precio_txt and precio_txt != '1€' and precio_txt != '1 €':
                            price = precio_txt
                        break
                # Visitamos la ficha real para sacar la descripcion completa y las
                # fotos de la galeria (ver enriquecer_ficha_nv) -- lo que trae el
                # listado es solo un resumen corto y la foto de portada.
                item_nv = {'title':title,'price':price,'location':loc,
                    'description':description,'url':href,'source':'NegociosEnVenta','date':TODAY}
                desc_completa, fotos = enriquecer_ficha_nv(href, session)
                if desc_completa and len(desc_completa) > len(description):
                    item_nv['description'] = desc_completa
                if fotos:
                    item_nv['fotos_url'] = fotos
                time.sleep(random.uniform(0.4, 0.9))
                added = add_listing(item_nv)
                if added: total_nv += 1
        except Exception as e:
            print(f'  Error {page_url}: {e}')
    print(f'  NegociosEnVenta TOTAL: {total_nv}')


# ══════════════════════════════════════════════════════
# 5b. NEGOCIOSENVENTA -- TRASPASOS (hoteles + hostales-pensiones)
# ══════════════════════════════════════════════════════
# NUEVO, 21/09/2026 -- scrape_negociosenventa() de arriba solo mira la
# seccion "/venta/hosteleria/hoteles" del portal; el propio Juan detecto
# que la seccion "/traspaso/hosteleria/..." (traspaso de negocio, no venta
# del inmueble) NO se estaba mirando nunca. Es el MISMO sitio y la MISMA
# plantilla de tarjeta (h2.listviewtitle, span.textintro, span.numPrice),
# solo cambia la categoria de la URL -- reutilizamos el parseo tal cual.
#
# A diferencia de la funcion de venta (que asume fijo 2 paginas), aqui no
# sabemos de antemano cuantas paginas trae cada categoria de traspaso, asi
# que paginamos de verdad con ?page=N y paramos cuando dos paginas seguidas
# no traen ninguna ficha que no hubieramos visto ya EN ESTA MISMA pasada
# (igual que en Inmo Olaya) -- ojo, distinto de "ya estaba en cache de
# antes", que pararia de forma incorrecta si un dia no hay anuncios nuevos
# pero el portal sigue teniendo mas paginas con anuncios antiguos.
#
# IMPORTANTE -- Operacion: estos anuncios SON traspaso por definicion
# (vienen de la categoria /traspaso/ del portal), pero el texto del propio
# anuncio no siempre contiene una de las frases que detectarOperacion()
# busca en el frontend (ver index_template.html) -- por eso aqui marcamos
# 'operacion_detectada':'traspaso' explicitamente en cada item, y
# getEffectiveOperacion() en el frontend se fia de ese dato antes de
# intentar adivinarlo por texto.
def scrape_negociosenventa_traspasos(driver):
    print('\n→ NegociosEnVenta (traspasos)...')
    import requests as req_mod
    BASE = 'https://www.negociosenventa.es'
    session = req_mod.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'})
    CATEGORIAS = [
        f'{BASE}/traspaso/hosteleria/hoteles',
        f'{BASE}/traspaso/hosteleria/hostales-pensiones',
    ]
    total_nvt = 0
    seen_nvt = set()
    for categoria_url in CATEGORIAS:
        print(f'  Categoria: {categoria_url}')
        paginas_vacias = 0
        for pagina in range(1, 30):
            page_url = categoria_url if pagina == 1 else f'{categoria_url}?page={pagina}'
            try:
                html = get_page(driver, page_url, wait=4)
                if not html:
                    print(f'    p{pagina}: sin respuesta, parando esta categoria')
                    break
                soup = BeautifulSoup(html, 'lxml')
                h2s = soup.find_all('h2', class_='listviewtitle')
                nuevos_pagina = 0
                for h in h2s:
                    a = h.find('a', href=True)
                    if not a:
                        continue
                    href = a.get('href', '')
                    if not href.startswith('http'):
                        href = BASE + href
                    href = href.split('?')[0].rstrip('/')
                    if not href or href in seen_nvt:
                        continue
                    seen_nvt.add(href)
                    nuevos_pagina += 1
                    if href in seen_urls:
                        continue  # ya lo teniamos de antes (otra fuente o pasada anterior)
                    title = clean(h.get_text())
                    if not title or len(title) < 5:
                        continue
                    container = h.parent  # div.newslisttext
                    loc_el = container.find('span', class_='textintro') if container else None
                    loc = clean(loc_el.get_text()) if loc_el else 'España'
                    desc_el = container.find('p') if container else None
                    description = clean(desc_el.get_text()) if desc_el else ''
                    price = 'Precio a consultar'
                    el = h
                    for _ in range(8):
                        el = el.parent
                        if not el:
                            break
                        p = el.find('span', class_='numPrice')
                        if p:
                            precio_txt = clean(p.get_text())
                            if precio_txt and precio_txt != '1€' and precio_txt != '1 €':
                                price = precio_txt
                            break
                    # Igual que en scrape_negociosenventa(): la ficha real trae la
                    # descripcion completa y las fotos de la galeria.
                    item_nvt = {
                        'title': title, 'price': price, 'location': loc,
                        'description': description, 'url': href,
                        'source': 'NegociosEnVenta', 'date': TODAY,
                        'operacion_detectada': 'traspaso',
                    }
                    desc_completa, fotos = enriquecer_ficha_nv(href, session)
                    if desc_completa and len(desc_completa) > len(description):
                        item_nvt['description'] = desc_completa
                    if fotos:
                        item_nvt['fotos_url'] = fotos
                    time.sleep(random.uniform(0.4, 0.9))
                    added = add_listing(item_nvt)
                    if added:
                        total_nvt += 1
                print(f'    p{pagina}: {nuevos_pagina} fichas nuevas')
                if nuevos_pagina == 0:
                    paginas_vacias += 1
                    if paginas_vacias >= 2:
                        break
                else:
                    paginas_vacias = 0
                time.sleep(random.uniform(1, 2))
            except Exception as e:
                print(f'    Error {page_url}: {e}')
                break
    print(f'  NegociosEnVenta (traspasos) TOTAL: {total_nvt}')


# ══════════════════════════════════════════════════════
# 6. ENGEL & VÖLKERS — hoteles en venta España
# ══════════════════════════════════════════════════════
def scrape_engelvoelkers(driver):
    print('\n→ Engel & Völkers...')
    import requests as req_mod
    HEADERS_EV = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept-Language': 'es-ES,es;q=0.9',
    }
    BASE = 'https://www.engelvoelkers.com'
    url = f'{BASE}/es/es/inmuebles/com/compra/hotel'
    total_ev = 0
    try:
        r = req_mod.get(url, headers=HEADERS_EV, timeout=15)
        if r.status_code != 200:
            print(f'  Status {r.status_code}, saltando')
            return
        soup = BeautifulSoup(r.text, 'lxml')
        cards = soup.find_all('article')
        for card in cards:
            # Link
            a = card.find('a', href=re.compile(r'/es/es/exposes/'))
            if not a: continue
            href = BASE + a.get('href','')
            href = href.split('?')[0].rstrip('/')
            if href in seen_urls: continue
            # Título desde img alt
            img = card.find('img')
            title = clean(img.get('alt','')) if img else ''
            if not title or len(title) < 8: continue
            # Texto completo para extraer ubicación y precio
            txt = card.get_text()
            # Precio
            pm = re.search(r'([\d.,]+(?:\.\d{3})*\s*€)', txt)
            price = clean(pm.group(1)) if pm else 'Precio a consultar'
            # Ubicación — primera línea antes del título
            loc = 'España'
            lines = [l.strip() for l in txt.split('\n') if l.strip()]
            for line in lines[:3]:
                if 'España' in line or 'Baleares' in line or ',' in line:
                    loc = line.split('España')[0].strip().rstrip(',').strip()
                    if loc: break
            added = add_listing({
                'title': title,
                'price': price,
                'location': loc or 'España',
                'description': '',
                'url': href,
                'source': 'Engel & Völkers',
                'date': TODAY
            })
            if added: total_ev += 1
    except Exception as e:
        print(f'  Error: {e}')
    print(f'  Engel & Völkers TOTAL: {total_ev}')


# ══════════════════════════════════════════════════════
# NUEVO — palabras clave para validar que un anuncio es
# realmente un hotel/alojamiento antes de aceptarlo.
# (Evita el bug que vimos en Hispacasas: una URL de paginación
# que decía "hoteles" pero devolvía fincas, chalets y áticos.)
# ══════════════════════════════════════════════════════
HOTEL_KEYWORDS = ['hotel', 'hostal', 'hostel', 'pensión', 'pension', 'aparthotel',
                  'posada', 'parador', 'fonda', 'casa rural', 'albergue', 'resort',
                  'guesthouse', 'b&b', 'boutique', 'apart-hotel',
                  'apartamento turístico', 'apartamentos turísticos', 'edificio turístico']

def _parece_hotel(*textos):
    """True si alguno de los textos dados contiene una palabra clave de hotel."""
    junto = ' '.join(t or '' for t in textos).lower()
    return any(k in junto for k in HOTEL_KEYWORDS)


# ══════════════════════════════════════════════════════
# 8. HISPACASAS — hoteles en venta España
# ══════════════════════════════════════════════════════
def scrape_hispacasas(driver):
    print('\n→ Hispacasas...')
    import requests as req_mod
    HEADERS_HC = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept-Language': 'es-ES,es;q=0.9',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Referer': 'https://www.hispacasas.com/',
    }
    BASE = 'https://www.hispacasas.com'
    # Página 1 y paginación confirmadas por búsqueda: viviendas-p/2, viviendas-p/3...
    # OJO: NO usar la ruta .../hotel/<provincia>/casas/N/ — comprobado que rompe
    # el filtro de categoría y devuelve fincas/áticos/chalets en vez de hoteles.
    urls = [f'{BASE}/venta/hotel/'] + [f'{BASE}/venta/hotel/viviendas-p/{n}/' for n in range(2, 12)]
    total_hc = 0
    paginas_vacias = 0
    session = req_mod.Session()

    for url in urls:
        if paginas_vacias >= 2:
            break

        # CAMBIO: antes usábamos el navegador Chrome (get_page/driver.get) y
        # se quedaba colgado 120s sin responder — típico de un sitio que
        # ralentiza deliberadamente el tráfico automatizado ("tarpit").
        # Ahora usamos requests directo, con timeout real y 2 reintentos
        # cortos — si el sitio tapona la conexión, fallamos rápido y
        # seguimos con la siguiente página en vez de perder 2 minutos.
        html = None
        for intento in range(2):
            try:
                r = session.get(url, headers=HEADERS_HC, timeout=12)
                if r.status_code == 200:
                    html = r.text
                else:
                    print(f'  [Hispacasas] {url} → status {r.status_code}')
                break
            except Exception as e:
                if intento == 0:
                    print(f'  [Hispacasas] {url} → intento 1 falló ({e}), reintentando...')
                    time.sleep(3)
                else:
                    print(f'  [Hispacasas] {url} → fallo tras 2 intentos: {e}')

        if not html:
            paginas_vacias += 1
            continue

        try:
            soup = BeautifulSoup(html, 'lxml')

            # ── Cascada de selectores: probamos varias estrategias típicas
            # de portales inmobiliarios españoles hasta que una encuentre algo.
            cards = []
            estrategia = None
            for nombre, selector in [
                ('article', lambda s: s.find_all('article')),
                ('div.ficha', lambda s: s.find_all('div', class_=re.compile(r'ficha', re.I))),
                ('div.listado-item', lambda s: s.find_all('div', class_=re.compile(r'listado.?item|list.?item', re.I))),
                ('div.anuncio', lambda s: s.find_all('div', class_=re.compile(r'anuncio|property.?card', re.I))),
                ('a con href de inmueble', lambda s: s.find_all('a', href=re.compile(r'/inmueble/|/hotel-')) ),
            ]:
                encontrados = selector(soup)
                if encontrados:
                    cards = encontrados
                    estrategia = nombre
                    break

            if not cards:
                print(f'  [Hispacasas] {url} → 0 tarjetas con ningún selector conocido. HTML recibido: {len(html)} chars.')
                paginas_vacias += 1
                continue

            paginas_vacias = 0
            nuevos_pagina = 0

            for card in cards:
                # Enlace a la ficha
                a = card if card.name == 'a' else card.find('a', href=True)
                if not a or not a.get('href'):
                    continue
                href = a.get('href', '')
                if not href.startswith('http'):
                    href = BASE + href
                href = href.split('?')[0].rstrip('/')
                if href in seen_urls:
                    continue

                texto_card = card.get_text(' ', strip=True)

                # Título: primer heading dentro de la tarjeta, o el texto del propio link
                title_el = card.find(['h1', 'h2', 'h3', 'h4'])
                title = clean(title_el.get_text()) if title_el else clean(a.get_text())
                if not title or len(title) < 5:
                    title = f'Hotel en venta ({texto_card[:40]})'

                # Validación defensiva: si ni el título ni el texto de la tarjeta
                # mencionan nada de hotel/hostal/etc., la descartamos — mejor
                # 0 anuncios que anuncios basura sin relación.
                if not _parece_hotel(title, texto_card[:200]):
                    continue

                # Precio: primer patrón "NNN.NNN €" en el texto de la tarjeta
                pm = re.search(r'([\d][\d.,]*)\s*€', texto_card)
                price = f'{pm.group(1)} €' if pm else 'Precio a consultar'

                # Ubicación: heurística simple — última palabra capitalizada del título
                loc = 'España'
                m = re.search(r'\ben\s+([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ\s]{2,30})$', title)
                if m:
                    loc = m.group(1).strip()

                item = {
                    'title': title,
                    'price': price,
                    'location': loc,
                    'description': texto_card[:800],
                    'url': href,
                    'source': 'Hispacasas',
                    'date': TODAY,
                }
                added = add_listing(item)
                if added:
                    total_hc += 1
                    nuevos_pagina += 1

            print(f'  Hispacasas [{estrategia}] {url.split("hispacasas.com")[-1]}: {nuevos_pagina} nuevos | Total: {total_hc}')
            time.sleep(random.uniform(2, 4))

        except Exception as e:
            print(f'  Error Hispacasas {url}: {e}')
            paginas_vacias += 1

    print(f'  Hispacasas TOTAL: {total_hc}')


# ══════════════════════════════════════════════════════
# 9. MILANUNCIOS — hoteles/hostales en venta o traspaso
#    ⚠️ Portal de clasificados grande (grupo Adevinta). Es el más
#    propenso a tener protección anti-bot fuerte, igual que Idealista.
#    Usamos el driver stealth desde el principio y, si aun así da 0,
#    lo más probable es que necesite el mismo tipo de arreglo que
#    Idealista (o directamente no sea viable sin proxies residenciales).
# ══════════════════════════════════════════════════════
def scrape_milanuncios(driver_stealth, fuentes_override=None):
    print('\n→ Milanuncios (nacional, modo suave)...')
    BASE = 'https://www.milanuncios.com'
    # fuentes_override: SOLO para pruebas sueltas (ver
    # test_milanuncios_traspasos.py) -- permite mirar una unica fuente en
    # vez de las 5 de siempre, para no tener que esperar al barrido
    # completo solo para comprobar un cambio puntual. La pasada normal
    # (produccion) no pasa este argumento, asi que sigue mirando las 5.
    # Fuentes NACIONALES (todos los hoteles en venta/traspaso, no por ciudad)
    FUENTES = fuentes_override if fuentes_override else [
        BASE + '/traspasos-de-hostales-y-hoteles/',
        BASE + '/anuncios/?s=hotel+en+venta',
        BASE + '/anuncios/?s=traspaso+hotel+hostal',
        BASE + '/anuncios/?s=venta+de+hotel',
        BASE + '/anuncios/?s=hostal+en+venta',
    ]
    SPAM = re.compile(r'buscamos|compramos|gesti[oo]n de venta|grupo inversor|\binversor\b|invertir|'
                      r'financiaci|se alquila|\balquiler\b|habitaci[oo]n en|se necesita|\bempleo\b|'
                      r'camarer|recepcionist|reforma|se ofrece|dispongo de activos|activos y empresas|toda espa|cartera de', re.I)
    # NUEVO: para la categoria DEDICADA de traspasos (FUENTES[0]) no se
    # filtra por 'alquiler'/'se alquila' -- un anuncio de traspaso casi
    # siempre menciona el alquiler actual del local (renta mensual, etc.),
    # eso es normal en un traspaso, no es ruido de un anuncio de puro
    # alquiler como en las otras 4 fuentes (busquedas mezcladas). Con el
    # filtro viejo se estaban descartando la mayoria de traspasos reales.
    SPAM_TRASPASOS = re.compile(r'buscamos|compramos|gesti[oo]n de venta|grupo inversor|\binversor\b|invertir|'
                      r'financiaci|habitaci[oo]n en|se necesita|\bempleo\b|'
                      r'camarer|recepcionist|reforma|se ofrece|dispongo de activos|activos y empresas|toda espa|cartera de', re.I)
    KEEP = re.compile(r'hotel|hostal|hostel|pensi[oo]n|albergue|apartahotel|casa rural|alojamiento', re.I)
    def pnum(s): s=re.sub(r'[^\d]','',s or ''); return int(s) if s else 0
    def tipo_ma(t):
        tl=(t or '').lower()
        if re.search(r'apartahotel|aparthotel',tl): return 'Apartahotel'
        if re.search(r'\bhostal\b',tl): return 'Hostal'
        if re.search(r'\bpensi',tl): return 'Pension'
        if re.search(r'albergue|hostel',tl): return 'Albergue'
        return 'Hotel'

    total_ma = 0
    try: get_page(driver_stealth, BASE, wait=4)
    except: pass

    for fuente in FUENTES:
        sin_nuevos = 0
        spam_activo = SPAM_TRASPASOS if fuente == FUENTES[0] else SPAM
        for pagina in range(1, 41):        # hasta 40 páginas por fuente
            sep = '&' if '?' in fuente else '?'
            url = fuente if pagina == 1 else f'{fuente}{sep}pagina={pagina}'
            try:
                html = get_page(driver_stealth, url, wait=4)
                if not html:
                    break
                low = html.lower()
                if len(html) < 5000 or any(b in low for b in
                        ['confirm you are human','are you a robot','access denied','datadome','geo.captcha']):
                    print(f'  [Milanuncios] bloqueo en {url[-40:]}')
                    time.sleep(random.uniform(18,28)); sin_nuevos += 1
                    if sin_nuevos >= 2: break
                    continue
                soup = BeautifulSoup(html, 'lxml')
                cards = soup.find_all('article', class_=re.compile(r'AdCard', re.I))
                if not cards:
                    break
                enc = 0
                for card in cards:
                    a = card.find('a', href=True)
                    if not a: continue
                    u = a['href']
                    if u.startswith('/'): u = BASE + u
                    u = u.split('?')[0].rstrip('/')
                    if u in seen_urls: continue
                    t_el = card.find(class_=re.compile(r'title', re.I))
                    titulo = clean(t_el.get_text()) if t_el else ''
                    texto = clean(card.get_text(' '))
                    blob = titulo + ' ' + texto
                    if not KEEP.search(blob) or spam_activo.search(blob): continue
                    pe = next((e for e in card.find_all(True) if not e.find_all() and '€' in e.get_text()), None)
                    precio = clean(pe.get_text()) if pe else ''
                    if pnum(precio) < 30000: continue
                    mm = re.search(r'([A-Za-zÀ-ÿ\.\-\' ]+?)\s*\(([A-Za-zÀ-ÿ\.\-\' ]+?)\)', texto)
                    loc = mm.group(1).strip() if mm else 'España'
                    item_ma = {
                        'title': titulo or 'Hotel en venta',
                        'price': precio or 'Precio a consultar',
                        'location': loc,
                        'description': texto[:300],
                        'url': u,
                        'source': 'Milanuncios',
                        'tipo': tipo_ma(blob),
                        'date': TODAY
                    }
                    # La primera fuente es la categoria dedicada de
                    # traspasos del propio Milanuncios -- todo lo que
                    # salga de ahi ES traspaso por definicion, aunque el
                    # anuncio en si no use la palabra (confirmado: de 462
                    # anuncios ya en cache solo 4 dicen "traspaso" en el
                    # texto). Las otras 4 fuentes son busquedas mixtas
                    # (venta+traspaso revueltos) y siguen dependiendo de
                    # detectarOperacion() como hasta ahora.
                    if fuente == FUENTES[0]:
                        item_ma['operacion_detectada'] = 'traspaso'
                    added = add_listing(item_ma)
                    if added: enc += 1; total_ma += 1
                if enc > 0:
                    print(f'  {url[-35:]} p{pagina}: {enc} | Total MA: {total_ma}')
                    sin_nuevos = 0
                else:
                    sin_nuevos += 1
                if sin_nuevos >= 2: break     # 2 páginas seguidas sin nuevos = fin de esta fuente
            except Exception as e:
                print(f'  Error Milanuncios p{pagina}: {e}'); break
            time.sleep(random.uniform(3, 6))   # ritmo rapido validado (0 bloqueos)

    print(f'  Milanuncios TOTAL: {total_ma}')

def scrape_lancoisdoval(driver):
    print('\n→ Lançois Doval...')
    import requests as req_mod
    HEADERS_LD = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept-Language': 'es-ES,es;q=0.9',
        'Referer': 'https://www.lancoisdoval.es/',
    }
    BASE = 'https://www.lancoisdoval.es'
    # NUEVO: añadida la página de "edificios en rentabilidad" — confirmada
    # por búsqueda, incluye edificios de apartamentos turísticos completos
    # que la página de "hoteles con encanto" no cubre.
    paginas = [
        f'{BASE}/hoteles-con-encanto-en-venta.html',
        f'{BASE}/venta-edificios-en-rentabilidad.html',
    ]
    total_ld = 0
    session = req_mod.Session()

    for url in paginas:
        html = None
        for intento in range(2):
            try:
                r = session.get(url, headers=HEADERS_LD, timeout=15)
                if r.status_code == 200:
                    html = r.text
                else:
                    print(f'  [Lançois Doval] status {r.status_code} en {url}')
                break
            except Exception as e:
                if intento == 0:
                    print(f'  [Lançois Doval] intento 1 falló ({e}), reintentando...')
                    time.sleep(3)
                else:
                    print(f'  [Lançois Doval] fallo tras 2 intentos: {e}')

        if not html:
            continue

        try:
            soup = BeautifulSoup(html, 'lxml')

            # Enlaces de fichas individuales: patrón confirmado "ldNNNN-propiedad-...html"
            # (distinto de las "nota-de-prensa-...html" que son artículos, no fichas).
            links = soup.find_all('a', href=re.compile(r'/ld\d+-propiedad-.*\.html$'))

            if not links:
                # Cascada de respaldo por si el patrón de URL cambia
                links = soup.find_all('a', href=re.compile(r'-propiedad-.*\.html$'))

            if not links:
                print(f'  [Lançois Doval] {url.split("lancoisdoval.es")[-1]} → 0 enlaces de ficha. HTML: {len(html)} chars.')
                continue

            vistos = set()
            nuevos_pagina = 0
            for a in links:
                href = a.get('href', '')
                if not href.startswith('http'):
                    href = BASE + href
                href = href.split('?')[0].rstrip('/')
                if href in vistos or href in seen_urls:
                    continue
                vistos.add(href)

                # Tarjeta = contenedor padre del link (varios niveles arriba,
                # buscando algo que ya incluya precio o descripción)
                card = a
                for _ in range(4):
                    if card.parent:
                        card = card.parent
                    else:
                        break
                texto_card = card.get_text(' ', strip=True)

                title = clean(a.get_text()) or clean(a.get('title', ''))
                if not title or len(title) < 5:
                    # Fallback: derivar título desde la URL (slug legible)
                    m = re.search(r'ld\d+-propiedad-(.+)\.html$', href)
                    title = m.group(1).replace('-', ' ').title() if m else 'Propiedad en venta'

                # Filtro ampliado: aceptamos también "turístic-/turistic-"
                # sueltos (edificios de apartamentos turísticos), no solo
                # palabras de hotel — la página de "edificios en rentabilidad"
                # tiene ese tipo de activo con frecuencia.
                t_lower = (title + ' ' + texto_card[:200]).lower()
                if not (_parece_hotel(title, texto_card[:200]) or 'turístic' in t_lower or 'turistic' in t_lower):
                    continue

                pm = re.search(r'([\d][\d.,]*)\s*€', texto_card)
                price = f'{pm.group(1)} €' if pm else 'Precio a consultar'

                item = {
                    'title': title,
                    'price': price,
                    'location': 'España',
                    'description': texto_card[:800],
                    'url': href,
                    'source': 'Lançois Doval',
                    'date': TODAY,
                }
                added = add_listing(item)
                if added:
                    total_ld += 1
                    nuevos_pagina += 1

            print(f'  Lançois Doval {url.split("lancoisdoval.es")[-1]}: {len(links)} enlaces vistos | {nuevos_pagina} nuevos | Total: {total_ld}')

        except Exception as e:
            print(f'  Error Lançois Doval {url}: {e}')

    print(f'  Lançois Doval TOTAL: {total_ld}')


# ══════════════════════════════════════════════════════
# 15. YAENCONTRE — edificios de apartamentos turísticos completos
#     Agregador con categoría "edificios" por ciudad (general, mezcla
#     edificios normales con turísticos). Confirmado por búsqueda con
#     volúmenes grandes: Valencia provincia 496, Madrid 230, Málaga 145,
#     Sevilla 97, Asturias 322 (lujo). El mejor hallazgo de esta tanda.
# ══════════════════════════════════════════════════════
def scrape_yaencontre(driver):
    print('\n→ Yaencontre...')
    import requests as req_mod
    HEADERS_YE = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept-Language': 'es-ES,es;q=0.9',
        'Referer': 'https://www.yaencontre.com/',
    }
    BASE = 'https://www.yaencontre.com'
    total_ye = 0
    session = req_mod.Session()

    for ciudad in NUROA_CIUDADES:  # reutilizamos la misma lista de ciudades
        url = f'{BASE}/venta/edificios/{ciudad}'

        html = None
        for intento in range(2):
            try:
                r = session.get(url, headers=HEADERS_YE, timeout=15)
                if r.status_code == 200:
                    html = r.text
                break
            except Exception as e:
                if intento == 0:
                    time.sleep(2)
                else:
                    print(f'  [Yaencontre] {url} → fallo: {e}')

        if not html:
            continue

        try:
            soup = BeautifulSoup(html, 'lxml')

            cards = []
            estrategia = None
            for nombre, selector in [
                ('article', lambda s: s.find_all('article')),
                ('div.listing', lambda s: s.find_all('div', class_=re.compile(r'listing|property|card|item-info', re.I))),
                ('a href numérico', lambda s: s.find_all('a', href=re.compile(r'-\d{5,}'))),
            ]:
                encontrados = selector(soup)
                if encontrados:
                    cards = encontrados
                    estrategia = nombre
                    break

            if not cards:
                print(f'  [Yaencontre] edificios-{ciudad} → 0 tarjetas. HTML: {len(html)} chars.')
                continue

            nuevos_pagina = 0
            for card in cards:
                a = card if card.name == 'a' else card.find('a', href=True)
                if not a or not a.get('href'):
                    continue
                href = a.get('href', '')
                if not href.startswith('http'):
                    href = BASE + href
                href = href.split('?')[0].rstrip('/')
                if href in seen_urls:
                    continue

                texto_card = card.get_text(' ', strip=True)
                title_el = card.find(['h1', 'h2', 'h3'])
                title = clean(title_el.get_text()) if title_el else clean(a.get_text())
                if not title or len(title) < 5:
                    continue

                # Esta categoría es "edificios" en general (no solo
                # turísticos), así que SÍ hace falta filtrar aquí — solo
                # nos quedamos con los que mencionan turismo/hotel/AT.
                t_lower = (title + ' ' + texto_card[:300]).lower()
                if not (_parece_hotel(title, texto_card[:300]) or
                        'turístic' in t_lower or 'turistic' in t_lower or
                        re.search(r'\blicencia\s+at\b', t_lower)):
                    continue

                pm = re.search(r'([\d][\d.,]*)\s*€', texto_card)
                price = f'{pm.group(1)} €' if pm else 'Precio a consultar'

                item = {
                    'title': title,
                    'price': price,
                    'location': ciudad.capitalize(),
                    'description': texto_card[:800],
                    'url': href,
                    'source': 'Yaencontre',
                    'date': TODAY,
                }
                added = add_listing(item)
                if added:
                    total_ye += 1
                    nuevos_pagina += 1

            if nuevos_pagina > 0:
                print(f'  Yaencontre [{estrategia}] edificios-{ciudad}: {nuevos_pagina} nuevos | Total: {total_ye}')
            time.sleep(random.uniform(1.5, 3))

        except Exception as e:
            print(f'  Error Yaencontre {url}: {e}')

    print(f'  Yaencontre TOTAL: {total_ye}')


# ══════════════════════════════════════════════════════
# 11. CASA SAPO — hoteles/negocios en venta (Portugal + España)
#     Portal grande sin señales de bloqueo conocidas. requests directo.
# ══════════════════════════════════════════════════════
def _area_pt(texto):
    """m2 construidos desde el texto de la tarjeta PT ('5 000m2', '1.250 m2', '250m2')."""
    m = re.search(r'(?<![A-Za-z])(\d{1,3}(?:[.\s]\d{3})*|\d+)\s*m\s*(?:\u00b2|2)', texto or '')
    if not m:
        return None
    n = re.sub(r'[^\d]', '', m.group(1))
    if not n:
        return None
    v = int(n)
    return v if 20 <= v <= 200000 else None

def _quartos_pt(texto):
    """habitaciones/camas si el anuncio las publica (en hoteles PT casi nunca)."""
    m = re.search(r'(\d{1,4})\s*(?:quartos?|camas?|dormit\u00f3rios?|habitaci[o\u00f3]n(?:es)?)', texto or '', re.I)
    if m:
        v = int(m.group(1))
        if 1 <= v <= 2000:
            return v
    return None

def scrape_casasapo(driver):
    print('\n→ Casa Sapo... [VERSION-CON-ARREGLO-XA0-v2]')
    import requests as req_mod
    HEADERS_CS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept-Language': 'pt-PT,pt;q=0.9,es;q=0.8',
        'Referer': 'https://casa.sapo.pt/',
    }
    BASE = 'https://casa.sapo.pt'
    # Página 1 confirmada (136 resultados). Probamos varios patrones de
    # paginación plausibles — no pude confirmar el exacto sin ver el HTML,
    # así que cada uno que falle simplemente no aporta URLs nuevas.
    urls = [f'{BASE}/negocio/hotel/']
    for n in range(2, 6):
        urls.append(f'{BASE}/negocio/hotel/pn{n}/')
        urls.append(f'{BASE}/negocio/hotel/?pn={n}')

    total_cs = 0
    paginas_vacias = 0
    session = req_mod.Session()

    for url in urls:
        if paginas_vacias >= 4:  # aquí toleramos más vacías: varios patrones de paginación fallarán a propósito
            break
        html = None
        for intento in range(2):
            try:
                r = session.get(url, headers=HEADERS_CS, timeout=15)
                if r.status_code == 200:
                    html = r.text
                break
            except Exception as e:
                if intento == 0:
                    time.sleep(2)
                else:
                    print(f'  [Casa Sapo] {url} → fallo: {e}')

        if not html:
            paginas_vacias += 1
            continue

        try:
            soup = BeautifulSoup(html, 'lxml')

            cards = []
            estrategia = None
            for nombre, selector in [
                ('article', lambda s: s.find_all('article')),
                ('div.property', lambda s: s.find_all('div', class_=re.compile(r'property|listing|imovel', re.I))),
                ('a href .htm', lambda s: s.find_all('a', href=re.compile(r'\.htm$'))),
            ]:
                encontrados = selector(soup)
                if encontrados:
                    cards = encontrados
                    estrategia = nombre
                    break

            if not cards:
                print(f'  [Casa Sapo] {url} → 0 tarjetas. HTML: {len(html)} chars.')
                paginas_vacias += 1
                continue

            nuevos_pagina = 0
            for card in cards:
                # CONFIRMADO con datos reales: coger el PRIMER <a> de la
                # tarjeta a veces trae un enlace de rastreo/contador
                # ("gespub.casa.sapo.pt/.../counter.aspx") en vez de la
                # ficha real -- pasaba en anuncios "destacados" con más
                # de un enlace dentro de la misma tarjeta. Ahora
                # preferimos un enlace que tenga pinta real de ficha
                # (".html" en el propio dominio), y solo si no hay
                # ninguno así, caemos al primero que encontremos.
                enlaces_candidatos = card.find_all('a', href=True) if card.name != 'a' else [card]
                a = None
                for candidato in enlaces_candidatos:
                    href_candidato = candidato.get('href', '')
                    if '.html' in href_candidato and 'sapo.pt' in (href_candidato if href_candidato.startswith('http') else BASE):
                        a = candidato
                        break
                if a is None and enlaces_candidatos:
                    a = enlaces_candidatos[0]
                if not a or not a.get('href'):
                    continue
                href = a.get('href', '')
                if 'counter.aspx' in href.lower() or 'gespub' in href.lower():
                    _mm = re.search(r'[?&]l=(https?://[^&]+)', href)
                    if _mm:
                        href = _mm.group(1)
                if not href.startswith('http'):
                    href = BASE + href
                href = href.split('?')[0].rstrip('/')
                if href in seen_urls:
                    continue
                # Descarta links de navegación/categoría, no fichas
                if href.rstrip('/').endswith(('/hotel', '/negocio', 'casa.sapo.pt')):
                    continue

                texto_card = card.get_text(' ', strip=True)
                title_el = card.find(['h1', 'h2', 'h3'])
                title = clean(title_el.get_text()) if title_el else clean(a.get_text())
                if not title or len(title) < 5:
                    continue
                if not _parece_hotel(title, texto_card[:200]):
                    continue

                pm = re.search(r'([\d][\d.,]*)\s*€', texto_card)
                price = f'{pm.group(1)} €' if pm else 'Precio a consultar'

                # CONFIRMADO con títulos reales: siguen el patrón
                # "Hotel [LUGAR], Distrito de [DISTRITO] [Usado/Novo/...]".
                # Sacamos los dos -- "lugar" (la ciudad/pueblo concreto) y
                # "distrito" (equivalente portugués a una provincia
                # española) -- en vez de dejar "Portugal" a secas para
                # los 101 anuncios. De paso, ponemos el distrito
                # DIRECTAMENTE en location_region: el sistema genérico
                # infer_region() busca nombres de provincias ESPAÑOLAS,
                # así que con texto portugués adivinaba region absurdos
                # (ej. "Cataluña" para un hotel en Cascais).
                location = 'Portugal'
                location_region = None
                _m_loc = re.search(r'^Hotel\s+(?:T\d+\s+)?(.*?),?\s*Distrito de\s+([A-ZÀ-Ú][a-zà-ú]+)',
                                    title, re.I)
                if _m_loc:
                    _lugar = _m_loc.group(1).split(',')[0].strip()
                    _distrito = _m_loc.group(2).strip()
                    if _lugar:
                        location = _lugar
                    if _distrito:
                        location_region = _distrito

                _m2_pt = _area_pt(texto_card)
                _rooms_pt = _quartos_pt(texto_card)
                item = {
                    'title': title,
                    'price': price,
                    'location': location,
                    'description': texto_card[:800],
                    'url': href,
                    'source': 'Casa Sapo',
                    'date': TODAY,
                }
                if location_region:
                    item['location_region'] = location_region
                if _m2_pt:
                    item['m2'] = _m2_pt
                if _rooms_pt:
                    item['rooms'] = _rooms_pt
                added = add_listing(item)
                if added:
                    total_cs += 1
                    nuevos_pagina += 1

            if nuevos_pagina > 0:
                paginas_vacias = 0
            print(f'  Casa Sapo [{estrategia}] {url.split("casa.sapo.pt")[-1]}: {nuevos_pagina} nuevos | Total: {total_cs}')
            time.sleep(random.uniform(2, 4))

        except Exception as e:
            print(f'  Error Casa Sapo {url}: {e}')
            paginas_vacias += 1

    print(f'  Casa Sapo TOTAL: {total_cs}')


# ══════════════════════════════════════════════════════
# 12. SUPERCASA — hoteles/hotelaria en venta (Portugal)
#     Portal hermano de Casa Sapo. URL confirmada por búsqueda:
#     /comprar-espacos_comerciais_ou_armazens/{zona}/com-hotelaria
# ══════════════════════════════════════════════════════
def scrape_supercasa(driver):
    print('\n→ Supercasa...')
    import requests as req_mod
    HEADERS_SC = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept-Language': 'pt-PT,pt;q=0.9,es;q=0.8',
        'Referer': 'https://supercasa.pt/',
    }
    BASE = 'https://supercasa.pt'
    # Intentamos primero sin zona (nacional) y si no, varias zonas grandes
    # confirmadas por búsqueda como que sí tienen resultados de hotelaria.
    urls = [
        f'{BASE}/comprar-espacos_comerciais_ou_armazens/com-hotelaria',
        f'{BASE}/comprar-espacos_comerciais_ou_armazens/lisboa/com-hotelaria',
        f'{BASE}/comprar-espacos_comerciais_ou_armazens/porto-distrito/com-hotelaria',
        f'{BASE}/comprar-espacos_comerciais_ou_armazens/porto/com-hotelaria',
        f'{BASE}/comprar-espacos_comerciais_ou_armazens/lagos/com-hotelaria',
        f'{BASE}/comprar-espacos_comerciais_ou_armazens/algarve/com-hotelaria',
    ]
    total_sc = 0

    for url in urls:
        # Supercasa va con Cloudflare -> usamos el NAVEGADOR (driver), no requests
        html = get_page(driver, url, wait=8)
        if html and any(x in html.lower() for x in ['just a moment','um momento','checking your browser','cf-browser-verification']):
            time.sleep(6)
            html = get_page(driver, url, wait=6)   # reintento tras el reto Cloudflare
        if not html:
            continue

        try:
            soup = BeautifulSoup(html, 'lxml')

            cards = []
            estrategia = None
            for nombre, selector in [
                ('article', lambda s: s.find_all('article')),
                ('div.property', lambda s: s.find_all('div', class_=re.compile(r'property|listing|imovel|card', re.I))),
                ('a href numérico', lambda s: s.find_all('a', href=re.compile(r'/\d{5,}'))),
            ]:
                encontrados = selector(soup)
                if encontrados:
                    cards = encontrados
                    estrategia = nombre
                    break

            if not cards:
                print(f'  [Supercasa] {url.split("supercasa.pt")[-1]} → 0 tarjetas. HTML: {len(html)} chars.')
                continue

            nuevos_pagina = 0
            for card in cards:
                a = card if card.name == 'a' else card.find('a', href=True)
                if not a or not a.get('href'):
                    continue
                href = a.get('href', '')
                if not href.startswith('http'):
                    href = BASE + href
                href = href.split('?')[0].rstrip('/')
                if href in seen_urls:
                    continue

                texto_card = card.get_text(' ', strip=True)
                title_el = card.find(['h1', 'h2', 'h3'])
                title = clean(title_el.get_text()) if title_el else clean(a.get_text())
                if not title or len(title) < 5:
                    continue
                # "hotelaria" es la palabra que usa este portal — la sumamos
                # a la validación estándar de _parece_hotel
                if not (_parece_hotel(title, texto_card[:200]) or 'hotelaria' in texto_card[:200].lower()):
                    continue

                pm = re.search(r'([\d][\d.,]*)\s*€', texto_card)
                price = f'{pm.group(1)} €' if pm else 'Precio a consultar'

                # CONFIRMADO con datos reales: el patrón de Supercasa es
                # DISTINTO al de Casa Sapo (a pesar de ser "hermanos") --
                # aquí es "[Tipo] em [Barrio], [Ciudad]" en vez de
                # "Hotel [Lugar], Distrito de [Distrito]". El intento
                # anterior (copiar el regex de Casa Sapo) dio 0/38 con
                # datos reales -- este es el patrón correcto, verificado
                # contra los 8 ejemplos reales del primer test.
                location = 'Portugal'
                location_region = None
                _m_loc = re.search(r'\bem\s+(.+)$', title)
                if _m_loc:
                    _partes = [p.strip() for p in _m_loc.group(1).split(',') if p.strip()]
                    if _partes:
                        location_region = _partes[-1]  # ciudad
                        # BUG REAL encontrado con un test de verdad:
                        # limpiar_location() (pensada para limpiar
                        # basura de ThinkSpain) corta automáticamente
                        # todo lo que va después de la primera coma --
                        # así que un valor tipo "Calle, Barrio" se
                        # quedaba solo en "Calle". Evitamos comas del
                        # todo: si hay 3+ partes (calle + barrio +
                        # ciudad), usamos el PENÚLTIMO segmento (el
                        # barrio, más útil que el nombre de una calle).
                        location = _partes[-2] if len(_partes) > 1 else _partes[-1]

                _m2_pt = _area_pt(texto_card)
                _rooms_pt = _quartos_pt(texto_card)
                item = {
                    'title': title,
                    'price': price,
                    'location': location,
                    'description': texto_card[:800],
                    'url': href,
                    'source': 'Supercasa',
                    'date': TODAY,
                }
                if location_region:
                    item['location_region'] = location_region
                if _m2_pt:
                    item['m2'] = _m2_pt
                if _rooms_pt:
                    item['rooms'] = _rooms_pt
                added = add_listing(item)
                if added:
                    total_sc += 1
                    nuevos_pagina += 1

            print(f'  Supercasa [{estrategia}] {url.split("supercasa.pt")[-1]}: {nuevos_pagina} nuevos | Total: {total_sc}')
            time.sleep(random.uniform(2, 4))

        except Exception as e:
            print(f'  Error Supercasa {url}: {e}')

    print(f'  Supercasa TOTAL: {total_sc}')


# ══════════════════════════════════════════════════════
# 13. ROBERTO BELOKI — negocios en venta (Gipuzkoa/Navarra),
#     filtrado a hoteles. ⚠️ Es una inmobiliaria GENERALISTA, no
#     especializada en hoteles — se espera un rendimiento bajo
#     (pocos o ningún hotel en cartera en un momento dado). No es
#     un fallo del scraper si da 0 o 1-2 resultados.
# ══════════════════════════════════════════════════════
def scrape_robertobeloki(driver):
    print('\n→ Roberto Beloki...')
    import requests as req_mod
    HEADERS_RB = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept-Language': 'es-ES,es;q=0.9',
        'Referer': 'https://www.robertobeloki.com/',
    }
    BASE = 'https://www.robertobeloki.com'
    urls = [f'{BASE}/negocios/', f'{BASE}/negocios/page/2/']
    total_rb = 0
    session = req_mod.Session()

    for url in urls:
        html = None
        for intento in range(2):
            try:
                r = session.get(url, headers=HEADERS_RB, timeout=15)
                if r.status_code == 200:
                    html = r.text
                break
            except Exception as e:
                if intento == 0:
                    time.sleep(2)
                else:
                    print(f'  [Roberto Beloki] {url} → fallo: {e}')

        if not html:
            continue

        try:
            soup = BeautifulSoup(html, 'lxml')

            cards = []
            estrategia = None
            for nombre, selector in [
                ('article', lambda s: s.find_all('article')),
                ('div.property', lambda s: s.find_all('div', class_=re.compile(r'property|listing|ficha|card', re.I))),
                ('a href numérico', lambda s: s.find_all('a', href=re.compile(r'/propiedad/|/inmueble/'))),
            ]:
                encontrados = selector(soup)
                if encontrados:
                    cards = encontrados
                    estrategia = nombre
                    break

            if not cards:
                print(f'  [Roberto Beloki] {url} → 0 tarjetas. HTML: {len(html)} chars.')
                continue

            nuevos_pagina = 0
            for card in cards:
                a = card if card.name == 'a' else card.find('a', href=True)
                if not a or not a.get('href'):
                    continue
                href = a.get('href', '')
                if not href.startswith('http'):
                    href = BASE + href
                href = href.split('?')[0].rstrip('/')
                if href in seen_urls:
                    continue

                texto_card = card.get_text(' ', strip=True)
                title_el = card.find(['h1', 'h2', 'h3'])
                title = clean(title_el.get_text()) if title_el else clean(a.get_text())
                if not title or len(title) < 5:
                    continue
                # Filtro estricto: esta web es generalista, así que aquí
                # el filtro _parece_hotel es el que hace todo el trabajo
                # de quedarnos solo con los pocos hoteles que haya.
                if not _parece_hotel(title, texto_card[:300]):
                    continue

                pm = re.search(r'([\d][\d.,]*)\s*€', texto_card)
                price = f'{pm.group(1)} €' if pm else 'Precio a consultar'

                item = {
                    'title': title,
                    'price': price,
                    'location': 'País Vasco / Navarra',
                    'description': texto_card[:800],
                    'url': href,
                    'source': 'Roberto Beloki',
                    'date': TODAY,
                }
                added = add_listing(item)
                if added:
                    total_rb += 1
                    nuevos_pagina += 1

            print(f'  Roberto Beloki [{estrategia}] {url.split("robertobeloki.com")[-1]}: {nuevos_pagina} nuevos | Total: {total_rb}')
            time.sleep(random.uniform(2, 4))

        except Exception as e:
            print(f'  Error Roberto Beloki {url}: {e}')

    print(f'  Roberto Beloki TOTAL: {total_rb}')


# ══════════════════════════════════════════════════════
# 14. NUROA — apartamentos y edificios turísticos en venta
#     Agregador con categoría propia por ciudad (confirmado por
#     búsqueda: Granada 185, Córdoba 172, Sevilla 108+37, Madrid 55...).
#     No confirmé el patrón exacto de paginación — probamos varios
#     candidatos típicos en cascada, igual que hicimos con Casa Sapo.
# ══════════════════════════════════════════════════════

# Ciudades/provincias grandes de España — ampliable si vemos que da
# buenos resultados. Solo nombres simples (sin tildes/espacios) porque
# son los que confirmé que funcionan en las URLs reales de Nuroa.
NUROA_CIUDADES = [
    'madrid', 'barcelona', 'valencia', 'sevilla', 'zaragoza', 'malaga',
    'murcia', 'palma', 'alicante', 'cordoba', 'valladolid', 'vigo',
    'gijon', 'granada', 'cadiz', 'tarragona', 'girona', 'almeria',
    'santander', 'toledo', 'marbella', 'bilbao', 'huelva', 'jaen',
    'caceres', 'badajoz', 'leon', 'burgos', 'salamanca', 'pontevedra',
]

def scrape_nuroa(driver):
    print('\n→ Nuroa...')
    import requests as req_mod
    HEADERS_NU = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept-Language': 'es-ES,es;q=0.9',
        'Referer': 'https://www.nuroa.es/',
    }
    BASE = 'https://www.nuroa.es'
    total_nu = 0
    session = req_mod.Session()

    for ciudad in NUROA_CIUDADES:
        # Dos categorías por ciudad: apartamentos sueltos y edificios completos
        for categoria in ['apartamentos-turisticos', 'edificio-apartamentos-turisticos']:
            url_base = f'{BASE}/venta/{categoria}-{ciudad}'
            # Cascada de candidatos de paginación (probamos solo página 1 y 2
            # por ciudad para no disparar el número de peticiones; si la
            # página 2 funciona con algún patrón, lo sabremos en el log)
            urls_intentar = [
                (url_base, 'p1'),
                (f'{url_base}?pagina=2', 'p2-pagina'),
                (f'{url_base}-2', 'p2-guion'),
            ]

            encontro_algo_en_ciudad = False
            for url, etiqueta in urls_intentar:
                if etiqueta != 'p1' and not encontro_algo_en_ciudad:
                    # Si la página 1 no dio nada, no perdemos tiempo probando
                    # variantes de página 2 de esa misma ciudad/categoría.
                    break

                html = None
                for intento in range(2):
                    try:
                        r = session.get(url, headers=HEADERS_NU, timeout=15)
                        if r.status_code == 200:
                            html = r.text
                        break
                    except Exception as e:
                        if intento == 0:
                            time.sleep(2)
                        else:
                            print(f'  [Nuroa] {url} → fallo: {e}')

                if not html:
                    continue

                try:
                    soup = BeautifulSoup(html, 'lxml')

                    cards = []
                    estrategia = None
                    for nombre, selector in [
                        ('article', lambda s: s.find_all('article')),
                        ('div.listing', lambda s: s.find_all('div', class_=re.compile(r'listing|property|anuncio|item-info', re.I))),
                        ('a href numérico', lambda s: s.find_all('a', href=re.compile(r'-\d{6,}'))),
                    ]:
                        encontrados = selector(soup)
                        if encontrados:
                            cards = encontrados
                            estrategia = nombre
                            break

                    if not cards:
                        if etiqueta == 'p1':
                            print(f'  [Nuroa] {categoria}-{ciudad} → 0 tarjetas. HTML: {len(html)} chars.')
                        continue

                    nuevos_pagina = 0
                    for card in cards:
                        a = card if card.name == 'a' else card.find('a', href=True)
                        if not a or not a.get('href'):
                            continue
                        href = a.get('href', '')
                        if not href.startswith('http'):
                            href = BASE + href
                        href = href.split('?')[0].rstrip('/')
                        if href in seen_urls:
                            continue

                        texto_card = card.get_text(' ', strip=True)
                        title_el = card.find(['h1', 'h2', 'h3'])
                        title = clean(title_el.get_text()) if title_el else clean(a.get_text())
                        if not title or len(title) < 5:
                            continue
                        # Aquí el filtro es más laxo: aceptamos también
                        # "turístico"/"turistico" sueltos, porque Nuroa ya
                        # filtró por esa categoría — no hace falta que
                        # aparezca la palabra "hotel" para que sea válido.
                        t_lower = (title + ' ' + texto_card[:200]).lower()
                        if not (_parece_hotel(title, texto_card[:200]) or 'turístic' in t_lower or 'turistic' in t_lower):
                            continue

                        pm = re.search(r'([\d][\d.,]*)\s*€', texto_card)
                        price = f'{pm.group(1)} €' if pm else 'Precio a consultar'

                        item = {
                            'title': title,
                            'price': price,
                            'location': ciudad.capitalize(),
                            'description': texto_card[:800],
                            'url': href,
                            'source': 'Nuroa',
                            'date': TODAY,
                        }
                        added = add_listing(item)
                        if added:
                            total_nu += 1
                            nuevos_pagina += 1

                    if nuevos_pagina > 0:
                        encontro_algo_en_ciudad = True
                        print(f'  Nuroa [{estrategia}] {categoria}-{ciudad} ({etiqueta}): {nuevos_pagina} nuevos | Total: {total_nu}')
                    time.sleep(random.uniform(1.5, 3))

                except Exception as e:
                    print(f'  Error Nuroa {url}: {e}')

    print(f'  Nuroa TOTAL: {total_nu}')


# ══════════════════════════════════════════════════════
# 7. HOTELSEVENDE — hoteles y B&B en venta España
# ══════════════════════════════════════════════════════
def scrape_hotelsevende(driver):
    print('\n→ HotelSeVende...')
    BASE = 'https://www.hotelsevende.es'
    EXCLUDE = ['en-venta','tipo','pais','page','estado','norteamerica',
               'inversion','contacto','about','alquiler','africa','asia',
               'sudamerica','europa','blog','vender']
    total_hs = 0
    seen_hs = set()

    # Recopilar links de las 11 páginas
    urls_fichas = []
    for pagina in range(1, 12):
        page_url = f'{BASE}/en-venta/pais/espana/' if pagina == 1 else f'{BASE}/en-venta/pais/espana/page/{pagina}/'
        try:
            html = get_page(driver, page_url, wait=3)
            if not html: continue
            soup = BeautifulSoup(html, 'lxml')
            for a in soup.find_all('a', href=re.compile(r'hotelsevende\.es')):
                href = a.get('href','').rstrip('/') + '/'
                if any(x in href for x in EXCLUDE): continue
                if href.count('/') < 4: continue
                if href not in seen_hs and href not in seen_urls:
                    seen_hs.add(href)
                    urls_fichas.append(href)
        except Exception as e:
            print(f'  Error pag {pagina}: {e}')

    print(f'  Links recopilados: {len(urls_fichas)}')

    # Entrar en cada ficha
    for href in urls_fichas:
        try:
            html = get_page(driver, href, wait=2)
            if not html: continue
            soup = BeautifulSoup(html, 'lxml')

            # Título
            h1 = soup.find('h1')
            title = clean(h1.get_text()) if h1 else ''
            if not title or len(title) < 8: continue

            # Precio
            pm = re.search(r'€([\d.,]+(?:\.\d{3})*)', soup.get_text())
            price = f'€{pm.group(1)}' if pm else 'Precio a consultar'
            if price == '€1': price = 'Precio a consultar'

            # Ciudad — <strong>Ciudad</strong> precedida por el valor
            loc = 'España'
            ciudad_label = soup.find('li', string=re.compile(r'^Ciudad$', re.I))
            if ciudad_label:
                prev = ciudad_label.find_previous_sibling('li')
                if prev:
                    strong = prev.find('strong')
                    if strong: loc = clean(strong.get_text())

            # Descripción — párrafos (cada <p> real se conserva como su propio párrafo,
            # igual que se ve en la ficha de verdad, en vez de pegarlo todo seguido)
            paras = soup.find_all('p')
            description = '\n\n'.join(clean_desc(p) for p in paras if len(p.get_text().strip()) > 40)

            added = add_listing({
                'title': title,
                'price': price,
                'location': loc,
                'description': description,
                'url': href,
                'source': 'HotelSeVende',
                'date': TODAY
            })
            if added: total_hs += 1
            time.sleep(1)
        except Exception as e:
            print(f'  Error ficha {href[:60]}: {e}')

    print(f'  HotelSeVende TOTAL: {total_hs}')


# ══════════════════════════════════════════════════════
# 8. IDEALISTA — hoteles en venta por provincia
# ══════════════════════════════════════════════════════
def scrape_idealista(driver):
    print('\n→ Idealista (modo suave + filtro hoteles reales)...')
    BASE = 'https://www.idealista.com'
    PROVINCIAS = [
        'madrid-provincia','barcelona-provincia','valencia-provincia',
        'sevilla-provincia','malaga-provincia','alicante',
        'murcia-provincia','zaragoza-provincia','valladolid-provincia',
        'balears-illes','las-palmas','santa-cruz-de-tenerife-provincia',
        'granada-provincia','cordoba-provincia','toledo-provincia',
        'girona-provincia','tarragona-provincia','lleida-provincia',
        'cadiz-provincia','huelva-provincia','almeria-provincia',
        'jaen-provincia','badajoz-provincia','caceres-provincia',
        'salamanca-provincia','burgos-provincia','leon-provincia',
        'asturias','cantabria','la-rioja',
        'navarra','guipuzcoa','vizcaya',
        'pontevedra-provincia','a-coruna-provincia','lugo-provincia',
        'ourense-provincia','ciudad-real-provincia','cuenca-provincia',
        'albacete-provincia','castellon','huesca-provincia',
        'segovia-provincia','soria-provincia','teruel-provincia',
        'ibiza-y-formentera','menorca'
    ]

    # Clasificador: devuelve tipo de hotel real, o None si es local comercial (se descarta)
    def tip_hotel(t):
        tl = (t or '').lower()
        if re.search(r'apartahotel|aparthotel|apart-hotel', tl): return 'Apartahotel'
        if re.search(r'hotel\s*rural', tl): return 'Hotel Rural'
        if re.search(r'\bboutique\b', tl): return 'Hotel boutique'
        if re.search(r'balneario', tl): return 'Balneario'
        if re.search(r'\bhostal\b', tl): return 'Hostal'
        if re.search(r'\bhotel\b|hotelero|complejo hotelero', tl): return 'Hotel'
        if re.search(r'\bpensi[oo]n\b|\bpensión\b', tl): return 'Pension'
        if re.search(r'albergue|\bhostel\b', tl): return 'Albergue'
        if re.search(r'casa rural|casa de hu[ee]spedes|hospeder|\bposada\b|\bfonda\b|\bparador\b|b\s*&\s*b|bed and breakfast', tl): return 'Casa rural / B&B'
        if re.search(r'habitacion|dormitorio|hu[ee]spedes|alojamiento tur|uso hotelero|turismo rural|\bresort\b|plazas', tl): return 'Alojamiento turistico'
        return None

    total_id = 0
    seen_id = set()

    # Home primero, como humano (coge cookies)
    try:
        get_page(driver, BASE, wait=2)
    except: pass

    for provincia in PROVINCIAS:
        url = f'{BASE}/venta-locales/{provincia}/con-hotel/'   # SOLO 1 pagina = modo suave
        try:
            html = get_page(driver, url, wait=6)
            # Si DataDome ha bloqueado la IP -> parar Idealista entero (no seguir quemando)
            if html and ('data-element-id' not in html) and any(b in html.lower() for b in
                    ['uso indebido', 'acceso se ha bloqueado', 'has sido bloqueado', 'datadome', 'geo.captcha']):
                print(f'  \u26a0\ufe0f Idealista ha bloqueado la IP (en {provincia}) - dejo de buscar en Idealista.')
                break
            if html:
                soup = BeautifulSoup(html, 'lxml')
                articles = soup.find_all('article', attrs={'data-element-id': True})
                enc = 0
                for art in articles:
                    item_id = art.get('data-element-id','')
                    if not item_id: continue
                    href = f'{BASE}/inmueble/{item_id}/'
                    if href in seen_id or href in seen_urls: continue
                    seen_id.add(href)
                    info = art.find(class_='item-info-container') or art
                    a = info.find('a', class_='item-link')
                    title = clean(a.get('title','')) if a else ''
                    if not title or len(title) < 8: continue
                    price_el = info.find(class_='item-price')
                    price = clean(price_el.get_text()) if price_el else 'Precio a consultar'
                    desc_el = info.find('p', class_='ellipsis') or info.find(class_=re.compile(r'item-description'))
                    description = clean(desc_el.get_text()) if desc_el else ''
                    # FILTRO: solo hoteles reales, descarta locales comerciales
                    tip = tip_hotel(title + ' ' + description)
                    if not tip:
                        continue
                    loc = provincia.replace('-provincia','').replace('-',' ').title()
                    mm = re.search(r',\s*([^,]+),\s*([^,]+)$', title)
                    if mm: loc = mm.group(2).strip()
                    added = add_listing({
                        'title': title,
                        'price': price,
                        'location': loc,
                        'description': description,
                        'url': href,
                        'source': 'Idealista',
                        'tipo': tip,
                        'date': TODAY
                    })
                    if added: enc += 1; total_id += 1
                if enc > 0:
                    print(f'  {provincia}: {enc} hoteles | Total ID: {total_id}')
        except Exception as e:
            print(f'  Error {provincia}: {e}')
        # PAUSA LARGA entre provincias = clave para NO banear
        time.sleep(random.uniform(12, 20))

    print(f'  Idealista TOTAL: {total_id}')

# ══════════════════════════════════════════════
# ECOURBANIZACIÓN — hoteles/hostales/apartamentos turísticos en venta y en
# TRASPASO (Granada y alrededores). Sitio WordPress + plugin Estatik, sin
# proteccion anti-bot -- se puede leer directo con requests, como Oi Real
# Estate / HotelSeVende. Visita la ficha real de cada anuncio (como esos
# dos), asi que la descripcion sale completa y con parrafos de verdad.
# ══════════════════════════════════════════════
def scrape_ecourbanizacion(driver):
    print('\n→ EcoUrbanización...')
    HEADERS_EU = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept-Language': 'es-ES,es;q=0.9',
    }
    BASE = 'https://www.ecourbanizacion.com/property-category/hostal-hotel/'
    session = req_mod.Session()

    # ── PASO 1: recorrer el listado paginado y recopilar las URLs de ficha ──
    urls_listado = []
    vistos_listado = set()
    for pagina in range(1, 11):
        url = BASE if pagina == 1 else f'{BASE}?paged={pagina}'
        try:
            r = session.get(url, headers=HEADERS_EU, timeout=15)
            if r.status_code != 200:
                print(f'  EcoUrbanización p{pagina}: status {r.status_code}, parando')
                break
            soup = BeautifulSoup(r.text, 'lxml')
            cards = soup.find_all('div', class_='es-listing')
            if not cards:
                print(f'  EcoUrbanización p{pagina}: sin anuncios, fin')
                break
            nuevos_pagina = 0
            for card in cards:
                a = card.find('a', href=re.compile(r'/property/'))
                if not a:
                    continue
                href = a.get('href', '').split('?')[0].rstrip('/')
                if not href or href in vistos_listado:
                    continue
                vistos_listado.add(href)
                urls_listado.append(href)
                nuevos_pagina += 1
            print(f'  EcoUrbanización p{pagina}: {nuevos_pagina} fichas nuevas')
            time.sleep(random.uniform(1.5, 3))
        except Exception as e:
            print(f'  EcoUrbanización error listado p{pagina}: {e}')
            break

    print(f'  EcoUrbanización: {len(urls_listado)} fichas en el listado.')

    # ── PASO 2: entrar en cada ficha y sacar título/precio/descripción completa ──
    total_eu = 0
    for href in urls_listado:
        if href in seen_urls:
            continue
        try:
            r = session.get(href, headers=HEADERS_EU, timeout=15)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, 'lxml')

            h1 = soup.find('h1', class_=re.compile(r'property-title'))
            title = clean(h1.get_text()) if h1 else ''
            if not title or len(title) < 8:
                continue

            price_el = soup.find(class_='es-price')
            price = clean(price_el.get_text()) if price_el else 'Precio a consultar'
            if not re.search(r'\d', price):
                price = 'Precio a consultar'

            desc_el = soup.find(class_=re.compile(r'es-property-field--post_content'))
            desc_val = desc_el.find(class_=re.compile(r'es-property-field__value')) if desc_el else None
            description = clean_desc(desc_val) if desc_val else ''

            # OJO: aquí NO se aplica el filtro _parece_hotel() -- a diferencia
            # de Hispacasas (donde una URL de "hoteles" devolvía fincas/chalets
            # por un bug del propio portal), esta categoría de EcoUrbanización
            # (hostal-hotel) sí está bien filtrada por el sitio, y muchos títulos
            # de apartamentos turísticos no llevan la palabra "hotel"/"hostal" ni
            # coinciden con los acentos exactos de HOTEL_KEYWORDS (p.ej. el sitio
            # escribe "turisticos" sin tilde) -- aplicar el filtro aquí descartaría
            # anuncios válidos por error.

            item_eu = {
                'title': title,
                'price': price,
                'location': 'España',
                'description': description,
                'url': href,
                'source': 'EcoUrbanización',
                'date': TODAY,
            }
            # Esta categoria mezcla venta y traspaso (ver cabecera de la
            # funcion) -- probado con datos reales: incluso mejorando los
            # patrones de texto del frontend, 8 de 29 traspasos seguian sin
            # detectarse por lo variado que es el texto de cada anuncio
            # ("Traspaso 3 Edificios...", "...Granada centro Traspaso"...).
            # Aqui, en cambio, SABEMOS que absolutamente todo anuncio de esta
            # categoria es Venta o Traspaso y nada mas -- asi que basta con
            # mirar si aparece 'traspas' en cualquier forma (traspaso,
            # traspasa, traspasan...) en el titulo o la descripcion.
            if re.search(r'traspas', title + ' ' + description, re.I):
                item_eu['operacion_detectada'] = 'traspaso'
            added = add_listing(item_eu)
            if added:
                total_eu += 1
                print(f'  ✅ {title[:60]}')
            time.sleep(random.uniform(1, 2))
        except Exception as e:
            print(f'  EcoUrbanización error ficha {href}: {e}')
            continue

    print(f'  EcoUrbanización TOTAL: {total_eu}')


def scrape_inmoolaya(driver):
    print('\n→ Inmo Olaya...')
    HEADERS_IO = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept-Language': 'es-ES,es;q=0.9',
    }
    session = req_mod.Session()

    # Tipos de propiedad de Inmo Olaya que son hoteleros/alojamiento (sacados
    # del propio desplegable "tp[]" de su buscador) -- deliberadamente no
    # metemos ningun filtro de "st[]" (estado: Venta/Traspaso/Alquiler/Venta
    # en rentabilidad) para traer TODO -- Venta y Traspaso incluidos -- y que
    # sea la deteccion de Operacion del front (detectarOperacion, por texto
    # del titulo/descripcion) la que distinga uno de otro, igual que con el
    # resto de portales.
    TIPOS_HOTEL_IO = [16, 52, 53, 54, 55, 56, 57, 59, 15, 63, 12, 70, 46, 60, 61, 45, 64, 44]
    tipos_qs = '&'.join(f'tp%5B%5D={t}' for t in TIPOS_HOTEL_IO)
    BASE = f'https://inmoolaya.com/propiedades/?{tipos_qs}'

    # ── PASO 1: recorrer el listado paginado y recopilar las URLs de ficha ──
    # CONFIRMADO con el sitio real: la paginacion no es "pagina 1,2,3..." si
    # no un desplazamiento de 12 en 12 empezando en el elemento 1 -- la
    # pagina 1 no lleva parametro, la 2 es &p=13, la 3 &p=25, etc. (12
    # anuncios por pagina). Paramos cuando una pagina no trae ninguna ficha
    # nueva dos veces seguidas, igual que en ThinkSpain.
    urls_listado = []
    vistos_listado = set()
    paginas_vacias = 0
    for pagina in range(1, 60):
        offset = (pagina - 1) * 12 + 1
        url = BASE if pagina == 1 else f'{BASE}&p={offset}'
        try:
            r = session.get(url, headers=HEADERS_IO, timeout=15)
            if r.status_code != 200:
                print(f'  Inmo Olaya p{pagina}: status {r.status_code}, parando')
                break
            soup = BeautifulSoup(r.text, 'lxml')
            # OJO: la clase 'property' tambien la usa <body> (body class="es
            # properties interior") -- por eso se descarta explicitamente, y
            # solo cuentan los divs que de verdad envuelven un link a una
            # ficha (/propiedad/<id>/...).
            cards = [c for c in soup.find_all(class_='property')
                     if c.name != 'body' and c.find('a', href=re.compile(r'/propiedad/\d+'))]
            nuevos_pagina = 0
            for card in cards:
                a = card.find('a', href=re.compile(r'/propiedad/\d+'))
                href = a.get('href', '').split('?')[0].rstrip('/')
                # Los links del listado son RELATIVOS (empiezan por
                # "/propiedad/..."), a diferencia de otros portales -- si no
                # se completan con el dominio, requests.get() peta con
                # "Invalid URL: No scheme supplied" al pedir la ficha.
                if href and not href.startswith('http'):
                    href = 'https://inmoolaya.com' + href
                if not href or href in vistos_listado:
                    continue
                vistos_listado.add(href)
                urls_listado.append(href)
                nuevos_pagina += 1
            print(f'  Inmo Olaya p{pagina}: {nuevos_pagina} fichas nuevas')
            if nuevos_pagina == 0:
                paginas_vacias += 1
                if paginas_vacias >= 2:
                    break
            else:
                paginas_vacias = 0
            time.sleep(random.uniform(1, 2))
        except Exception as e:
            print(f'  Inmo Olaya error listado p{pagina}: {e}')
            break

    print(f'  Inmo Olaya: {len(urls_listado)} fichas en el listado.')

    # ── PASO 2: entrar en cada ficha y sacar título/precio/ubicación/descripción/fotos ──
    total_io = 0
    for href in urls_listado:
        if href in seen_urls:
            continue
        try:
            r = session.get(href, headers=HEADERS_IO, timeout=15)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, 'lxml')

            h1 = soup.find('h1', class_='prop-title')
            title = clean(h1.get_text()) if h1 else ''
            if not title or len(title) < 8:
                continue

            # El precio y la ubicacion viven juntos en el mismo bloque de
            # cabecera (.property-title) -- CONFIRMADO que ese bloque NO se
            # repite en ningun otro sitio de la pagina (a diferencia de la
            # clase 'property' de las tarjetas del listado, que si aparece
            # repetida en carruseles de "propiedades relacionadas").
            cabecera = soup.find(class_='property-title')

            precio_el = cabecera.find(class_='precio') if cabecera else None
            precio_txt = clean(precio_el.get_text()) if precio_el else ''
            # En traspasos el bloque trae tambien "Alquiler actual: X€" debajo
            # del precio del traspaso -- nos quedamos solo con la primera
            # cifra (el precio del traspaso/venta en si). Esa misma frase nos
            # sirve tambien para saber CON CERTEZA que es un traspaso (no
            # aparece nunca en una venta normal) -- mas fiable que depender
            # de que el texto del anuncio use alguna de las frases de
            # OPERACION_PATRONES_TRASPASO en el frontend.
            es_traspaso_io = bool(re.search(r'alquiler\s+actual', precio_txt, re.I))
            m_precio = re.search(r'[\d.,]+\s*€', precio_txt)
            price = m_precio.group(0) if m_precio else 'Precio a consultar'

            # Ubicacion: h4 con formato "Municipio · Provincia" -- usamos solo
            # el municipio (antes del "·") y dejamos que infer_region() (ya
            # usado por add_listing para TODOS los portales) saque la
            # comunidad autónoma a partir de él, igual que con el resto de
            # fuentes -- la segunda mitad a veces es la provincia y a veces
            # coincide con el nombre de la comunidad, así que no es fiable
            # usarla directamente como comunidad.
            h4 = cabecera.find('h4') if cabecera else None
            location = ''
            if h4:
                partes = clean(h4.get_text()).split('·')
                location = partes[0].strip() if partes else ''

            desc_el = soup.find(class_='property-description')
            description = clean_desc(desc_el) if desc_el else ''

            # Fotos: la galeria completa (.galery-full) trae un <a> por foto
            # apuntando a la version en alta resolucion (_xl.jpg) -- excepto
            # el icono del certificado energetico (energia.png), que no es
            # una foto del inmueble y hay que descartar.
            fotos = []
            galeria = soup.find(class_='galery-full')
            if galeria:
                for a in galeria.find_all('a', href=True):
                    src = a['href']
                    if not src or 'energia' in src:
                        continue
                    if not src.startswith('http'):
                        src = 'https://inmoolaya.com' + src
                    if src not in fotos:
                        fotos.append(src)

            listing = {
                'title': title,
                'price': price,
                'location': location or 'España',
                'description': description,
                'url': href,
                'source': 'Inmo Olaya',
                'date': TODAY,
            }
            if fotos:
                listing['fotos_url'] = fotos
            if es_traspaso_io:
                listing['operacion_detectada'] = 'traspaso'

            added = add_listing(listing)
            if added:
                total_io += 1
                print(f'  ✅ {title[:60]}')
            time.sleep(random.uniform(1, 2))
        except Exception as e:
            print(f'  Inmo Olaya error ficha {href}: {e}')
            continue

    print(f'  Inmo Olaya TOTAL: {total_io}')

if __name__ == '__main__':
    print(f'=== Hotel Monitor Local — {TODAY} ===\n')

    cache = load_cache()
    driver = init_driver()

    # ── GRUPO 1: ThinkSpain + LucasFox (Chrome 1) ──────
    try:
        try: scrape_thinkspain(driver)
        except Exception as e: print(f'Error ThinkSpain: {e}')

        try: scrape_lucasfox(driver)
        except Exception as e: print(f'Error LucasFox: {e}')
    finally:
        try: driver.quit()
        except: pass

    # ── GRUPO 2: LuxuryEstate solo (Chrome 2) ──────────
    print('\nIniciando Chrome 2 para LuxuryEstate...')
    driver2 = init_driver()
    try:
        try: scrape_luxuryestate(driver2)
        except Exception as e: print(f'Error LuxuryEstate: {e}')
    finally:
        try: driver2.quit()
        except: pass

    # ── GRUPO 3: NegociosEnVenta + HotelSeVende (Chrome 3) ──
    print('\nIniciando Chrome 3...')
    driver3 = init_driver()
    try:
        try: scrape_negociosenventa(driver3)
        except Exception as e: print(f'Error NegociosEnVenta: {e}')

        try: scrape_negociosenventa_traspasos(driver3)
        except Exception as e: print(f'Error NegociosEnVenta (traspasos): {e}')

        try: scrape_hotelsevende(driver3)
        except Exception as e: print(f'Error HotelSeVende: {e}')

        try: scrape_hispacasas(driver3)
        except Exception as e: print(f'Error Hispacasas: {e}')

        try: scrape_lancoisdoval(driver3)
        except Exception as e: print(f'Error Lançois Doval: {e}')

        try: scrape_casasapo(driver3)
        except Exception as e: print(f'Error Casa Sapo: {e}')

        try: scrape_supercasa(driver3)
        except Exception as e: print(f'Error Supercasa: {e}')

        try: scrape_robertobeloki(driver3)
        except Exception as e: print(f'Error Roberto Beloki: {e}')

        # Nuroa DESACTIVADO: solo busca edificios turísticos, que no hay en venta (siempre 0)

        try: scrape_yaencontre(driver3)
        except Exception as e: print(f'Error Yaencontre: {e}')
    finally:
        try: driver3.quit()
        except: pass

    # ── GRUPO 4: Idealista + Milanuncios (Chrome 4 stealth) ──
    print('\nIniciando Chrome 4 para Idealista y Milanuncios...')
    driver4 = init_driver_stealth()
    try:
        try: scrape_idealista(driver4)
        except Exception as e: print(f'Error Idealista: {e}')

        try: scrape_milanuncios(driver4)
        except Exception as e: print(f'Error Milanuncios: {e}')
    finally:
        try: driver4.quit()
        except: pass

    # ── GRUPO 3: Sin Chrome (requests) ──────────────────
    try: scrape_oirealestate(None)
    except Exception as e: print(f'Error Oi Real Estate: {e}')

    try: scrape_engelvoelkers(None)
    except Exception as e: print(f'Error Engel Volkers: {e}')

    try: scrape_ecourbanizacion(None)
    except Exception as e: print(f'Error EcoUrbanizacion: {e}')

    try: scrape_inmoolaya(None)
    except Exception as e: print(f'Error Inmo Olaya: {e}')

    print('\nNavegador cerrado.')

    # Merge con cache
    urls_encontradas = {item['url'] for item in found_listings}
    cache_nuevo = dict(cache)
    nuevos = 0
    for item in found_listings:
        url_key = item['url']
        if url_key not in cache_nuevo:
            cache_nuevo[url_key] = item
            nuevos += 1
        else:
            cache_nuevo[url_key]['price']       = item.get('price', cache_nuevo[url_key].get('price',''))
            _desc_nueva = item.get('description') or ''
            _desc_vieja = cache_nuevo[url_key].get('description') or ''
            # No pisar una descripcion ya guardada con una vacia por un
            # fallo puntual del scraping de hoy -- nos quedamos con la
            # mas larga de las dos (normalmente la nueva, salvo que hoy
            # haya venido mas corta o vacia).
            cache_nuevo[url_key]['description'] = _desc_nueva if len(_desc_nueva) >= len(_desc_vieja) else _desc_vieja
            cache_nuevo[url_key]['tipo']        = item.get('tipo', cache_nuevo[url_key].get('tipo',''))
            cache_nuevo[url_key]['ausencias']   = 0
            # Refrescar datos estructurados (m2/habitaciones/camas/banos) con lo
            # scrapeado HOY. Antes no se copiaban aqui, asi que los anuncios ya
            # cacheados nunca cogian m2/hab aunque mejorasemos el scraper -> por
            # eso salian con m2 solo los NUEVOS. Ahora se actualizan siempre.
            for _k in ('rooms', 'm2', 'beds', 'bathrooms', 'fotos_url', 'operacion_detectada'):
                if item.get(_k):
                    cache_nuevo[url_key][_k] = item[_k]

    # Backfill: anuncios guardados ANTES de tener el campo 'tipo' (o 'estado')
    # los clasificamos ahora, para que el Excel/JSON completo quede coherente,
    # no solo los que se scrapean a partir de hoy.
    backfilled = 0; rooms_fill = 0; precio_fix = 0; m2_fill = 0
    _ROOMS_RE = re.compile(r'(\d{1,4})\s*(?:habitaciones|habitacion|habs?\b|dormitorios|rooms?|bedrooms?|llaves|quartos?)', re.I)
    _M2_RE = re.compile(r'(?<![a-zA-Z])([\d][\d.,\xa0]*)\s*m\s*(?:\u00b2|2)(?![a-z0-9])', re.I)
    for item in cache_nuevo.values():
        if not item.get('tipo'):
            item['tipo'] = clasificar_tipo(item.get('title',''), item.get('description',''))
            backfilled += 1
        if not item.get('estado'):
            item['estado'] = 'Activo'
        # Backfill habitaciones desde title+description (TODOS los anuncios del cache)
        if not item.get('rooms'):
            _blob = (item.get('title','') or '') + ' ' + (item.get('description','') or '')
            _m = _ROOMS_RE.search(_blob)
            if _m:
                _rv = int(_m.group(1))
                if 1 <= _rv <= 2000:
                    item['rooms'] = _rv; rooms_fill += 1
        # Backfill m² desde title+description (TODOS los anuncios del cache)
        # -- no existía ningún respaldo para esto hasta ahora. Mismo orden
        # que en add_listing(): descripción primero (sin procesar por
        # clean(), conserva el \xa0 real), título como plan B.
        if not item.get('m2'):
            _mm = None
            for _fuente in (item.get('description','') or '', item.get('title','') or ''):
                _mm = _M2_RE.search(_fuente)
                if _mm:
                    break
            if _mm:
                try:
                    _m2v = int(float(_mm.group(1).replace('\xa0', '').replace('.', '').replace(',', '.')))
                    if 5 <= _m2v <= 1_000_000:
                        item['m2'] = _m2v; m2_fill += 1
                except ValueError:
                    pass
        # Sanear precios basura en TODO el cache (no solo los nuevos) --
        # mismo arreglo que en add_listing(): vacío también cuenta.
        _pn = re.sub(r'[^\d]', '', item.get('price','') or '')
        if _pn:
            _pv = int(_pn)
            if _pv < 1000 or _pv > 100_000_000:
                item['price'] = 'Precio a consultar'; precio_fix += 1
        elif item.get('price') != 'Precio a consultar':
            item['price'] = 'Precio a consultar'; precio_fix += 1
    if backfilled:
        print(f'  Clasificados retroactivamente (sin "tipo" previo): {backfilled} anuncios.')
    if rooms_fill:
        print(f'  Habitaciones rellenadas retroactivamente: {rooms_fill} anuncios.')
    if m2_fill:
        print(f'  m² rellenados retroactivamente: {m2_fill} anuncios.')
    if precio_fix:
        print(f'  Precios basura saneados: {precio_fix} anuncios.')

    # ── Detectar portales que han fallado ESTA ejecución (bloqueo de IP,
    # captcha, caída, cambio de maquetación...) para no penalizar a sus
    # anuncios como si se hubiesen retirado de verdad. Si un portal que
    # tenía bastantes anuncios en cache no ha encontrado NINGUNO hoy, lo
    # tratamos como fallo de ejecución, no como que todo se vendió de
    # golpe. Es deliberadamente conservador (mejor no marcar una baja real
    # unos días de más, que marcar de baja en masa anuncios que siguen
    # activos por un bloqueo puntual del portal).
    fuentes_cache = {}
    for item in cache.values():
        src = item.get('source', '')
        if src:
            fuentes_cache[src] = fuentes_cache.get(src, 0) + 1
    fuentes_hoy = {}
    for item in found_listings:
        src = item.get('source', '')
        if src:
            fuentes_hoy[src] = fuentes_hoy.get(src, 0) + 1
    UMBRAL_MIN_CACHE = 5
    portales_fallidos = {
        fuente for fuente, n_cache in fuentes_cache.items()
        if n_cache >= UMBRAL_MIN_CACHE and fuentes_hoy.get(fuente, 0) == 0
    }
    if portales_fallidos:
        print(f'  ⚠️ Portales sin ningun resultado hoy (tratados como fallo, no como bajas reales): {sorted(portales_fallidos)}')

    print('\nRevisando bajas...')
    cache_nuevo = limpiar_bajas(cache_nuevo, urls_encontradas, portales_fallidos)
    save_cache(cache_nuevo)
    print(f'Cache guardado: {len(cache_nuevo)} totales ({nuevos} nuevos).')

    # Historico permanente de retirados (comparables). Se acumula aparte y
    # nunca se pierde, aunque la cache se resetee o cambiemos de scraper.
    hist_retirados = actualizar_historico_retirados(cache_nuevo)

    todos = list(cache_nuevo.values())
    def fsort(x):
        try: return datetime.strptime(x.get('date','01/01/2000'), '%d/%m/%Y')
        except: return datetime.min
    todos.sort(key=fsort, reverse=True)

    # OFERTAS TOTALES = solo ACTIVOS. Los retirados no van aqui: van a su
    # hoja/archivo aparte (comparables). Excluimos del historico los que
    # ahora mismo estan activos (por si un anuncio se reactivo).
    todos_activos = [h for h in todos if h.get('estado') != 'Retirado']
    activos_urls = {h.get('url') for h in todos_activos}
    retirados_hist = [h for h in hist_retirados.values() if h.get('url') not in activos_urls]

    print(f'\n{"="*50}')
    print(f'TOTAL ANUNCIOS: {len(todos)}  (activos: {len(todos_activos)} | retirados histórico: {len(retirados_hist)})')
    print('='*50)

    # Cruce automático con licencias turísticas oficiales -- se hace aquí,
    # cada vez que se scrapea, en vez de dejarlo solo para cuando alguien
    # pulsa "Descargar Excel" en la web. Modifica los mismos objetos de
    # todos_activos (que son los de cache_nuevo), así que un save_cache()
    # después de esto ya deja licencia_texto/licencia_motivo guardados.
    cruzar_licencias_con_activos(todos_activos)
    save_cache(cache_nuevo)

    with open('index_template.html','r',encoding='utf-8') as f:
        template = f.read()

    # Inyectar benchmark ADR si existe (generado por scraper_adr.py, corre 1x/mes)
    adr_benchmark_json = '{}'
    if os.path.exists('adr_benchmark.json'):
        with open('adr_benchmark.json','r',encoding='utf-8') as fb:
            adr_benchmark_json = fb.read().strip()
        print('adr_benchmark.json encontrado — inyectando datos reales Booking')
    else:
        print('adr_benchmark.json no existe — tasación usará fallback INE')

    html = template.replace('__LISTINGS_JSON__', json.dumps(todos_activos, ensure_ascii=False))
    html = html.replace('__RETIRADOS_JSON__', json.dumps(retirados_hist, ensure_ascii=False))
    html = html.replace('__ADR_BENCHMARK_JSON__', adr_benchmark_json)

    with open('index.html','w',encoding='utf-8') as f:
        f.write(html)
    print(f'index.html generado con {len(todos_activos)} activos + {len(retirados_hist)} retirados (comparables).')

    # Licencias: se actualiza aparte, solo si toca esta semana (ver
    # ejecutar_licencias_si_toca — no es cada día). Va aquí, después de
    # que index.html ya esté generado y guardado, así que aunque algo
    # falle en licencias, los anuncios de hoy no se pierden.
    ejecutar_licencias_si_toca()

    if os.environ.get('GITHUB_ACTIONS'):
        print('\nEjecutando en GitHub Actions: el commit y push los hace el propio workflow (scrape.yml).')
    else:
        subir_github(len(todos))
        input('\nPresiona Enter para cerrar...')
