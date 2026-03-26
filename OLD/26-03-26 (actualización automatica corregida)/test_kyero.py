import undetected_chromedriver as uc
from bs4 import BeautifulSoup
import re, time

def init_driver():
    opts = uc.ChromeOptions()
    opts.add_argument('--window-size=1366,768')
    opts.add_argument('--lang=es-ES')
    driver = uc.Chrome(options=opts, version_main=None, use_subprocess=True)
    return driver

driver = init_driver()

try:
    driver.get('https://www.idealista.com')
    time.sleep(3)
    driver.get('https://www.idealista.com/venta-locales/madrid-provincia/con-hotel/')
    time.sleep(6)
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)
    
    soup = BeautifulSoup(driver.page_source, 'lxml')
    art = soup.find('article', attrs={'data-element-id': True})
    
    # Ver solo la parte de texto del article (sin imágenes)
    item_info = art.find(class_=re.compile(r'item-info|item-detail|item-data|property', re.I))
    if item_info:
        print('item-info encontrado:')
        print(str(item_info)[:1000])
    else:
        # Ver texto completo del article
        print('Texto article:')
        print(art.get_text()[:500])
        # Ver todas las clases usadas
        all_classes = set()
        for el in art.find_all(True):
            for c in el.get('class',[]):
                all_classes.add(c)
        print('\nClases en article:', sorted(all_classes)[:30])

finally:
    driver.quit()
