# Web Scraper 🏠
## Gather simple information from [Immobiliare](https://immobiliare.it) and [Idealista](https://www.idealista.it/) and print it to a CSV file


### Setup
- [Idealista only] Grab API key from [ZenRows](https://app.zenrows.com/), and place it into `config.yml`
- urls to be parsed should be placed in a file named `idealista_urls.txt` or `immobiliare_urls.txt` inside `data/`, one on each line

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

python3 idealista_scraper.py 

python3 immobiliare_scraper.py
```
