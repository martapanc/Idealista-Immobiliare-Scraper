import json
import sqlite3


def seed(conn: sqlite3.Connection) -> None:
    existing = conn.execute(
        "SELECT id FROM sites WHERE name = ?", ("Engel & Völkers Andorra",)
    ).fetchone()

    if existing:
        site_id = existing[0]
        conn.execute(
            "UPDATE field_rules SET selector = ?, attr = ? WHERE site_id = ? AND field_name = 'images'",
            (
                "script:*:json_array:uploadCareImageIds",
                "https://uploadcare.engelvoelkers.com/{}/-/format/webp/-/stretch/off/-/progressive/yes/-/resize/1440x/-/quality/lighter/",
                site_id,
            ),
        )
        conn.execute("UPDATE sites SET slug = 'engelvoelkers' WHERE id = ? AND slug IS NULL", (site_id,))
        conn.commit()
        return

    conn.execute("""
        INSERT INTO sites (name, slug, base_url, listing_urls, link_pattern, next_page_tpl, active)
        VALUES (?, ?, ?, ?, ?, ?, 1)
    """, (
        "Engel & Völkers Andorra",
        "engelvoelkers",
        "https://www.engelvoelkers.com",
        json.dumps([
            "https://www.engelvoelkers.com/ad/es/inmuebles/res/compra/inmobiliario",
        ]),
        r"/ad/es/exposes/[a-f0-9-]+",
        "{url}?page={n}",
    ))
    site_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Price: "2.500.000 €" or "Precio a consultar"
    # Specs: "4 Dormitorios", "3 Baños", "~345 m² Superficie total"
    # Reference: "ID de la propiedad: W-049FBE"
    # Images: all UUIDs embedded in uploadCareImageIds JSON array in inline scripts
    # NOTE: Replace selectors with [data-testid="..."] once confirmed in devtools
    rules = [
        # (field_name, selector, attr, regex, multi, after_heading)
        ("ref",           "regex:ID de la propiedad:\\s*(\\S+)",                                                           None,   None,          0, None),
        ("title",         "h1",                                                                                             None,   None,          0, None),
        ("price",         "regex:(?i)([\\d][\\d\\.\\s]*€|precio a consultar)",                                             None,   None,          0, None),
        ("operation",     "regex:(?i)(venta|alquiler)",                                                                     None,   None,          0, None),
        ("property_type", "regex:(?i)(casa unifamiliar|piso|[aá]tico|local|terreno|parking|chalet|villa|d[uú]plex|finca)",  None,   None,          0, None),
        ("parish",        "regex:(?i)(La Massana|Andorra la Vella|Escaldes[- ]Engordany|Ordino|Canillo|Sant Juli[aà]|Encamp|Pas de la Casa)", None, None, 0, None),
        ("rooms",         "regex:(\\d+)\\s*[Dd]ormitorio",                                                                 None,   None,          0, None),
        ("bathrooms",     "regex:(\\d+)\\s*[Bb]a[ñn]o",                                                                    None,   None,          0, None),
        ("size_m2",       "regex:~?([\\d\\.]+)\\s*m[²2]\\s*Superficie total",                                              None,   None,          0, None),
        ("terrace_m2",    "regex:~?([\\d\\.]+)\\s*m[²2]\\s*Superficie terraza",                                            None,   None,          0, None),
        ("description",   "p",                                                                                              None,   None,          0, None),
        ("agent_name",    "regex:(?s)(?:Contacta con|Agente)\\s+([^\\n\\|<]{2,50})",                                       None,   None,          0, None),
        ("agent_phone",   "a[href^='tel:']",                                                                                "href", "tel:(.*)",    0, None),
        ("agent_email",   "a[href^='mailto:']",                                                                             "href", "mailto:(.*)", 0, None),
        ("images",        "script:*:json_array:uploadCareImageIds",
         "https://uploadcare.engelvoelkers.com/{}/-/format/webp/-/stretch/off/-/progressive/yes/-/resize/1440x/-/quality/lighter/",
         None, 1, None),
    ]

    conn.executemany("""
        INSERT INTO field_rules (site_id, field_name, selector, attr, regex, multi, after_heading)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, [(site_id, *r) for r in rules])

    conn.commit()
    print(f"  Seeded: Engel & Völkers Andorra (site_id={site_id})")
