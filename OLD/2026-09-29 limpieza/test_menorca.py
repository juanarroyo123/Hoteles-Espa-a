# -*- coding: utf-8 -*-
"""
Prueba SOLO el scraper de licencias de Menorca (descargar_baleares_menorca,
en scraper_licencias.py) sin tocar nada más: no descarga las otras 17
fuentes de licencias, no toca licencias_completo.json, no toca
hoteles_cache.json ni index.html. Es de solo lectura -- puedes ejecutarlo
las veces que quieras sin ningún riesgo.

Cómo usarlo:
  Doble clic en test_menorca.bat (o "python test_menorca.py" en la carpeta
  del proyecto).

Al terminar, imprime un resumen (total de registros, por municipio, por
tipo de alojamiento) y dos ejemplos completos, y guarda todos los
registros en menorca_prueba.json por si quieres revisarlos con detalle.
"""
import json
import os
import sys
from collections import Counter

CARPETA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CARPETA)


def main():
    import scraper_licencias  # se importa aquí para que un error de red/import quede claro

    print("Descargando SOLO el registro de Menorca (no toca nada más)...\n")
    registros = scraper_licencias.descargar_baleares_menorca()

    if not registros:
        print("\nNo se ha descargado ningún registro -- revisa el mensaje de error de arriba")
        print("(lo más probable: sin conexión a internet, o la fuente ha cambiado de URL).")
        sys.exit(1)

    print(f"\n{'='*50}")
    print(f"TOTAL registros de Menorca: {len(registros)}")
    print('='*50)

    por_municipio = Counter(r['municipio'] for r in registros)
    print("\nPor municipio:")
    for m, n in por_municipio.most_common():
        print(f"  {m:20} {n}")

    por_tipo = Counter(r['tipo'] for r in registros)
    print("\nPor tipo:")
    for t, n in por_tipo.most_common():
        print(f"  {t:25} {n}")

    con_hab = sum(1 for r in registros if r.get('hab'))
    con_plazas = sum(1 for r in registros if r.get('plazas'))
    print(f"\nCon nº de habitaciones: {con_hab} / {len(registros)}")
    print(f"Con nº de plazas: {con_plazas} / {len(registros)}")

    print("\nDos ejemplos completos:")
    for r in registros[:2]:
        print(" ", r)

    salida = os.path.join(CARPETA, 'menorca_prueba.json')
    with open(salida, 'w', encoding='utf-8') as f:
        json.dump(registros, f, ensure_ascii=False, indent=2)
    print(f"\nTodos los registros guardados en: {salida}")
    print("\nSi todo esto tiene buena pinta (municipios reales, nombres, habitaciones),")
    print("el scraper está listo -- se incorporará solo la próxima vez que toque")
    print("actualizar licencias (cada 7 días), o puedes forzarlo antes si quieres.")


if __name__ == '__main__':
    main()
