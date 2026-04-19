import json
import sqlite3


def seed(conn: sqlite3.Connection) -> None:
    existing = conn.execute(
        "SELECT id FROM sites WHERE name = ?", ("Immobiliaria Superior",)
    ).fetchone()

    if existing:
        site_id = existing[0]
    else:
        conn.execute("""
            INSERT INTO sites (name, slug, base_url, listing_urls, link_pattern, next_page_tpl, active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
        """, (
            "Immobiliaria Superior",
            "superior",
            "https://www.immobiliariasuperior.com",
            json.dumps([
                "https://www.immobiliariasuperior.com/en/see-all?page=1",
            ]),
            r"/en/estate/ref\d+/",
            "https://www.immobiliariasuperior.com/en/see-all?page={n}",
        ))
        site_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.execute("UPDATE sites SET slug = 'superior' WHERE id = ? AND slug IS NULL", (site_id,))

    # price in <p class="preu-fitxa">, can be "Consult"
    # rooms/size/terrace in <p class="item-ico"> elements: "1 bedroom", "53 m²", "21 m² [Terrace]"
    # images in inline JS: dynamicimgEl = [{src: 'https://.../productes/image/NNN-N.jpg'}, ...]
    rules = [
        # (field_name, selector, attr, regex, multi, after_heading)
        ("ref",           "url:/en/estate/(ref\\d+)/",                                                                   None,   None,              0, None),
        ("title",         "h1",                                                                                           None,   None,              0, None),
        ("price",         ".preu-fitxa",                                                                                  None,   None,              0, None),
        ("operation",     "url:-(sale|rent)-",                                                                            None,   None,              0, None),
        ("property_type", "url:/en/estate/ref\\d+/([^-]+)",                                                              None,   None,              0, None),
        ("parish",        "regex:(?i)(La Massana|Andorra la Vella|Escaldes[- ]Engordany|Ordino|Canillo|Sant Juli[aà]|Encamp|Pas de la Casa)", None, None, 0, None),
        ("rooms",         "regex:(?i)(\\d+)\\s*bedrooms?",                                                               None,   None,              0, None),
        ("bathrooms",     "regex:(?i)(\\d+)\\s*bathrooms?",                                                              None,   None,              0, None),
        ("size_m2",       "regex:(?i)(\\d[\\d,\\.]*)[\\s\\u00a0]*m[²2](?!.*\\[\\s*Terrace)",                           None,   None,              0, None),
        ("terrace_m2",    "regex:(?i)(\\d[\\d,\\.]*)[\\s\\u00a0]*m[²2]\\s*\\[\\s*Terrace",                             None,   None,              0, None),
        ("description",   'script:*:"description":\\s*"([^"]{40,})"',                                                   None,   None,              0, None),
        ("agent_name",    "regex:(?i)(Immobiliaria Superior|ImmoSuperior)",                                               None,   None,              0, None),
        ("agent_phone",   "a[href^='tel:']",                                                                              "href", "tel:(.*)",        0, None),
        ("images",        "script:*:src:\\s*'(https://www\\.immobiliariasuperior\\.com/images/productes/image/[^']+)'",  None,   None,              1, None),
    ]

    # INSERT OR IGNORE ensures any rule added later is filled in without clobbering existing ones.
    # Explicit selector updates come after so corrections always win.
    conn.executemany("""
        INSERT OR IGNORE INTO field_rules (site_id, field_name, selector, attr, regex, multi, after_heading)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, [(site_id, *r) for r in rules])

    # Apply selector corrections to existing rows
    for field_name, selector, *_ in rules:
        conn.execute(
            "UPDATE field_rules SET selector = ? WHERE site_id = ? AND field_name = ?",
            (selector, site_id, field_name),
        )

    conn.commit()
    print(f"  Seeded: Immobiliaria Superior (site_id={site_id})")
