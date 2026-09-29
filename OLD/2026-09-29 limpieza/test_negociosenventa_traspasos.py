"""
Prueba SUELTA de los traspasos de NegociosEnVenta (hoteles + hostales-
pensiones), sin tocar hoteles_cache.json ni el scraper principal -- solo
para ver que la funcion nueva trae datos buenos antes de activarla de
verdad (ver scraper.py, la llamada esta sin activar).

OJO: esta funcion SI necesita un navegador (usa get_page(driver, ...),
igual que scrape_negociosenventa() normal) -- no es como Inmo Olaya, que
solo usaba requests. Hace falta pasarle un driver real.

Uso:  python test_negociosenventa_traspasos.py
"""
import scraper

scraper.found_listings.clear()
scraper.seen_urls.clear()

driver = scraper.init_driver()
try:
    scraper.scrape_negociosenventa_traspasos(driver)
finally:
    try:
        driver.quit()
    except Exception:
        pass

print(f'\n=== RESULTADO: {len(scraper.found_listings)} anuncios encontrados ===\n')
for item in scraper.found_listings:
    print('-' * 70)
    print('TITULO      :', item['title'])
    print('PRECIO      :', item['price'])
    print('UBICACION   :', item['location'], '| COMUNIDAD:', item.get('location_region'))
    print('TIPO        :', item.get('tipo'))
    print('OPERACION   :', item.get('operacion_detectada'))
    print('URL         :', item['url'])
    print('DESCRIPCION :')
    print((item.get('description') or '')[:400])
    print()
