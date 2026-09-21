# -*- coding: utf-8 -*-
"""
Prueba SUELTA del arreglo de "descripcion completa + fotos reales desde
la ficha" en NegociosEnVenta (scrape_negociosenventa + scrape_negocios
enventa_traspasos comparten la misma funcion enriquecer_ficha_nv) --
no toca hoteles_cache.json, solo imprime para poder revisar antes de
que corra el robot automatico.

Antes de este cambio: 'description' era solo el resumen corto de la
tarjeta del listado (1-2 frases) y 'fotos_url' no existia -- CERO fotos
para todos los anuncios de este portal. Con esto deberias ver
descripciones largas (varios parrafos) y varias fotos por anuncio.

Uso:  python test_negociosenventa_fichas.py
"""
import scraper

scraper.found_listings.clear()
scraper.seen_urls.clear()

driver = scraper.init_driver()
try:
    scraper.scrape_negociosenventa(driver)
    scraper.scrape_negociosenventa_traspasos(driver)
finally:
    try:
        driver.quit()
    except Exception:
        pass

items = scraper.found_listings
print(f'\n=== RESULTADO: {len(items)} anuncios encontrados ===\n')

con_fotos = [it for it in items if it.get('fotos_url')]
sin_fotos = [it for it in items if not it.get('fotos_url')]
print(f'Con fotos: {len(con_fotos)} / {len(items)}  (sin fotos: {len(sin_fotos)}, normalmente porque la ficha ya no existe -- anuncio retirado)')
print(f'Descripcion media: {sum(len(it.get("description") or "") for it in items) // max(len(items),1)} caracteres\n')

for item in items[:15]:
    print('-' * 70)
    print('TITULO      :', item['title'])
    print('OPERACION   :', item.get('operacion_detectada') or '(por texto)')
    print('FOTOS       :', len(item.get('fotos_url') or []))
    if item.get('fotos_url'):
        print('  primera   :', item['fotos_url'][0])
    print('DESCRIPCION (', len(item.get('description') or ''), 'caracteres ):')
    print((item.get('description') or '')[:500])
    print()

if len(items) > 15:
    print(f'... y {len(items) - 15} anuncios mas (no mostrados aqui, pero contados arriba)')
