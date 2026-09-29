#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
retag_milanuncios_traspasos.py -- Vuelve a correr Milanuncios entero (las 5
fuentes, incluida la de traspasos) para que los anuncios de la categoria
"/traspasos-de-hostales-y-hoteles/" que YA tenias en el cache se corrijan
ya con 'operacion_detectada':'traspaso' en vez de esperar a la proxima
pasada automatica del robot (que ya lo haria sola, esto es solo para
verlo hoy mismo).

A diferencia de los agregar_*.py (que solo AÑADEN anuncios nuevos y
saltan los que ya existen), este ACTUALIZA los que ya tienes -- por eso
hace falta repetir aqui el mismo paso de fusion que usa scraper.py, no
solo el 'añadir'.

OJO: esto vuelve a mirar las 5 fuentes de Milanuncios enteras (462+
anuncios), asi que tarda varios minutos y abre una ventana de Chrome
(modo stealth). No mete anuncios "nuevos" que ganar -- es solo para
corregir la etiqueta de Operacion de los que ya estan.

Uso (desde C:\\HotelMonitor):
    python retag_milanuncios_traspasos.py
    python regenerar_web.py      <- para que se vea en la web y se suba
"""
import json
import os

import scraper

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, 'hoteles_cache.json')


def main():
    print('Cargando hoteles_cache.json actual...')
    with open(CACHE_FILE, 'r', encoding='utf-8') as f:
        cache_data = json.load(f)
    cache = {item['url']: item for item in cache_data}
    print(f'  {len(cache)} anuncios ya en el cache.')

    scraper.found_listings.clear()
    scraper.seen_urls.clear()  # OJO: a proposito SIN precargar del cache, igual que hace scraper.py -- para que Milanuncios se re-visite entero y se puedan corregir los que ya existen

    driver = scraper.init_driver_stealth()
    try:
        scraper.scrape_milanuncios(driver)
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    nuevos = 0
    actualizados = 0
    for item in scraper.found_listings:
        url_key = item['url']
        if url_key not in cache:
            cache[url_key] = item
            nuevos += 1
        else:
            antes = cache[url_key].get('operacion_detectada')
            cache[url_key]['price'] = item.get('price', cache[url_key].get('price', ''))
            _desc_nueva = item.get('description') or ''
            _desc_vieja = cache[url_key].get('description') or ''
            cache[url_key]['description'] = _desc_nueva if len(_desc_nueva) >= len(_desc_vieja) else _desc_vieja
            cache[url_key]['tipo'] = item.get('tipo', cache[url_key].get('tipo', ''))
            cache[url_key]['ausencias'] = 0
            for _k in ('rooms', 'm2', 'beds', 'bathrooms', 'fotos_url', 'operacion_detectada'):
                if item.get(_k):
                    cache[url_key][_k] = item[_k]
            if cache[url_key].get('operacion_detectada') != antes:
                actualizados += 1

    print(f'\n{nuevos} anuncios nuevos, {actualizados} anuncios existentes corregidos a Traspaso.')

    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(cache.values()), f, ensure_ascii=False, indent=1)
    print(f'hoteles_cache.json guardado: {len(cache)} anuncios totales.')
    print('\nAhora corre:  python regenerar_web.py')


if __name__ == '__main__':
    main()
