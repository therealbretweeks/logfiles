from flask import Flask, render_template, jsonify, request
import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import os
import json
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "db.json")

TUBE_DOMAINS = [
    "Beeg", "XVideos", "XNXX", "Pornhub", "xHamster", "Eporner", "SpankBang",
    "HQporner", "PornTrex", "RedTube", "YouPorn", "YouJizz", "Tube8", "Motherless",
    "TXXX", "DrTuber", "AnySex", "Perfect Girls", "PornDoe", "PornDig", "PornHoarder",
    "XXXFiles", "TNAFlix", "PussySpace", "FullPorner", "ParadiseHill", "XFreeHD",
    "Porn300", "PornoBae", "LetsJerk", "WatchXXXFree", "4kPorn", "YourPorn",
    "XMoviesForYou", "PornHat", "PornDish", "Porn4Days", "TrendyPorn", "PornSlash",
    "EroMe", "PornGo", "PornTop", "PornXP", "NetFapX", "FreeoMovie", "InPorn",
    "WatchPorn", "OK.xxx", "Porn00", "JustPorn", "WhoresHub", "CamStreams"
]

FORBIDDEN_WORDS = ["feet", "foot", "toes", "footjob", "shrimping", "oralfoot"]

DEFAULT_SEED_QUERIES = [
    "daddy roleplay",
    "stepdaughter roleplay",
    "daddy daughter",
    "step daddy",
    "daddy dom",
    "taboo roleplay",
    "daddy ageplay",
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

def load_db():
    if not os.path.exists(DB_FILE):
        return []
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            return json.loads(content) if content else []
    except:
        return []

def save_db(data):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except:
        pass

def safe_get_text(el):
    try:
        return el.get_text(strip=True) if el else ""
    except:
        return ""

def parse_duration(text):
    """Convert mm:ss or hh:mm:ss string to seconds."""
    try:
        parts = text.strip().split(':')
        return sum(int(p) * (60 ** i) for i, p in enumerate(reversed(parts)))
    except:
        return 600

def strip_quotes(q):
    """Return query with surrounding quotes removed."""
    return q.strip('"\'')

def is_exact(q):
    """True if query is wrapped in quotes — signals exact phrase search."""
    return (q.startswith('"') and q.endswith('"')) or (q.startswith("'") and q.endswith("'"))

def make_record(title, url, thumb, source, duration=600):
    t = title.strip() if title else ''
    if not t or not url:
        return None
    return {
        "title": t,
        "url": url,
        "thumb": thumb or '',
        "source": source,
        "duration": duration,
        "added_date": datetime.now().isoformat(),
        "is_album": False
    }

def add_record(lst, title, url, thumb, source, duration=600):
    """Build record and append only if valid."""
    r = make_record(title, url, thumb, source, duration)
    if r:
        lst.append(r)

# ==================== SCRAPERS ====================

def scrape_spankbang(q, page=1):
    """SpankBang via their internal search API (avoids bot detection on HTML pages)."""
    results = []
    try:
        params = {
            'q': q,
            'page': page,
            'per_page': 30,
        }
        # SpankBang exposes a JSON search endpoint used by their own frontend
        url = "https://spankbang.com/api/search/"
        headers = {**HEADERS, 'X-Requested-With': 'XMLHttpRequest', 'Referer': 'https://spankbang.com/'}
        res = requests.get(url, params=params, headers=headers, timeout=6)
        print(f"SpankBang API q={q!r} p={page}: status {res.status_code}")
        if res.status_code == 200:
            data = res.json()
            videos = data.get('videos') or data.get('results') or data.get('items') or []
            for v in videos:
                title = v.get('title') or v.get('name') or ''
                vid_url = v.get('url') or v.get('link') or ''
                if vid_url and not vid_url.startswith('http'):
                    vid_url = 'https://spankbang.com' + vid_url
                thumb = v.get('thumbnail') or v.get('thumb') or v.get('image') or ''
                duration = v.get('duration') or v.get('length') or 600
                add_record(results, title, vid_url, thumb, "SpankBang", int(duration))
            if not results:
                # Fallback: HTML parse
                results = _scrape_spankbang_html(q, page)
        else:
            results = _scrape_spankbang_html(q, page)
    except Exception as e:
        print(f"SpankBang error (q={q!r} p={page}): {e}")
        results = _scrape_spankbang_html(q, page)
    return results

def _scrape_spankbang_html(q, page=1):
    results = []
    try:
        slug = re.sub(r'\s+', '-', q.strip().lower())
        url = f"https://spankbang.com/s/{requests.utils.quote(slug, safe='-')}/{page}/"
        res = requests.get(url, headers=HEADERS, timeout=6)
        soup = BeautifulSoup(res.text, 'html.parser')
        # Extract from embedded JS data if present
        m = re.search(r'var\s+videos\s*=\s*(\[.*?\]);', res.text, re.DOTALL)
        if m:
            try:
                videos = json.loads(m.group(1))
                for v in videos:
                    title = v.get('title', '')
                    vid_url = 'https://spankbang.com' + v.get('url', '')
                    thumb = v.get('poster') or v.get('thumb') or ''
                    add_record(results, title, vid_url, thumb, "SpankBang", v.get('duration', 600))
                return results
            except:
                pass
        items = soup.select('.video-item, [data-id], li[id^="v"]')
        print(f"SpankBang HTML q={q!r} p={page}: {len(items)} items")
        for item in items:
            try:
                title_el = item.select_one('.n, .title')
                link_el = item.select_one('a[href]')
                img_el = item.select_one('img[data-src], img[src]')
                if not (title_el and link_el):
                    continue
                thumb = (img_el.get('data-src') or img_el.get('src') or '') if img_el else ''
                href = link_el.get('href', '')
                full_url = ('https://spankbang.com' + href) if href.startswith('/') else href
                add_record(results, safe_get_text(title_el), full_url, thumb, "SpankBang")
            except:
                continue
    except Exception as e:
        print(f"SpankBang HTML error: {e}")
    return results


def scrape_camstreams(q, page=1):
    """Scrape camstreams.tv search results."""
    results = []
    try:
        url = f"https://www.camstreams.tv/search/?q={requests.utils.quote(q)}&page={page}"
        res = requests.get(url, headers=HEADERS, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        # Try multiple possible container selectors
        items = soup.select('.video-item, .thumb, .model-item, article, .stream-item, [class*="video"], [class*="thumb"]')
        print(f"CamStreams q={q!r} p={page}: {len(items)} items (status {res.status_code})")
        for item in items:
            try:
                title_el = item.select_one('a[title], .title, h3, h4, [class*="title"], [class*="name"]')
                link_el = item.select_one('a[href]')
                img_el = item.select_one('img[data-src], img[src]')
                if not link_el:
                    continue
                title = (link_el.get('title') or safe_get_text(title_el) or '').strip()
                if not title:
                    continue
                thumb = (img_el.get('data-src') or img_el.get('src') or '') if img_el else ''
                href = link_el.get('href', '')
                full_url = href if href.startswith('http') else ('https://www.camstreams.tv' + href)
                results.append(make_record(title, full_url, thumb, "CamStreams"))
            except:
                continue
    except Exception as e:
        print(f"CamStreams error (q={q!r} p={page}): {e}")
    return results


def scrape_xhamster(q, page=1):
    results = []
    try:
        url = f"https://xhamster.com/search/{requests.utils.quote(q)}?page={page}"
        res = requests.get(url, headers=HEADERS, timeout=5)
        html = res.text

        # xHamster embeds video data as JSON in a script tag
        m = re.search(r'window\.initials\s*=\s*(\{.*?\});\s*</script>', html, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
                videos = (data.get('searchResult', {}) or data.get('videoSearchResult', {})).get('models', [])
                for v in videos:
                    title = v.get('title') or v.get('name') or ''
                    vid_url = v.get('pageURL') or v.get('url') or ''
                    thumb = (v.get('thumbURL') or v.get('thumbnailURL') or
                             v.get('coverURL') or v.get('thumbs', [{}])[0].get('src', '') if v.get('thumbs') else '')
                    duration = v.get('duration') or 600
                    add_record(results, title, vid_url, thumb, "xHamster", int(duration))
                print(f"xHamster JSON q={q!r} p={page}: {len(results)} items")
                return results
            except Exception as je:
                print(f"xHamster JSON parse error: {je}")

        # Fallback: HTML parsing
        soup = BeautifulSoup(html, 'html.parser')
        items = soup.select('.thumb-list__item, .video-thumb, [class*="VideoThumb"], [class*="video-thumb"]')
        print(f"xHamster HTML q={q!r} p={page}: {len(items)} items (status {res.status_code})")
        for item in items:
            try:
                link_el = item.select_one('a[href*="xhamster"]')
                if not link_el:
                    link_el = item.select_one('a[href]')
                title = (link_el.get('title') or '') if link_el else ''
                if not title:
                    title_el = item.select_one('[class*="title"], [class*="name"], h3, h4')
                    title = safe_get_text(title_el)
                img_el = item.select_one('img[data-src], img[src]')
                thumb = (img_el.get('data-src') or img_el.get('src') or '') if img_el else ''
                vid_url = link_el.get('href', '') if link_el else ''
                add_record(results, title, vid_url, thumb, "xHamster")
            except:
                continue
    except Exception as e:
        print(f"xHamster error (q={q!r} p={page}): {e}")
    return results


def scrape_xvideos(q, page=0):
    results = []
    try:
        url = f"https://www.xvideos.com/?k={requests.utils.quote(q)}&p={page}"
        res = requests.get(url, headers=HEADERS, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        for item in soup.select('.thumb-block'):
            try:
                title_el = item.select_one('.title a, p.title a')
                link_el = item.select_one('a[href]')
                img_el = item.select_one('img')
                if not (title_el and link_el):
                    continue
                thumb = (img_el.get('data-src') or img_el.get('src') or '') if img_el else ''
                dur_el = item.select_one('.duration')
                href = link_el.get('href', '')
                full_url = ("https://www.xvideos.com" + href) if href.startswith('/') else href
                add_record(results, safe_get_text(title_el), full_url, thumb, "XVideos",
                           parse_duration(safe_get_text(dur_el)) if dur_el else 600)
            except:
                continue
    except Exception as e:
        print(f"XVideos error (q={q!r} p={page}): {e}")
    return results


def scrape_xnxx(q, page=0):
    results = []
    try:
        url = f"https://www.xnxx.com/search/{requests.utils.quote(q)}/{page}"
        res = requests.get(url, headers=HEADERS, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        for item in soup.select('.thumb-block, .mozaique .thumb'):
            try:
                title_el = item.select_one('.title a, p.title a')
                link_el = item.select_one('a[href]')
                img_el = item.select_one('img')
                if not (title_el and link_el):
                    continue
                thumb = (img_el.get('data-src') or img_el.get('src') or '') if img_el else ''
                href = link_el.get('href', '')
                full_url = ("https://www.xnxx.com" + href) if href.startswith('/') else href
                add_record(results, safe_get_text(title_el), full_url, thumb, "XNXX")
            except:
                continue
    except Exception as e:
        print(f"XNXX error (q={q!r} p={page}): {e}")
    return results


def scrape_pornhub(q, page=1):
    results = []
    try:
        url = f"https://www.pornhub.com/video/search?search={requests.utils.quote(q)}&p={page}"
        res = requests.get(url, headers=HEADERS, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        for item in soup.select('li.pcVideoListItem, .videoBox'):
            try:
                title_el = item.select_one('.title a, span.title a')
                link_el = item.select_one('a[href]')
                img_el = item.select_one('img')
                if not (title_el and link_el):
                    continue
                thumb = ''
                if img_el:
                    thumb = img_el.get('data-thumb_url') or img_el.get('data-src') or img_el.get('src') or ''
                dur_el = item.select_one('.duration, var.duration')
                href = link_el.get('href', '')
                full_url = ("https://www.pornhub.com" + href) if href.startswith('/') else href
                add_record(results, safe_get_text(title_el), full_url, thumb, "Pornhub",
                           parse_duration(safe_get_text(dur_el)) if dur_el else 600)
            except:
                continue
    except Exception as e:
        print(f"Pornhub error (q={q!r} p={page}): {e}")
    return results


def scrape_beeg(q, page=1):
    results = []
    try:
        url = f"https://beeg.com/search/{requests.utils.quote(q)}/{page}"
        res = requests.get(url, headers=HEADERS, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        for item in soup.select('.thumb, article.video-item'):
            try:
                title_el = item.select_one('.title, h3')
                link_el = item.select_one('a[href]')
                img_el = item.select_one('img')
                if not (title_el and link_el):
                    continue
                thumb = (img_el.get('data-src') or img_el.get('src') or '') if img_el else ''
                href = link_el.get('href', '')
                full_url = ("https://beeg.com" + href) if href.startswith('/') else href
                add_record(results, safe_get_text(title_el), full_url, thumb, "Beeg")
            except:
                continue
    except Exception as e:
        print(f"Beeg error (q={q!r} p={page}): {e}")
    return results


# ==================== EPORNER API ====================

def run_single_scrape(clean_q, page=1):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    # Wrap in quotes for exact-phrase when the original query had quotes
    encoded = requests.utils.quote(clean_q)
    url = f"https://www.eporner.com/api/v2/video/search/?query={encoded}&per_page=100&page={page}&format=xml"
    records = []
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            for video in root.findall('.//video'):
                title = (video.find('title').text or "").strip()
                if not title or any(fw in title.lower() for fw in FORBIDDEN_WORDS):
                    continue
                vid_url = video.find('url').text or ""
                thumb = video.find('default_thumb').text or ""
                length_sec = video.find('length_sec').text or "600"
                char_sum = sum(ord(c) for c in title)
                source = TUBE_DOMAINS[char_sum % len(TUBE_DOMAINS)]
                records.append(make_record(title, vid_url, thumb, source, int(length_sec)))
    except Exception as e:
        print("Eporner error:", e)
    return records


# ==================== ORCHESTRATION ====================

def _fan_out(sub_queries, scrape_pages, executor):
    futures = []
    for sq in sub_queries:
        for pg in scrape_pages:
            futures.append(executor.submit(run_single_scrape, sq, pg))
            futures.append(executor.submit(scrape_spankbang, sq, pg))
            futures.append(executor.submit(scrape_camstreams, sq, pg))
            futures.append(executor.submit(scrape_xvideos, sq, pg - 1))
            futures.append(executor.submit(scrape_xnxx, sq, pg - 1))
            futures.append(executor.submit(scrape_xhamster, sq, pg))
            futures.append(executor.submit(scrape_pornhub, sq, pg))
            futures.append(executor.submit(scrape_beeg, sq, pg))
    return futures


def seed_database():
    master_db = load_db()
    existing_urls = {x["url"] for x in master_db if "url" in x}
    new_records = []

    with ThreadPoolExecutor(max_workers=64) as executor:
        futures = _fan_out(DEFAULT_SEED_QUERIES, list(range(1, 10)), executor)
        for f in futures:
            try:
                for record in f.result():
                    u = record.get("url")
                    if u and u not in existing_urls:
                        new_records.append(record)
                        existing_urls.add(u)
            except:
                pass

    if new_records:
        save_db(master_db + new_records)
        print(f"Seeded {len(new_records)} new records. Total: {len(master_db) + len(new_records)}")
    return master_db + new_records


def run_deep_target_scrape(query, page=1, preferred_source=None):
    exact = is_exact(query)
    clean = strip_quotes(query)

    # Comma-separated = multiple sub-queries (but not inside quoted string)
    if not exact and "," in clean:
        sub_queries = [q.strip() for q in clean.split(",") if q.strip()]
    else:
        sub_queries = [clean] if clean else DEFAULT_SEED_QUERIES[:3]

    aggregated = []
    # 5 pages per scraper per call, all parallel — fast enough and still deep
    scrape_pages = list(range(page, page + 5))

    with ThreadPoolExecutor(max_workers=64) as executor:
        futures = _fan_out(sub_queries, scrape_pages, executor)
        for f in futures:
            try:
                aggregated.extend(f.result())
            except:
                pass

    # If exact phrase, filter to only results whose title contains the phrase
    if exact:
        phrase = clean.lower()
        aggregated = [r for r in aggregated if phrase in r.get("title", "").lower()]

    master_db = load_db()
    existing_urls = {x["url"] for x in master_db if "url" in x}

    new_records, seen = [], set()
    for record in aggregated:
        u = record.get("url")
        t = record.get("title", "").strip()
        if u and t and u not in existing_urls and u not in seen:
            new_records.append(record)
            seen.add(u)

    if new_records:
        save_db(master_db + new_records)
        results = new_records
    else:
        results = [r for r in master_db if any(sq.lower() in r.get("title", "").lower() for sq in sub_queries)]
        if not results:
            results = aggregated

    if preferred_source and preferred_source != "All":
        prioritized = [r for r in results if r.get("source", "").lower() == preferred_source.lower()]
        others = [r for r in results if r.get("source", "").lower() != preferred_source.lower()]
        results = prioritized + others

    return results[:1000]


@app.route("/")
def index():
    return render_template("index.html", networks=TUBE_DOMAINS)


@app.route("/fast_search", methods=["GET"])
def fast_search():
    query = request.args.get("query", "").strip()
    page = int(request.args.get("page", 1))
    preferred_source = request.args.get("source", None)

    if any(fw in query.lower() for fw in FORBIDDEN_WORDS):
        return jsonify([])

    if query:
        return jsonify(run_deep_target_scrape(query, page=page, preferred_source=preferred_source))

    master_db = load_db()
    if len(master_db) < 50:
        master_db = seed_database()

    start = (page - 1) * 200
    return jsonify(master_db[start:start + 200])


if __name__ == "__main__":
    db = load_db()
    if len(db) < 100:
        print("\n--- Seeding database on startup... ---")
        seed_database()
        print(f"Database has {len(load_db())} records.")
    print("\n--- SERVER RUNNING ---")
    print("Open http://127.0.0.1:5000")
    print("----------------------\n")
    app.run(debug=True, host="127.0.0.1", port=5000)
