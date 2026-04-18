"""
generic_scraper.py — Configurable multi-site real estate scraper for Andorra

Site-specific extraction logic (CSS selectors, URL patterns) lives in the SQLite
`sites` and `field_rules` tables.  To add a new estate-agent website insert rows
into those tables and re-run — no code changes required.

Selector types in field_rules.selector:
  css:SELECTOR      — standard CSS selector (default when no prefix)
  regex:PATTERN     — regex applied to full page text; group 1 captured if present
  url:PATTERN       — regex applied to the listing URL itself

Usage:
    python3 generic_scraper.py                # scrape all active sites
    python3 generic_scraper.py --list-sites   # print configured sites
    python3 generic_scraper.py --site "NAME"  # scrape one site by name
"""

import argparse
import json
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DB_PATH     = "realty.db"
PHOTOS_DIR  = "photos"
DELAY       = 1.5
SKIP_PHOTOS = False

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en,ca;q=0.9,es;q=0.8",
}

# ---------------------------------------------------------------------------
# Database schema
# ---------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS sites (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT    UNIQUE NOT NULL,
    base_url       TEXT    NOT NULL,
    listing_urls   TEXT    NOT NULL,   -- JSON array of starting page URLs
    link_pattern   TEXT    NOT NULL,   -- regex that matches a detail-page path
    next_page_tpl  TEXT,              -- pagination template, e.g. "{url}&page={n}"
    active         INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS field_rules (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id        INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    field_name     TEXT    NOT NULL,  -- target column in listings, or "images"
    selector       TEXT    NOT NULL,  -- selector or regex:/url: prefixed pattern
    attr           TEXT,             -- HTML attribute to read (NULL → .get_text())
    regex          TEXT,             -- optional cleanup regex; group 1 if present
    multi          INTEGER DEFAULT 0,-- 1 → join all matches with " | "
    after_heading  TEXT,             -- scope CSS search to content after this heading
    UNIQUE(site_id, field_name)
);

CREATE TABLE IF NOT EXISTS listings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id       INTEGER REFERENCES sites(id),
    url           TEXT    UNIQUE NOT NULL,
    ref           TEXT,
    title         TEXT,
    operation     TEXT,
    property_type TEXT,
    parish        TEXT,
    price         TEXT,
    size_m2       TEXT,
    rooms         TEXT,
    suite_rooms   TEXT,
    bathrooms     TEXT,
    floor         TEXT,
    parking       TEXT,
    terrace_m2    TEXT,
    year_built    TEXT,
    availability  TEXT,
    features      TEXT,
    amenities     TEXT,
    description   TEXT,
    energy_rating TEXT,
    agent_name    TEXT,
    agent_phone   TEXT,
    agent_email   TEXT,
    agent_web     TEXT,
    scraped_at    TEXT
);

CREATE TABLE IF NOT EXISTS photos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id   INTEGER REFERENCES listings(id),
    url          TEXT    UNIQUE NOT NULL,
    local_path   TEXT,
    downloaded   INTEGER DEFAULT 0
);
"""


def init_db(conn):
    conn.executescript(SCHEMA)
    conn.commit()


# ---------------------------------------------------------------------------
# Seed data — Andorra Sotheby's International Realty
#
# NOTE: Sotheby's HTML exposes very few CSS classes.  Most fields are extracted
#       via full-text regex ("regex:" prefix).  Selectors may need adjustment
#       if the site structure changes — update field_rules rows in the DB.
# ---------------------------------------------------------------------------
def seed_sothebys(conn):
    existing = conn.execute(
        "SELECT id FROM sites WHERE name = ?", ("Andorra Sotheby's",)
    ).fetchone()

    if existing:
        site_id = existing[0]
        # Migrations: update selectors that have been corrected
        migrations = {
            "rooms":      "regex:(?i)bedrooms?\\s+(\\d+)",
            "bathrooms":  "regex:(?i)bathrooms?\\s+(\\d+)",
            "size_m2":    "regex:(?i)area\\s+([\\d\\.]+)\\s*m",
            "price":      "regex:(?i)price\\s+(consult|[\\d][\\d\\.\\s,]*\\s*€)",
        }
        for field, selector in migrations.items():
            conn.execute(
                "UPDATE field_rules SET selector = ? WHERE site_id = ? AND field_name = ?",
                (selector, site_id, field),
            )
        conn.execute(
            "UPDATE sites SET next_page_tpl = ? WHERE name = ? AND next_page_tpl IS NULL",
            ("{url}?page={n}", "Andorra Sotheby's"),
        )
        conn.commit()
        return

    conn.execute("""
        INSERT INTO sites (name, base_url, listing_urls, link_pattern, next_page_tpl, active)
        VALUES (?, ?, ?, ?, ?, 1)
    """, (
        "Andorra Sotheby's",
        "https://www.andorra-sothebysrealty.com",
        json.dumps([
            "https://www.andorra-sothebysrealty.com/en/sale-and-rent/-all-types-andorra",
        ]),
        r"/en/[^/]+/\d+$",
        "{url}?page={n}",
    ))
    site_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # (field_name, selector, attr, regex, multi, after_heading)
    rules = [
        ("ref",           "url:/(\\d+)$",                              None,   None,                                  0, None),
        ("title",         "h1",                                         None,   None,                                  0, None),
        ("price",         "regex:(?i)price\\s+(consult|[\\d][\\d\\.\\s,]*\\s*€)", None, None,                           0, None),
        ("rooms",         "regex:(?i)bedrooms?\\s+(\\d+)",                None,   None,                                  0, None),
        ("bathrooms",     "regex:(?i)bathrooms?\\s+(\\d+)",              None,   None,                                  0, None),
        ("size_m2",       "regex:(?i)area\\s+([\\d\\.]+)\\s*m",         None,   None,                                  0, None),
        ("description",   "p",                                          None,   None,                                  0, None),
        ("features",      "li",                                         None,   None,                                  1, "Features"),
        ("agent_phone",   "a[href^='tel:']",                            "href", "tel:(.*)",                            0, None),
        ("agent_email",   "a[href^='mailto:']",                         "href", "mailto:(.*)",                         0, None),
        ("energy_rating", "img[src*='energetica']",                     "src",  r"energetica-(\w+)\.",                 0, None),
        ("images",        "img[src*='andorra-sothebysrealty.com']",     "src",  None,                                  1, None),
    ]

    conn.executemany("""
        INSERT INTO field_rules (site_id, field_name, selector, attr, regex, multi, after_heading)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, [(site_id, *r) for r in rules])

    conn.commit()
    print(f"  Seeded: Andorra Sotheby's (site_id={site_id})")


# ---------------------------------------------------------------------------
# Field extraction engine
# ---------------------------------------------------------------------------
def _container_after_heading(soup, heading_text):
    """Return the first block-level sibling after a heading containing heading_text."""
    for tag in soup.find_all(re.compile(r"^h[1-6]$")):
        if heading_text.lower() in tag.get_text(strip=True).lower():
            for sib in tag.find_next_siblings():
                if sib.name:
                    return sib
    return None


def _extract_one(el, attr, regex):
    val = el.get(attr, "") if attr else el.get_text(strip=True)
    if regex and val:
        m = re.search(regex, val)
        if not m:
            return ""
        val = (m.group(1) if m.lastindex else m.group(0)).strip()
    return val.strip()


def apply_rule(soup, url, rule):
    selector     = rule["selector"]
    attr         = rule["attr"]
    regex        = rule["regex"]
    multi        = rule["multi"]
    after        = rule["after_heading"]

    # URL-pattern extraction
    if selector.startswith("url:"):
        m = re.search(selector[4:], url)
        if not m:
            return None
        return (m.group(1) if m.lastindex else m.group(0)).strip()

    # Full-text regex
    if selector.startswith("regex:"):
        text = soup.get_text(separator=" ", strip=True)
        m = re.search(selector[6:], text)
        if not m:
            return None
        val = (m.group(1) if m.lastindex else m.group(0)).strip()
        return val or None

    # CSS selector (with optional heading scope)
    css = selector[4:] if selector.startswith("css:") else selector
    if after:
        container = _container_after_heading(soup, after)
        elements = container.select(css) if container else []
    else:
        elements = soup.select(css)

    if not elements:
        return None

    if multi:
        parts = [v for el in elements if (v := _extract_one(el, attr, regex))]
        return " | ".join(parts) if parts else None
    else:
        # For description-style rules with many matches, prefer the longest
        if not attr and not after and len(elements) > 1:
            best = max(elements, key=lambda el: len(el.get_text(strip=True)))
            return _extract_one(best, attr, regex) or None
        return _extract_one(elements[0], attr, regex) or None


def parse_detail(soup, url, rules, site_id):
    data = {
        "url": url,
        "site_id": site_id,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }
    photo_urls = []

    for rule in rules:
        field = rule["field_name"]

        if field == "images":
            css = rule["selector"]
            if css.startswith("css:"):
                css = css[4:]
            a = rule["attr"] or "src"
            for img in soup.select(css):
                src = img.get(a, "")
                if src:
                    if not src.startswith("http"):
                        src = urljoin(url, src)
                    if src not in photo_urls:
                        photo_urls.append(src)
            continue

        value = apply_rule(soup, url, rule)
        if value:
            data[field] = value

    return data, photo_urls


# ---------------------------------------------------------------------------
# Listing URL discovery
# ---------------------------------------------------------------------------
def iter_listing_urls(site):
    base_url      = site["base_url"]
    start_urls    = json.loads(site["listing_urls"])
    link_re       = re.compile(site["link_pattern"])
    next_page_tpl = site["next_page_tpl"]
    seen          = set()

    for start_url in start_urls:
        page = 1
        current_url = start_url
        while True:
            print(f"  Page {page}: {current_url}")
            try:
                soup = fetch(current_url)
            except requests.HTTPError as e:
                print(f"  HTTP {e} — stopping.")
                break

            found = 0
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if not href.startswith("http"):
                    href = urljoin(base_url, href)
                if link_re.search(href) and href not in seen:
                    seen.add(href)
                    found += 1
                    yield href

            print(f"  → {found} new listing URL(s)")

            if not next_page_tpl or found == 0:
                break
            page += 1
            current_url = next_page_tpl.format(url=start_url, n=page)
            time.sleep(DELAY)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
_session = requests.Session()


def fetch(url):
    resp = _session.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def download_file(url, dest_path):
    try:
        resp = _session.get(url, headers=HEADERS, timeout=60, stream=True)
        resp.raise_for_status()
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"    [photo error] {url}: {e}")
        return False


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------
def listing_exists(conn, url):
    return conn.execute(
        "SELECT 1 FROM listings WHERE url = ?", (url,)
    ).fetchone() is not None


def upsert_listing(conn, data):
    cols         = ", ".join(data.keys())
    placeholders = ", ".join("?" for _ in data)
    updates      = ", ".join(f"{k} = excluded.{k}" for k in data if k != "url")
    sql = (
        f"INSERT INTO listings ({cols}) VALUES ({placeholders}) "
        f"ON CONFLICT(url) DO UPDATE SET {updates}"
    )
    conn.execute(sql, list(data.values()))
    conn.commit()
    return conn.execute(
        "SELECT id FROM listings WHERE url = ?", (data["url"],)
    ).fetchone()[0]


def insert_photos(conn, listing_id, urls):
    pending = []
    for url in urls:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO photos (listing_id, url) VALUES (?, ?)",
                (listing_id, url),
            )
            row = conn.execute(
                "SELECT downloaded FROM photos WHERE url = ?", (url,)
            ).fetchone()
            if row and not row[0]:
                pending.append(url)
        except sqlite3.Error:
            pass
    conn.commit()
    return pending


def mark_photo_downloaded(conn, url, local_path):
    conn.execute(
        "UPDATE photos SET local_path = ?, downloaded = 1 WHERE url = ?",
        (local_path, url),
    )
    conn.commit()


def download_photos(conn, listing_id, photo_urls):
    pending = insert_photos(conn, listing_id, photo_urls)
    if not pending:
        return
    print(f"    Downloading {len(pending)} photo(s)…")
    for url in pending:
        filename = url.split("/")[-1].split("?")[0] or "photo.jpg"
        dest = os.path.join(PHOTOS_DIR, str(listing_id), filename)
        if os.path.exists(dest):
            mark_photo_downloaded(conn, url, dest)
            continue
        time.sleep(0.2)
        if download_file(url, dest):
            mark_photo_downloaded(conn, url, dest)
            print(f"      ✓ {filename}")
        else:
            print(f"      ✗ {filename}")


# ---------------------------------------------------------------------------
# Per-site scrape loop
# ---------------------------------------------------------------------------
def scrape_site(conn, site):
    rows = conn.execute(
        "SELECT id, site_id, field_name, selector, attr, regex, multi, after_heading "
        "FROM field_rules WHERE site_id = ? ORDER BY id",
        (site["id"],),
    ).fetchall()
    cols  = ["id", "site_id", "field_name", "selector", "attr", "regex", "multi", "after_heading"]
    rules = [dict(zip(cols, r)) for r in rows]

    total_new = total_skipped = 0

    for listing_url in iter_listing_urls(site):
        if listing_exists(conn, listing_url):
            total_skipped += 1
            continue

        print(f"  [{site['name']}] {listing_url}")
        try:
            soup = fetch(listing_url)
        except requests.HTTPError as e:
            print(f"    HTTP error: {e}")
            time.sleep(DELAY)
            continue

        data, photo_urls = parse_detail(soup, listing_url, rules, site["id"])
        listing_id = upsert_listing(conn, data)
        total_new += 1

        print(
            f"    {data.get('title', '')[:55]} | "
            f"{data.get('price', '')} | "
            f"{data.get('size_m2', '')}m² | "
            f"{data.get('rooms', '')} hab | "
            f"{len(photo_urls)} photos"
        )

        if not SKIP_PHOTOS:
            download_photos(conn, listing_id, photo_urls)

        time.sleep(DELAY)

    return total_new, total_skipped


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Configurable Andorra real-estate scraper")
    parser.add_argument("--list-sites", action="store_true", help="Print configured sites and exit")
    parser.add_argument("--site", metavar="NAME", help="Scrape only the named site")
    args = parser.parse_args()

    os.makedirs(PHOTOS_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    seed_sothebys(conn)

    if args.list_sites:
        rows = conn.execute(
            "SELECT id, name, base_url, active FROM sites ORDER BY id"
        ).fetchall()
        for r in rows:
            status = "active" if r[3] else "inactive"
            print(f"  [{r[0]}] {r[1]}  {r[2]}  ({status})")
        conn.close()
        return

    where  = "WHERE active = 1"
    params = []
    if args.site:
        if args.site.isdigit():
            where += " AND id = ?"
            params.append(int(args.site))
        else:
            where += " AND name = ?"
            params.append(args.site)

    site_rows = conn.execute(
        f"SELECT id, name, base_url, listing_urls, link_pattern, next_page_tpl "
        f"FROM sites {where}",
        params,
    ).fetchall()
    site_cols = ["id", "name", "base_url", "listing_urls", "link_pattern", "next_page_tpl"]
    sites = [dict(zip(site_cols, r)) for r in site_rows]

    if not sites:
        print("No matching active sites found.")
        conn.close()
        return

    total_new = total_skipped = 0
    for site in sites:
        print(f"\n{'=' * 60}")
        print(f"Scraping: {site['name']}  ({site['base_url']})")
        print("=" * 60)
        new, skipped = scrape_site(conn, site)
        total_new    += new
        total_skipped += skipped

    # Retry photos left undownloaded from any prior run
    if not SKIP_PHOTOS:
        pending = conn.execute(
            "SELECT listing_id, url FROM photos WHERE downloaded = 0"
        ).fetchall()
        if pending:
            print(f"\nRetrying {len(pending)} undownloaded photo(s)…")
            for listing_id, url in pending:
                filename = url.split("/")[-1].split("?")[0] or "photo.jpg"
                dest = os.path.join(PHOTOS_DIR, str(listing_id), filename)
                if os.path.exists(dest):
                    mark_photo_downloaded(conn, url, dest)
                    continue
                time.sleep(0.2)
                if download_file(url, dest):
                    mark_photo_downloaded(conn, url, dest)
                    print(f"  ✓ [{listing_id}] {filename}")
                else:
                    print(f"  ✗ [{listing_id}] {filename}")

    conn.close()
    print(f"\nDone. New: {total_new}, skipped (already in DB): {total_skipped}")
    print(f"Database: {DB_PATH}   Photos: {PHOTOS_DIR}/")


if __name__ == "__main__":
    main()
