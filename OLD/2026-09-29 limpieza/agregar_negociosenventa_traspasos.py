#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agregar_negociosenventa_traspasos.py -- Corre SOLO los traspasos de
NegociosEnVenta (hoteles + hostales-pensiones, unos 29 anuncios, un par de
minutos) y mete lo que encuentre en hoteles_cache.json, sin tener que
lanzar el scraper.py completo (que tarda 20-40 min y repasa 20 portales).

Es un empujon puntual para verlo ya en la web hoy mismo. A partir de manana,
como la llamada a scrape_negociosenventa_traspasos() ya esta activada
dentro de scraper.py, la pasada diaria normal se encarga sola de
mantenerlo actualizado (nuevos anuncios, precios que cambian, etc.) -- este
script puntual ya no hara falta usarlo mas.

OJO: esta funcion SI necesita un navegador (usa get_page(driver, ...)) --
a diferencia de Inmo Olaya/EcoUrbanizacion, que solo usaban requests.
Vera abrirse una ventana de Chrome mientras corre.

Uso (desde C:\\HotelMonitor):
    python agregar_negociosenventa_traspasos.py
    python regenerar_web.py      <- para que se vea en la web y se suba
"""
import json
import os
import re

import scraper

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, 'hoteles_cache.json')

_ROOMS_RE = re.compile(r'(\d{1,4})\s*(?:habitaciones|habitacion|habs?\b|dormitorios|rooms?|bedrooms?|llaves|quartos?)', re.I)
_M2_RE = re.compile(r'(?<![a-zA-Z])([\d][\d.,\xa0]*)\s*m\s*(?:\u00b2|2)(?![a-z0-9])', re.I)


def main():
    print('Cargando hoteles_cache.json actual...')
    with open(CACHE_FILE, 'r', encoding='utf-8') as f:
        cache_data = json.load(f)
    cache = {item['url']: item for item in cache_data}
    print(f'  {len(cache)} anuncios ya en el cache.')

    # Para que add_listing() no vuelva a anadir nada que ya tengamos
    # (por si se corre este script mas de una vez).
    scraper.found_listings.clear()
    scraper.seen_urls.clear()
    scraper.seen_urls.update(cache.keys())

    driver = scraper.init_driver()
    try:
        scraper.scrape_negociosenventa_traspasos(driver)
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    nuevos = 0
    for item in scraper.found_listings:
        url = item['url']
        if url in cache:
            continue  # de sobra, seen_urls ya deberia haberlo evitado

        # Mismo backfill de habitaciones/m2 que hace scraper.py para
        # TODOS los anuncios del cache -- asi sale completo desde ya,
        # sin tener que esperar a la proxima pasada completa.
        if not item.get('rooms'):
            _blob = (item.get('title', '') or '') + ' ' + (item.get('description', '') or '')
            _m = _ROOMS_RE.search(_blob)
            if _m:
                _rv = int(_m.group(1))
                if 1 <= _rv <= 2000:
                    item['rooms'] = _rv
        if not item.get('m2'):
            _mm = None
            for _fuente in (item.get('description', '') or '', item.get('title', '') or ''):
                _mm = _M2_RE.search(_fuente)
                if _mm:
                    break
            if _mm:
                try:
                    item['m2'] = int(float(_mm.group(1).replace('.', '').replace(',', '.').replace('\xa0', '')))
                except ValueError:
                    pass

        item['ausencias'] = 0
        cache[url] = item
        nuevos += 1

    print(f'\n{nuevos} anuncios nuevos de NegociosEnVenta (traspasos) anadidos al cache.')

    if nuevos:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(list(cache.values()), f, ensure_ascii=False, indent=1)
        print(f'hoteles_cache.json guardado: {len(cache)} anuncios totales.')
        print('\nAhora corre:  python regenerar_web.py')
    else:
        print('No se guardo nada (no habia anuncios nuevos que anadir).')


if __name__ == '__main__':
    main()
