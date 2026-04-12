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
python3 buscocasa_scraper.py
```

**Input:** Place URLs (one per line) in:
- `data/immobiliare_urls.txt` — individual property page URLs
- `data/idealista_urls.txt` — individual property page URLs

`buscocasa_scraper.py` needs no input file — it scrapes all rentals and sales automatically.

**Output:** Timestamped CSV files written to `output/` directory.

## Configuration

A `.env` file (git-ignored) must exist for the Idealista scraper with a ScraperAPI key:
```
SCRAPERAPI_KEY=your_api_key_here
```

Copy `.env.example` as a starting point.

## Architecture

Three independent, standalone Python scripts with no shared code:

- **`immobiliare_scraper.py`** — Direct HTTP requests via `requests`, parses HTML with BeautifulSoup targeting CSS classes specific to immobiliare.it. Input: individual property URLs.
- **`idealista_scraper.py`** — Routes requests through ScraperAPI to bypass anti-bot measures on idealista.it, then parses with BeautifulSoup. Input: individual property URLs.
- **`buscocasa_scraper.py`** — Direct HTTP requests via `requests`, parses HTML with BeautifulSoup targeting CSS classes specific to buscocasa.ad. Paginates the filter endpoints (`operacio[]=1` rentals, `operacio[]=2` sales) using `&pn=N`. Fetches each detail page and stores all fields in a SQLite database (`buscocasa.db`). Also downloads full-resolution photos to `photos/{listing_id}/`. Resumable: re-runs skip listings already in the DB.

All scripts follow the same flow: read URLs → fetch pages → parse HTML → write CSV. The CSV schema is identical across all scrapers (Title, Link, Type, Asking, Notes, Where, Size, Rooms, Rating, Plan, Agent, Status), though Notes, Where, Rating, Plan, and Status are always left empty.

## Key Constraints

- All scrapers are coupled to specific HTML class names on the target sites — CSS changes upstream will break parsing silently.
- No test suite exists.
- URLs are processed sequentially; no concurrency.