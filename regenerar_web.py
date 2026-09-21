#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
regenerar_web.py — Reconstruye index.html a partir de index_template.html
y los datos que ya tienes guardados (hoteles_cache.json,
retirados_historico.json), y lo sube a GitHub. Úsalo cuando yo te haya
tocado la plantilla (index_template.html) con algún cambio de la propia
web -- una columna, un botón, un orden distinto, etc. -- pero NO haga
falta tocar los datos (eso ya lo hace scraper.py o restaurar_activos.py
cuando corresponde).

No cambia ningún anuncio de Activo a Retirado ni al revés: coge los datos
tal cual están ahora mismo en hoteles_cache.json y solo reconstruye la
página con la plantilla más reciente.

USO (desde la carpeta C:\\HotelMonitor):
    python regenerar_web.py
"""
import json
import os
import subprocess
from datetime import date

TODAY = date.today().strftime('%d/%m/%Y')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, 'hoteles_cache.json')
RETIRADOS_FILE = os.path.join(BASE_DIR, 'retirados_historico.json')
TEMPLATE_FILE = os.path.join(BASE_DIR, 'index_template.html')
INDEX_FILE = os.path.join(BASE_DIR, 'index.html')
ADR_FILE = os.path.join(BASE_DIR, 'adr_benchmark.json')


def cargar_retirados():
    if os.path.exists(RETIRADOS_FILE):
        try:
            with open(RETIRADOS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                return {x.get('url'): x for x in data if x.get('url')}
            if isinstance(data, dict):
                return data
        except Exception as e:
            print(f'  Aviso: no se pudo leer retirados_historico.json ({e}).')
    return {}


def subir_github():
    print('\nSubiendo a GitHub...')
    try:
        os.chdir(BASE_DIR)
        subprocess.run(['git', 'stash'], capture_output=True)
        subprocess.run(['git', 'pull', 'origin', 'main', '--rebase'], check=True)
        subprocess.run(['git', 'stash', 'pop'], capture_output=True)
        subprocess.run(['git', 'add', 'index.html'], check=True)
        # hoteles_cache.json tambien se sube aqui -- si no, cualquier cambio
        # manual (agregar_ecourbanizacion.py, agregar_inmoolaya.py,
        # adjuntar_pdf.py, restaurar_activos.py...) se queda solo en tu
        # ordenador y la proxima vez que corra el scraper automatico en
        # GitHub Actions lo pisaria sin querer (el robot parte siempre del
        # hoteles_cache.json que hay EN GitHub, no del de tu carpeta).
        subprocess.run(['git', 'add', 'hoteles_cache.json'], check=True)
        # Carpeta de PDFs adjuntados con adjuntar_pdf.py (puede no existir
        # todavia la primera vez que se usa este script).
        if os.path.isdir(os.path.join(BASE_DIR, 'documentos')):
            subprocess.run(['git', 'add', 'documentos'], check=True)
        result = subprocess.run(['git', 'diff', '--cached', '--quiet'], capture_output=True)
        if result.returncode != 0:
            subprocess.run(['git', 'commit', '-m', f'Regenerar web ({TODAY})'], check=True)
            subprocess.run(['git', 'push', 'origin', 'main'], check=True)
            print('Subido OK: https://juanarroyo123.github.io/Hoteles-Espa-a/')
        else:
            print('Sin cambios nuevos que subir (el index.html generado es igual al de antes).')
    except Exception as e:
        print(f'Error git: {e}')


def main():
    os.chdir(BASE_DIR)
    print('Regenerando index.html desde index_template.html + datos actuales...\n')

    with open(CACHE_FILE, 'r', encoding='utf-8') as f:
        cache_data = json.load(f)
    cache = {item['url']: item for item in cache_data}

    with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
        template = f.read()

    hist_retirados = cargar_retirados()
    todos = list(cache.values())
    todos_activos = [h for h in todos if h.get('estado') != 'Retirado']
    activos_urls = {h.get('url') for h in todos_activos}
    retirados_hist = [h for h in hist_retirados.values() if h.get('url') not in activos_urls]

    adr_benchmark_json = '{}'
    if os.path.exists(ADR_FILE):
        with open(ADR_FILE, 'r', encoding='utf-8') as fb:
            adr_benchmark_json = fb.read().strip()

    html = template.replace('__LISTINGS_JSON__', json.dumps(todos_activos, ensure_ascii=False))
    html = html.replace('__RETIRADOS_JSON__', json.dumps(retirados_hist, ensure_ascii=False))
    html = html.replace('__ADR_BENCHMARK_JSON__', adr_benchmark_json)

    with open(INDEX_FILE, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'index.html regenerado: {len(todos_activos)} activos + {len(retirados_hist)} retirados (comparables).')

    subir_github()
    input('\nPresiona Enter para cerrar...')


if __name__ == '__main__':
    main()
