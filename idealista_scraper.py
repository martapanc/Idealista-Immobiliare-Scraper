import asyncio
import csv
import os
import random
import time
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup
from patchright.async_api import async_playwright


async def _fetch_html(url: str) -> Optional[str]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="es-ES",
            timezone_id="Europe/Andorra",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            extra_http_headers={
                "Accept-Language": "es-ES,es;q=0.9,it;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-User": "?1",
                "Sec-Fetch-Dest": "document",
            },
        )
        html = None
        try:
            page = await context.new_page()

            # Warm up session on homepage first so DataDome sets cookies
            await page.goto("https://www.idealista.com/", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(random.randint(2000, 4000))

            # Navigate to the listing
            response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            if response is None or response.status >= 400:
                print(f"  HTTP {response.status if response else 'None'} for {url}")
            else:
                await page.wait_for_timeout(random.randint(1500, 3000))
                await page.evaluate("window.scrollBy(0, window.innerHeight * 0.6)")
                await page.wait_for_timeout(random.randint(800, 1800))
                html = await page.content()
        except Exception as exc:
            print(f"  Browser error fetching {url}: {exc}")
        finally:
            await browser.close()
        return html


def fetch_page(url: str) -> Optional[str]:
    return asyncio.run(_fetch_html(url))


headers = ["Title", "Link", "Type", "Asking", "Notes", "Where",
           "Size (garden)", "Rooms", "Rating", "Plan", "Agent", "Status"]

with open("data/idealista_urls.txt", "r") as url_file:
    urls = [line.strip() for line in url_file if line.strip()]

os.makedirs("output", exist_ok=True)
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
output_filename = f"output/idealista_{timestamp}.csv"

with open(output_filename, mode="w", newline="") as csv_file:
    writer = csv.writer(csv_file)
    writer.writerow(headers)

    for url in urls:
        time.sleep(random.uniform(4, 9))
        html = fetch_page(url)

        if html is not None:
            soup = BeautifulSoup(html, 'html.parser')

            # Title
            title = soup.find("span", class_="main-info__title-main").text.strip()

            # Price
            span_element = soup.find("span", class_="info-data-price")
            price = span_element.find("span", class_="txt-bold").text.replace(".", "").strip()

            # Rooms & Size
            div_element = soup.find("div", class_="info-features")
            spans = div_element.find_all("span")
            size = spans[0].text.replace("m2", "m²").strip()
            rooms = spans[1].text.replace("locali", "").strip()

            # Type
            div_element = soup.find("div", class_="details-property_features")
            li_elements = div_element.find_all("li")
            property_type = li_elements[0].text.strip()

            # Agent
            a_element = soup.find("a", class_="about-advertiser-name")
            if a_element is not None:
                agent = a_element.text.strip()
            else:
                agent = "Privato"

            # Print the extracted data
            print("Url", url)
            print("Title:", title)
            print("Price:", price)
            print("Size:", size)
            print("Rooms:", rooms)
            print("Type:", property_type)
            print("Agent:", agent)

            writer.writerow([title, url, property_type, price, "", "", size, rooms, "", "", agent, ""])
        else:
            print(url, "Failed to retrieve the webpage.")

        print("-------")

print(f"CSV file '{output_filename}' has been created with all the extracted values and headers.")
