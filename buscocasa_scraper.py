"""
buscocasa_scraper.py — Scraper for buscocasa.ad

Paginates through the filter results (rentals + sales), fetches each listing's
detail page, stores all data in a local SQLite database, and downloads photos.

Usage:
    python3 buscocasa_scraper.py

Config (constants below):
    DB_PATH       — SQLite database file
    PHOTOS_DIR    — root directory for downloaded photos
    DELAY         — seconds to wait between requests
    SKIP_PHOTOS   — set True to skip photo downloads
"""

import os
import re
import time
import sqlite3
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urljoin

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DB_PATH = "buscocasa.db"
PHOTOS_DIR = os.path.join("photos", "buscocasa")
DELAY = 1.0          # seconds between HTTP requests
SKIP_PHOTOS = False  # set True to only store photo URLs, not download them

BASE_URL = "https://www.buscocasa.ad"
FILTER_URLS = {
    "Lloguer": f"{BASE_URL}/ca/filter?operacio%5B%5D=1",
    "Venda":   f"{BASE_URL}/ca/filter?operacio%5B%5D=2",
}
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "ca,es;q=0.9,en;q=0.8",
}


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS listings (
            id            INTEGER PRIMARY KEY,
            url           TEXT    UNIQUE NOT NULL,
            title         TEXT,
            operation     TEXT,
            property_type TEXT,
            parish        TEXT,
            price         TEXT,
            size_m2       TEXT,
            rooms         TEXT,
            bathrooms     TEXT,
            floor         TEXT,
            parking       TEXT,
            ref_immo      TEXT,
            year_built    TEXT,
            availability  TEXT,
            amenities     TEXT,
            description   TEXT,
            agent_id      TEXT,
            agent_name    TEXT,
            agent_contact TEXT,
            agent_phone   TEXT,
            agent_email   TEXT,
            agent_web     TEXT,
            scraped_at    TEXT
        );

        CREATE TABLE IF NOT EXISTS photos (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id   INTEGER NOT NULL,
            url          TEXT    UNIQUE NOT NULL,
            local_path   TEXT,
            downloaded   INTEGER DEFAULT 0,
            FOREIGN KEY (listing_id) REFERENCES listings(id)
        );
    """)
    conn.commit()


def listing_exists(conn: sqlite3.Connection, listing_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM listings WHERE id = ?", (listing_id,)
    ).fetchone()
    return row is not None


def upsert_listing(conn: sqlite3.Connection, data: dict) -> None:
    cols = ", ".join(data.keys())
    placeholders = ", ".join("?" for _ in data)
    updates = ", ".join(f"{k} = excluded.{k}" for k in data if k != "id")
    sql = (
        f"INSERT INTO listings ({cols}) VALUES ({placeholders}) "
        f"ON CONFLICT(id) DO UPDATE SET {updates}"
    )
    conn.execute(sql, list(data.values()))
    conn.commit()


def insert_photos(conn: sqlite3.Connection, listing_id: int, urls: list[str]) -> list[str]:
    """Insert photo URLs; return list of URLs not yet downloaded."""
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


def mark_photo_downloaded(conn: sqlite3.Connection, url: str, local_path: str) -> None:
    conn.execute(
        "UPDATE photos SET local_path = ?, downloaded = 1 WHERE url = ?",
        (local_path, url),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
_session = requests.Session()


def fetch(url: str) -> BeautifulSoup:
    resp = _session.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def download_file(url: str, dest_path: str) -> bool:
    """Download binary file; return True on success."""
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
# Pagination — collect listing URLs from filter pages
# ---------------------------------------------------------------------------
def iter_listing_urls(filter_url: str):
    """Yield listing URLs from all pages of a filter result."""
    page = 1
    seen = set()
    while True:
        url = filter_url if page == 1 else f"{filter_url}&pn={page}"
        print(f"  Page {page}: {url}")
        try:
            soup = fetch(url)
        except requests.HTTPError as e:
            print(f"  HTTP {e} — stopping.")
            break

        cards = soup.find_all(
            "a", attrs={"kmk-seguiment": re.compile(r"^llistat$")}
        )
        if not cards:
            print("  No listings found — end of results.")
            break

        new_on_page = 0
        for card in cards:
            href = card.get("href", "")
            if "/immoble/" not in href:
                continue
            if not href.startswith("http"):
                href = BASE_URL + href
            if href not in seen:
                seen.add(href)
                new_on_page += 1
                yield href

        print(f"  → {new_on_page} new URLs on page {page}")
        if new_on_page == 0:
            break

        # Check if there's a next page in the pagination widget
        pagination = soup.find("ul", class_="uk-pagination")
        if not pagination:
            break
        next_pages = [
            a.get("href") for a in pagination.find_all("a")
            if a.get("href") and f"pn={page + 1}" in a.get("href", "")
        ]
        if not next_pages:
            break

        page += 1
        time.sleep(DELAY)


# ---------------------------------------------------------------------------
# Detail page parser
# ---------------------------------------------------------------------------
def parse_listing_id(url: str):
    m = re.search(r"/immoble/(\d+)/", url)
    return int(m.group(1)) if m else None


def parse_detail(soup: BeautifulSoup, url: str) -> dict:
    data: dict = {}

    # Title — strip the back-arrow <a> and price <span> from h1
    h1 = soup.find("h1")
    if h1:
        for tag in h1.find_all(["a", "span"]):
            tag.decompose()
        data["title"] = h1.get_text(strip=True).strip('"')

    # Price
    price_span = soup.find("span", class_="uk-text-primary")
    if price_span:
        raw = price_span.get_text(strip=True)
        data["price"] = re.sub(r"[€\.]", "", raw).strip()

    # Parish — breadcrumb: Andorra > Parish > ...
    breadcrumb_ems = soup.select("div.fitxa-titol em, div.fitxa-content em")
    # The breadcrumb uses <em><i ...></i></em> TEXT pattern
    parish_parts = []
    for em in soup.find_all("em"):
        # Skip ems that contain only an icon
        if em.find("i") and not em.get_text(strip=True):
            continue
        parent = em.parent
        if parent and "angle-double-right" in str(parent):
            text = em.get_text(strip=True)
            if text:
                parish_parts.append(text)

    # Alternative: parse breadcrumb from the angle-double-right icons context
    breadcrumb_raw = []
    for em_block in soup.find_all("em"):
        icon = em_block.find("i", class_=re.compile(r"angle-double-right"))
        if icon:
            # The text follows the </em> tag
            next_sib = em_block.next_sibling
            if next_sib and isinstance(next_sib, str):
                t = next_sib.strip()
                if t:
                    breadcrumb_raw.append(t)
            # Also check if text is directly after </em> in a different structure
            parent_text = em_block.parent.get_text(separator="|")
            # Extract the text segment
    if breadcrumb_raw:
        # First entry is country (Andorra), second is parish
        if len(breadcrumb_raw) >= 2:
            data["parish"] = breadcrumb_raw[1].strip()

    # Property attributes table
    prop_table = soup.find("table")
    if prop_table:
        attr_map = {
            "tipus":                    "property_type",
            "operació":                 "operation",
            "operacio":                 "operation",
            "superficie (m2)":          "size_m2",
            "habitacions":              "rooms",
            "banys":                    "bathrooms",
            "número de planta":         "floor",
            "numero de planta":         "floor",
            "número places parking":    "parking",
            "numero places parking":    "parking",
            "ref. immo":                "ref_immo",
            "any construcció":          "year_built",
            "any construccio":          "year_built",
            "disponibilitat":           "availability",
        }
        for row in prop_table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) == 2:
                key = cells[0].get_text(strip=True).lower()
                val = cells[1].get_text(strip=True)
                field = attr_map.get(key)
                if field and val:
                    data[field] = val

    # Amenities (checkboxes in Característiques section)
    char_section = None
    for div in soup.find_all("div", class_="fitxa-dreta"):
        if "Característiques" in div.get_text():
            char_section = div
            break
    if char_section:
        items = char_section.find_all("label")
        if not items:
            # Sometimes they're plain spans/text with icons
            text = char_section.get_text(separator="|", strip=True)
            amenities = [
                a.strip() for a in text.split("|")
                if a.strip() and "Característiques" not in a
                and not re.match(r"^[\d\W]+$", a.strip())
            ]
            if amenities:
                data["amenities"] = ", ".join(amenities)
        else:
            data["amenities"] = ", ".join(l.get_text(strip=True) for l in items)

    # Description
    desc_div = soup.find("div", id="fitxa-item-desc")
    if desc_div:
        btn = desc_div.find("span", id="fitxa-item-desc-boto")
        if btn:
            btn.decompose()
        data["description"] = desc_div.get_text(separator=" ", strip=True)

    # Agent — img alt near taula-usuari holds the company name
    agent_table = soup.find("table", class_="taula-usuari")
    if agent_table:
        # Agent company logo with alt
        agent_img = agent_table.find_previous("img", alt=True)
        if agent_img:
            data["agent_name"] = agent_img.get("alt", "").strip()

        for row in agent_table.find_all("tr"):
            text = row.get_text(strip=True)
            # Contact person
            m = re.search(r"Contactar amb (.+)", text)
            if m:
                data["agent_contact"] = m.group(1).strip()
            # Phone
            phone_a = row.find("a", href=re.compile(r"^tel:"))
            if phone_a:
                data["agent_phone"] = phone_a.get_text(strip=True)
            # Email
            email_a = row.find("a", href=re.compile(r"^mailto:"))
            if email_a:
                data["agent_email"] = email_a.get_text(strip=True)
            # Website
            web_a = row.find("a", attrs={"kmk-seguiment": "fitxa-usuari-web"})
            if web_a:
                data["agent_web"] = web_a.get_text(strip=True)

    # Agent ID from tracking attributes
    agent_id_match = re.search(
        r'kmk-seguiment-idprofessional="(\d+)"', str(soup)
    )
    if agent_id_match:
        data["agent_id"] = agent_id_match.group(1)

    # Photos — full-res images from the slideshow
    photos = []
    for img in soup.select("#kmkSlideShow img[src]"):
        src = img.get("src", "")
        if src and "fotos_items" in src and src not in photos:
            photos.append(src)
    # Fallback: ruta+imagen attributes
    if not photos:
        for img in soup.find_all("img", attrs={"ruta": True, "imagen": True}):
            src = urljoin(img["ruta"], img["imagen"])
            if src not in photos:
                photos.append(src)

    data["scraped_at"] = datetime.now(timezone.utc).isoformat()
    return data, photos


# ---------------------------------------------------------------------------
# Photo download
# ---------------------------------------------------------------------------
def download_photos(
    conn: sqlite3.Connection,
    listing_id: int,
    photo_urls: list[str],
) -> None:
    pending = insert_photos(conn, listing_id, photo_urls)
    if not pending:
        return
    print(f"    Downloading {len(pending)} photo(s)…")
    for url in pending:
        filename = url.split("/")[-1]
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
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    total_new = 0
    total_skipped = 0

    for operation, filter_url in FILTER_URLS.items():
        print(f"\n{'=' * 60}")
        print(f"Scraping: {operation}  ({filter_url})")
        print("=" * 60)

        for listing_url in iter_listing_urls(filter_url):
            listing_id = parse_listing_id(listing_url)
            if listing_id is None:
                print(f"  [skip] Could not parse ID from {listing_url}")
                continue

            if listing_exists(conn, listing_id):
                total_skipped += 1
                continue

            print(f"  [{listing_id}] {listing_url}")
            try:
                soup = fetch(listing_url)
            except requests.HTTPError as e:
                print(f"    HTTP error: {e}")
                time.sleep(DELAY)
                continue

            data, photo_urls = parse_detail(soup, listing_url)
            data["id"] = listing_id
            data["url"] = listing_url

            upsert_listing(conn, data)
            total_new += 1

            print(
                f"    {data.get('title', '')[:55]} | "
                f"{data.get('price', '')} | "
                f"{data.get('size_m2', '')}m² | "
                f"{data.get('rooms', '')} hab | "
                f"{data.get('agent_name', '')} | "
                f"{len(photo_urls)} photos"
            )

            if not SKIP_PHOTOS:
                download_photos(conn, listing_id, photo_urls)

            time.sleep(DELAY)

    # Retry any photos that are in the DB but not yet downloaded
    # (covers interrupted runs or previous runs with SKIP_PHOTOS=True)
    if not SKIP_PHOTOS:
        pending_photos = conn.execute(
            "SELECT listing_id, url FROM photos WHERE downloaded = 0"
        ).fetchall()
        if pending_photos:
            print(f"\nRetrying {len(pending_photos)} previously undownloaded photo(s)…")
            for listing_id, url in pending_photos:
                filename = url.split("/")[-1]
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
    print(f"Database: {DB_PATH}")
    print(f"Photos:   {PHOTOS_DIR}/")


if __name__ == "__main__":
    main()
