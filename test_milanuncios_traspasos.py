"""
Prueba SUELTA de la fuente de traspasos de Milanuncios
(/traspasos-de-hostales-y-hoteles/), sin tocar hoteles_cache.json --
solo para comprobar que ahora sale bien marcada como 'operacion_detectada':
'traspaso' antes de correr el retag completo (que mira las 5 fuentes y
tarda mas).

Uso:  python test_milanuncios_traspasos.py
"""
import scraper

scraper.found_listings.clear()
scraper.seen_urls.clear()

driver = scraper.init_driver_stealth()
try:
    scraper.scrape_milanuncios(driver, fuentes_override=['https://www.milanuncios.com/traspasos-de-hostales-y-hoteles/'])
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
    print()
