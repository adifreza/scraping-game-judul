import open_romsfun_tabs as m
import re

url = 'https://romsfun.com/roms/playstation-2/fifa-14-legacy-edition-3.html'
html = m.fetch_html(url)

if not html:
    print('Failed to fetch HTML')
else:
    count = len(re.findall(r'Download ROM', html, re.IGNORECASE))
    print(f'Count: {count}')
    hrefs = re.findall(r'href=[\"\']([^\"\']*?download[^\"\']*?)[\"\']', html, re.IGNORECASE)
    print(f'Hrefs: {hrefs[:5]}')
    match = re.search(r'Download ROM', html, re.IGNORECASE)
    if match:
        start = max(0, match.start() - 400)
        end = min(len(html), match.end() + 400)
        print('Snippet:')
        print(html[start:end])
