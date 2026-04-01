# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Web scraper that extracts property listings from two Italian real estate websites ([Immobiliare.it](https://immobiliare.it) and [Idealista.it](https://www.idealista.it/)) and exports results to CSV files.

## Setup & Commands

```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run scrapers
python3 immobiliare_scraper.py
python3 idealista_scraper.py
```

**Input:** Place URLs (one per line) in:
- `data/immobiliare_urls.txt`
- `data/idealista_urls.txt`

**Output:** Timestamped CSV files written to `output/` directory.

## Configuration

`config.yml` (git-ignored) must exist for the Idealista scraper with a ZenRows API key:
```yaml
zenrows_api_key: <your_api_key>
```

Copy `config-local.yml` as a starting point. Get a ZenRows API key from [app.zenrows.com](https://app.zenrows.com/).

## Architecture

Two independent, standalone Python scripts with no shared code:

- **`immobiliare_scraper.py`** — Direct HTTP requests via `requests`, parses HTML with BeautifulSoup targeting CSS classes specific to immobiliare.it.
- **`idealista_scraper.py`** — Routes requests through the ZenRows proxy API (premium proxies enabled) to bypass rate limiting on idealista.it, then parses with BeautifulSoup.

Both scripts follow the same flow: read URLs → fetch pages → parse HTML → write CSV. The CSV schema is identical across both scrapers (Title, Link, Type, Asking, Notes, Where, Size, Rooms, Rating, Plan, Agent, Status), though Notes, Where, Rating, Plan, and Status are always left empty.

## Key Constraints

- Both scrapers are coupled to specific HTML class names on the target sites — CSS changes upstream will break parsing silently.
- No test suite exists.
- URLs are processed sequentially; no concurrency.