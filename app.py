from flask import Flask, render_template, jsonify, request
import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import os
import json
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
    "WatchPorn", "OK.xxx", "Porn00", "JustPorn", "WhoresHub"
]

FORBIDDEN_WORDS = ["feet", "foot", "toes", "footjob", "shrimping", "oralfoot"]

# Default queries used to pre-populate the database on first load
DEFAULT_SEED_QUERIES = [
    "daddy roleplay",
    "stepdaughter roleplay",
    "daddy daughter",
    "step daddy",
    "daddy dom",
    "taboo roleplay",
    "daddy ageplay",
]

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

# ==================== REAL SCRAPERS ====================

def scrape_spankbang(q):
    results = []
    try:
        url = f"https://spankbang.com/s/{requests.utils.quote(q)}/"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=6)
        soup = BeautifulSoup(res.text, 'html.parser')
        for item in soup.select('.video-item')[:20]:
            try:
                title_el = item.select_one('.n')
                link_el = item.select_one('a')
                img_el = item.select_one('img')
                if title_el and link_el and img_el:
                    results.append({
                        "title": safe_get_text(title_el),
                        "url": "https://spankbang.com" + link_el.get('href', ''),
                        "thumb": img_el.get('src') or img_el.get('data-src', ''),
                        "source": "SpankBang",
                        "duration": 600,
                        "added_date": datetime.now().isoformat(),
                        "is_album": False
                    })
            except:
                continue
    except Exception as e:
        print(f"SpankBang error: {e}")
    return results

def scrape_xhamster(q):
    results = []
    try:
        url = f"https://xhamster.com/search/{requests.utils.quote(q)}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=6)
        soup = BeautifulSoup(res.text, 'html.parser')
        for item in soup.select('.thumb-list__item, .video-thumb')[:20]:
            try:
                title_el = item.select_one('.video-thumb-info__name, .thumb-title')
                link_el = item.select_one('a')
                img_el = item.select_one('img')
                if title_el and link_el and img_el:
                    results.append({
                        "title": safe_get_text(title_el),
                        "url": link_el.get('href') or '',
                        "thumb": img_el.get('src') or img_el.get('data-src', ''),
                        "source": "xHamster",
                        "duration": 600,
                        "added_date": datetime.now().isoformat(),
                        "is_album": False
                    })
            except:
                continue
    except Exception as e:
        print(f"xHamster error: {e}")
    return results

def scrape_beeg(q):
    results = []
    try:
        url = f"https://beeg.com/search/{requests.utils.quote(q)}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=6)
        soup = BeautifulSoup(res.text, 'html.parser')
        for item in soup.select('.thumb')[:20]:
            try:
                title_el = item.select_one('.title')
                link_el = item.select_one('a')
                img_el = item.select_one('img')
                if title_el and link_el and img_el:
                    results.append({
                        "title": safe_get_text(title_el),
                        "url": "https://beeg.com" + link_el.get('href', ''),
                        "thumb": img_el.get('src') or img_el.get('data-src', ''),
                        "source": "Beeg",
                        "duration": 600,
                        "added_date": datetime.now().isoformat(),
                        "is_album": False
                    })
            except:
                continue
    except Exception as e:
        print(f"Beeg error: {e}")
    return results

# ==================== EPORNER ====================

def run_single_scrape(clean_q, page=1):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    url = "https://www.eporner.com/api/v2/video/search/?query=" + requests.utils.quote(clean_q)
    url += "&per_page=100&page=" + str(page) + "&format=xml"

    records = []
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            videos = root.findall('.//video')
            for video in videos:
                title = video.find('title').text or ""
                if any(fw in title.lower() for fw in FORBIDDEN_WORDS):
                    continue
                vid_url = video.find('url').text or ""
                thumb = video.find('default_thumb').text or ""
                length_sec = video.find('length_sec').text or "600"
                char_sum = sum(ord(c) for c in title)
                assigned_site = TUBE_DOMAINS[char_sum % len(TUBE_DOMAINS)]
                records.append({
                    "title": title.strip(),
                    "url": vid_url,
                    "thumb": thumb,
                    "source": assigned_site,
                    "duration": int(length_sec),
                    "added_date": datetime.now().isoformat(),
                    "is_album": False
                })
    except Exception as e:
        print("Eporner error:", e)
    return records


def seed_database():
    """Populate db with results from multiple default queries across multiple pages."""
    master_db = load_db()
    existing_urls = {x["url"] for x in master_db if "url" in x}
    new_records = []

    tasks = []
    for query in DEFAULT_SEED_QUERIES:
        for page in range(1, 4):  # pages 1-3 = up to 300 results per query
            tasks.append((query, page))

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(run_single_scrape, q, p): (q, p) for q, p in tasks}
        for f in futures:
            try:
                for record in f.result():
                    if record.get("url") and record["url"] not in existing_urls:
                        new_records.append(record)
                        existing_urls.add(record["url"])
            except:
                pass

    if new_records:
        save_db(master_db + new_records)
        print(f"Seeded {len(new_records)} new records. Total: {len(master_db) + len(new_records)}")
    return master_db + new_records


def run_deep_target_scrape(query, page=1, preferred_source=None):
    if "," in query:
        sub_queries = [q.strip() for q in query.split(",") if q.strip()]
    else:
        sub_queries = [query.strip()] if query.strip() else DEFAULT_SEED_QUERIES[:3]

    aggregated_results = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = []

        if preferred_source:
            ps = preferred_source.lower()
            if ps == "spankbang":
                futures += [executor.submit(scrape_spankbang, sq) for sq in sub_queries]
            elif ps in ["xhamster", "xhamster.com"]:
                futures += [executor.submit(scrape_xhamster, sq) for sq in sub_queries]
            elif ps == "beeg":
                futures += [executor.submit(scrape_beeg, sq) for sq in sub_queries]

        # Run multiple pages per sub-query for volume
        for sq in sub_queries:
            for pg in range(page, page + 3):
                futures.append(executor.submit(run_single_scrape, sq, pg))

        for f in futures:
            try:
                aggregated_results.extend(f.result())
            except:
                pass

    master_db = load_db()
    existing_urls = {x["url"] for x in master_db if "url" in x}

    final_new_records = []
    seen = set()
    for record in aggregated_results:
        u = record.get("url")
        if u and u not in existing_urls and u not in seen:
            final_new_records.append(record)
            seen.add(u)

    if final_new_records:
        save_db(master_db + final_new_records)
        results = final_new_records
    else:
        # Return from db if nothing new
        results = [r for r in master_db if any(sq.lower() in r.get("title", "").lower() for sq in sub_queries)]
        if not results:
            results = aggregated_results

    if preferred_source and preferred_source != "All":
        prioritized = [r for r in results if r.get("source", "").lower() == preferred_source.lower()]
        others = [r for r in results if r.get("source", "").lower() != preferred_source.lower()]
        results = prioritized + others

    return results[:200]


@app.route("/")
def index():
    return render_template("index.html", networks=TUBE_DOMAINS)


@app.route("/fast_search", methods=["GET"])
def fast_search():
    query = request.args.get("query", "").strip().lower()
    page = int(request.args.get("page", 1))
    preferred_source = request.args.get("source", None)

    if any(fw in query for fw in FORBIDDEN_WORDS):
        return jsonify([])

    if query:
        live_batch = run_deep_target_scrape(query, page=page, preferred_source=preferred_source)
        return jsonify(live_batch)

    master_db = load_db()
    if len(master_db) < 50:
        master_db = seed_database()

    start = (page - 1) * 200
    return jsonify(master_db[start:start + 200])


if __name__ == "__main__":
    print("\n--- Seeding database on startup... ---")
    db = load_db()
    if len(db) < 100:
        seed_database()
    print(f"Database has {len(load_db())} records.")
    print("\n--- SERVER RUNNING ---")
    print("Open http://127.0.0.1:5000")
    print("----------------------\n")
    app.run(debug=True, host="127.0.0.1", port=5000)
