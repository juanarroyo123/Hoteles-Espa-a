#!/usr/bin/env python3
"""
Hotel Monitor — Scraper local con cache acumulativo
Portales activos: ThinkSpain, Lucas Fox
"""
import json, re, time, os, subprocess, random
from datetime import date, datetime, timedelta
from html import unescape

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
import requests as req_mod
from bs4 import BeautifulSoup

TODAY      = date.today().strftime('%d/%m/%Y')
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hoteles_cache.json')

HOTEL_KW = ['hotel','hostal','hostel','pensión','pension','aparthotel',
            'posada','parador','fonda','casa rural','alojamiento turístico',
            'albergue','resort','casa de huespedes','bed and breakfast',
            'hotel boutique','boutique hotel','complejo hotelero','negocio hotelero',
            'guesthouse','b&b','inn ','lodge','rural house']

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
    m = re.search(r'hace\s+(\d+)\s+(día|dia|semana|mes|año|ano)', t)
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
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f'Cache cargado: {len(data)} anuncios previos.')
        return {item['url']: item for item in data}
    print('Cache vacío — primera ejecución.')
    return {}

def save_cache(cache_dict):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(cache_dict.values()), f, ensure_ascii=False, indent=2)

# ─── driver ───────────────────────────────────────────
def init_driver():
    print('Iniciando Chrome...')
    opts = uc.ChromeOptions()
    opts.add_argument('--window-size=1920,1080')
    opts.add_argument('--lang=es-ES')
    driver = uc.Chrome(options=opts, version_main=None, use_subprocess=True)
    print('Chrome listo.\n')
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

def add_listing(item):
    url = item.get('url','').strip().split('?')[0].rstrip('/')
    if not url or url in seen_urls: return False
    if not item.get('title') or len(item['title']) < 8: return False
    if es_duplicado(item, found_listings): return False
    seen_urls.add(url)
    item['url']         = url
    item['title']       = item['title'][:120]
    item['description'] = item.get('description','')[:300]
    found_listings.append(item)
    return True

# ══════════════════════════════════════════════════════
# 1. THINKSPAIN — requests + JSON-LD
# ══════════════════════════════════════════════════════
def scrape_thinkspain(driver):
    print('→ ThinkSpain...')
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
        'Referer': 'https://www.thinkspain.com/',
    }
    BASE_URLS = [
        'https://www.thinkspain.com/property-for-sale/hotels',
        'https://www.thinkspain.com/property-for-sale/guest-houses-bed-breakfasts',
        'https://www.thinkspain.com/property-for-sale/andalucia/hotels',
        'https://www.thinkspain.com/property-for-sale/costa-del-sol/hotels',
        'https://www.thinkspain.com/property-for-sale/costa-blanca/hotels',
        'https://www.thinkspain.com/property-for-sale/catalonia/hotels',
        'https://www.thinkspain.com/property-for-sale/balearic-islands/hotels',
        'https://www.thinkspain.com/property-for-sale/canary-islands/hotels',
        'https://www.thinkspain.com/property-for-sale/madrid/hotels',
        'https://www.thinkspain.com/property-for-sale/valencia/hotels',
        'https://www.thinkspain.com/property-for-sale/galicia/hotels',
        'https://www.thinkspain.com/property-for-sale/murcia/hotels',
        'https://www.thinkspain.com/property-for-sale/asturias/hotels',
        'https://www.thinkspain.com/property-for-sale/cantabria/hotels',
        'https://www.thinkspain.com/property-for-sale/castilla-y-leon/hotels',
        'https://www.thinkspain.com/property-for-sale/extremadura/hotels',
        'https://www.thinkspain.com/property-for-sale/aragon/hotels',
        'https://www.thinkspain.com/property-for-sale/basque-country/hotels',
    ]

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

    seen_ts = set()
    total_ts = 0
    for base_url in BASE_URLS:
        region = base_url.split('/')[-1]
        paginas_vacias = 0
        for numpag in range(1, 50):
            url = base_url if numpag == 1 else f'{base_url}?numpag={numpag}'
            try:
                r = req_mod.get(url, headers=HEADERS, timeout=15)
                if r.status_code != 200: break
                soup = BeautifulSoup(r.text, 'lxml')
                enc = 0
                for s in soup.find_all('script', type='application/ld+json'):
                    try:
                        data = json.loads(s.get_text())
                        if data.get('@type') != 'ItemList': continue
                        for item in data.get('itemListElement', []):
                            prod = item.get('item', {})
                            url_a = prod.get('url','').split('?')[0].rstrip('/')
                            if not url_a or url_a in seen_ts: continue
                            name = prod.get('name','')
                            if not name: continue
                            titulo, loc = parsear_titulo_ts(name)
                            precio = extraer_precio_ts(name)
                            seen_ts.add(url_a)
                            added = add_listing({'title': titulo, 'price': precio, 'location': loc,
                                                 'description': clean(prod.get('description','')),
                                                 'url': url_a, 'source': 'ThinkSpain'})
                            if added: enc += 1
                    except: continue
                total_ts += enc
                if enc > 0:
                    print(f'  {region} p{numpag}: {enc} nuevos | Total TS: {total_ts}')
                    paginas_vacias = 0
                else:
                    paginas_vacias += 1
                if paginas_vacias >= 2: break
                time.sleep(0.3)
            except Exception as e:
                print(f'  Error {region} p{numpag}: {e}'); break
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
def limpiar_bajas(cache, urls_encontradas):
    para_eliminar = []
    for url, item in cache.items():
        if url not in urls_encontradas:
            ausencias = item.get('ausencias', 0) + 1
            item['ausencias'] = ausencias
            if ausencias >= 3: para_eliminar.append(url)
        else:
            item['ausencias'] = 0
    for url in para_eliminar: del cache[url]
    if para_eliminar:
        print(f'  Eliminados {len(para_eliminar)} anuncios sin actividad (3+ ejecuciones).')
    return cache

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
        subprocess.run(['git','add','index.html','hoteles_cache.json','index_template.html'], check=True)
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
def scrape_luxuryestate(driver):
    print('\n→ LuxuryEstate...')
    BASE = 'https://www.luxuryestate.com/es/hotels-spain'
    total_le = 0
    paginas_vacias = 0

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
            enc = 0

            for card in cards:
                # URL
                a = card.find('a', href=re.compile(r'/es/p\d+'))
                if not a: continue
                href = a.get('href', '')
                if not href.startswith('http'): href = 'https://www.luxuryestate.com' + href
                href = href.split('?')[0].rstrip('/')
                if href in seen_urls: continue

                # Precio
                price_el = card.find('div', class_=re.compile(r'price'))
                price = clean(price_el.get_text()).replace(' ', '') if price_el else 'Precio a consultar'
                # Normalizar "€480.000" → "480.000 €"
                price = re.sub(r'€\s*([\d.,]+)', r'\1 €', price).strip()

                # Ubicación — buscar texto con "Hotel en X" o "en X, Provincia"
                loc = ''
                loc_el = card.find(string=re.compile(r'\bHotel\b.{2,40}(,|en)\s+[A-ZÁÉÍÓÚÑ]', re.I))
                if loc_el:
                    m = re.search(r'Hotel\s+en\s+(.+?)(?:,\s*Provincia|\s*$)', str(loc_el), re.I)
                    if m: loc = m.group(1).strip()
                if not loc:
                    # Extraer de la URL: p131627604-hotel-for-sale-sietamo → Sietamo
                    m = re.search(r'hotel-for-sale-(.+)$', href)
                    if m: loc = m.group(1).replace('-', ' ').title()

                # Título
                title_el = card.find(['h2','h3','h4'])
                if title_el:
                    title = clean(title_el.get_text())
                else:
                    # Construir desde descripción o nombre URL
                    title = f'Hotel en venta en {loc}' if loc else 'Hotel en venta en España'

                # Descripción
                desc_el = card.find('p')
                description = clean(desc_el.get_text()).replace('~', ' ')[:300] if desc_el else ''

                added = add_listing({
                    'title': title,
                    'price': price,
                    'location': loc or 'España',
                    'description': description,
                    'url': href,
                    'source': 'LuxuryEstate',
                    'date': TODAY
                })
                if added: enc += 1; total_le += 1

            total = len([x for x in found_listings if x['source'] == 'LuxuryEstate'])
            if enc > 0:
                print(f'  p{pagina}: {enc} nuevos | Total LE: {total}')
            time.sleep(1)

        except Exception as e:
            print(f'  Error p{pagina}: {e}')
            break

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
                    description = clean(desc_el.get_text())[:300] if desc_el else ''

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
def scrape_negociosenventa(driver):
    print('\n→ NegociosEnVenta...')
    BASE = 'https://www.negociosenventa.es'
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
                # Precio en li padre
                li = h.find_parent('li')
                price_el = li.find('span', class_='numPrice') if li else None
                price = clean(price_el.get_text()) if price_el else 'Precio a consultar'
                added = add_listing({'title':title,'price':price,'location':loc,
                    'description':description,'url':href,'source':'NegociosEnVenta','date':TODAY})
                if added: total_nv += 1
        except Exception as e:
            print(f'  Error {page_url}: {e}')
    print(f'  NegociosEnVenta TOTAL: {total_nv}')

if __name__ == '__main__':
    print(f'=== Hotel Monitor Local — {TODAY} ===\n')

    cache = load_cache()
    driver = init_driver()

    try:
        try: scrape_thinkspain(driver)
        except Exception as e: print(f'Error ThinkSpain: {e}')

        try: scrape_lucasfox(driver)
        except Exception as e: print(f'Error LucasFox: {e}')

        # Reiniciar Chrome para LuxuryEstate
        try: driver.quit()
        except: pass
        print('\nReiniciando Chrome para LuxuryEstate...')
        driver = init_driver()

        try: scrape_luxuryestate(driver)
        except Exception as e: print(f'Error LuxuryEstate: {e}')

        try: scrape_oirealestate(driver)
        except Exception as e: print(f'Error Oi Real Estate: {e}')

        try: scrape_negociosenventa(driver)
        except Exception as e: print(f'Error NegociosEnVenta: {e}')
    finally:
        try: driver.quit()
        except: pass
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
            cache_nuevo[url_key]['description'] = item.get('description', cache_nuevo[url_key].get('description',''))
            cache_nuevo[url_key]['ausencias']   = 0

    print('\nRevisando bajas...')
    cache_nuevo = limpiar_bajas(cache_nuevo, urls_encontradas)
    save_cache(cache_nuevo)
    print(f'Cache guardado: {len(cache_nuevo)} totales ({nuevos} nuevos).')

    todos = list(cache_nuevo.values())
    def fsort(x):
        try: return datetime.strptime(x.get('date','01/01/2000'), '%d/%m/%Y')
        except: return datetime.min
    todos.sort(key=fsort, reverse=True)

    print(f'\n{"="*50}')
    print(f'TOTAL ANUNCIOS: {len(todos)}')
    print('='*50)

    with open('index_template.html','r',encoding='utf-8') as f:
        template = f.read()
    with open('index.html','w',encoding='utf-8') as f:
        f.write(template.replace('__LISTINGS_JSON__', json.dumps(todos, ensure_ascii=False)))
    print(f'index.html generado con {len(todos)} anuncios.')

    subir_github(len(todos))
    input('\nPresiona Enter para cerrar...')
