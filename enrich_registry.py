#!/usr/bin/env python3
"""
enrich_registry.py — Enriquecimiento de licencias hoteleras

Stack: undetected-chromedriver (Booking + Google Travel en el mismo Chrome)
       UN solo Chrome por worker, reutilizado para todo el lote.

Requiere:  pip install undetected-chromedriver beautifulsoup4 lxml

Uso:
    python enrich_registry.py --input licencias.json.gz --limit 100 --workers 2
    python enrich_registry.py --input licencias.json.gz --limit 500 --workers 3 --fast --headless
"""

import json, re, time, os, random, unicodedata, argparse, gzip, threading
from datetime import date, timedelta
from difflib import SequenceMatcher

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup

HERE       = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(HERE, 'registro_enriquecido.json')

# ── Fechas snapshot (miércoles ~35 días vista) ───────────────────────────────
def _fechas_consulta():
    d = date.today() + timedelta(days=35)
    while d.weekday() != 2:
        d += timedelta(days=1)
    return d.strftime('%Y-%m-%d'), (d + timedelta(days=1)).strftime('%Y-%m-%d')

CHECKIN, CHECKOUT = _fechas_consulta()

# ════════════════════════════════════════════════════════════════════════════
#  MODELO OCUPACIÓN / RevPAR INE
# ════════════════════════════════════════════════════════════════════════════
OCUP_REGION = {
    'Baleares':0.75,'Canarias':0.79,'Madrid':0.77,'Cataluña':0.77,
    'Andalucía':0.72,'C. Valenciana':0.79,'Murcia':0.70,'Galicia':0.62,
    'Asturias':0.58,'Castilla y León':0.56,'País Vasco':0.68,
}
CAT_OCUP_MULT  = {1:0.82, 2:0.88, 3:0.94, 4:1.00, 5:0.96}
REVPAR_INE_REGION = {
    'Baleares':147,'Canarias':114,'Madrid':113,'Cataluña':110,
    'Andalucía':95,'C. Valenciana':88,'Murcia':70,'Galicia':57,
    'Asturias':53,'Castilla y León':50,'País Vasco':92,
}
CAT_REVP_MULT  = {1:0.35, 2:0.53, 3:0.73, 4:1.00, 5:2.33}
PROV_A_REGION  = {
    'ÁLAVA':'País Vasco','VIZCAYA':'País Vasco','GUIPÚZCOA':'País Vasco',
    'MADRID':'Madrid','BARCELONA':'Cataluña','GIRONA':'Cataluña',
    'TARRAGONA':'Cataluña','LLEIDA':'Cataluña',
    'MÁLAGA':'Andalucía','SEVILLA':'Andalucía','GRANADA':'Andalucía',
    'CÁDIZ':'Andalucía','ALMERÍA':'Andalucía','CÓRDOBA':'Andalucía',
    'HUELVA':'Andalucía','JAÉN':'Andalucía',
    'ILLES BALEARS':'Baleares','BALEARES':'Baleares',
    'SANTA CRUZ DE TENERIFE':'Canarias','LAS PALMAS':'Canarias',
    'VALENCIA':'C. Valenciana','ALICANTE':'C. Valenciana','CASTELLÓN':'C. Valenciana',
    'MURCIA':'Murcia','PONTEVEDRA':'Galicia','A CORUÑA':'Galicia',
    'LUGO':'Galicia','OURENSE':'Galicia','ASTURIAS':'Asturias',
}

def region_de(p):
    return PROV_A_REGION.get((p or '').upper().strip(), 'Otras')

def modelar_ocupacion(prov, cat):
    return round(min(0.95, OCUP_REGION.get(region_de(prov), 0.62)
                     * CAT_OCUP_MULT.get(cat or 4, 1.0)), 3)

def revpar_ine(prov, cat):
    return round(REVPAR_INE_REGION.get(region_de(prov), 56)
                 * CAT_REVP_MULT.get(cat or 4, 1.0) * 1.04)

# ════════════════════════════════════════════════════════════════════════════
#  UTILIDADES
# ════════════════════════════════════════════════════════════════════════════
def _norm(s):
    if not s: return ''
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    for w in ['hotel','hostal','pension','pensión','apartamentos','casa','rural',
              'albergue','el','la','los','las','de','del']:
        s = re.sub(rf'\b{w}\b', '', s)
    return re.sub(r'[^a-z0-9 ]', ' ', re.sub(r'\s+', ' ', s)).strip()

def field(lic, *claves, default=''):
    for k in claves:
        v = lic.get(k)
        if v not in (None, '', '—', '-'): return v
    return default

def calle_de(d):
    d = re.sub(r'\d+.*$', '', d or '').strip(' ,')
    return re.sub(
        r'^(calle|c/|avenida|avda|plaza|pza|paseo|camino|carretera|ctra)\b\.?\s*',
        '', d, flags=re.I).strip()

def match_score(nr, nl, mun, txt, dir=''):
    sim = SequenceMatcher(None, _norm(nr), _norm(nl)).ratio()
    t   = _norm(txt)
    mok = 1.0 if _norm(mun) and _norm(mun) in t else 0.0
    c   = _norm(calle_de(dir))
    cok = 1.0 if c and len(c) > 3 and c in t else 0.0
    return round(min(1.0, 0.70*sim + 0.20*mok + 0.10*cok), 3)

def _num(txt):
    m = re.search(r'(\d[\d.\s]*)', (txt or '').replace('\xa0', ' '))
    return int(re.sub(r'[^\d]', '', m.group(1))) if m else None

def _rating_10(txt):
    """Rating escala /10 (Booking)."""
    m = re.search(r'(\d[.,]\d)', txt or '')
    return float(m.group(1).replace(',', '.')) if m else None

def _rating_5(txt):
    """Rating escala /5 (Google)."""
    m = re.search(r'([1-5][.,]\d)', txt or '')
    return float(m.group(1).replace(',', '.')) if m else None

def _estrellas(txt):
    m = re.search(r'(\d)', str(txt or ''))
    return int(m.group(1)) if m else None

def _hab_de_plazas(p):
    try: return max(1, round(int(p) / 1.9)) if p else None
    except: return None

def _hab_de_tipo(tipo):
    t = (tipo or '').lower()
    if 'casa rural' in t or 'agroturismo' in t: return 6
    if 'pensión' in t or 'pension' in t or 'hostal' in t: return 12
    if 'apartament' in t: return 15
    if 'albergue' in t: return 18
    if 'hotel' in t: return 30
    return None

# ════════════════════════════════════════════════════════════════════════════
#  CHROME — inicialización serializada (evita PermissionError en paralelo)
# ════════════════════════════════════════════════════════════════════════════
_driver_init_lock = threading.Lock()

def _chrome_major():
    import subprocess, platform
    cmds = []
    if platform.system() == 'Windows':
        cmds = [
            ['reg','query',r'HKEY_CURRENT_USER\Software\Google\Chrome\BLBeacon','/v','version'],
            ['reg','query',r'HKEY_LOCAL_MACHINE\SOFTWARE\Google\Chrome\BLBeacon','/v','version'],
        ]
    elif platform.system() == 'Darwin':
        cmds = [['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome','--version']]
    else:
        cmds = [['google-chrome','--version'],['chromium','--version']]
    for c in cmds:
        try:
            out = __import__('subprocess').run(c, capture_output=True, text=True, timeout=8).stdout
            m   = re.search(r'(\d+)\.\d+\.\d+', out)
            if m: return int(m.group(1))
        except: pass
    return None

def init_driver(headless=True):
    with _driver_init_lock:
        opts = uc.ChromeOptions()
        opts.add_argument('--window-size=1280,900')
        opts.add_argument('--lang=es-ES')
        opts.add_argument('--disable-gpu')
        opts.add_argument('--disable-extensions')
        opts.add_argument('--disable-dev-shm-usage')
        opts.add_argument('--no-first-run')
        opts.add_argument('--blink-settings=imagesEnabled=false')
        opts.page_load_strategy = 'eager'
        if headless:
            opts.add_argument('--headless=new')
            opts.add_argument('--no-sandbox')
        major = _chrome_major()
        if major:
            print(f'  Chrome v{major}', flush=True)
        d = uc.Chrome(options=opts, use_subprocess=True, version_main=major)
        d.set_page_load_timeout(25)
        try:
            d.execute_cdp_cmd('Network.setBlockedURLs', {'urls': [
                '*.png','*.jpg','*.jpeg','*.gif','*.webp','*.svg',
                '*.woff','*.woff2','*.ttf','*.mp4']})
            d.execute_cdp_cmd('Network.enable', {})
        except: pass
        d.execute_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        return d

def _click_consent(driver):
    """Acepta cookies en Booking y Google (un intento, silencioso si falla)."""
    for sel in [
        '#onetrust-accept-btn-handler',
        'button[aria-label*="Aceptar"]',
        'button[aria-label*="Accept"]',
        'button[id*="accept"]',
        'form:has(button) button',      # Google consent form
    ]:
        try:
            driver.find_element(By.CSS_SELECTOR, sel).click()
            time.sleep(0.5)
            return True
        except: pass
    return False

# ════════════════════════════════════════════════════════════════════════════
#  BOOKING.COM
# ════════════════════════════════════════════════════════════════════════════
def _bk_precios_vistos(card):
    txt  = card.get_text(' ', strip=True).replace('\xa0', ' ')
    tok  = r'(\d{1,3}(?:[.\s]\d{3})+|\d{2,6})'
    hits = re.findall(r'€\s*' + tok, txt) + re.findall(tok + r'\s*€', txt)
    out  = []
    for m in hits:
        n = int(re.sub(r'[^\d]', '', m))
        if 15 <= n <= 5000: out.append(n)   # cap a 5000 para filtrar totales
    return sorted(set(out))

def _bk_precio(card, noches=1):
    """Extrae precio/noche. noches=1 porque buscamos 1 noche."""
    for sel in [
        'span[data-testid="price-and-discounted-price"]',
        '[data-testid="price-and-discounted-price"]',
        '[data-testid="availability-rate-information"]',
        'span.prco-valign-middle-helper',
    ]:
        el = card.select_one(sel)
        if el:
            n = _num(el.get_text())
            if n and 15 <= n <= 5000: return n

    # Fallback: precio más bajo de los vistos
    vistos = [v for v in _bk_precios_vistos(card) if 15 <= v <= 3000]
    return vistos[0] if vistos else None

def scrape_booking(driver, nombre, municipio, provincia, direccion, pausa):
    q   = f"{nombre} {municipio}".strip()
    url = (f"https://www.booking.com/searchresults.es.html"
           f"?ss={q.replace(' ', '+')}"
           f"&checkin={CHECKIN}&checkout={CHECKOUT}"
           f"&group_adults=2&no_rooms=1&group_children=0&lang=es")
    try:
        driver.get(url)
        time.sleep(random.uniform(*pausa))
        _click_consent(driver)
        soup = BeautifulSoup(driver.page_source, 'lxml')
    except Exception as e:
        return {'fuente': 'booking', 'error': str(e)[:120]}

    # Comprobar si hay CAPTCHA o bloqueo
    page_txt = soup.get_text(' ')
    if 'javascript' in page_txt.lower()[:500] and 'robot' in page_txt.lower()[:500]:
        return {'fuente': 'booking', 'error': 'captcha/js_block'}

    card = soup.select_one('div[data-testid="property-card"]')
    if not card:
        return {'fuente': 'booking', 'sin_resultado': True}

    nom_el   = card.select_one('div[data-testid="title"]')
    score_el = card.select_one('div[data-testid="review-score"]')
    link_el  = card.select_one('a[data-testid="title-link"]')
    nom_txt   = nom_el.get_text(strip=True) if nom_el else ''
    score_txt = score_el.get_text(' ', strip=True) if score_el else ''
    rev_m     = re.search(r'([\d.]+)\s*(?:coment|reseñ|review)', score_txt, re.I)
    precio    = _bk_precio(card)
    precios   = _bk_precios_vistos(card)

    return {
        'fuente'        : 'booking',
        'nombre'        : nom_txt,
        'precio_noche'  : precio,
        'precios_vistos': precios,
        'rating'        : _rating_10(score_txt),
        'reviews'       : _num(rev_m.group(1)) if rev_m else None,
        'url'           : (link_el['href'].split('?')[0]
                           if link_el and link_el.has_attr('href') else None),
        'match'         : match_score(nombre, nom_txt, municipio,
                                      card.get_text(' '), direccion),
    }

# ════════════════════════════════════════════════════════════════════════════
#  GOOGLE TRAVEL
# ════════════════════════════════════════════════════════════════════════════
# Cookie de consentimiento GDPR de Google — salta la pantalla "Antes de continuar"
# Caduca ocasionalmente; si falla, el driver la acepta por Chrome como fallback.
_GT_COOKIE = "SOCS=CAESEwgDEgk0ODE3Nzk3MjkaAmVzIAEaBgiA_LyxBg; NID=511=; OGPC=19034207-1:"

_GT_CONSENT_ACCEPTED = threading.Event()   # basta con aceptarlo una vez por sesión

def _gt_aceptar_consent(driver):
    """Navega a google.com y acepta el consentimiento. Solo hace falta una vez."""
    if _GT_CONSENT_ACCEPTED.is_set():
        return
    try:
        driver.get('https://www.google.com/')
        time.sleep(1.5)
        for sel in [
            'button[aria-label*="Aceptar todo"]',
            'button[aria-label*="Accept all"]',
            '#L2AGLb',                    # id clásico del botón "Acepto"
            'form:last-of-type button',
        ]:
            try:
                driver.find_element(By.CSS_SELECTOR, sel).click()
                time.sleep(0.8)
                _GT_CONSENT_ACCEPTED.set()
                return
            except: pass
    except: pass

def scrape_google_travel(driver, nombre, municipio, pausa):
    q   = f"{nombre} {municipio} hotel".strip()
    url = f"https://www.google.com/travel/search?q={q.replace(' ', '+')}&hl=es&gl=es"
    try:
        driver.get(url)
        time.sleep(random.uniform(*pausa))
        # Si vemos la pantalla de consent, la aceptamos y recargamos
        if 'antes de continuar' in driver.page_source.lower()[:2000]:
            _gt_aceptar_consent(driver)
            driver.get(url)
            time.sleep(random.uniform(*pausa))
        soup = BeautifulSoup(driver.page_source, 'lxml')
    except Exception as e:
        return {'fuente': 'google_travel', 'error': str(e)[:120]}

    texto = soup.get_text(' ', strip=True)

    # Rating /5 y reseñas
    rating = None; reviews = None
    for p in [
        r'([1-5][.,]\d)\s*\(?\s*([\d.\s]{1,9})\s*\)?\s*(?:reseñ|opin|review|valorac)',
        r'([1-5][.,]\d)\s*estrella?s?\s*[·•|\-–]?\s*([\d.\s]{1,9})\s*(?:reseñ|opin)',
        r'([1-5][.,]\d)\s*\(\s*([\d.\s]{2,9})\s*\)',
    ]:
        m = re.search(p, texto, re.I)
        if m:
            rating  = float(m.group(1).replace(',', '.'))
            reviews = _num(m.group(2))
            break

    precios = [int(p) for p in re.findall(r'(\d{2,4})\s*€', texto)]
    precios = sorted(set(p for p in precios if 25 <= p <= 2000))[:12]
    return {
        'fuente'       : 'google_travel',
        'rating'       : rating,
        'reviews'      : reviews,
        'precio_tipico': int(sorted(precios)[len(precios)//2]) if precios else None,
        'rango'        : [min(precios), max(precios)] if precios else None,
        'url'          : url,
    }

# ════════════════════════════════════════════════════════════════════════════
#  WORKER — 1 thread = 1 Chrome, hace Booking Y Google en el mismo navegador
# ════════════════════════════════════════════════════════════════════════════
_cache_lock = threading.Lock()

def _worker(chunk, cache, headless, wid, pausa, stats, stats_lock, t0):
    try:
        driver = init_driver(headless)
    except Exception as e:
        print(f"[w{wid}] ERROR iniciando Chrome: {e}", flush=True)
        return

    # Aceptar consent de Google al arrancar (una sola vez)
    _gt_aceptar_consent(driver)

    hechos = 0
    try:
        for lic in chunk:
            nom       = field(lic, 'nombre', 'name') or '?'
            nombre    = field(lic, 'nombre', 'name', 'denominacion', 'establecimiento')
            municipio = field(lic, 'municipio', 'localidad', 'poblacion', 'ciudad')
            provincia = field(lic, 'provincia', 'prov')
            direccion = field(lic, 'direccion', 'dir', 'domicilio', 'calle', 'address')
            categoria = (_estrellas(field(lic, 'categoria_estrellas', 'estrellas'))
                         or _estrellas(field(lic, 'categoria', 'cat')))
            habs      = (field(lic, 'habitaciones', 'hab', 'rooms', default=None)
                         or _hab_de_plazas(field(lic, 'plazas', 'plazas_totales',
                                                 'capacidad', default=None))
                         or _hab_de_tipo(field(lic, 'tipo')))
            try: habs = int(habs) if habs else None
            except: habs = None

            try:
                bk = scrape_booking(driver, nombre, municipio, provincia,
                                    direccion, pausa['booking_wait'])
                time.sleep(random.uniform(*pausa['bk_to_gt']))
                gt = scrape_google_travel(driver, nombre, municipio,
                                          pausa['google_wait'])
            except Exception as e:
                msg = str(e).lower()
                if any(k in msg for k in ('invalid session','no such session',
                                           'disconnected','not reachable')):
                    print(f"[w{wid}] Sesión muerta — reiniciando...", flush=True)
                    try: driver.quit()
                    except: pass
                    time.sleep(3)
                    try:
                        driver = init_driver(headless)
                        _gt_aceptar_consent(driver)
                    except: pass
                bk = {'fuente': 'booking',      'error': str(e)[:80]}
                gt = {'fuente': 'google_travel', 'error': str(e)[:80]}

            # ── Elegir ADR fiable ──
            adr_google  = gt.get('precio_tipico')
            adr_booking = bk.get('precio_noche')
            rango_g     = gt.get('rango')
            bk_fiable   = adr_booking
            # Booking sospechoso si supera 1.8x el máximo de Google (precio total, etc.)
            if adr_booking and rango_g and adr_booking > rango_g[1] * 1.8:
                bk_fiable = None
                bk['precio_sospechoso'] = adr_booking
            # Google primero (mediana limpia), Booking como respaldo
            adr_real = adr_google or bk_fiable

            ocup         = modelar_ocupacion(provincia, categoria)
            rev_real     = round(adr_real * ocup)      if adr_real          else None
            rev_ine      = revpar_ine(provincia, categoria)
            ingreso_real = round(rev_real * habs * 365) if (rev_real and habs) else None
            ingreso_ine  = round(rev_ine  * habs * 365) if habs               else None

            r = {
                'n_registro'   : field(lic, 'n_reg','n_registro','id',
                                       'registro','codigo', default=None),
                'nombre'       : nombre,
                'direccion'    : direccion,
                'municipio'    : municipio,
                'provincia'    : provincia,
                'categoria'    : categoria,
                'habitaciones' : habs,
                'booking'      : bk,
                'google_travel': gt,
                'estimacion'   : {
                    'adr_real'          : adr_real,
                    'ocupacion'         : ocup,
                    'revpar_real'       : rev_real,
                    'revpar_ine'        : rev_ine,
                    'ingreso_anual_real': ingreso_real,
                    'ingreso_anual_ine' : ingreso_ine,
                    'precision'         : 'real' if adr_real else 'solo_ine',
                },
                'fecha_consulta': CHECKIN,
            }

            with _cache_lock:
                cache[r['n_registro']] = r
                with stats_lock:
                    stats['n'] += 1
                    n = stats['n']
                elapsed = time.time() - t0
                rate    = elapsed / n
                e       = r['estimacion']
                fuente  = ('bk' if (bk_fiable and not adr_google)
                           else 'gt' if adr_google else '--')
                print(
                    f"[w{wid}]({n:>4}) {nom[:32]:32}  "
                    f"ADR={str(e['adr_real'])+'€':>7} ({fuente})  "
                    f"rev/año={str(ingreso_real)+'€' if ingreso_real else 'None':>9}  "
                    f"bk_match={bk.get('match')}  "
                    f"gt_price={gt.get('precio_tipico')}€  "
                    f"[{rate:.1f}s/h]",
                    flush=True
                )
                hechos += 1
                if hechos % 20 == 0:
                    save_cache(cache)

            time.sleep(random.uniform(*pausa['entre_hoteles']))
    finally:
        if hechos % 20 != 0:
            with _cache_lock: save_cache(cache)
        try: driver.quit()
        except: pass

# ════════════════════════════════════════════════════════════════════════════
#  CACHE / IO
# ════════════════════════════════════════════════════════════════════════════
def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, encoding='utf-8') as f:
            return {r['n_registro']: r for r in json.load(f)}
    return {}

def save_cache(c):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(c.values()), f, ensure_ascii=False, indent=2)

def cargar_licencias(ruta):
    op = gzip.open if ruta.endswith('.gz') else open
    with op(ruta, 'rt', encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, list): return data
    if isinstance(data, dict):
        for k in ('licencias','hoteles','data','items','results'):
            if isinstance(data.get(k), list): return data[k]
        plana = []
        for v in data.values():
            if isinstance(v, list): plana.extend(v)
            elif isinstance(v, dict): plana.append(v)
        return plana
    return []

def _dedup(licencias):
    vistos, out = set(), []
    for l in licencias:
        k = (field(l,'n_reg','n_registro','id','registro','codigo') or
             (field(l,'nombre') + '|' + field(l,'municipio')).lower())
        if k and k not in vistos:
            vistos.add(k); out.append(l)
    return out

def _reg_key(lic):
    return field(lic, 'n_reg','n_registro','id','registro','codigo', default=None)

def _peek(licencias, n=5):
    print(f'\nMUESTRA — {len(licencias)} licencias:\n')
    for lic in licencias[:n]:
        nombre    = field(lic, 'nombre','name','denominacion','establecimiento')
        municipio = field(lic, 'municipio','localidad','poblacion','ciudad')
        provincia = field(lic, 'provincia','prov')
        direccion = field(lic, 'direccion','dir','domicilio','calle','address')
        cat  = _estrellas(field(lic,'categoria_estrellas','estrellas')
                          or field(lic,'categoria','cat'))
        habs = (field(lic,'habitaciones','hab','rooms',default=None)
                or _hab_de_plazas(field(lic,'plazas','plazas_totales',
                                        'capacidad',default=None)))
        reg  = field(lic,'n_reg','n_registro','id','registro','codigo',default='?')
        print(f"  [{reg}] {nombre or 'SIN NOMBRE'}")
        print(f"        dir='{direccion}'  muni='{municipio}'  "
              f"prov='{provincia}'  {cat}*  {habs} hab")
    print()

# ════════════════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser(
        description='Enriquece licencias hoteleras con ADR (Booking + Google, sin API)')
    ap.add_argument('--input',    default='licencias.json')
    ap.add_argument('--limit',    type=int, default=100)
    ap.add_argument('--workers',  type=int, default=2,
                    help='Chromes en paralelo (recomendado 2-3)')
    ap.add_argument('--fast',     action='store_true',
                    help='Pausas cortas (más riesgo de CAPTCHA)')
    ap.add_argument('--headless', action='store_true',
                    help='Sin ventana Chrome (algo más rápido)')
    ap.add_argument('--peek',     action='store_true',
                    help='Solo muestra campos leídos, no scrapea')
    args = ap.parse_args()

    licencias = cargar_licencias(args.input)
    if args.peek:
        _peek(licencias); return

    antes = len(licencias)
    licencias = _dedup(licencias)
    print(f'{antes} licencias  ·  {len(licencias)} tras dedup')

    cache      = load_cache()
    pendientes = [l for l in licencias if _reg_key(l) not in cache][:args.limit]
    print(f'{len(cache)} ya hechas  ·  {len(pendientes)} en esta tanda  ·  '
          f'{args.workers} Chrome(s) en paralelo')
    if not pendientes:
        print('Nada pendiente.'); return

    if args.fast:
        pausa = {
            'booking_wait' : (1.5, 2.5),
            'bk_to_gt'     : (0.5, 1.0),
            'google_wait'  : (1.5, 2.5),
            'entre_hoteles': (0.5, 1.5),
        }
    else:
        pausa = {
            'booking_wait' : (2.5, 4.0),
            'bk_to_gt'     : (1.0, 2.0),
            'google_wait'  : (2.5, 4.0),
            'entre_hoteles': (1.5, 3.0),
        }

    print(f'Snapshot: {CHECKIN} -> {CHECKOUT}\n')

    stats      = {'n': 0}
    stats_lock = threading.Lock()
    chunks     = [pendientes[i::args.workers] for i in range(args.workers)]
    t0         = time.time()

    hilos = [
        threading.Thread(
            target=_worker,
            args=(chunks[i], cache, args.headless, i+1,
                  pausa, stats, stats_lock, t0),
            daemon=True
        )
        for i in range(args.workers)
    ]
    for h in hilos: h.start()
    for h in hilos: h.join()

    with _cache_lock: save_cache(cache)
    mins  = (time.time() - t0) / 60
    total = stats['n']
    print(f'\nGuardado: {CACHE_FILE}')
    print(f'{len(cache)} en cache  ·  {total} procesados esta tanda')
    print(f'{mins:.1f} min  ·  {mins*60/max(1,total):.1f} s/hotel')

if __name__ == '__main__':
    main()
