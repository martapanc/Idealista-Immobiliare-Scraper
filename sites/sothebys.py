import json
import sqlite3


def seed(conn: sqlite3.Connection) -> None:
    existing = conn.execute(
        "SELECT id FROM sites WHERE name = ?", ("Andorra Sotheby's",)
    ).fetchone()

    if existing:
        site_id = existing[0]
        migrations = {
            "rooms":      "regex:(?i)bedrooms?\\s+(\\d+)",
            "bathrooms":  "regex:(?i)bathrooms?\\s+(\\d+)",
            "size_m2":    "regex:(?i)area\\s+([\\d\\.]+)\\s*m",
            "price":      "regex:(?i)price\\s+(consult|[\\d][\\d\\.\\s,]*\\s*€)",
            "images":     "img[src*='/watermark/'][src$='.jpeg']",
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
        conn.execute("UPDATE sites SET slug = 'sothebys' WHERE id = ? AND slug IS NULL", (site_id,))
        conn.commit()
        return

    conn.execute("""
        INSERT INTO sites (name, slug, base_url, listing_urls, link_pattern, next_page_tpl, active)
        VALUES (?, ?, ?, ?, ?, ?, 1)
    """, (
        "Andorra Sotheby's",
        "sothebys",
        "https://www.andorra-sothebysrealty.com",
        json.dumps([
            "https://www.andorra-sothebysrealty.com/en/sale-and-rent/-all-types-andorra",
        ]),
        r"/en/[^/]+/\d+$",
        "{url}?page={n}",
    ))
    site_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Most fields extracted via full-text regex — the site has minimal CSS classes.
    # Update field_rules rows directly in the DB if you find stable selectors in devtools.
    rules = [
        # (field_name, selector, attr, regex, multi, after_heading)
        ("ref",           "url:/(\\d+)$",                                               None,   None,                          0, None),
        ("title",         "h1",                                                          None,   None,                          0, None),
        ("price",         "regex:(?i)price\\s+(consult|[\\d][\\d\\.\\s,]*\\s*€)",       None,   None,                          0, None),
        ("rooms",         "regex:(?i)bedrooms?\\s+(\\d+)",                               None,   None,                          0, None),
        ("bathrooms",     "regex:(?i)bathrooms?\\s+(\\d+)",                              None,   None,                          0, None),
        ("size_m2",       "regex:(?i)area\\s+([\\d\\.]+)\\s*m",                         None,   None,                          0, None),
        ("description",   "p",                                                           None,   None,                          0, None),
        ("features",      "li",                                                          None,   None,                          1, "Features"),
        ("agent_phone",   "a[href^='tel:']",                                             "href", "tel:(.*)",                    0, None),
        ("agent_email",   "a[href^='mailto:']",                                          "href", "mailto:(.*)",                 0, None),
        ("energy_rating", "img[src*='energetica']",                                     "src",  r"energetica-(\w+)\.",          0, None),
        ("images",        "img[src*='/watermark/'][src$='.jpeg']",                       "src",  None,                          1, None),
    ]

    conn.executemany("""
        INSERT INTO field_rules (site_id, field_name, selector, attr, regex, multi, after_heading)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, [(site_id, *r) for r in rules])

    conn.commit()
    print(f"  Seeded: Andorra Sotheby's (site_id={site_id})")
