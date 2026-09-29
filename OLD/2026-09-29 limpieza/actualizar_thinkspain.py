#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
actualizar_thinkspain.py -- Vuelve a pasar SOLO por ThinkSpain (no por los
otros 19 portales) y ACTUALIZA en hoteles_cache.json la descripcion completa
y las fotos de los anuncios que ya teniamos, ademas de anadir los que sean
nuevos. Sirve para no tener que esperar al scraper.py completo (20-40 min)
solo para que se note esta mejora.

Tarda mas que un scraper suelto normal porque ahora, ficha por ficha, entra
en la pagina de cada anuncio para sacar el texto entero y las fotos (antes
solo leia el listado). Con ~600-800 anuncios de ThinkSpain, cuenta varios
minutos -- no es instantaneo, pero es mucho mas corto que el scraper entero.

A partir de manana esto ya NO hace falta correrlo mas: scrape_thinkspain()
ya esta dentro de scraper.py tal cual estaba antes (aqui no hubo que activar
nada nuevo, a diferencia de EcoUrbanizacion, porque ThinkSpain ya era una
fuente activa y solo le mejoramos como saca los datos) -- la tarea programada
de manana a las 10:00 ya lo hace solo, todos los dias.

Uso (desde C:\\HotelMonitor):
    python actualizar_thinkspain.py
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

    # OJO: al contrario que en agregar_ecourbanizacion.py, aqui NO
    # precargamos seen_urls con las URLs que ya hay en el cache. Alli
    # queriamos solo anuncios NUEVOS (EcoUrbanizacion era una fuente que no
    # existia antes). Aqui lo que queremos es volver a pasar por TODOS los
    # anuncios de ThinkSpain -- los nuevos Y los que ya teniamos -- para que
    # los que ya teniamos se ACTUALICEN con la descripcion completa y las
    # fotos, en vez de saltarselos por ya existir.
    scraper.found_listings.clear()
    scraper.seen_urls.clear()

    scraper.scrape_thinkspain(None)

    print(f'\n{len(scraper.found_listings)} anuncios de ThinkSpain encontrados en esta pasada.')

    nuevos = 0
    actualizados = 0
    for item in scraper.found_listings:
        url = item['url']

        # Mismo backfill de habitaciones/m2 que hace scraper.py para todos
        # los anuncios del cache, para que salga completo desde ya.
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

        if url not in cache:
            item['ausencias'] = 0
            cache[url] = item
            nuevos += 1
        else:
            # Mismo criterio de seguridad que usa scraper.py en su propio
            # merge: nunca nos quedamos con una descripcion mas corta que la
            # que ya teniamos (por si hoy fallase la visita a esa ficha en
            # concreto), y las fotos solo se refrescan si hoy se encontro
            # alguna -- si no, se quedan las que ya habia.
            existente = cache[url]
            desc_nueva = item.get('description') or ''
            desc_vieja = existente.get('description') or ''
            existente['description'] = desc_nueva if len(desc_nueva) >= len(desc_vieja) else desc_vieja
            existente['price'] = item.get('price', existente.get('price', ''))
            existente['tipo'] = item.get('tipo', existente.get('tipo', ''))
            existente['ausencias'] = 0
            for _k in ('rooms', 'm2', 'beds', 'bathrooms', 'fotos_url'):
                if item.get(_k):
                    existente[_k] = item[_k]
            actualizados += 1

    print(f'\n{nuevos} anuncios nuevos añadidos, {actualizados} anuncios ya existentes actualizados '
          f'(descripción completa + fotos).')

    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(cache.values()), f, ensure_ascii=False, indent=1)
    print(f'hoteles_cache.json guardado: {len(cache)} anuncios totales.')
    print('\nAhora corre:  python regenerar_web.py')


if __name__ == '__main__':
    main()
