import requests
from bs4 import BeautifulSoup
import csv
from datetime import datetime

headers = ["Title", "Link", "Type", "State", "Asking", "Notes", "Where",
           "Size (garden)", "Rooms", "Rating", "Plan", "Agent", "Status"]

with open("data/immobiliare_urls.txt", "r") as url_file:
    urls = [line.strip() for line in url_file if line.strip()]

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_filename = f"output/immobiliare_{timestamp}.csv"

    with open(output_filename, mode="w", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(headers)

        for url in urls:
            response = requests.get(url)

            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')

                # Title
                title = soup.find("h1", class_="in-titleBlock__title").text.strip()

                # Price
                price = soup.find("li", class_="in-detail__mainFeaturesPrice").text.strip()
                price = price.replace("€", "").replace(".", "").strip()

                # Rooms
                li_element = soup.find("li", {"aria-label": "locali"})
                div_element = li_element.find("div", class_="in-feat__data")
                rooms = div_element.text.strip()

                # Size
                li_element = soup.find("li", {"aria-label": "superficie"})
                div_element = li_element.find("div", class_="in-feat__data")
                size = div_element.text.strip()

                # Description
                description = soup.find("p", class_="in-description__title").text.strip()

                # Type
                dt_element = soup.find("dt", text="tipologia")
                dd_element = dt_element.find_next_sibling("dd")
                property_type = dd_element.text.strip()

                # Agent
                div_element = soup.find("div", class_="in-referent")
                a_element = div_element.find("a")
                agent = a_element.text.strip()

                # Print the extracted data
                print("Url", url)
                print("Title:", title)
                print("Price:", price)
                print("Size:", size)
                print("Rooms:", rooms)
                print("Description:", description)
                print("Type:", property_type)
                print("Agent:", agent)
                print("-------")

                writer.writerow([title, url, property_type, description, price, "", "", size, rooms, "", "", agent, ""])

            else:
                print("Failed to retrieve the webpage. Status code:", response.status_code)

print(f"CSV file '{output_filename}' has been created with all the extracted values and headers.")
