import json
import sqlite3


def seed(conn: sqlite3.Connection) -> None:
    existing = conn.execute(
        "SELECT id FROM sites WHERE name = ?", ("Immobiliaria Galí",)
    ).fetchone()

    if existing:
        site_id = existing[0]
        migrations = {
            "price":  (".fichapropiedad-precio", None),
            "images": (".visorficha-miniaturas li", "cargafoto"),
        }
        for field, (selector, attr) in migrations.items():
            conn.execute(
                "UPDATE field_rules SET selector = ?, attr = ?, regex = ? WHERE site_id = ? AND field_name = ?",
                (selector, attr, r"sub:s\.jpg$:.jpg" if field == "images" else None, site_id, field),
            )
        conn.execute("UPDATE sites SET slug = 'gali' WHERE id = ? AND slug IS NULL", (site_id,))
        conn.commit()
        return

    conn.execute("""
        INSERT INTO sites (name, slug, base_url, listing_urls, link_pattern, next_page_tpl, active)
        VALUES (?, ?, ?, ?, ?, ?, 1)
    """, (
        "Immobiliaria Galí",
        "gali",
        "https://www.immobiliariagali.com",
        json.dumps([
            "https://www.immobiliariagali.com/?pag=1&idio=2",
        ]),
        r"/ficha/[^/]+/[^/]+/[^/]+/\d+/\d+/en",
        # {url} is unused; only {n} varies
        "https://www.immobiliariagali.com/?pag={n}&idio=2",
    ))
    site_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Detail page labels (English): "Reference 02941", "Bedrooms 2",
    # "Net Internal Area 84.98 m2", "Year Built 2024", etc.
    rules = [
        # (field_name, selector, attr, regex, multi, after_heading)
        ("ref",           "regex:(?i)reference\\s+(\\S+)",                                                             None,   None,          0, None),
        ("title",         "h1",                                                                                         None,   None,          0, None),
        ("price",         ".fichapropiedad-precio",                                                                        None,   None,          0, None),
        ("operation",     "regex:(?i)(for sale|for rent)",                                                              None,   None,          0, None),
        ("property_type", "regex:(?i)(flat|house|villa|commercial|land|parking|office|chalet|duplex|studio)",           None,   None,          0, None),
        ("parish",        "regex:(?i)(La Massana|Andorra la Vella|Escaldes[- ]Engordany|Ordino|Canillo|Sant Juli[aà]|Encamp|Pas de la Casa)", None, None, 0, None),
        ("rooms",         "regex:(?i)bedrooms?\\s+(\\d+)",                                                              None,   None,          0, None),
        ("bathrooms",     "regex:(?i)bathrooms?\\s+(\\d+)",                                                             None,   None,          0, None),
        ("size_m2",       "regex:(?i)net internal area\\s+([\\d\\.]+)\\s*m",                                           None,   None,          0, None),
        ("terrace_m2",    "regex:(?i)terrace\\s+(?:size\\s+)?([\\d\\.]+)\\s*m",                                        None,   None,          0, None),
        ("floor",         "regex:(?i)^floor\\s+(\\d+)",                                                                None,   None,          0, None),
        ("year_built",    "regex:(?i)year built\\s+(\\d{4})",                                                          None,   None,          0, None),
        ("features",      "li",                                                                                         None,   None,          1, "Features"),
        ("description",   "p",                                                                                          None,   None,          0, None),
        ("agent_name",    "regex:(?i)Immobiliaria Gal[íi]",                                                            None,   None,          0, None),
        ("agent_phone",   "a[href^='tel:']",                                                                            "href", "tel:(.*)",    0, None),
        ("agent_email",   "a[href^='mailto:']",                                                                         "href", "mailto:(.*)", 0, None),
        ("images",        ".visorficha-miniaturas li",                                                                    "cargafoto", r"sub:s\.jpg$:.jpg", 1, None),
    ]

    conn.executemany("""
        INSERT INTO field_rules (site_id, field_name, selector, attr, regex, multi, after_heading)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, [(site_id, *r) for r in rules])

    conn.commit()
    print(f"  Seeded: Immobiliaria Galí (site_id={site_id})")
