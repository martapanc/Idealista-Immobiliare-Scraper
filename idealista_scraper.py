import requests
from bs4 import BeautifulSoup
import csv
from datetime import datetime

headers = ["Title", "Link", "Type", "Asking", "Notes", "Where",
           "Size (garden)", "Rooms", "Rating", "Plan", "Agent", "Status"]

with open("data/idealista_urls.txt", "r") as url_file:
    urls = [line.strip() for line in url_file if line.strip()]

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_filename = f"output/idealista_{timestamp}.csv"

    with open(output_filename, mode="w", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(headers)

        for url in urls:
            cookies = {
                'userUUID': 'bdfae43e-7354-4830-bb75-3cdbdc473039',
                'askToSaveAlertPopUp': 'true',
                'cookieSearch-1': '"/vendita-case/casina-reggio-emilia/:1694197210707"',
                'galleryHasBeenBoosted': 'true',
                'contact076f8563-81ad-4d21-ba0c-5fa9b951b487': '"{\'email\':null,\'phone\':null,\'phonePrefix\':null,\'friendEmails\':null,\'name\':null,\'message\':null,\'message2Friends\':null,\'maxNumberContactsAllow\':10,\'defaultMessage\':true}"',
                'send076f8563-81ad-4d21-ba0c-5fa9b951b487': '"{\'friendsEmail\':null,\'email\':null,\'message\':null}"',
                'SESSION': 'fb3d38dd5a1f5e99~076f8563-81ad-4d21-ba0c-5fa9b951b487',
                'utag_main': 'v_id:018a7605c1150011b70fcd13d37d04075011f06d00b72$_sn:3$_se:4$_ss:0$_st:1694254643027$ses_id:1694252216399%3Bexp-session$_pn:4%3Bexp-session',
                'datadome': '3lfLMENIUPpzhQ3k1NzDvaFekvKtjahyPePSdcrNw8c-~7fSDQ~Dmo8jcslv0p4CwpM7kW1EQweO72PEve78G~TXob9R8cbllTcAM_jpOrVOuC5~oDu2u6NTvNhSW44n',
            }

            headers = {
                'authority': 'www.idealista.it',
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'accept-language': 'en-GB,en;q=0.9',
                'cache-control': 'max-age=0',
                # 'cookie': 'userUUID=bdfae43e-7354-4830-bb75-3cdbdc473039; askToSaveAlertPopUp=true; cookieSearch-1="/vendita-case/casina-reggio-emilia/:1694197210707"; galleryHasBeenBoosted=true; contact076f8563-81ad-4d21-ba0c-5fa9b951b487="{\'email\':null,\'phone\':null,\'phonePrefix\':null,\'friendEmails\':null,\'name\':null,\'message\':null,\'message2Friends\':null,\'maxNumberContactsAllow\':10,\'defaultMessage\':true}"; send076f8563-81ad-4d21-ba0c-5fa9b951b487="{\'friendsEmail\':null,\'email\':null,\'message\':null}"; SESSION=fb3d38dd5a1f5e99~076f8563-81ad-4d21-ba0c-5fa9b951b487; utag_main=v_id:018a7605c1150011b70fcd13d37d04075011f06d00b72$_sn:3$_se:4$_ss:0$_st:1694254643027$ses_id:1694252216399%3Bexp-session$_pn:4%3Bexp-session; datadome=3lfLMENIUPpzhQ3k1NzDvaFekvKtjahyPePSdcrNw8c-~7fSDQ~Dmo8jcslv0p4CwpM7kW1EQweO72PEve78G~TXob9R8cbllTcAM_jpOrVOuC5~oDu2u6NTvNhSW44n',
                'sec-ch-ua': '"Chromium";v="116", "Not)A;Brand";v="24", "Brave";v="116"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"macOS"',
                'sec-fetch-dest': 'document',
                'sec-fetch-mode': 'navigate',
                'sec-fetch-site': 'none',
                'sec-fetch-user': '?1',
                'sec-gpc': '1',
                'upgrade-insecure-requests': '1',
                'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36',
            }

            response = requests.get(url, cookies=cookies, headers=headers)

            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')

                # Title
                title = soup.find("span", class_="main-info__title-main").text.strip()

                # Price
                span_element = soup.find("span", class_="info-data-price").text.strip()
                price = span_element.find("span", class_="txt-bold").text.strip()

                # Rooms & Size
                div_element = soup.find("div", class_="info-features")
                spans = div_element.find_all("span")
                size = spans[0].text.strip()
                rooms = spans[1].text.replace("locali", "").strip()

                # Type
                div_element = soup.find("div", class_="details-property_features")
                li_elements = div_element.find_all("li")
                property_type = li_elements[0].text.strip()

                # Agent
                a_element = soup.find("a", class_="about-advertiser-name")
                agent = a_element.text.strip()

                # Print the extracted data
                print("Url", url)
                print("Title:", title)
                print("Price:", price)
                print("Size:", size)
                print("Rooms:", rooms)
                print("Type:", property_type)
                print("Agent:", agent)
                print("-------")

                writer.writerow([title, url, property_type, price, "", "", size, rooms, "", "", agent, ""])

            else:
                print("Failed to retrieve the webpage. Status code:", response.status_code)

print(f"CSV file '{output_filename}' has been created with all the extracted values and headers.")
