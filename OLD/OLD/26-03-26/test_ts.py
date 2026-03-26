import undetected_chromedriver as uc
from bs4 import BeautifulSoup
import time

opts = uc.ChromeOptions()
opts.add_argument('--window-size=1920,1080')
driver = uc.Chrome(options=opts, version_main=None, use_subprocess=True)

print('Cargando ThinkSpain costa-blanca...')
driver.get('https://www.thinkspain.com/property-for-sale/costa-blanca/hotels')
time.sleep(8)
driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
time.sleep(3)

html = driver.page_source
with open('thinkspain_debug.html', 'w', encoding='utf-8') as f:
    f.write(html)
print('HTML guardado.')

soup = BeautifulSoup(html, 'lxml')
all_links = [a['href'] for a in soup.find_all('a', href=True) if '/property-for-sale/' in a['href']]
print(f'Total enlaces: {len(all_links)}')
for l in list(set(all_links))[:30]:
    print(' ', l)

driver.quit()
