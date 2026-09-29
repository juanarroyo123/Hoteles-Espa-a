# -*- coding: utf-8 -*-
"""
Incorpora AHORA MISMO el registro de Menorca (ya descargado por
test_menorca.py en menorca_prueba.json) dentro de licencias_completo.json,
sin tener que esperar a la actualización semanal ni volver a descargar las
otras 17 fuentes nacionales.

Requisito: haber ejecutado antes test_menorca.py (o test_menorca.bat), que
es lo que genera menorca_prueba.json.

Es seguro ejecutarlo varias veces: si ya habías incorporado Menorca antes,
primero quita esas filas y luego vuelve a añadir las nuevas, así nunca se
duplican.

NO toca la fecha de "última actualización de licencias" -- la actualización
semanal completa (las 17 fuentes) seguirá ocurriendo en su día normal y
volverá a refrescar Menorca junto con todo lo demás.
"""
import json
import os
import sys

CARPETA = os.path.dirname(os.path.abspath(__file__))
RUTA_LIC = os.path.join(CARPETA, 'licencias_completo.json')
RUTA_MENORCA = os.path.join(CARPETA, 'menorca_prueba.json')


def main():
    if not os.path.exists(RUTA_MENORCA):
        print(f'No encuentro {RUTA_MENORCA}.')
        print('Ejecuta primero test_menorca.py (o test_menorca.bat).')
        sys.exit(1)
    if not os.path.exists(RUTA_LIC):
        print(f'No encuentro {RUTA_LIC} -- ¿estás en la carpeta correcta?')
        sys.exit(1)

    with open(RUTA_MENORCA, 'r', encoding='utf-8') as f:
        menorca = json.load(f)
    print(f'Registros de Menorca a incorporar: {len(menorca)}')

    with open(RUTA_LIC, 'r', encoding='utf-8') as f:
        lic = json.load(f)
    columnas = lic['columnas']
    filas = lic['filas']
    print(f'Licencias antes de incorporar Menorca: {len(filas)}')

    i_prov = columnas.index('provincia')
    i_muni = columnas.index('municipio')
    municipios_menorca = {r['municipio'] for r in menorca}

    # Quita cualquier fila de Menorca que ya hubiera (de una incorporación
    # anterior), para poder ejecutar este script varias veces sin duplicar.
    antes = len(filas)
    filas = [f_ for f_ in filas
             if not (f_[i_prov] == 'ILLES BALEARS' and f_[i_muni] in municipios_menorca)]
    quitadas = antes - len(filas)
    if quitadas:
        print(f'(Se han quitado {quitadas} filas de una incorporación anterior, para no duplicar)')

    nuevas = [[r.get(c, '') for c in columnas] for r in menorca]
    filas.extend(nuevas)

    with open(RUTA_LIC, 'w', encoding='utf-8') as f:
        json.dump({'columnas': columnas, 'filas': filas}, f, ensure_ascii=False, separators=(',', ':'))

    print(f'Añadidas {len(nuevas)} filas nuevas de Menorca.')
    print(f'Total licencias ahora: {len(filas)}')
    print(f'\n{RUTA_LIC} actualizado. Ya puedes ejecutar comprobar_licencias.py')
    print('para ver si sube el nº de anuncios cruzados.')


if __name__ == '__main__':
    main()
