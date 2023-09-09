import requests
from bs4 import BeautifulSoup

# URL of the webpage you want to scrape
url = "https://www.immobiliare.it/annunci/101194581/"

# Send a GET request to the URL
response = requests.get(url)

# Check if the request was successful (status code 200)
if response.status_code == 200:
    # Parse the HTML content of the page
    soup = BeautifulSoup(response.text, 'html.parser')

    # Title
    title = soup.find("h1", class_="in-titleBlock__title").text.strip()

    # Price
    price = soup.find("li", class_="in-detail__mainFeaturesPrice").text.strip()

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
    print("Title:", title)
    print("Price:", price)
    print("Size:", size)
    print("Rooms:", rooms)
    print("Description:", description)
    print("Type:", property_type)
    print("Agent:", agent)

else:
    print("Failed to retrieve the webpage. Status code:", response.status_code)
