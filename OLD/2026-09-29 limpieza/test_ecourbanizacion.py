"""
Prueba SUELTA de EcoUrbanizacion, sin tocar hoteles_cache.json ni el
scraper principal -- solo para ver que la funcion nueva trae datos buenos
antes de activarla de verdad (ver scraper.py, esta comentada la llamada).

Uso:  python test_ecourbanizacion.py
"""
import scraper

# Reseteamos el estado global que usa add_listing() para que esta prueba
# no dependa de si ya se corrio el scraper grande antes en esta sesion.
scraper.found_listings.clear()
scraper.seen_urls.clear()

scraper.scrape_ecourbanizacion(None)

print(f'\n=== RESULTADO: {len(scraper.found_listings)} anuncios encontrados ===\n')
for item in scraper.found_listings:
    print('-' * 70)
    print('TITULO :', item['title'])
    print('PRECIO :', item['price'])
    print('URL    :', item['url'])
    print('DESCRIPCION:')
    print(item['description'][:600])
    print()
