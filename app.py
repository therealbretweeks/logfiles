from flask import Flask, render_template, jsonify, request
import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import os
import json
import re
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "db.json")

TUBE_DOMAINS = sorted([
    "4kPorn", "AnySex", "Beeg", "CamStreams", "CamWhores", "DrTuber", "EroMe",
    "Eporner", "FreeoMovie", "FullPorner", "HQporner", "InPorn", "JustPorn",
    "LetsJerk", "Motherless", "NetFapX", "OK.xxx", "ParadiseHill", "Perfect Girls",
    "Porn00", "Porn300", "Porn4Days", "PornDig", "PornDish", "PornDoe", "PornGo",
    "PornHat", "PornHoarder", "PornSlash", "PornTop", "PornTrex", "PornXP",
    "PornoBae", "Pornhub", "PussySpace", "RedTube", "SpankBang", "TNAFlix",
    "TXXX", "Tube8", "TrendyPorn", "WatchPorn", "WatchXXXFree", "WhoresHub",
    "XFreeHD", "XNXX", "XMoviesForYou", "XVideos", "XXXFiles", "YouJizz",
    "YouPorn", "YourPorn", "xHamster",
], key=lambda x: x.lower())

FORBIDDEN_WORDS = [
    "feet", "foot", "toes", "footjob", "shrimping", "oralfoot",
    "gay", "twink", "twinks", "faggot", "men fucking men", "gay sex",
    "gay porn", "gay video", "bareback men",
]

GAY_TITLE_WORDS = {"gay", "twink", "twinks", "faggot"}

DEFAULT_SEED_QUERIES = [
    "stepdaughter roleplay", "daddy daughter", "step daddy",
    "taboo roleplay", "stepmom",
]

BASE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

def safe_get(url, extra_headers=None, timeout=2):
    headers = {**BASE_HEADERS, **(extra_headers or {})}
    for attempt in range(3):
        try:
            return requests.get(url, headers=headers, timeout=timeout)
        except (requests.exceptions.SSLError, requests.exceptions.ConnectionError):
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))
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

def make_record(title, url, thumb, source, duration=600, preview_url=''):
    t = (title or '').strip()
    if not t or not url:
        return None
    tl = t.lower()
    # Global content filter
    if any(fw in tl for fw in FORBIDDEN_WORDS):
        return None
    words = set(re.split(r'\W+', tl))
    if words & GAY_TITLE_WORDS:
        return None
    return {
        "title": t, "url": url, "thumb": thumb or '',
        "source": source, "duration": duration,
        "added_date": datetime.now().isoformat(), "is_album": False,
    }

def add_record(lst, title, url, thumb, source, duration=600, preview_url=''):
    r = make_record(title, url, thumb, source, duration, preview_url)
    if r:
        lst.append(r)


# ==================== SCRAPERS ====================

def scrape_eporner(q, page=1):
    records = []
    try:
        url = (f"https://www.eporner.com/api/v2/video/search/?query={requests.utils.quote(q)}"
               f"&per_page=100&page={page}&format=xml&thumbsize=big&order=top-rated")
        res = safe_get(url)
        if not res or res.status_code != 200:
            return records
        root = ET.fromstring(res.content)
        for video in root.findall('.//video'):
            title_el = video.find('title')
            url_el = video.find('url')
            thumb_el = video.find('default_thumb')
            dur_el = video.find('length_sec')
            preview_el = video.find('preview')  # direct .mp4 preview clip
            if title_el is None or url_el is None:
                continue
            title = (title_el.text or '').strip()
            if not title or any(fw in title.lower() for fw in FORBIDDEN_WORDS):
                continue
            length_sec = int(dur_el.text or 600) if dur_el is not None else 600
            preview_url = (preview_el.text or '') if preview_el is not None else ''
            add_record(records, title, url_el.text or '', (thumb_el.text or '') if thumb_el is not None else '', "Eporner", length_sec, preview_url)
        print(f"Eporner q={q!r} p={page}: {len(records)} records")
    except Exception as e:
        print(f"Eporner error: {e}")
    return records


def scrape_xhamster(q, page=1):
    results = []
    try:
        url = (f"https://xhamster.com/api/front/search"
               f"?query={requests.utils.quote(q)}&page={page}&per_page=32&category=&orientations=straight")
        res = safe_get(url, extra_headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'})
        if not res or res.status_code != 200:
            return results
        data = res.json()
        videos = (data.get('videos') or {}).get('items') or data.get('items') or []
        for v in videos:
            title = v.get('title') or v.get('name') or ''
            vid_url = v.get('pageURL') or v.get('url') or ''
            thumbs = v.get('thumbs') or []
            thumb = (thumbs[0].get('src') or '') if thumbs else (v.get('thumbURL') or v.get('thumbnail') or '')
            duration = v.get('duration') or 600
            preview_url = v.get('videoPreviewURL') or v.get('previewURL') or ''
            add_record(results, title, vid_url, thumb, "xHamster", int(duration), preview_url)
        print(f"xHamster q={q!r} p={page}: {len(results)} items")
    except Exception as e:
        print(f"xHamster error: {e}")
    return results


def _sb_parse_html(html, q, page, label="HTML"):
    """Parse SpankBang HTML for video data via JSON blobs or DOM."""
    results = []
    soup = BeautifulSoup(html, 'html.parser')

    for pattern in [
        r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>',
        r'window\.__DATA__\s*=\s*({.+?});',
        r'window\.pageData\s*=\s*({.+?});',
    ]:
        m = re.search(pattern, html, re.DOTALL)
        if m:
            try:
                raw = json.loads(m.group(1))
                if 'props' in raw:
                    raw = raw.get('props', {}).get('pageProps', {})
                for key in ('videos', 'results', 'items', 'searchResults', 'videoList', 'data'):
                    vlist = raw.get(key) or []
                    if isinstance(vlist, dict):
                        vlist = vlist.get('videos') or vlist.get('items') or []
                    if not isinstance(vlist, list):
                        continue
                    for v in vlist:
                        title = v.get('title') or v.get('name') or ''
                        vid_url = v.get('url') or v.get('link') or ''
                        if vid_url and not vid_url.startswith('http'):
                            vid_url = 'https://spankbang.com' + vid_url
                        thumb = v.get('thumbnail') or v.get('poster') or v.get('thumb') or ''
                        dur = int(v.get('duration') or v.get('length') or 600)
                        add_record(results, title, vid_url, thumb, "SpankBang", dur)
                if results:
                    print(f"SpankBang {label}/JSON q={q!r} p={page}: {len(results)} items")
                    return results
            except:
                pass

    m = re.search(r'"videos"\s*:\s*(\[.+?\])', html, re.DOTALL)
    if m:
        try:
            vlist = json.loads(m.group(1))
            for v in vlist:
                title = v.get('title') or v.get('name') or ''
                vid_url = v.get('url') or v.get('link') or ''
                if vid_url and not vid_url.startswith('http'):
                    vid_url = 'https://spankbang.com' + vid_url
                thumb = v.get('thumbnail') or v.get('poster') or v.get('thumb') or ''
                add_record(results, title, vid_url, thumb, "SpankBang")
            if results:
                return results
        except:
            pass

    # DOM fallback — SpankBang video items have id like "v-xxxxx"
    for item in soup.select('li[id^="v-"], div[id^="v-"], .video-item, .videoblock'):
        try:
            link_el = item.select_one('a[href]')
            title_el = item.select_one('.n, .title, h3, p.t, [class*="title"]')
            img_el = item.select_one('img[data-src], img[src]')
            if not (link_el and title_el):
                continue
            title = safe_get_text(title_el)
            href = link_el.get('href', '')
            if not href or href in ('/', '#', ''):
                continue
            full_url = ('https://spankbang.com' + href) if href.startswith('/') else href
            thumb = (img_el.get('data-src') or img_el.get('src') or '') if img_el else ''
            add_record(results, title, full_url, thumb, "SpankBang")
        except:
            continue

    print(f"SpankBang {label}/DOM q={q!r} p={page}: {len(results)} items")
    return results


def scrape_spankbang_bulk(q, pages):
    """One Playwright browser navigates multiple SpankBang pages sequentially."""
    results = []
    slug = re.sub(r'\s+', '-', q.strip().lower())

    if PLAYWRIGHT_AVAILABLE:
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-blink-features=AutomationControlled',
                        '--disable-infobars',
                    ]
                )
                ctx = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                    viewport={'width': 1280, 'height': 900},
                    java_script_enabled=True,
                )
                ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

                for pg in pages:
                    search_url = f"https://spankbang.com/s/{requests.utils.quote(slug, safe='-')}/{pg}/"
                    page_captured = []

                    def make_handler(lst):
                        def handle_response(resp):
                            try:
                                if 'spankbang.com' in resp.url and resp.status == 200:
                                    ct = resp.headers.get('content-type', '')
                                    if 'json' in ct:
                                        data = resp.json()
                                        vlist = data.get('videos') or data.get('results') or data.get('items') or []
                                        if vlist:
                                            lst.extend(vlist)
                            except:
                                pass
                        return handle_response

                    page_obj = ctx.new_page()
                    page_obj.on('response', make_handler(page_captured))
                    try:
                        page_obj.goto(search_url, wait_until='networkidle', timeout=25000)
                    except:
                        try:
                            page_obj.wait_for_timeout(3000)
                        except:
                            pass

                    if page_captured:
                        for v in page_captured:
                            title = v.get('title') or v.get('name') or ''
                            vid_url = v.get('url') or v.get('link') or ''
                            if vid_url and not vid_url.startswith('http'):
                                vid_url = 'https://spankbang.com' + vid_url
                            thumb = v.get('thumbnail') or v.get('poster') or v.get('thumb') or ''
                            dur = int(v.get('duration') or v.get('length') or 600)
                            add_record(results, title, vid_url, thumb, "SpankBang", dur)
                        print(f"SpankBang bulk XHR q={q!r} p={pg}: {len(page_captured)} json items")
                    else:
                        html = page_obj.content()
                        page_results = _sb_parse_html(html, q, pg, label=f"bulk-p{pg}")
                        results.extend(page_results)

                    page_obj.close()

                browser.close()
        except Exception as e:
            print(f"SpankBang Playwright error: {e}")
            # HTTP fallback
            for pg in pages:
                results.extend(_scrape_spankbang_http(q, pg))
    else:
        for pg in pages:
            results.extend(_scrape_spankbang_http(q, pg))

    print(f"SpankBang bulk total q={q!r}: {len(results)} items across {len(pages)} pages")
    return results


def _scrape_spankbang_http(q, page):
    slug = re.sub(r'\s+', '-', q.strip().lower())
    url = f"https://spankbang.com/s/{requests.utils.quote(slug, safe='-')}/{page}/"
    res = safe_get(url, extra_headers={
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
    })
    if res and res.status_code == 200:
        return _sb_parse_html(res.text, q, page, label="http")
    return []


def scrape_xvideos(q, page=0):
    results = []
    try:
        url = f"https://www.xvideos.com/?k={requests.utils.quote(q)}&p={page}"
        res = safe_get(url)
        if not res:
            return results
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
        print(f"XVideos q={q!r} p={page}: {len(results)} items")
    except Exception as e:
        print(f"XVideos error: {e}")
    return results


def scrape_xnxx(q, page=0):
    results = []
    try:
        url = f"https://www.xnxx.com/search/{requests.utils.quote(q)}/{page}"
        res = safe_get(url)
        if not res:
            return results
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
        print(f"XNXX q={q!r} p={page}: {len(results)} items")
    except Exception as e:
        print(f"XNXX error: {e}")
    return results


def scrape_pornhub(q, page=1):
    results = []
    try:
        url = f"https://www.pornhub.com/video/search?search={requests.utils.quote(q)}&p={page}"
        res = safe_get(url)
        if not res:
            return results
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
        print(f"Pornhub q={q!r} p={page}: {len(results)} items")
    except Exception as e:
        print(f"Pornhub error: {e}")
    return results


def scrape_beeg(q, page=1):
    results = []
    try:
        url = f"https://beeg.com/index.php?query={requests.utils.quote(q)}&page={page}"
        res = safe_get(url)
        if not res or res.status_code != 200:
            return results
        soup = BeautifulSoup(res.text, 'html.parser')
        for item in soup.select('[data-id], .video-item, article.video'):
            try:
                link_el = item.select_one('a[href]')
                title_el = item.select_one('.title, h3, [class*="title"]')
                img_el = item.select_one('img[data-src], img[src]')
                if not (link_el and title_el):
                    continue
                title = safe_get_text(title_el)
                href = link_el.get('href', '')
                full_url = ('https://beeg.com' + href) if href.startswith('/') else href
                thumb = (img_el.get('data-src') or img_el.get('src') or '') if img_el else ''
                dur_el = item.select_one('.duration, [class*="dur"]')
                add_record(results, title, full_url, thumb, "Beeg",
                           parse_duration(safe_get_text(dur_el)) if dur_el else 600)
            except:
                continue
        print(f"Beeg q={q!r} p={page}: {len(results)} items")
    except Exception as e:
        print(f"Beeg error: {e}")
    return results


def scrape_camstreams(q, page=1):
    results = []
    try:
        for url in [
            f"https://camstreams.tv/search/{requests.utils.quote(q)}/videos/{page}/",
            f"https://www.camstreams.tv/search/?q={requests.utils.quote(q)}&page={page}",
            f"https://camstreams.tv/?s={requests.utils.quote(q)}",
        ]:
            res = safe_get(url, extra_headers={'Referer': 'https://camstreams.tv/'})
            if not res or res.status_code != 200:
                continue
            soup = BeautifulSoup(res.text, 'html.parser')
            seen = set()
            for item in soup.select('.thumb, .video-item, .item, article, [class*="thumb"], [class*="video"]'):
                try:
                    link_el = item.find('a', href=True)
                    if not link_el:
                        continue
                    href = link_el.get('href', '').strip()
                    if not href or href in ('/', '#') or any(x in href for x in ['/tag/', '/cat/', '/page/']):
                        continue
                    full_url = href if href.startswith('http') else 'https://camstreams.tv' + href
                    if full_url in seen:
                        continue
                    seen.add(full_url)
                    title = (link_el.get('title') or safe_get_text(item.select_one('.title, h3, h4, [class*="title"]'))).strip()
                    if not title:
                        continue
                    img_el = item.find('img')
                    thumb = (img_el.get('data-src') or img_el.get('src') or '') if img_el else ''
                    add_record(results, title, full_url, thumb, "CamStreams")
                except:
                    continue
            if results:
                break
        print(f"CamStreams q={q!r} p={page}: {len(results)} items")
    except Exception as e:
        print(f"CamStreams error: {e}")
    return results



def scrape_camwhores(q, page=1):
    results = []
    try:
        for url in [
            f"https://www.camwhores.tv/search/{requests.utils.quote(q)}/videos/{page}/",
            f"https://camwhores.tv/search/?q={requests.utils.quote(q)}&page={page}",
        ]:
            res = safe_get(url, extra_headers={'Referer': 'https://camwhores.tv/'})
            if not res or res.status_code != 200:
                continue
            soup = BeautifulSoup(res.text, 'html.parser')
            seen = set()
            for item in soup.select('.thumb, .video-item, .item, article, [class*="thumb"], [class*="video"]'):
                try:
                    link_el = item.find('a', href=True)
                    if not link_el:
                        continue
                    href = link_el.get('href', '').strip()
                    if not href or href in ('/', '#') or any(x in href for x in ['/tag/', '/cat/', '/page/']):
                        continue
                    full_url = href if href.startswith('http') else 'https://www.camwhores.tv' + href
                    if full_url in seen:
                        continue
                    seen.add(full_url)
                    title = (link_el.get('title') or safe_get_text(item.select_one('.title, h3, h4, [class*="title"]'))).strip()
                    if not title:
                        continue
                    img_el = item.find('img')
                    thumb = (img_el.get('data-src') or img_el.get('src') or '') if img_el else ''
                    dur_el = item.select_one('.duration, [class*="dur"]')
                    add_record(results, title, full_url, thumb, "CamWhores",
                               parse_duration(safe_get_text(dur_el)) if dur_el else 600)
                except:
                    continue
            if results:
                break
        print(f"CamWhores q={q!r} p={page}: {len(results)} items")
    except Exception as e:
        print(f"CamWhores error: {e}")
    return results


def _generic_scrape(q, page, base_url, search_url, source, item_sel, title_sel, link_sel, img_sel, dur_sel=None):
    """Shared HTML scraper for sites with standard grid layouts."""
    results = []
    try:
        res = safe_get(search_url)
        if not res or res.status_code != 200:
            return results
        soup = BeautifulSoup(res.text, 'html.parser')
        for item in soup.select(item_sel):
            try:
                title_el = item.select_one(title_sel) if title_sel else None
                link_el = item.select_one(link_sel) if link_sel else item.select_one('a[href]')
                img_el = item.select_one(img_sel) if img_sel else item.select_one('img')
                if not link_el:
                    continue
                title = safe_get_text(title_el) if title_el else (link_el.get('title') or '').strip()
                if not title:
                    continue
                href = link_el.get('href', '')
                full_url = (base_url + href) if (href.startswith('/') and base_url) else href
                if not full_url.startswith('http'):
                    continue
                thumb = ''
                if img_el:
                    thumb = img_el.get('data-src') or img_el.get('data-original') or img_el.get('src') or ''
                dur = 600
                if dur_sel:
                    dur_el = item.select_one(dur_sel)
                    if dur_el:
                        dur = parse_duration(safe_get_text(dur_el))
                add_record(results, title, full_url, thumb, source, dur)
            except:
                continue
        print(f"{source} q={q!r} p={page}: {len(results)} items")
    except Exception as e:
        print(f"{source} error: {e}")
    return results


def scrape_redtube(q, page=1):
    return _generic_scrape(q, page,
        'https://www.redtube.com',
        f'https://www.redtube.com/?search={requests.utils.quote(q)}&page={page}',
        'RedTube',
        '.video_link, .videoblock, li.pcVideoListItem',
        '.title a, .video-title a, span.title',
        'a[href*="/"]',
        'img[data-src], img[src]',
        '.duration, .video-duration')

def scrape_youporn(q, page=1):
    return _generic_scrape(q, page,
        'https://www.youporn.com',
        f'https://www.youporn.com/search/videos/?search={requests.utils.quote(q)}&page={page}',
        'YouPorn',
        '.video-box, .videoBox, li.pcVideoListItem',
        '.title a, span.title a',
        'a[href]',
        'img[data-src], img[src]',
        '.duration')

def scrape_tube8(q, page=1):
    return _generic_scrape(q, page,
        'https://www.tube8.com',
        f'https://www.tube8.com/search/?q={requests.utils.quote(q)}&page={page}',
        'Tube8',
        '.videoBox, li.pcVideoListItem, .video-box',
        '.title a, span.title a',
        'a[href]',
        'img[data-src], img[src]',
        '.duration')

def scrape_hqporner(q, page=1):
    return _generic_scrape(q, page,
        'https://hqporner.com',
        f'https://hqporner.com/?q={requests.utils.quote(q)}&p={page}',
        'HQporner',
        '.col-6, .video-item, article',
        'h3 a, h2 a, .title a',
        'a[href]',
        'img[data-src], img[src]',
        '.duration, .video-duration')

def scrape_txxx(q, page=1):
    return _generic_scrape(q, page,
        'https://txxx.com',
        f'https://txxx.com/search/?q={requests.utils.quote(q)}&page={page}',
        'TXXX',
        '.item, .thumb, .video-item',
        '.title, h3, .video-title',
        'a[href]',
        'img[data-src], img[src]',
        '.duration')

def scrape_drtuber(q, page=1):
    return _generic_scrape(q, page,
        'https://www.drtuber.com',
        f'https://www.drtuber.com/video/search?q={requests.utils.quote(q)}&p={page}',
        'DrTuber',
        '.video_item, .thumb_item, li.item',
        '.title a, h3 a',
        'a[href]',
        'img[data-src], img[src]',
        '.duration')

def scrape_tnaflix(q, page=1):
    return _generic_scrape(q, page,
        'https://www.tnaflix.com',
        f'https://www.tnaflix.com/search?what={requests.utils.quote(q)}&page={page}',
        'TNAFlix',
        '.videoWrapper, .thumb, .video-item',
        '.title a, h3 a, .videoTitle',
        'a[href]',
        'img[data-src], img[src]',
        '.duration')

def scrape_anysex(q, page=1):
    return _generic_scrape(q, page,
        'https://anysex.com',
        f'https://anysex.com/?q={requests.utils.quote(q)}&page={page}',
        'AnySex',
        '.item, .thumb, .videoblock',
        '.title, h3, .video-title',
        'a[href]',
        'img[data-src], img[src]',
        '.duration')

def scrape_perfectgirls(q, page=1):
    return _generic_scrape(q, page,
        'https://www.perfectgirls.net',
        f'https://www.perfectgirls.net/?q={requests.utils.quote(q)}&page={page}',
        'Perfect Girls',
        '.item, .thumb, .video_item',
        '.title a, h3 a',
        'a[href]',
        'img[data-src], img[src]',
        '.duration')

def scrape_porndoe(q, page=1):
    return _generic_scrape(q, page,
        'https://porndoe.com',
        f'https://porndoe.com/search?q={requests.utils.quote(q)}&page={page}',
        'PornDoe',
        '.video-item, .thumb, article',
        '.title a, h3 a, .video-title',
        'a[href]',
        'img[data-src], img[src]',
        '.duration')

def scrape_xfreehd(q, page=1):
    return _generic_scrape(q, page,
        'https://xfreehd.com',
        f'https://xfreehd.com/search/{requests.utils.quote(q)}/{page}/',
        'XFreeHD',
        '.video-item, .thumb_item, .item',
        '.title a, h3 a',
        'a[href]',
        'img[data-src], img[src]',
        '.duration')

def scrape_fullporner(q, page=1):
    return _generic_scrape(q, page,
        'https://fullporner.com',
        f'https://fullporner.com/?q={requests.utils.quote(q)}&p={page}',
        'FullPorner',
        '.col-6, .video-item, .item',
        'h3 a, h2 a, .title a',
        'a[href]',
        'img[data-src], img[src]',
        '.duration')

def scrape_porn300(q, page=1):
    return _generic_scrape(q, page,
        'https://www.porn300.com',
        f'https://www.porn300.com/search/?q={requests.utils.quote(q)}&p={page}',
        'Porn300',
        '.thumb, .video-item, .item',
        '.title a, h3 a',
        'a[href]',
        'img[data-src], img[src]',
        '.duration')

def scrape_pornobaee(q, page=1):
    return _generic_scrape(q, page,
        'https://pornobae.com',
        f'https://pornobae.com/search/{requests.utils.quote(q)}/{page}/',
        'PornoBae',
        '.video-item, .thumb, .item',
        '.title a, h3 a',
        'a[href]',
        'img[data-src], img[src]',
        '.duration')

def scrape_letsjerk(q, page=1):
    return _generic_scrape(q, page,
        'https://letsjerk.tv',
        f'https://letsjerk.tv/search/{requests.utils.quote(q)}/{page}/',
        'LetsJerk',
        '.item, .video-item, .thumb',
        '.title a, h3 a',
        'a[href]',
        'img[data-src], img[src]',
        '.duration')

def scrape_pornhat(q, page=1):
    return _generic_scrape(q, page,
        'https://pornhat.com',
        f'https://pornhat.com/search/{requests.utils.quote(q)}/{page}/',
        'PornHat',
        '.video-item, .item, .thumb',
        '.title a, h3 a',
        'a[href]',
        'img[data-src], img[src]',
        '.duration')

def scrape_netfapx(q, page=1):
    return _generic_scrape(q, page,
        'https://netfapx.com',
        f'https://netfapx.com/search/{requests.utils.quote(q)}/{page}/',
        'NetFapX',
        '.item, .video-item, .thumb',
        '.title a, h3 a',
        'a[href]',
        'img[data-src], img[src]',
        '.duration')

def scrape_inporn(q, page=1):
    return _generic_scrape(q, page,
        'https://www.inporn.com',
        f'https://www.inporn.com/search/?q={requests.utils.quote(q)}&page={page}',
        'InPorn',
        '.item, .video-item, .thumb',
        '.title a, h3 a',
        'a[href]',
        'img[data-src], img[src]',
        '.duration')

def scrape_txxx_style(name, base, search_tpl, q, page):
    """Shared scraper for TXXX-family sites (txxx, tubepornclassic, etc)."""
    return _generic_scrape(q, page, base,
        search_tpl.format(q=requests.utils.quote(q), page=page),
        name,
        '.item, .thumb, .video_item',
        '.title, h3, .video-title',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_porndig(q, page=1):
    return _generic_scrape(q, page,
        'https://porndig.com',
        f'https://porndig.com/search?q={requests.utils.quote(q)}&page={page}',
        'PornDig',
        '.item, .video-item, .thumb',
        '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_pornhoarder(q, page=1):
    return _generic_scrape(q, page,
        'https://pornhoarder.tv',
        f'https://pornhoarder.tv/search/{requests.utils.quote(q)}/{page}/',
        'PornHoarder',
        '.item, .video-item, .thumb',
        '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_pussyspace(q, page=1):
    return _generic_scrape(q, page,
        'https://pussyspace.com',
        f'https://pussyspace.com/search/{requests.utils.quote(q)}/{page}/',
        'PussySpace',
        '.item, .video-item, .thumb',
        '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_xmoviesforyou(q, page=1):
    return _generic_scrape(q, page,
        'https://xmoviesforyou.com',
        f'https://xmoviesforyou.com/search/{requests.utils.quote(q)}/{page}/',
        'XMoviesForYou',
        '.item, .video-item, .thumb',
        '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_porntop(q, page=1):
    return _generic_scrape(q, page,
        'https://porntop.com',
        f'https://porntop.com/search/{requests.utils.quote(q)}/{page}/',
        'PornTop',
        '.item, .video-item, .thumb',
        '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_pornxp(q, page=1):
    return _generic_scrape(q, page,
        'https://pornxp.com',
        f'https://pornxp.com/search/{requests.utils.quote(q)}/{page}/',
        'PornXP',
        '.item, .video-item, .thumb',
        '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_porn00(q, page=1):
    return _generic_scrape(q, page,
        'https://www.porn00.org',
        f'https://www.porn00.org/search/{requests.utils.quote(q)}/{page}/',
        'Porn00',
        '.item, .video-item, .thumb',
        '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_freeo(q, page=1):
    return _generic_scrape(q, page,
        'https://www.freeomovie.to',
        f'https://www.freeomovie.to/search/{requests.utils.quote(q)}/{page}/',
        'FreeoMovie',
        '.item, .video-item, .thumb',
        '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_whoreshub(q, page=1):
    return _generic_scrape(q, page,
        'https://whoreshub.com',
        f'https://whoreshub.com/search/{requests.utils.quote(q)}/{page}/',
        'WhoresHub',
        '.item, .video-item, .thumb',
        '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_porntex(q, page=1):
    return _generic_scrape(q, page,
        'https://www.porntex.com',
        f'https://www.porntex.com/search/?q={requests.utils.quote(q)}&p={page}',
        'PornTrex',
        '.item, .video-item, .thumb',
        '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_4kporn(q, page=1):
    return _generic_scrape(q, page,
        'https://4kporn.xxx',
        f'https://4kporn.xxx/search/{requests.utils.quote(q)}/{page}/',
        '4kPorn',
        '.item, .video-item, .thumb',
        '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_yourporn(q, page=1):
    return _generic_scrape(q, page,
        'https://yourporn.sexy',
        f'https://yourporn.sexy/search/?q={requests.utils.quote(q)}&page={page}',
        'YourPorn',
        '.item, .video-item, .thumb, .post',
        '.title a, h3 a, a[title]',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_xxxfiles(q, page=1):
    return _generic_scrape(q, page,
        'https://xxxfiles.com',
        f'https://xxxfiles.com/search/{requests.utils.quote(q)}/{page}/',
        'XXXFiles',
        '.item, .video-item, .thumb',
        '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_erome(q, page=1):
    results = []
    try:
        url = f"https://www.erome.com/search?q={requests.utils.quote(q)}&page={page}"
        res = safe_get(url, extra_headers={'Accept': 'text/html'})
        if not res or res.status_code != 200:
            return results
        soup = BeautifulSoup(res.text, 'html.parser')
        for item in soup.select('.album-link, .album, [class*="album"]'):
            try:
                link_el = item if item.name == 'a' else item.select_one('a[href]')
                if not link_el:
                    continue
                href = link_el.get('href', '')
                full_url = ('https://www.erome.com' + href) if href.startswith('/') else href
                title_el = item.select_one('p, .title, h3')
                title = safe_get_text(title_el) or link_el.get('title', '')
                if not title:
                    continue
                img_el = item.select_one('img')
                thumb = (img_el.get('data-src') or img_el.get('src') or '') if img_el else ''
                add_record(results, title, full_url, thumb, "EroMe")
            except:
                continue
        print(f"EroMe q={q!r} p={page}: {len(results)} items")
    except Exception as e:
        print(f"EroMe error: {e}")
    return results

def scrape_motherless(q, page=1):
    results = []
    try:
        url = f"https://motherless.com/gv/straight?search_term={requests.utils.quote(q)}&page={page}"
        res = safe_get(url)
        if not res or res.status_code != 200:
            return results
        soup = BeautifulSoup(res.text, 'html.parser')
        for item in soup.select('.thumb-container, .video-thumb'):
            try:
                link_el = item.select_one('a[href*="/"]')
                title_el = item.select_one('.filename, .title, span')
                img_el = item.select_one('img')
                if not link_el:
                    continue
                title = safe_get_text(title_el) or link_el.get('title', '')
                if not title:
                    continue
                href = link_el.get('href', '')
                full_url = ('https://motherless.com' + href) if href.startswith('/') else href
                thumb = (img_el.get('data-src') or img_el.get('src') or '') if img_el else ''
                add_record(results, title, full_url, thumb, "Motherless")
            except:
                continue
        print(f"Motherless q={q!r} p={page}: {len(results)} items")
    except Exception as e:
        print(f"Motherless error: {e}")
    return results


# ==================== ALT SCRAPERS (BDSM / TRANS / FETISH) ====================

def scrape_porncom(q, page=1):
    return _generic_scrape(q, page, 'https://www.porn.com',
        f'https://www.porn.com/search/?search={requests.utils.quote(q)}&page={page}',
        'Porn.com', '.item, .video-item, .thumb', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_ixxx(q, page=1):
    return _generic_scrape(q, page, 'https://www.ixxx.com',
        f'https://www.ixxx.com/search/{requests.utils.quote(q)}/{page}/',
        'IXXX', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_vxxx(q, page=1):
    return _generic_scrape(q, page, 'https://www.vxxx.com',
        f'https://www.vxxx.com/search/{requests.utils.quote(q)}/{page}/',
        'VXXX', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_pornone(q, page=1):
    return _generic_scrape(q, page, 'https://pornone.com',
        f'https://pornone.com/search/?q={requests.utils.quote(q)}&page={page}',
        'PornOne', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_sxyprn(q, page=1):
    return _generic_scrape(q, page, 'https://sxyprn.com',
        f'https://sxyprn.com/search/{requests.utils.quote(q)}/{page}/',
        'SxyPrn', '.item, .thumb, .post', '.title a, h3 a, a[title]',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_boundhub(q, page=1):
    return _generic_scrape(q, page, 'https://boundhub.com',
        f'https://boundhub.com/search/?search_query={requests.utils.quote(q)}&page={page}',
        'BoundHub', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_thisvid(q, page=1):
    return _generic_scrape(q, page, 'https://thisvid.com',
        f'https://thisvid.com/search/?q={requests.utils.quote(q)}&page={page}',
        'ThisVid', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_hypnotube(q, page=1):
    return _generic_scrape(q, page, 'https://hypnotube.com',
        f'https://hypnotube.com/search/{requests.utils.quote(q)}/{page}/',
        'HypnoTube', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_heavyfetish(q, page=1):
    return _generic_scrape(q, page, 'https://heavyfetish.com',
        f'https://heavyfetish.com/search/{requests.utils.quote(q)}/{page}/',
        'HeavyFetish', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_tubebdsm(q, page=1):
    return _generic_scrape(q, page, 'https://www.tubebdsm.com',
        f'https://www.tubebdsm.com/search/{requests.utils.quote(q)}/{page}/',
        'TubeBDSM', '.item, .thumb, .video-item, .videoblock', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_spankingtube(q, page=1):
    return _generic_scrape(q, page, 'https://spankingtube.com',
        f'https://spankingtube.com/search/{requests.utils.quote(q)}/{page}/',
        'SpankingTube', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_bdsmstreak(q, page=1):
    return _generic_scrape(q, page, 'https://bdsmstreak.com',
        f'https://bdsmstreak.com/search/{requests.utils.quote(q)}/{page}/',
        'BdsmStreak', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_bdsmone(q, page=1):
    return _generic_scrape(q, page, 'https://bdsm.one',
        f'https://bdsm.one/search/{requests.utils.quote(q)}/{page}/',
        'BDSM.one', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_punishbang(q, page=1):
    return _generic_scrape(q, page, 'https://punishbang.com',
        f'https://punishbang.com/search/{requests.utils.quote(q)}/{page}/',
        'PunishBang', '.item, .thumb, .video-item, .videoblock', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_hcbdsm(q, page=1):
    return _generic_scrape(q, page, 'https://hcbdsm.com',
        f'https://hcbdsm.com/search/{requests.utils.quote(q)}/{page}/',
        'hcBDSM', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_bondagevalley(q, page=1):
    return _generic_scrape(q, page, 'https://bondagevalley.cc',
        f'https://bondagevalley.cc/search/{requests.utils.quote(q)}/{page}/',
        'BondageValley', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_pornfd(q, page=1):
    return _generic_scrape(q, page, 'https://pornfd.com',
        f'https://pornfd.com/search/{requests.utils.quote(q)}/{page}/',
        'PornFD', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_femefun(q, page=1):
    return _generic_scrape(q, page, 'https://femefun.com',
        f'https://femefun.com/search/{requests.utils.quote(q)}/{page}/',
        'FemeFun', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_domporn(q, page=1):
    return _generic_scrape(q, page, 'https://domporn.net',
        f'https://domporn.net/search/{requests.utils.quote(q)}/{page}/',
        'DomPorn', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_bdsmx(q, page=1):
    return _generic_scrape(q, page, 'https://bdsmx.tube',
        f'https://bdsmx.tube/search/{requests.utils.quote(q)}/{page}/',
        'BDSMx', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_ashemaletube(q, page=1):
    return _generic_scrape(q, page, 'https://www.ashemaletube.com',
        f'https://www.ashemaletube.com/search/?q={requests.utils.quote(q)}&page={page}',
        'aShemaleTube', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_shemalez(q, page=1):
    return _generic_scrape(q, page, 'https://shemalez.com',
        f'https://shemalez.com/search/{requests.utils.quote(q)}/{page}/',
        'Shemalez', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_transjizz(q, page=1):
    return _generic_scrape(q, page, 'https://transjizz.com',
        f'https://transjizz.com/search/{requests.utils.quote(q)}/{page}/',
        'TransJizz', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_trannytube(q, page=1):
    return _generic_scrape(q, page, 'https://trannytube.tv',
        f'https://trannytube.tv/search/{requests.utils.quote(q)}/{page}/',
        'TrannyTube', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_shemale6(q, page=1):
    return _generic_scrape(q, page, 'https://shemale6.com',
        f'https://shemale6.com/search/{requests.utils.quote(q)}/{page}/',
        'Shemale6', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_tgtube(q, page=1):
    return _generic_scrape(q, page, 'https://tgtube.com',
        f'https://tgtube.com/search/{requests.utils.quote(q)}/{page}/',
        'TGTube', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_trannyvideosxxx(q, page=1):
    return _generic_scrape(q, page, 'https://trannyvideosxxx.com',
        f'https://trannyvideosxxx.com/search/{requests.utils.quote(q)}/{page}/',
        'TrannyVideosXXX', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_xshemale(q, page=1):
    return _generic_scrape(q, page, 'https://xshemale.tv',
        f'https://xshemale.tv/search/{requests.utils.quote(q)}/{page}/',
        'XShemale', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_shemaletubevideos(q, page=1):
    return _generic_scrape(q, page, 'https://shemaletubevideos.com',
        f'https://shemaletubevideos.com/search/{requests.utils.quote(q)}/{page}/',
        'ShemaleTubeVideos', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_transflix(q, page=1):
    return _generic_scrape(q, page, 'https://transflix.net',
        f'https://transflix.net/search/{requests.utils.quote(q)}/{page}/',
        'TransFlix', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_gettranny(q, page=1):
    return _generic_scrape(q, page, 'https://gettranny.com',
        f'https://gettranny.com/search/{requests.utils.quote(q)}/{page}/',
        'GetTranny', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_spicytranny(q, page=1):
    return _generic_scrape(q, page, 'https://spicytranny.com',
        f'https://spicytranny.com/search/{requests.utils.quote(q)}/{page}/',
        'SpicyTranny', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_trannyone(q, page=1):
    return _generic_scrape(q, page, 'https://www.tranny.one',
        f'https://www.tranny.one/search/{requests.utils.quote(q)}/{page}/',
        'Tranny.one', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_tsmodelstube(q, page=1):
    return _generic_scrape(q, page, 'https://tsmodelstube.com',
        f'https://tsmodelstube.com/search/{requests.utils.quote(q)}/{page}/',
        'TSModelsTube', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_abtranny(q, page=1):
    return _generic_scrape(q, page, 'https://abtranny.com',
        f'https://abtranny.com/search/{requests.utils.quote(q)}/{page}/',
        'ABTranny', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_transhub(q, page=1):
    return _generic_scrape(q, page, 'https://transhub.to',
        f'https://transhub.to/search/{requests.utils.quote(q)}/{page}/',
        'TransHub', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_transtube(q, page=1):
    return _generic_scrape(q, page, 'https://transtube.tv',
        f'https://transtube.tv/search/{requests.utils.quote(q)}/{page}/',
        'TransTube', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_shemale777(q, page=1):
    return _generic_scrape(q, page, 'https://shemale777.com',
        f'https://shemale777.com/search/{requests.utils.quote(q)}/{page}/',
        'Shemale777', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_transvids(q, page=1):
    return _generic_scrape(q, page, 'https://transvids.tv',
        f'https://transvids.tv/search/{requests.utils.quote(q)}/{page}/',
        'TransVids', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')

def scrape_shemalevids(q, page=1):
    return _generic_scrape(q, page, 'https://shemalevids.org',
        f'https://shemalevids.org/search/{requests.utils.quote(q)}/{page}/',
        'ShemaleVids', '.item, .thumb, .video-item', '.title a, h3 a',
        'a[href]', 'img[data-src], img[src]', '.duration')


ALT_SCRAPERS = [
    # General tubes (reused from main)
    scrape_pornhub, scrape_xvideos, scrape_xhamster, scrape_xnxx,
    scrape_youporn, scrape_redtube, scrape_eporner, scrape_tube8, scrape_txxx,
    # New general
    scrape_porncom, scrape_ixxx, scrape_vxxx, scrape_pornone, scrape_sxyprn,
    # BDSM / Fetish
    scrape_boundhub, scrape_thisvid, scrape_hypnotube, scrape_heavyfetish,
    scrape_tubebdsm, scrape_spankingtube, scrape_bdsmstreak, scrape_bdsmone,
    scrape_punishbang, scrape_hcbdsm, scrape_bondagevalley, scrape_pornfd,
    scrape_femefun, scrape_domporn, scrape_bdsmx,
    # Trans / Shemale
    scrape_ashemaletube, scrape_shemalez, scrape_transjizz, scrape_trannytube,
    scrape_shemale6, scrape_tgtube, scrape_trannyvideosxxx, scrape_xshemale,
    scrape_shemaletubevideos, scrape_transflix, scrape_gettranny, scrape_spicytranny,
    scrape_trannyone, scrape_tsmodelstube, scrape_abtranny, scrape_transhub,
    scrape_transtube, scrape_shemale777, scrape_transvids, scrape_shemalevids,
]

ALT_DB_FILE = os.path.join(BASE_DIR, "alt_db.json")

def load_alt_db():
    if not os.path.exists(ALT_DB_FILE):
        return []
    try:
        with open(ALT_DB_FILE, "r", encoding="utf-8") as f:
            return json.loads(f.read().strip() or "[]")
    except:
        return []

def save_alt_db(data):
    try:
        with open(ALT_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except:
        pass

def _do_alt_scrape(sub_queries, site_pages):
    with ThreadPoolExecutor(max_workers=32) as executor:
        futures = []
        for sq in sub_queries:
            for pg in site_pages:
                for scraper in ALT_SCRAPERS:
                    p = pg - 1 if scraper in (scrape_xvideos, scrape_xnxx) else pg
                    futures.append((executor.submit(scraper, sq, p), sq))
            futures.append((executor.submit(scrape_spankbang_bulk, sq, site_pages), sq))
        return _collect(futures)

def run_alt_scrape(query, page=1, preferred_source=None, sort_by='default'):
    exact = is_exact(query)
    clean = strip_quotes(query)
    if not exact and "," in clean:
        sub_queries = [q.strip() for q in clean.split(",") if q.strip()]
    else:
        sub_queries = [clean] if clean else ["bdsm", "trans", "fetish"]

    page_size = 100
    start = (page - 1) * page_size
    need_up_to = start + page_size

    master_db = load_alt_db()
    pool = _build_pool(master_db, sub_queries, exact, clean)

    if len(pool) < need_up_to:
        already = max(len(pool) // max(len(sub_queries), 1) // 25, 0)
        batch_start = already + 1
        batch_size = 1 if page == 1 else 3
        site_pages = list(range(batch_start, batch_start + batch_size))
        aggregated = _do_alt_scrape(sub_queries, site_pages)
        existing_urls = {x["url"] for x in master_db if "url" in x}
        new_records, seen = [], set()
        for r in aggregated:
            u = r.get("url")
            t = (r.get("title") or '').strip()
            if u and t and u not in existing_urls and u not in seen:
                new_records.append(r)
                seen.add(u)
        if new_records:
            master_db = master_db + new_records
            save_alt_db(master_db)
        pool = _build_pool(master_db, sub_queries, exact, clean)
        if not pool:
            pool = new_records

    if preferred_source and preferred_source != "All":
        pool = [r for r in pool if r.get("source", "").lower() == preferred_source.lower()]

    if sort_by == 'duration_desc':
        pool = sorted(pool, key=lambda r: r.get('duration', 0), reverse=True)
    elif sort_by == 'duration_asc':
        pool = sorted(pool, key=lambda r: r.get('duration', 0))
    elif sort_by == 'date_desc':
        pool = sorted(pool, key=lambda r: r.get('added_date', ''), reverse=True)

    return pool[start:start + page_size]


# ==================== ORCHESTRATION ====================

# All scrapers except SpankBang (handled via bulk)
# Fast tier — known to return results quickly
SCRAPERS_FAST = [
    scrape_eporner,
    scrape_xhamster,
    scrape_xvideos,
    scrape_xnxx,
    scrape_pornhub,
    scrape_anysex,
    scrape_perfectgirls,
    scrape_porntop,
    scrape_txxx,
    scrape_camstreams,
    scrape_camwhores,
]

# Slow tier — tried on page 2+
SCRAPERS_SLOW = [
    scrape_beeg,
    scrape_redtube,
    scrape_youporn,
    scrape_tube8,
    scrape_hqporner,
    scrape_drtuber,
    scrape_tnaflix,
    scrape_porndoe,
    scrape_xfreehd,
    scrape_fullporner,
    scrape_porn300,
    scrape_pornobaee,
    scrape_letsjerk,
    scrape_pornhat,
    scrape_netfapx,
    scrape_inporn,
    scrape_porndig,
    scrape_pornhoarder,
    scrape_pussyspace,
    scrape_xmoviesforyou,
    scrape_pornxp,
    scrape_porn00,
    scrape_freeo,
    scrape_whoreshub,
    scrape_porntex,
    scrape_4kporn,
    scrape_yourporn,
    scrape_xxxfiles,
    scrape_erome,
    scrape_motherless,
]

SCRAPERS_NO_SB = SCRAPERS_FAST + SCRAPERS_SLOW


def _collect(futures_with_sq):
    out = []
    for f, sq in futures_with_sq:
        try:
            for r in f.result(timeout=8):
                r['_q'] = sq.lower()
                out.append(r)
        except Exception as e:
            pass
    return out


def _do_scrape(sub_queries, site_pages, fast_only=False):
    scrapers = SCRAPERS_FAST if fast_only else SCRAPERS_NO_SB
    with ThreadPoolExecutor(max_workers=32) as executor:
        futures = []
        for sq in sub_queries:
            for pg in site_pages:
                for scraper in scrapers:
                    p = pg - 1 if scraper in (scrape_xvideos, scrape_xnxx) else pg
                    futures.append((executor.submit(scraper, sq, p), sq))
            futures.append((executor.submit(scrape_spankbang_bulk, sq, site_pages), sq))
        return _collect(futures)


def _save_new(aggregated, master_db):
    existing_urls = {x["url"] for x in master_db if "url" in x}
    new_records, seen = [], set()
    for r in aggregated:
        u = r.get("url")
        t = (r.get("title") or '').strip()
        if u and t and u not in existing_urls and u not in seen:
            new_records.append(r)
            seen.add(u)
    if new_records:
        save_db(master_db + new_records)
    return new_records


def _build_pool(master_db, sub_queries, exact, clean):
    qs = {sq.lower() for sq in sub_queries}
    if exact:
        phrase = clean.lower()
        return [r for r in master_db if phrase in r.get("title", "").lower()]
    pool = [r for r in master_db if r.get("_q", "") in qs]
    return pool


def seed_database():
    master_db = load_db()
    aggregated = _do_scrape(DEFAULT_SEED_QUERIES[:3], list(range(1, 4)))
    new_records = _save_new(aggregated, master_db)
    print(f"Seeded {len(new_records)} new records.")
    return master_db + new_records


def run_deep_target_scrape(query, page=1, preferred_source=None, sort_by='default'):
    exact = is_exact(query)
    clean = strip_quotes(query)

    if not exact and "," in clean:
        sub_queries = [q.strip() for q in clean.split(",") if q.strip()]
    else:
        sub_queries = [clean] if clean else DEFAULT_SEED_QUERIES[:3]

    page_size = 100
    start = (page - 1) * page_size
    need_up_to = start + page_size  # need at least this many in pool

    master_db = load_db()
    pool = _build_pool(master_db, sub_queries, exact, clean)

    if len(pool) < need_up_to:
        already = max(len(pool) // max(len(sub_queries), 1) // 25, 0)
        batch_start = already + 1
        # Page 1: 1 site-page, fast scrapers only → results in ~3s
        # Page 2+: 3 site-pages, all scrapers
        batch_size = 1 if page == 1 else 3
        fast_only = (page == 1)
        site_pages = list(range(batch_start, batch_start + batch_size))
        aggregated = _do_scrape(sub_queries, site_pages, fast_only=fast_only)
        new_records = _save_new(aggregated, master_db)
        master_db = load_db()
        pool = _build_pool(master_db, sub_queries, exact, clean)
        if not pool:
            pool = new_records

    if preferred_source and preferred_source != "All":
        pool = [r for r in pool if r.get("source", "").lower() == preferred_source.lower()]

    # Sort
    if sort_by == 'duration_desc':
        pool = sorted(pool, key=lambda r: r.get('duration', 0), reverse=True)
    elif sort_by == 'duration_asc':
        pool = sorted(pool, key=lambda r: r.get('duration', 0))
    elif sort_by == 'date_desc':
        pool = sorted(pool, key=lambda r: r.get('added_date', ''), reverse=True)
    elif sort_by == 'date_asc':
        pool = sorted(pool, key=lambda r: r.get('added_date', ''))

    return pool[start:start + page_size]


ALT_DOMAINS = [
    "Porn.com", "IXXX", "VXXX", "PornOne", "SxyPrn", "Pornhub", "XVideos", "xHamster",
    "XNXX", "YouPorn", "RedTube", "SpankBang", "Eporner", "Tube8", "TXXX",
    "BoundHub", "ThisVid", "HypnoTube", "HeavyFetish", "TubeBDSM", "SpankingTube",
    "BdsmStreak", "BDSM.one", "PunishBang", "hcBDSM", "BondageValley", "PornFD",
    "FemeFun", "DomPorn", "BDSMx",
    "aShemaleTube", "Shemalez", "TransJizz", "TrannyTube", "Shemale6", "TGTube",
    "TrannyVideosXXX", "XShemale", "ShemaleTubeVideos", "TransFlix", "GetTranny",
    "SpicyTranny", "Tranny.one", "TSModelsTube", "ABTranny", "TransHub", "TransTube",
    "Shemale777", "TransVids", "ShemaleVids",
]

@app.route("/")
def index():
    return render_template("index.html", networks=TUBE_DOMAINS, alt_networks=ALT_DOMAINS)


@app.route("/fast_search", methods=["GET"])
def fast_search():
    query = request.args.get("query", "").strip()
    page = int(request.args.get("page", 1))
    preferred_source = request.args.get("source", None)
    sort_by = request.args.get("sort", "default")

    if any(fw in query.lower() for fw in FORBIDDEN_WORDS):
        return jsonify([])

    if query:
        return jsonify(run_deep_target_scrape(query, page=page, preferred_source=preferred_source, sort_by=sort_by))

    master_db = load_db()
    if len(master_db) < 50:
        master_db = seed_database()
    start = (page - 1) * 200
    return jsonify(master_db[start:start + 200])


@app.route("/alt_search", methods=["GET"])
def alt_search():
    query = request.args.get("query", "").strip()
    page = int(request.args.get("page", 1))
    preferred_source = request.args.get("source", None)
    sort_by = request.args.get("sort", "default")
    if not query:
        return jsonify([])
    return jsonify(run_alt_scrape(query, page=page, preferred_source=preferred_source, sort_by=sort_by))


@app.route("/clear_db", methods=["POST"])
def clear_db():
    try:
        save_db([])
        if os.path.exists(ALT_DB_FILE):
            with open(ALT_DB_FILE, "w", encoding="utf-8") as f:
                json.dump([], f)
        return jsonify({"status": "cleared"})
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)}), 500


if __name__ == "__main__":
    db = load_db()
    if len(db) < 100:
        print("\n--- Seeding database ---")
        seed_database()
        print(f"Database: {len(load_db())} records")
    print("\n--- SERVER RUNNING: http://127.0.0.1:5000 ---\n")
    app.run(debug=True, host="127.0.0.1", port=5000)
