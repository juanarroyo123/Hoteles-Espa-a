"""
Activa DE VERDAD, en un solo comando, las dos cosas nuevas que hemos
preparado -- sin correr el scraper completo (que pasa por todos los
portales: ThinkSpain, LucasFox, Milanuncios, etc.):

  1) NegociosEnVenta: rellena fotos y descripcion completa de TODOS los
     anuncios que ya tienes en hoteles_cache.json (mismo que hacia
     actualizar_fotos_negociosenventa.py -- no hace falta Chrome).

  2) Idealista Traspasos: scrapea de verdad el link multi-ubicacion (con
     el filtro que descarta agencias inmobiliarias/talleres/tiendas) y
     mete los resultados nuevos en el cache (necesita Chrome stealth).

Guarda hoteles_cache.json al final de cada paso. NO toca ningun otro
portal y NO marca nada como Retirado (eso solo lo hace scraper.py
completo, que revisa todos los portales a la vez -- aqui como solo
tocamos dos fuentes, marcar bajas seria incorrecto).

Uso:  python activar_novedades.py
Luego: python regenerar_web.py   (para construir index.html y subirlo a GitHub)
"""
import random
import time

import requests

import scraper

cache = scraper.load_cache()

# ── 1) NegociosEnVenta: fotos + descripcion completa de lo ya cacheado ──
print('=== 1/2: NegociosEnVenta (fotos + descripcion de lo ya guardado) ===\n')

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'
})

objetivo_nv = [item for item in cache.values() if item.get('source') == 'NegociosEnVenta']
print(f'Anuncios de NegociosEnVenta en el cache: {len(objetivo_nv)}\n')

actualizados_nv = 0
sin_cambios_nv = 0
ko_nv = 0

for i, item in enumerate(objetivo_nv, 1):
    url = item.get('url')
    desc_vieja = item.get('description') or ''
    desc_nueva, fotos_nuevas = scraper.enriquecer_ficha_nv(url, session)

    cambio = False
    if desc_nueva and len(desc_nueva) > len(desc_vieja):
        item['description'] = desc_nueva
        cambio = True
    if fotos_nuevas:
        item['fotos_url'] = fotos_nuevas
        cambio = True

    titulo = (item.get('title') or '')[:55]
    if cambio:
        actualizados_nv += 1
        print(f'  [{i}/{len(objetivo_nv)}] OK  {titulo}  ({len(fotos_nuevas)} fotos)')
    elif desc_nueva is None and not fotos_nuevas:
        ko_nv += 1
        print(f'  [{i}/{len(objetivo_nv)}] KO  {titulo}  (ficha no encontrada -- puede estar retirada)')
    else:
        sin_cambios_nv += 1

    time.sleep(random.uniform(0.4, 0.9))

scraper.save_cache(cache)
print(f'\nNegociosEnVenta -- actualizados: {actualizados_nv} | sin cambios: {sin_cambios_nv} | KO: {ko_nv}')
print('hoteles_cache.json guardado.\n')

# ── 2) Idealista Traspasos: scraping real + merge en el cache ──
print('=== 2/2: Idealista Traspasos (URL multi-ubicacion) ===\n')

scraper.found_listings.clear()
scraper.seen_urls.clear()

driver = scraper.init_driver_stealth()
try:
    scraper.scrape_idealista_traspasos(driver)
finally:
    try:
        driver.quit()
    except Exception:
        pass

nuevos_idt = 0
actualizados_idt = 0
for item in scraper.found_listings:
    url_key = item['url']
    if url_key not in cache:
        cache[url_key] = item
        nuevos_idt += 1
    else:
        cache[url_key]['price'] = item.get('price', cache[url_key].get('price', ''))
        _desc_nueva = item.get('description') or ''
        _desc_vieja = cache[url_key].get('description') or ''
        cache[url_key]['description'] = _desc_nueva if len(_desc_nueva) >= len(_desc_vieja) else _desc_vieja
        cache[url_key]['tipo'] = item.get('tipo', cache[url_key].get('tipo', ''))
        cache[url_key]['ausencias'] = 0
        for _k in ('rooms', 'm2', 'beds', 'bathrooms', 'fotos_url', 'operacion_detectada'):
            if item.get(_k):
                cache[url_key][_k] = item[_k]
        actualizados_idt += 1

scraper.save_cache(cache)
print(f'\nIdealista Traspasos -- encontrados: {len(scraper.found_listings)} | nuevos: {nuevos_idt} | ya existian: {actualizados_idt}')
print(f'hoteles_cache.json guardado: {len(cache)} anuncios totales.')

print('\n=== HECHO. Ahora corre:  python regenerar_web.py   para construir la web y subirla a GitHub. ===')
