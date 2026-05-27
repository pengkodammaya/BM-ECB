import httpx
with open('.fred_key') as f:
    api_key = f.read().strip()

# Search FRED for Malaysia
url = f'https://api.stlouisfed.org/fred/series/search?search_text=Malaysia+GDP&api_key={api_key}&file_type=json&limit=5'
r = httpx.get(url, timeout=15)
d = r.json()
if 'seriess' in d:
    for s in d['seriess'][:5]:
        print(f'{s["id"]}: {s["title"]} ({s["frequency"]})')
else:
    print('No results')
    print(d)
