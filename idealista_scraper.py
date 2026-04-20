import csv
import json
import os
import re
import time
import random
from datetime import datetime
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.environ["SCRAPER_API_KEY"]

# How many property detail pages to scrape per listing URL in data/idealista_urls.txt
_max_raw = os.environ.get("IDEALISTA_MAX_PROPERTIES", "40")
try:
    MAX_PROPERTIES = max(1, int(_max_raw.strip()))
except ValueError:
    MAX_PROPERTIES = 40

# Upper bound on how many listing result pages to walk (~30 ads per page).
LISTING_PAGES_CAP = 100


def _fetch(url: str) -> requests.Response:
    return requests.get(
        "https://api.scraperapi.com",
        params={"api_key": api_key, "url": url},
        timeout=120,
    )


def _is_detail_url(url: str) -> bool:
    path = urlparse(url).path or ""
    return "/inmueble/" in path


def _listing_page_url(base_url: str, page: int) -> str:
    """
    idealista.com uses path pagination, e.g.
    .../barcelona/garraf/pagina-2.htm (not ?pagina=2).
    """
    parsed = urlparse(base_url)
    path = parsed.path.rstrip("/")
    path = re.sub(r"/pagina-\d+\.htm$", "", path)
    if page <= 1:
        new_path = path + "/"
    else:
        new_path = f"{path}/pagina-{page}.htm"
    return urlunparse(
        (parsed.scheme, parsed.netloc, new_path, parsed.params, parsed.query, parsed.fragment)
    )


def _extract_utag_data(html: str) -> dict | None:
    marker = "var utag_data = "
    idx = html.find(marker)
    if idx == -1:
        return None
    brace_start = html.find("{", idx)
    if brace_start == -1:
        return None
    depth = 0
    for i in range(brace_start, len(html)):
        if html[i] == "{":
            depth += 1
        elif html[i] == "}":
            depth -= 1
            if depth == 0:
                blob = html[brace_start : i + 1]
                try:
                    return json.loads(blob)
                except json.JSONDecodeError:
                    return None
    return None


def _total_pages_from_utag(html: str) -> int | None:
    data = _extract_utag_data(html)
    if not data:
        return None
    raw = (data.get("list") or {}).get("totalPageNumber")
    if raw is None:
        return None
    try:
        return max(1, int(str(raw)))
    except ValueError:
        return None


def _listing_card_urls(listing_url: str, html: str) -> tuple[list[str], int]:
    """Returns (detail URLs in order, count of item-link nodes seen)."""
    soup = BeautifulSoup(html, "html.parser")
    base = f"{urlparse(listing_url).scheme}://{urlparse(listing_url).netloc}"
    main = soup.select_one("main#main-content")
    scope = main if main is not None else soup

    accepted: list[str] = []
    seen: set[str] = set()
    raw_count = 0

    for a in scope.select('a.item-link[href*="inmueble"]'):
        href = (a.get("href") or "").strip()
        if "/inmueble/" not in href:
            continue
        raw_count += 1
        full = urljoin(base + "/", href.lstrip("/"))
        if full not in seen:
            seen.add(full)
            accepted.append(full)

    return accepted, raw_count


def collect_listing_detail_urls(listing_seed_url: str) -> list[str]:
    """Paginate the listing until we have up to MAX_PROPERTIES detail URLs."""
    collected: list[str] = []
    seen: set[str] = set()

    total_pages_hint: int | None = None

    for page in range(1, LISTING_PAGES_CAP + 1):
        page_url = _listing_page_url(listing_seed_url, page)
        resp = _fetch(page_url)
        time.sleep(random.uniform(3, 7))
        if resp.status_code != 200:
            print(page_url, "Failed (listing fetch). Status:", resp.status_code, resp.text[:300])
            break

        if page == 1:
            total_pages_hint = _total_pages_from_utag(resp.text)

        urls, raw_n = _listing_card_urls(page_url, resp.text)

        if raw_n == 0:
            print(f"No listing items on page {page}; stopping pagination.")
            break

        for u in urls:
            if u not in seen:
                seen.add(u)
                collected.append(u)
                if len(collected) >= MAX_PROPERTIES:
                    break

        if len(collected) >= MAX_PROPERTIES:
            break

        if total_pages_hint is not None and page >= total_pages_hint:
            break

    return collected[:MAX_PROPERTIES]


def _clean_rooms(raw: str) -> str:
    s = raw.strip()
    s = re.sub(r"\s*(locali|hab\.?|habitaciones?|rooms?)\s*", "", s, flags=re.I)
    return s.strip()


def extract_row(soup: BeautifulSoup, url: str) -> tuple[list[str], str | None]:
    """Returns (csv_row, error_message). Row is empty if error_message is set."""
    try:
        title_el = soup.find("span", class_="main-info__title-main")
        if title_el is None:
            return [], "missing title span (wrong page type or blocking?)"
        title = title_el.get_text(strip=True)

        price_el = soup.find("span", class_="info-data-price")
        if price_el is None:
            return [], "missing price"
        bold = price_el.find("span", class_="txt-bold")
        if bold is None:
            return [], "missing price amount"
        price = bold.get_text(strip=True).replace(".", "").strip()

        feat = soup.find("div", class_="info-features")
        if feat is None:
            size, rooms = "", ""
        else:
            spans = feat.find_all("span", recursive=False)
            size = spans[0].get_text(strip=True).replace("m2", "m²") if spans else ""
            rooms_raw = spans[1].get_text(strip=True) if len(spans) > 1 else ""
            rooms = _clean_rooms(rooms_raw)

        feat_div = soup.find("div", class_="details-property_features")
        if feat_div is None:
            property_type = ""
        else:
            li_elements = feat_div.find_all("li")
            property_type = li_elements[0].get_text(strip=True) if li_elements else ""

        a_element = soup.find("a", class_="about-advertiser-name")
        agent = a_element.get_text(strip=True) if a_element is not None else "Privato"

        row = [title, url, property_type, price, "", "", size, rooms, "", "", agent, ""]
        return row, None
    except Exception as exc:
        return [], str(exc)


headers = ["Title", "Link", "Type", "Asking", "Notes", "Where",
           "Size (garden)", "Rooms", "Rating", "Plan", "Agent", "Status"]

with open("data/idealista_urls.txt", "r") as url_file:
    seed_urls = [line.strip() for line in url_file if line.strip()]

os.makedirs("output", exist_ok=True)
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
output_filename = f"output/idealista_{timestamp}.csv"

to_scrape: list[str] = []
for u in seed_urls:
    if _is_detail_url(u):
        to_scrape.append(u)
        continue
    details = collect_listing_detail_urls(u)
    if not details:
        print(u, "No listing links collected after pagination.")
        print("-------")
        continue
    print(f"Listing expanded to {len(details)} detail URL(s) (cap {MAX_PROPERTIES}).")
    to_scrape.extend(details)

if not to_scrape:
    print("No URLs to scrape. Check data/idealista_urls.txt and SCRAPER_API_KEY.")
else:
    print(f"Scraping {len(to_scrape)} property page(s).")

with open(output_filename, mode="w", newline="") as csv_file:
    writer = csv.writer(csv_file)
    writer.writerow(headers)

    for url in to_scrape:
        response = _fetch(url)
        time.sleep(random.uniform(3, 7))

        if response.status_code != 200:
            print(url, "Failed to retrieve the webpage. Status code:", response.status_code)
            print("Response:", response.text[:500])
            print("-------")
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        row, err = extract_row(soup, url)
        if err:
            print(url, "Parse error:", err)
            print("-------")
            continue

        title, _, property_type, price, _, _, size, rooms, _, _, agent, _ = row
        print("Url", url)
        print("Title:", title)
        print("Price:", price)
        print("Size:", size)
        print("Rooms:", rooms)
        print("Type:", property_type)
        print("Agent:", agent)

        writer.writerow(row)
        print("-------")

print(f"CSV file '{output_filename}' has been created with all the extracted values and headers.")
