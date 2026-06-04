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
    "daddy roleplay", "stepdaughter roleplay", "daddy daughter",
    "step daddy", "daddy dom", "taboo roleplay", "daddy ageplay",
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

def safe_get(url, extra_headers=None, timeout=6):
    """GET with retry on SSL/connection errors."""
    headers = {**HEADERS, **(extra_headers or {})}
    for attempt in range(3):
        try:
            return requests.get(url, headers=headers, timeout=timeout)
        except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
            if attempt == 2:
                raise
            import time; time.sleep(0.5 * (attempt + 1))
    return None

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
    try:
        parts = text.strip().split(':')
        return sum(int(p) * (60 ** i) for i, p in enumerate(reversed(parts)))
    except:
        return 600

def strip_quotes(q):
    return q.strip('"\'')

def is_exact(q):
    return (q.startswith('"') and q.endswith('"')) or (q.startswith("'") and q.endswith("'"))

def make_record(title, url, thumb, source, duration=600):
    t = (title or '').strip()
    if not t or not url:
        return None
    return {
        "title": t, "url": url, "thumb": thumb or '',
        "source": source, "duration": duration,
        "added_date": datetime.now().isoformat(), "is_album": False
    }

def add_record(lst, title, url, thumb, source, duration=600):
    r = make_record(title, url, thumb, source, duration)
    if r:
        lst.append(r)

# ==================== SCRAPERS ====================

def scrape_eporner(q, page=1):
    records = []
    try:
        url = ("https://www.eporner.com/api/v2/video/search/?query="
               + requests.utils.quote(q)
               + f"&per_page=100&page={page}&format=xml")
        res = safe_get(url)
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            for video in root.findall('.//video'):
                title = (video.find('title').text or '').strip()
                if not title or any(fw in title.lower() for fw in FORBIDDEN_WORDS):
                    continue
                vid_url = video.find('url').text or ''
                thumb = video.find('default_thumb').text or ''
                length_sec = int(video.find('length_sec').text or 600)
                source = TUBE_DOMAINS[sum(ord(c) for c in title) % len(TUBE_DOMAINS)]
                add_record(records, title, vid_url, thumb, source, length_sec)
    except Exception as e:
        print(f"Eporner error: {e}")
    return records


def scrape_xvideos(q, page=0):
    results = []
    try:
        url = f"https://www.xvideos.com/?k={requests.utils.quote(q)}&p={page}"
        res = safe_get(url)
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
        res = safe_get(url)
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
        res = safe_get(url)
        soup = BeautifulSoup(res.text, 'html.parser')
        for item in soup.select('li.pcVideoListItem, .videoBox'):
            try:
                title_el = item.select_one('.title a, span.title a')
                link_el = item.select_one('a[href]')
                img_el = item.select_one('img')
                if not (title_el and link_el):
                    continue
                thumb = (img_el.get('data-thumb_url') or img_el.get('data-src') or img_el.get('src') or '') if img_el else ''
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


def scrape_xhamster(q, page=1):
    results = []
    try:
        url = f"https://xhamster.com/search/{requests.utils.quote(q)}?page={page}"
        res = safe_get(url)
        html = res.text

        # xHamster SSR embeds all data in window.initials
        m = re.search(r'window\.initials\s*=\s*(\{.+?\});\s*(?:window\.|</script>)', html, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
                videos = []
                # Walk known paths — their structure changes between deploys
                for top in ('searchResult', 'videoSearchResult', 'categoryVideoResult'):
                    node = data.get(top) or {}
                    for sub in ('videos', 'models', 'items', 'data', 'videoList'):
                        cand = node.get(sub, [])
                        if isinstance(cand, list) and cand and isinstance(cand[0], dict):
                            videos = cand
                            break
                    if videos:
                        break
                # Last resort: any top-level list whose first item has pageURL
                if not videos:
                    for v in data.values():
                        if isinstance(v, list) and v and isinstance(v[0], dict) and v[0].get('pageURL'):
                            videos = v
                            break
                for v in videos:
                    title = v.get('title') or v.get('name') or ''
                    vid_url = v.get('pageURL') or v.get('url') or ''
                    thumbs = v.get('thumbs') or []
                    thumb = (thumbs[0].get('src') or thumbs[0].get('url') or '') if thumbs else ''
                    thumb = thumb or v.get('thumbURL') or v.get('thumbnailURL') or v.get('coverURL') or ''
                    duration = v.get('duration') or 600
                    add_record(results, title, vid_url, thumb, "xHamster", int(duration))
                print(f"xHamster JSON q={q!r} p={page}: {len(results)} items")
                if results:
                    return results
            except Exception as je:
                print(f"xHamster JSON error: {je}")

        # HTML fallback
        soup = BeautifulSoup(html, 'html.parser')
        items = soup.select('.thumb-list__item, .video-thumb')
        print(f"xHamster HTML q={q!r} p={page}: {len(items)} items")
        for item in items:
            try:
                link_el = item.select_one('a[href]')
                if not link_el:
                    continue
                title = (link_el.get('title') or '').strip()
                if not title:
                    title_el = item.select_one('[class*="title"], [class*="name"]')
                    title = safe_get_text(title_el)
                img_el = item.select_one('img')
                thumb = (img_el.get('data-src') or img_el.get('src') or '') if img_el else ''
                add_record(results, title, link_el.get('href', ''), thumb, "xHamster")
            except:
                continue
    except Exception as e:
        print(f"xHamster error (q={q!r} p={page}): {e}")
    return results


def scrape_camstreams(q, page=1):
    results = []
    try:
        url = f"https://www.camstreams.tv/search/?q={requests.utils.quote(q)}&page={page}"
        res = safe_get(url)
        soup = BeautifulSoup(res.text, 'html.parser')
        # Only accept items that have both an img AND a link with a meaningful href
        raw = soup.select('.video-item, .stream-item, .model-item, .thumb-item')
        items = [el for el in raw if el.find('img') and el.find('a', href=True)]
        print(f"CamStreams q={q!r} p={page}: {len(items)} items (status {res.status_code})")
        seen = set()
        for item in items:
            try:
                link_el = item.select_one('a[href*="/video"], a[href*="/stream"], a[href*="/model"], a[href*="/cam"]')
                if not link_el:
                    link_el = item.find('a', href=True)
                href = (link_el.get('href') or '') if link_el else ''
                if not href or href in ('/', '#'):
                    continue
                full_url = href if href.startswith('http') else ('https://www.camstreams.tv' + href)
                if full_url in seen:
                    continue
                seen.add(full_url)
                title = (link_el.get('title') or '').strip() if link_el else ''
                if not title:
                    title_el = item.select_one('.title, h3, h4, [class*="name"]')
                    title = safe_get_text(title_el)
                if not title:
                    continue
                img_el = item.find('img')
                thumb = (img_el.get('data-src') or img_el.get('src') or '') if img_el else ''
                add_record(results, title, full_url, thumb, "CamStreams")
            except:
                continue
    except Exception as e:
        print(f"CamStreams error (q={q!r} p={page}): {e}")
    return results


def scrape_beeg(q, page=1):
    results = []
    try:
        url = f"https://beeg.com/search/{requests.utils.quote(q)}/{page}"
        res = safe_get(url)
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


# ==================== ORCHESTRATION ====================

def _fan_out(sub_queries, scrape_pages, executor):
    futures = []
    for sq in sub_queries:
        for pg in scrape_pages:
            futures.append(executor.submit(scrape_eporner, sq, pg))
            futures.append(executor.submit(scrape_xvideos, sq, pg - 1))
            futures.append(executor.submit(scrape_xnxx, sq, pg - 1))
            futures.append(executor.submit(scrape_xhamster, sq, pg))
            futures.append(executor.submit(scrape_pornhub, sq, pg))
            futures.append(executor.submit(scrape_beeg, sq, pg))
            futures.append(executor.submit(scrape_camstreams, sq, pg))
    return futures


def seed_database():
    master_db = load_db()
    existing_urls = {x["url"] for x in master_db if "url" in x}
    new_records = []
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = _fan_out(DEFAULT_SEED_QUERIES, list(range(1, 6)), executor)
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

    if not exact and "," in clean:
        sub_queries = [q.strip() for q in clean.split(",") if q.strip()]
    else:
        sub_queries = [clean] if clean else DEFAULT_SEED_QUERIES[:3]

    scrape_pages = list(range(page, page + 5))
    aggregated = []

    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = _fan_out(sub_queries, scrape_pages, executor)
        for f in futures:
            try:
                aggregated.extend(f.result())
            except:
                pass

    if exact:
        phrase = clean.lower()
        aggregated = [r for r in aggregated if phrase in r.get("title", "").lower()]

    master_db = load_db()
    existing_urls = {x["url"] for x in master_db if "url" in x}

    new_records, seen = [], set()
    for record in aggregated:
        u = record.get("url")
        t = (record.get("title") or '').strip()
        if u and t and u not in existing_urls and u not in seen:
            new_records.append(record)
            seen.add(u)

    if new_records:
        save_db(master_db + new_records)
        results = new_records
    else:
        results = [r for r in master_db if any(sq.lower() in r.get("title", "").lower() for sq in sub_queries)]
        if not results:
            results = [r for r in aggregated if (r.get("title") or '').strip()]

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
        print("\n--- Seeding database ---")
        seed_database()
        print(f"Database: {len(load_db())} records")
    print("\n--- SERVER RUNNING: http://127.0.0.1:5000 ---\n")
    app.run(debug=True, host="127.0.0.1", port=5000)
