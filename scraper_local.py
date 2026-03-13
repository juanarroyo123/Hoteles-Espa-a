#!/usr/bin/env python3
"""
Hotel Monitor — Scraper máximo con cache acumulativo y sistema de baja
"""
import json, re, time, os, subprocess
from datetime import date, datetime, timedelta
from html import unescape

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

TODAY      = date.today().strftime('%d/%m/%Y')
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hoteles_cache.json')

HOTEL_KW = ['hotel','hostal','hostel','pensión','pension','aparthotel',
            'posada','parador','fonda','casa rural','alojamiento turístico',
            'albergue','resort','casa de huespedes','bed and breakfast',
            'hotel boutique','boutique hotel','complejo hotelero','negocio hotelero',
            'guesthouse','b&b','inn ','lodge','rural house']

# Títulos/páginas a descartar aunque tengan keyword de hotel
SPAM_KW = ['404', 'página no encontrada', 'page not found', 'property for sale',
           'property for rent', 'i want to advertise', 'advertise on think',
           'sign up', 'register', 'login', 'cookie', 'privacy policy',
           'terms of use', 'contact us', 'about us']

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
        'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,
        'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12,
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
                'acceptAllButton','accept-cookies','CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll']:
        try: driver.find_element(By.ID, bid).click(); time.sleep(0.3); return
        except: pass
    for txt in ['Aceptar todo','Aceptar todas','Aceptar','Accept all','Acceptar','Entendido']:
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

# ─── obtener fecha real ───────────────────────────────
def get_fecha_real(driver, url, source):
    try:
        html = get_page(driver, url, wait=2)
        if not html: return TODAY
        soup = BeautifulSoup(html, 'lxml')
        if 'idealista' in url:
            for el in soup.find_all(['p','span','div','time']):
                txt = clean(el.get_text())
                if re.search(r'publicad[oa]\s+(el\s+)?\d', txt, re.I):
                    return parsear_fecha(txt)
            for el in soup.find_all(attrs={'data-date': True}):
                return parsear_fecha(el['data-date'])
        if 'thinkspain' in url:
            for el in soup.find_all(['span','p','div','time']):
                txt = clean(el.get_text())
                if re.search(r'(listed|added|posted|publicad|fecha)[\s:]+', txt, re.I):
                    return parsear_fecha(txt)
        if 'kyero' in url:
            el = soup.find(class_=re.compile('listing-date|date-added|property-date'))
            if el: return parsear_fecha(clean(el.get_text()))
        if 'fotocasa' in url:
            el = soup.find(class_=re.compile('re-Card-date|publicationDate|date'))
            if el: return parsear_fecha(clean(el.get_text()))
        time_el = soup.find('time')
        if time_el:
            dt = time_el.get('datetime') or clean(time_el.get_text())
            return parsear_fecha(dt)
        body = soup.get_text(' ')
        for patron in [
            r'publicad[oa]\s+(?:el\s+)?(\d{1,2}\s+de\s+[a-záéíóúñ]+(?:\s+de\s+\d{4})?)',
            r'(hace\s+\d+\s+(?:día|dia|semana|mes|año)[s]?)',
            r'(\d{1,2}\s+de\s+[a-záéíóúñ]+\s+(?:de\s+)?\d{4})',
            r'(\d{4}-\d{2}-\d{2})',
        ]:
            m = re.search(patron, body, re.I)
            if m: return parsear_fecha(m.group(1))
    except: pass
    return TODAY

# ─── listings ─────────────────────────────────────────
found_listings = []
seen_urls = set()

def add_listing(item):
    url = item.get('url','').strip().split('?')[0].rstrip('/')
    if not url or url in seen_urls: return False
    if not item.get('title') or len(item['title']) < 8: return False
    seen_urls.add(url)
    item['url']         = url
    item['title']       = item['title'][:120]
    item['description'] = item.get('description','')[:300]
    found_listings.append(item)
    return True

# ══════════════════════════════════════════════════════
# 1. THINKSPAIN — requests + JSON-LD, sin Selenium, rápido y completo
# ══════════════════════════════════════════════════════
def scrape_thinkspain(driver):
    """ThinkSpain via requests + JSON-LD — no necesita Selenium"""
    import requests as req_mod
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
        # 1. Quitar precio del inicio (ej: "6.900.000 € Hotel en venta...")
        t = re.sub(r'^[\d][\d.,]*\s*€\s*', '', name).strip()
        t = re.sub(r'^€\s*[\d][\d.,]*\s*', '', t).strip()
        # 2. Quitar ref y sufijos de precio
        t = re.sub(r'\s*\(Ref:.*?\)', '', t)
        t = re.sub(r'\s*-\s*€.*', '', t).strip()
        # 3. Quitar título duplicado (ThinkSpain repite "Hotel en X Hotel en X")
        words = t.split()
        if len(words) >= 8:
            mid = len(words) // 2
            p1 = ' '.join(words[:mid])
            p2 = ' '.join(words[mid:])
            if p1.lower()[:20] == p2.lower()[:20]:
                t = p1
        # 4. Traducir campos en inglés
        t = re.sub(r'\bfor sale\b', 'en venta', t, flags=re.IGNORECASE)
        t = re.sub(r'(\d+)\s+bedroom\s+', r'\1 habitaciones ', t, flags=re.IGNORECASE)
        t = t.strip()
        # 5. Extraer localización
        m = re.search(r'(?:en venta en|in)\s+(.+?)(?:\s+Hotel|\s+Guesthouse|$)', t, re.IGNORECASE)
        if m:
            loc = m.group(1).strip().rstrip(',').strip()
        else:
            m2 = re.search(r'in\s+(.+)$', t, re.IGNORECASE)
            loc = m2.group(1).strip() if m2 else 'España'
        return t, loc

    def extraer_precio_ts(name):
        # Precio suele estar al inicio: "6.900.000 € Hotel..."
        m = re.search(r'^([\d][\d.,]+)\s*€', name.strip())
        if m:
            return m.group(1) + ' €'
        m = re.search(r'€\s*([\d][\d.,]+)', name)
        if m:
            return m.group(1) + ' €'
        m = re.search(r'([\d][\d.,]+)\s*€', name)
        if m:
            return m.group(1) + ' €'
        return 'Precio a consultar'

    seen_urls = set()
    total_ts = 0

    for base_url in BASE_URLS:
        region = base_url.split('/')[-1]
        paginas_vacias = 0
        for numpag in range(1, 50):
            url = base_url if numpag == 1 else f'{base_url}?numpag={numpag}'
            try:
                r = req_mod.get(url, headers=HEADERS, timeout=15)
                if r.status_code != 200:
                    break
                soup = BeautifulSoup(r.text, 'lxml')
                enc = 0
                for s in soup.find_all('script', type='application/ld+json'):
                    try:
                        data = json.loads(s.get_text())
                        if data.get('@type') != 'ItemList': continue
                        for item in data.get('itemListElement', []):
                            prod = item.get('item', {})
                            url_anuncio = prod.get('url','').split('?')[0].rstrip('/')
                            if not url_anuncio or url_anuncio in seen_urls: continue
                            name = prod.get('name','')
                            if not name: continue
                            titulo, loc = parsear_titulo_ts(name)
                            precio = extraer_precio_ts(name)
                            desc = clean(prod.get('description',''))
                            seen_urls.add(url_anuncio)
                            added = add_listing({
                                'title': titulo,
                                'price': precio,
                                'location': loc,
                                'description': desc,
                                'url': url_anuncio,
                                'source': 'ThinkSpain'
                            })
                            if added: enc += 1
                    except Exception:
                        continue
                total_ts += enc
                if enc > 0:
                    print(f'  {region} p{numpag}: {enc} nuevos | Total TS: {total_ts}')
                    paginas_vacias = 0
                else:
                    paginas_vacias += 1
                if paginas_vacias >= 2: break
                time.sleep(0.3)
            except Exception as e:
                print(f'  Error {region} p{numpag}: {e}')
                break


# ══════════════════════════════════════════════════════
# 2. IDEALISTA — URLs nacionales directas (rápido)
# ══════════════════════════════════════════════════════
def scrape_idealista(driver):
    print('\n→ Idealista...')
    # URLs nacionales: evita iterar provincias, va directo a toda España
    bases_nacionales = [
        'https://www.idealista.com/venta-locales/con-hotel/',
        'https://www.idealista.com/venta-locales/con-hotel-rural/',
        'https://www.idealista.com/venta-locales/con-hostal/',
        'https://www.idealista.com/venta-locales/con-pension/',
        'https://www.idealista.com/venta-locales/con-aparthotel/',
        'https://www.idealista.com/venta-locales/con-alojamiento-turistico/',
    ]
    for base in bases_nacionales:
        tipo = base.rstrip('/').split('con-')[-1]
        for pagina in range(1, 15):
            url = base if pagina == 1 else f'{base}pagina-{pagina}.htm'
            html = get_page(driver, url, wait=2)
            if not html: break
            soup = BeautifulSoup(html, 'lxml')
            if soup.find(string=re.compile('no hemos encontrado|sin resultados|0 locales', re.I)):
                break
            arts = soup.find_all('article', class_=re.compile('item'))
            if not arts: break
            enc = 0
            for art in arts:
                title_a  = art.find('a', class_='item-link')
                price_el = art.find(class_=re.compile('price'))
                desc_el  = art.find(class_=re.compile('item-description|description'))
                loc_el   = art.find(class_=re.compile('item-detail-location|location'))
                if not title_a: continue
                title = clean(title_a.get('title') or title_a.get_text())
                if len(title) < 8: continue
                href = title_a.get('href','')
                if href.startswith('/'): href = 'https://www.idealista.com' + href
                # Extraer ubicación del título o elemento
                loc = ''
                if loc_el: loc = clean(loc_el.get_text())
                elif ',' in title:
                    parts = title.split(',')
                    loc = parts[-1].strip() if len(parts) > 1 else 'España'
                added = add_listing({
                    'title':       title,
                    'price':       clean(price_el.get_text()) if price_el else 'Precio a consultar',
                    'location':    loc or 'España',
                    'description': clean(desc_el.get_text()) if desc_el else '',
                    'url':         href or url,
                    'source':      'Idealista'
                })
                if added: enc += 1
            total = len([x for x in found_listings if x['source']=='Idealista'])
            print(f'  {tipo} p{pagina}: {enc} nuevos | Total Idealista: {total}')
            if enc == 0: break
            time.sleep(0.8)

# ══════════════════════════════════════════════════════
# 3. KYERO — arreglado con scroll y múltiples URLs
# ══════════════════════════════════════════════════════
def scrape_kyero(driver):
    print('\n→ Kyero...')
    bases = [
        'https://www.kyero.com/es/hoteles-en-venta-en-espana',
        'https://www.kyero.com/es/hoteles-en-venta',
        'https://www.kyero.com/es/negocios-en-venta/espana',
    ]
    seen_this = set()
    for base in bases:
        for pagina in range(1, 20):
            url = base if pagina == 1 else f'{base}?p={pagina}'
            html = get_page(driver, url, wait=4)
            if not html: break
            # Scroll para cargar lazy-load
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2)")
            time.sleep(0.3)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(0.3)
            soup = BeautifulSoup(driver.page_source, 'lxml')
            # Kyero: buscar JSON-LD primero
            for script in soup.find_all('script', type='application/ld+json'):
                try:
                    data = json.loads(script.string or '')
                    items = data if isinstance(data, list) else data.get('itemListElement', [data])
                    for it in items:
                        if not isinstance(it, dict): continue
                        item = it.get('item', it)
                        name = item.get('name','')
                        if not name or not es_hotel(name): continue
                        price_info = item.get('offers',{})
                        price = f"{price_info.get('price','')} {price_info.get('priceCurrency','€')}".strip() if price_info else 'Precio a consultar'
                        addr = item.get('address',{})
                        loc = addr.get('addressLocality') or addr.get('addressRegion') or 'España'
                        link = item.get('url','').split('?')[0]
                        if link and link not in seen_this:
                            seen_this.add(link)
                            add_listing({'title':clean(name),'price':price,'location':clean(loc),'description':clean(item.get('description','')),'url':link,'source':'Kyero'})
                except: pass
            # HTML cards
            cards = (soup.find_all('article') or
                     soup.find_all('li', class_=re.compile(r'property|listing|result', re.I)) or
                     soup.find_all('div', class_=re.compile(r'property-card|listing-card|PropertyCard', re.I)))
            enc = 0
            for card in cards:
                title_el = card.find(['h2','h3','h4','h1'])
                price_el = card.find(class_=re.compile(r'price', re.I))
                loc_el   = card.find(class_=re.compile(r'location|town|area|city|municipality', re.I))
                a_el     = card.find('a', href=True)
                if not title_el: continue
                title = clean(title_el.get_text())
                if len(title) < 8 or not es_hotel(title): continue
                href = a_el['href'] if a_el else ''
                if href.startswith('/'): href = 'https://www.kyero.com' + href
                href_clean = href.split('?')[0]
                if href_clean in seen_this: continue
                if href_clean: seen_this.add(href_clean)
                added = add_listing({'title':title,'price':clean(price_el.get_text()) if price_el else 'Precio a consultar','location':clean(loc_el.get_text()) if loc_el else 'España','description':'','url':href or url,'source':'Kyero'})
                if added: enc += 1
            total = len([x for x in found_listings if x['source']=='Kyero'])
            if enc > 0: print(f'  Kyero p{pagina}: {enc} | Total: {total}')
            if enc == 0 and pagina > 1: break
            time.sleep(0.8)

# ══════════════════════════════════════════════════════
# 4. FOTOCASA — mejorado
# ══════════════════════════════════════════════════════
def scrape_fotocasa(driver):
    print('\n→ Fotocasa...')
    bases = [
        'https://www.fotocasa.es/es/comprar/hoteles/toda-espana/l',
        'https://www.fotocasa.es/es/comprar/hoteles/toda-espana/l?order=publication-desc',
    ]
    seen_this = set()
    for base in bases:
        for pagina in range(1, 15):
            url = f'{base}&page={pagina}' if pagina > 1 else base
            html = get_page(driver, url, wait=4)
            if not html: break
            # Scroll
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2)"); time.sleep(0.3)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight)"); time.sleep(0.3)
            soup = BeautifulSoup(driver.page_source, 'lxml')
            # Buscar en JSON embebido de Next.js
            for script in soup.find_all('script'):
                txt = script.string or ''
                if '__NEXT_DATA__' in txt or 'initialState' in txt or 'listings' in txt.lower():
                    try:
                        # Extraer JSON de window.__NEXT_DATA__
                        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', str(script.parent), re.DOTALL)
                        if m:
                            data = json.loads(m.group(1))
                            props = data.get('props',{}).get('pageProps',{})
                            items = (props.get('initialProps',{}).get('listings',[]) or
                                     props.get('listings',[]) or
                                     props.get('result',{}).get('items',[]))
                            for item in items:
                                title = item.get('title') or item.get('name','')
                                if not title or not es_hotel(title): continue
                                price = str(item.get('price',{}).get('value','') or item.get('price','') or 'Precio a consultar')
                                if price and price != 'Precio a consultar': price += ' €'
                                addr = item.get('address',{}) or {}
                                loc = addr.get('municipality') or addr.get('province') or 'España'
                                link = 'https://www.fotocasa.es' + (item.get('url') or item.get('link',''))
                                href_clean = link.split('?')[0]
                                if href_clean in seen_this: continue
                                seen_this.add(href_clean)
                                add_listing({'title':clean(title),'price':clean(price),'location':clean(loc),'description':clean(item.get('description','')),'url':href_clean,'source':'Fotocasa'})
                    except: pass
            # HTML cards
            cards = (soup.find_all(class_=re.compile(r're-Card\b', re.I)) or
                     soup.find_all('article') or
                     soup.find_all('li', class_=re.compile(r'listing|result|property', re.I)))
            enc = 0
            for card in cards:
                title_el = (card.find(class_=re.compile(r're-Card-title|CardTitle', re.I)) or
                            card.find(['h2','h3','h4']))
                price_el = card.find(class_=re.compile(r're-Card-price|CardPrice|price', re.I))
                loc_el   = card.find(class_=re.compile(r're-Card-location|CardLocation|location', re.I))
                a_el     = card.find('a', href=True)
                if not title_el: continue
                title = clean(title_el.get_text())
                if len(title) < 8 or not es_hotel(title): continue
                href = a_el['href'] if a_el else ''
                if href.startswith('/'): href = 'https://www.fotocasa.es' + href
                href_clean = href.split('?')[0]
                if href_clean in seen_this: continue
                seen_this.add(href_clean)
                added = add_listing({'title':title,'price':clean(price_el.get_text()) if price_el else 'Precio a consultar','location':clean(loc_el.get_text()) if loc_el else 'España','description':'','url':href_clean or url,'source':'Fotocasa'})
                if added: enc += 1
            total = len([x for x in found_listings if x['source']=='Fotocasa'])
            if enc > 0: print(f'  Fotocasa p{pagina}: {enc} | Total: {total}')
            if enc == 0 and pagina > 1: break
            time.sleep(0.3)

# ══════════════════════════════════════════════════════
# 5. HABITACLIA — hoteles Catalunya y España
# ══════════════════════════════════════════════════════
def scrape_habitaclia(driver):
    print('\n→ Habitaclia...')
    bases = [
        'https://www.habitaclia.com/venta-hotel-en-espana.htm',
        'https://www.habitaclia.com/venta-hostal-en-espana.htm',
        'https://www.habitaclia.com/venta-pension-en-espana.htm',
    ]
    seen_this = set()
    for base in bases:
        for pagina in range(1, 15):
            url = base if pagina == 1 else re.sub(r'\.htm$', f'-{pagina}.htm', base)
            html = get_page(driver, url, wait=3)
            if not html: break
            soup = BeautifulSoup(html, 'lxml')
            cards = (soup.find_all('article') or
                     soup.find_all(class_=re.compile(r'list-item|property|result', re.I)))
            if not cards: break
            enc = 0
            for card in cards:
                title_el = card.find(['h2','h3','h4']) or card.find(class_=re.compile(r'title|name', re.I))
                price_el = card.find(class_=re.compile(r'price|precio', re.I))
                loc_el   = card.find(class_=re.compile(r'location|zona|area|town', re.I))
                a_el     = card.find('a', href=True)
                if not title_el: continue
                title = clean(title_el.get_text())
                if len(title) < 8: continue
                href = a_el['href'] if a_el else ''
                if href.startswith('/'): href = 'https://www.habitaclia.com' + href
                if not href.startswith('http'): href = 'https://www.habitaclia.com/' + href
                href_clean = href.split('?')[0]
                if href_clean in seen_this: continue
                seen_this.add(href_clean)
                added = add_listing({'title':title,'price':clean(price_el.get_text()) if price_el else 'Precio a consultar','location':clean(loc_el.get_text()) if loc_el else 'España','description':'','url':href_clean or url,'source':'Habitaclia'})
                if added: enc += 1
            total = len([x for x in found_listings if x['source']=='Habitaclia'])
            if enc > 0: print(f'  Habitaclia {base.split("-")[1]} p{pagina}: {enc} | Total: {total}')
            if enc == 0 and pagina > 1: break
            time.sleep(0.8)

# ══════════════════════════════════════════════════════
# 6. ENGEL & VÖLKERS — hoteles España
# ══════════════════════════════════════════════════════
def scrape_engelvoelkers(driver):
    print('\n→ Engel & Völkers...')
    urls = [
        'https://www.engelvoelkers.com/es-es/search/?q=hotel&geoCodeId=&sortOrder=DESC&sortField=sortPrice&pageIndex=0&businessArea=residential&wohnflaeche_von=&wohnflaeche_bis=&zimmer_von=&zimmer_bis=&kaufpreis_von=&kaufpreis_bis=&country=ESP&propertytype=Hotel',
        'https://www.engelvoelkers.com/es-es/search/?q=hotel+en+venta&country=ESP&businessArea=commercial',
    ]
    seen_this = set()
    for url in urls:
        for pagina in range(0, 10):
            paged = url.replace('pageIndex=0', f'pageIndex={pagina}')
            html = get_page(driver, paged, wait=4)
            if not html: break
            soup = BeautifulSoup(html, 'lxml')
            cards = (soup.find_all(class_=re.compile(r'property-card|result-card|ev-property', re.I)) or
                     soup.find_all('article'))
            if not cards: break
            enc = 0
            for card in cards:
                title_el = card.find(['h2','h3','h4']) or card.find(class_=re.compile(r'title|name', re.I))
                price_el = card.find(class_=re.compile(r'price|precio', re.I))
                loc_el   = card.find(class_=re.compile(r'location|place|city', re.I))
                a_el     = card.find('a', href=True)
                if not title_el: continue
                title = clean(title_el.get_text())
                if len(title) < 8 or not es_hotel(title): continue
                href = a_el['href'] if a_el else ''
                if href.startswith('/'): href = 'https://www.engelvoelkers.com' + href
                href_clean = href.split('?')[0]
                if href_clean in seen_this: continue
                seen_this.add(href_clean)
                added = add_listing({'title':title,'price':clean(price_el.get_text()) if price_el else 'Precio a consultar','location':clean(loc_el.get_text()) if loc_el else 'España','description':'','url':href_clean or paged,'source':'Engel & Völkers'})
                if added: enc += 1
            total = len([x for x in found_listings if x['source']=='Engel & Völkers'])
            if enc > 0: print(f'  E&V p{pagina}: {enc} | Total: {total}')
            if enc == 0 and pagina > 0: break
            time.sleep(0.3)

# ══════════════════════════════════════════════════════
# 7. LUCAS FOX — hoteles lujo
# ══════════════════════════════════════════════════════
def scrape_lucasfox(driver):
    print('\n→ Lucas Fox...')
    urls = [
        'https://www.lucasfox.es/es/comprar/hoteles-en-venta/',
        'https://www.lucasfox.es/es/propiedades/?tipo=hotel&pais=espana',
    ]
    seen_this = set()
    for url in urls:
        html = get_page(driver, url, wait=3)
        if not html: continue
        soup = BeautifulSoup(html, 'lxml')
        links = [a['href'] for a in soup.find_all('a', href=True)
                 if '/es/propiedades/' in a['href'] or '/es/comprar/' in a['href']]
        for href in list(set(links))[:40]:
            if not href.startswith('http'): href = 'https://www.lucasfox.es' + href
            href_clean = href.split('?')[0]
            if href_clean in seen_this: continue
            seen_this.add(href_clean)
            detail_html = get_page(driver, href, wait=2)
            if not detail_html: continue
            if not es_hotel(detail_html[:3000]): continue
            dsoup = BeautifulSoup(detail_html, 'lxml')
            title_el = dsoup.find('h1')
            price_el = dsoup.find(class_=re.compile(r'price|precio', re.I))
            loc_el   = dsoup.find(class_=re.compile(r'location|ubicacion|city', re.I))
            if not title_el: continue
            title = clean(title_el.get_text())
            if len(title) < 8: continue
            add_listing({'title':title,'price':clean(price_el.get_text()) if price_el else 'Precio a consultar','location':clean(loc_el.get_text()) if loc_el else 'España','description':'','url':href_clean,'source':'Lucas Fox'})
            time.sleep(0.3)
    total = len([x for x in found_listings if x['source']=='Lucas Fox'])
    print(f'  Lucas Fox total: {total}')

# ══════════════════════════════════════════════════════
# enriquecer fechas solo para anuncios nuevos
# ══════════════════════════════════════════════════════
def enriquecer_fechas(driver, cache):
    nuevos = [x for x in found_listings if x['url'] not in cache]
    en_cache = [x for x in found_listings if x['url'] in cache]
    print(f'\nAnuncios nuevos: {len(nuevos)} | En cache (conservan fecha): {len(en_cache)}')
    for i, item in enumerate(nuevos, 1):
        print(f'  Fecha {i}/{len(nuevos)}: {item["title"][:50]}...')
        item['date'] = get_fecha_real(driver, item['url'], item['source'])
        time.sleep(0.3)
    for item in en_cache:
        item['date'] = cache[item['url']].get('date', TODAY)

# ══════════════════════════════════════════════════════
# sistema de baja — eliminar anuncios que ya no existen
# ══════════════════════════════════════════════════════
def limpiar_bajas(cache, urls_encontradas):
    """
    Si un anuncio del cache no se ha encontrado en esta ejecución,
    incrementa su contador de ausencias. Si lleva 3 ejecuciones sin
    aparecer, se elimina del cache.
    """
    bajas = 0
    para_eliminar = []
    for url, item in cache.items():
        if url not in urls_encontradas:
            ausencias = item.get('ausencias', 0) + 1
            item['ausencias'] = ausencias
            if ausencias >= 3:
                para_eliminar.append(url)
                bajas += 1
        else:
            item['ausencias'] = 0  # resetear si vuelve a aparecer
    for url in para_eliminar:
        del cache[url]
    if bajas > 0:
        print(f'  Eliminados {bajas} anuncios que llevan 3+ ejecuciones sin aparecer.')
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
        print('Sube manualmente: git add index.html && git commit -m "manual" && git push origin main')

# ══════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════
if __name__ == '__main__':
    print(f'=== Hotel Monitor — {TODAY} ===\n')

    cache = load_cache()
    driver = init_driver()

    try:
        scrape_thinkspain(driver)
        scrape_idealista(driver)
        scrape_kyero(driver)
        scrape_fotocasa(driver)
        scrape_habitaclia(driver)
        scrape_engelvoelkers(driver)
        scrape_lucasfox(driver)
        enriquecer_fechas(driver, cache)
    finally:
        driver.quit()
        print('\nNavegador cerrado.')

    # Merge con cache
    urls_encontradas = {item['url'] for item in found_listings}
    cache_nuevo = dict(cache)
    nuevos_añadidos = 0
    for item in found_listings:
        url_key = item['url']
        if url_key not in cache_nuevo:
            cache_nuevo[url_key] = item
            nuevos_añadidos += 1
        else:
            # Actualizar precio y descripción, conservar fecha original
            cache_nuevo[url_key]['price']       = item.get('price', cache_nuevo[url_key].get('price',''))
            cache_nuevo[url_key]['description'] = item.get('description', cache_nuevo[url_key].get('description',''))
            cache_nuevo[url_key]['ausencias']   = 0

    # Sistema de baja
    print('\nRevisando bajas...')
    cache_nuevo = limpiar_bajas(cache_nuevo, urls_encontradas)

    save_cache(cache_nuevo)
    print(f'Cache guardado: {len(cache_nuevo)} totales ({nuevos_añadidos} nuevos añadidos).')

    # Ordenar por fecha más reciente
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
