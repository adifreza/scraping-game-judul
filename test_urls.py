import urllib.request
import re

urls = [
    "https://romsfun.com/?s=ghost+rider+ps2",
    "https://romsfun.com/browse-all-roms/?s=ghost+rider",
    "https://romsfun.com/browse-all-roms/?s=ghost+rider&console=ps2",
    "https://romsfun.com/browse-all-roms/?s=ghost+rider&console=playstation-2",
    "https://romsfun.com/browse-all-roms/?s=ghost+rider&platform=ps2"
]

headers = {'User-Agent': 'Mozilla/5.0'}

for url in urls:
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            status = response.getcode()
            final_url = response.geturl()
            content = response.read(5000).decode('utf-8', errors='ignore')
            title_match = re.search(r'<title>(.*?)</title>', content, re.IGNORECASE | re.DOTALL)
            title = title_match.group(1).strip()[:200] if title_match else "N/A"
            print(f"URL: {url}\nStatus: {status}\nFinal: {final_url}\nTitle: {title}\n{'-'*20}")
    except Exception as e:
        print(f"URL: {url}\nError: {e}\n{'-'*20}")
