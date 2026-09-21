"""
Script suelto para ir a buscar fotos y descripcion completa SOLO de los
anuncios de NegociosEnVenta que YA ESTAN guardados en hoteles_cache.json
(los que se scrapearon antes del arreglo de fotos/descripcion), sin tener
que correr el scraper completo -- que tarda mucho porque pasa por TODOS
los portales (ThinkSpain, LucasFox, Idealista, Milanuncios...), no solo
NegociosEnVenta.

Usa la misma funcion enriquecer_ficha_nv() que ya usa scrape_negociosenventa()
de verdad, y que solo necesita requests (NO hace falta Chrome/driver), asi
que esto va bastante mas rapido.

No toca ningun otro portal ni anuncio -- solo actualiza 'fotos_url' y
'description' de los anuncios con source == "NegociosEnVenta", y guarda
el cache. Los anuncios NUEVOS de NegociosEnVenta (publicados despues del
ultimo scraper.py) seguirian sin aparecer -- para eso hace falta el
scraper completo como siempre.

Uso:  python actualizar_fotos_negociosenventa.py
Luego: python regenerar_web.py   (para subir el cache actualizado a la web)
"""
import random
import time

import requests

import scraper

cache = scraper.load_cache()

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'
})

objetivo = [item for item in cache.values() if item.get('source') == 'NegociosEnVenta']
print(f'Anuncios de NegociosEnVenta en el cache: {len(objetivo)}\n')

actualizados = 0
sin_cambios = 0
ko = 0

for i, item in enumerate(objetivo, 1):
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
        actualizados += 1
        print(f'  [{i}/{len(objetivo)}] OK  {titulo}  ({len(fotos_nuevas)} fotos)')
    elif desc_nueva is None and not fotos_nuevas:
        ko += 1
        print(f'  [{i}/{len(objetivo)}] KO  {titulo}  (ficha no encontrada -- puede estar retirada)')
    else:
        sin_cambios += 1
        print(f'  [{i}/{len(objetivo)}] --  {titulo}  (sin cambios, ya estaba bien)')

    time.sleep(random.uniform(0.4, 0.9))

scraper.save_cache(cache)
print(f'\nActualizados: {actualizados} | Sin cambios: {sin_cambios} | KO (ficha no encontrada): {ko}')
print('hoteles_cache.json guardado.')
print('\nAhora corre:  python regenerar_web.py   para reconstruir index.html y subirlo a GitHub.')
