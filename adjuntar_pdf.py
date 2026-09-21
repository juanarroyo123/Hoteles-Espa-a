#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
adjuntar_pdf.py -- Adjunta un PDF (dossier, planos, cuentas...) a un anuncio
concreto para que se vea EN LA WEB PARA CUALQUIERA QUE ENTRE, no solo para
ti (a diferencia del boton "+ Anadir PDF" de dentro de la propia ficha, que
guarda el PDF solo en tu navegador). El fichero se copia dentro del
proyecto (carpeta documentos/) y hoteles_cache.json se actualiza para que
sepa que ese anuncio tiene ese documento.

Uso (desde C:\\HotelMonitor):
    python adjuntar_pdf.py "<url_del_anuncio>" "<ruta_del_pdf>"

Ejemplo:
    python adjuntar_pdf.py "https://inmoolaya.com/propiedad/12795/hotel-en-venta" "C:\\Users\\Juan\\Downloads\\dossier.pdf"

La URL es la misma que sale en "Ver anuncio original" dentro de la ficha.

Despues de correrlo:
    python regenerar_web.py      <- para que se vea en la web y se suba
"""
import json
import os
import re
import shutil
import sys
import unicodedata

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, 'hoteles_cache.json')
DOCS_DIR = os.path.join(BASE_DIR, 'documentos')


def slug(texto):
    texto = unicodedata.normalize('NFKD', texto or '').encode('ascii', 'ignore').decode('ascii')
    texto = re.sub(r'[^a-zA-Z0-9]+', '_', texto).strip('_').lower()
    return texto or 'documento'


def main():
    if len(sys.argv) != 3:
        print('Uso: python adjuntar_pdf.py "<url_del_anuncio>" "<ruta_del_pdf>"')
        sys.exit(1)
    url_anuncio = sys.argv[1].strip()
    ruta_pdf = sys.argv[2].strip().strip('"')

    if not os.path.isfile(ruta_pdf):
        print(f'No existe el fichero: {ruta_pdf}')
        sys.exit(1)
    if not ruta_pdf.lower().endswith('.pdf'):
        print('Ese fichero no es un .pdf -- de momento solo se admiten PDFs.')
        sys.exit(1)

    with open(CACHE_FILE, 'r', encoding='utf-8') as f:
        cache_data = json.load(f)

    item = next((x for x in cache_data if x.get('url') == url_anuncio), None)
    if item is None:
        # Busqueda flexible por si la URL viene con/sin barra final.
        candidatos = [x for x in cache_data if x.get('url', '').rstrip('/') == url_anuncio.rstrip('/')]
        item = candidatos[0] if candidatos else None
    if item is None:
        print('No se ha encontrado ningun anuncio con esa URL en hoteles_cache.json.')
        print('Copia la URL tal cual aparece en el boton "Ver anuncio original" de la ficha.')
        sys.exit(1)

    os.makedirs(DOCS_DIR, exist_ok=True)

    # Nombre real del fichero en el repo: saneado (sin espacios/acentos, que
    # dan problemas en URLs), pero el nombre ORIGINAL se guarda aparte para
    # que se vea igual que te lo mandaron en la web.
    nombre_original = os.path.basename(ruta_pdf)
    base_nombre = slug(os.path.splitext(nombre_original)[0])
    id_anuncio = slug(item.get('title', ''))[:40] or 'anuncio'
    destino_nombre = f'{id_anuncio}_{base_nombre}.pdf'
    contador = 1
    while os.path.exists(os.path.join(DOCS_DIR, destino_nombre)):
        contador += 1
        destino_nombre = f'{id_anuncio}_{base_nombre}_{contador}.pdf'

    shutil.copyfile(ruta_pdf, os.path.join(DOCS_DIR, destino_nombre))

    item.setdefault('documentos', [])
    item['documentos'].append({'nombre': nombre_original, 'archivo': f'documentos/{destino_nombre}'})

    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=1)

    print(f'PDF adjuntado a: {item.get("title","")[:70]}')
    print(f'  guardado como documentos/{destino_nombre}  (se vera como "{nombre_original}")')
    print('\nAhora corre:  python regenerar_web.py')


if __name__ == '__main__':
    main()
