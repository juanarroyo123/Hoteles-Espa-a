# Prueba rapida y aislada (NO toca el cache ni la web) para comprobar que
# la descripcion completa EN ESPAÑOL y las fotos de ThinkSpain se sacan bien
# antes de que el scraper de verdad las use.
import re
import scraper

urls_prueba = [
    'https://www.thinkspain.com/property-for-sale/9383731',
]

session = scraper.req_mod.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
    'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
    'Referer': 'https://www.thinkspain.com/property-for-sale',
})

for url in urls_prueba:
    print('=' * 70)
    print('URL:', url)
    r = session.get(url, timeout=20)
    r.encoding = 'utf-8'
    print('status pagina ficha:', r.status_code, '| tamaño html:', len(r.text))
    if r.status_code != 200:
        continue

    soup = scraper.BeautifulSoup(r.text, 'lxml')
    desc_el = soup.find('p', class_='property-description')
    desc_en = scraper.clean_desc(desc_el) if desc_el else ''
    print('\n--- DESCRIPCION EN INGLES (la que viene por defecto en la ficha) ---')
    print('longitud:', len(desc_en))

    m_id = re.search(r'/property-for-sale/(\d+)', url)
    desc_es = ''
    if m_id:
        r_es = session.get(
            'https://www.thinkspain.com/load-property-description',
            params={'id': m_id.group(1), 'requestedLanguage': 'es', 'preview': '0'},
            headers={'X-Requested-With': 'XMLHttpRequest'},
            timeout=15,
        )
        print('status traduccion es:', r_es.status_code)
        if r_es.status_code == 200:
            data_es = r_es.json()
            print('success:', data_es.get('success'))
            if data_es.get('success') and data_es.get('content'):
                soup_es = scraper.BeautifulSoup(data_es['content'], 'lxml')
                desc_es_el = soup_es.find('p', class_='property-description')
                desc_es = scraper.clean_desc(desc_es_el) if desc_es_el else ''

    print('\n--- DESCRIPCION EN ESPAÑOL (la que va a usar el scraper) ---')
    print('longitud:', len(desc_es))
    print(desc_es)

    fotos = []
    for img in soup.select('div.twc__property--slider-primary img'):
        src = img.get('src') or ''
        if not src or src.startswith('data:'):
            src = img.get('data-src') or ''
        if src and src.startswith('http') and src not in fotos:
            fotos.append(src)
    print('\n--- FOTOS ---')
    print('encontradas:', len(fotos))
    for f in fotos:
        print(' -', f)

print('\n' + '=' * 70)
print('Si la descripcion en español sale completa (sin "..." al final) y con acentos bien, y las fotos tienen URL real (cdn.thinkwebcontent.com), esta funcionando bien.')
