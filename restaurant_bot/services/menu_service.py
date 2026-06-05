from __future__ import annotations

from restaurant_bot.database import get_connection
from restaurant_bot.i18n import normalize_lang
from restaurant_bot.services import restaurant_service


def default_restaurant_id() -> int:
    restaurant = restaurant_service.get_deployment_restaurant()
    if not restaurant:
        raise RuntimeError("No active restaurants configured.")
    return int(restaurant["id"])


def cents_to_usd(cents: int, currency_symbol: str = "$") -> str:
    return f"{currency_symbol}{cents / 100:.2f}"


def list_categories(
    active_only: bool = True,
    language: str = "en",
    restaurant_id: int | None = None,
) -> list[dict]:
    language = normalize_lang(language)
    restaurant_id = restaurant_id or default_restaurant_id()
    query = """
        SELECT
            mc.*,
            COALESCE(mct.name, mc.name_en) AS display_name
        FROM menu_categories mc
        LEFT JOIN menu_category_translations mct
            ON mct.category_id = mc.id
           AND mct.language = ?
    """
    params: list[object] = [language, restaurant_id]
    conditions = ["mc.restaurant_id = ?"]
    if active_only:
        conditions.append("mc.is_active = 1")
    query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY mc.sort_order, display_name"
    with get_connection() as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def get_category(category_id: int, restaurant_id: int | None = None) -> dict | None:
    restaurant_id = restaurant_id or default_restaurant_id()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM menu_categories WHERE id = ? AND restaurant_id = ?",
            (category_id, restaurant_id),
        ).fetchone()
        return dict(row) if row else None


def list_items(
    category_id: int | None = None,
    active_only: bool = True,
    language: str = "en",
    restaurant_id: int | None = None,
) -> list[dict]:
    language = normalize_lang(language)
    restaurant_id = restaurant_id or default_restaurant_id()
    query = """
        SELECT
            mi.*,
            mc.name_en AS category_name,
            mc.is_active AS category_active,
            COALESCE(mit.name, mi.name_en) AS display_name,
            COALESCE(mit.description, mi.description_en) AS display_description
        FROM menu_items mi
        JOIN menu_categories mc ON mc.id = mi.category_id
        LEFT JOIN menu_item_translations mit
            ON mit.item_id = mi.id
           AND mit.language = ?
    """
    conditions: list[str] = ["mi.restaurant_id = ?"]
    params: list[object] = [language, restaurant_id]
    if category_id is not None:
        conditions.append("mi.category_id = ?")
        params.append(category_id)
    if active_only:
        conditions.append("mi.is_active = 1")
        conditions.append("mc.is_active = 1")
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY mc.sort_order, mi.name_en"
    with get_connection() as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def get_item(
    item_id: int,
    active_only: bool = False,
    language: str = "en",
    restaurant_id: int | None = None,
) -> dict | None:
    language = normalize_lang(language)
    restaurant_id = restaurant_id or default_restaurant_id()
    query = """
        SELECT
            mi.*,
            mc.name_en AS category_name,
            mc.is_active AS category_active,
            COALESCE(mit.name, mi.name_en) AS display_name,
            COALESCE(mit.description, mi.description_en) AS display_description
        FROM menu_items mi
        JOIN menu_categories mc ON mc.id = mi.category_id
        LEFT JOIN menu_item_translations mit
            ON mit.item_id = mi.id
           AND mit.language = ?
        WHERE mi.id = ? AND mi.restaurant_id = ?
    """
    params: list[object] = [language, item_id, restaurant_id]
    if active_only:
        query += " AND mi.is_active = 1 AND mc.is_active = 1"
    with get_connection() as conn:
        row = conn.execute(query, params).fetchone()
        return dict(row) if row else None


def create_item(
    category_id: int,
    name_en: str,
    description_en: str,
    price_cents: int,
    name_km: str = "",
    name_zh: str = "",
    description_km: str = "",
    description_zh: str = "",
    restaurant_id: int | None = None,
) -> int:
    restaurant_id = restaurant_id or default_restaurant_id()
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO menu_items (
                restaurant_id, category_id, name_en, name_km, name_zh,
                description_en, description_km, description_zh, price_cents
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                restaurant_id,
                category_id,
                name_en,
                name_km,
                name_zh,
                description_en,
                description_km,
                description_zh,
                price_cents,
            ),
        )
        item_id = int(cur.lastrowid)
        upsert_item_translation(conn, item_id, "en", name_en, description_en)
        upsert_item_translation(conn, item_id, "kh", name_km or name_en, description_km or description_en)
        upsert_item_translation(conn, item_id, "zh", name_zh or name_en, description_zh or description_en)
        return item_id


def update_item(item_id: int, field: str, value: object) -> None:
    allowed_fields = {
        "name_en",
        "name_km",
        "name_zh",
        "description_en",
        "description_km",
        "description_zh",
        "price_cents",
        "category_id",
        "image_file_id",
    }
    if field not in allowed_fields:
        raise ValueError(f"Unsupported menu item field: {field}")
    with get_connection() as conn:
        conn.execute(
            f"UPDATE menu_items SET {field} = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (value, item_id),
        )
        if field in {"name_en", "description_en", "name_km", "description_km", "name_zh", "description_zh"}:
            sync_item_translations(conn, item_id)


def set_item_active(item_id: int, is_active: bool) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE menu_items SET is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (1 if is_active else 0, item_id),
        )


def slugify(value: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "category"


def upsert_category_translation(
    conn,
    category_id: int,
    language: str,
    name: str,
) -> None:
    conn.execute(
        """
        INSERT INTO menu_category_translations (category_id, language, name)
        VALUES (?, ?, ?)
        ON CONFLICT(category_id, language) DO UPDATE SET name = excluded.name
        """,
        (category_id, language, name),
    )


def create_category(
    name_en: str,
    name_km: str,
    name_zh: str,
    sort_order: int = 0,
    restaurant_id: int | None = None,
) -> int:
    restaurant_id = restaurant_id or default_restaurant_id()
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO menu_categories (restaurant_id, name_en, name_km, slug, sort_order)
            VALUES (?, ?, ?, ?, ?)
            """,
            (restaurant_id, name_en, name_km, slugify(name_en), sort_order),
        )
        category_id = int(cur.lastrowid)
        upsert_category_translation(conn, category_id, "en", name_en)
        upsert_category_translation(conn, category_id, "kh", name_km or name_en)
        upsert_category_translation(conn, category_id, "zh", name_zh or name_en)
        return category_id


def update_category(category_id: int, field: str, value: object) -> None:
    allowed_fields = {"name_en", "name_km", "sort_order", "is_active"}
    if field not in allowed_fields:
        raise ValueError(f"Unsupported category field: {field}")
    with get_connection() as conn:
        conn.execute(f"UPDATE menu_categories SET {field} = ? WHERE id = ?", (value, category_id))
        if field == "name_en":
            upsert_category_translation(conn, category_id, "en", str(value))
            conn.execute("UPDATE menu_categories SET slug = ? WHERE id = ?", (slugify(str(value)), category_id))
        elif field == "name_km":
            upsert_category_translation(conn, category_id, "kh", str(value))


def update_category_translation(category_id: int, language: str, name: str) -> None:
    with get_connection() as conn:
        upsert_category_translation(conn, category_id, language, name)
        if language == "en":
            conn.execute("UPDATE menu_categories SET name_en = ?, slug = ? WHERE id = ?", (name, slugify(name), category_id))
        elif language == "kh":
            conn.execute("UPDATE menu_categories SET name_km = ? WHERE id = ?", (name, category_id))


def set_category_active(category_id: int, is_active: bool) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE menu_categories SET is_active = ? WHERE id = ?",
            (1 if is_active else 0, category_id),
        )


def upsert_item_translation(conn, item_id: int, language: str, name: str, description: str) -> None:
    conn.execute(
        """
        INSERT INTO menu_item_translations (item_id, language, name, description)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(item_id, language) DO UPDATE SET
            name = excluded.name,
            description = excluded.description
        """,
        (item_id, language, name, description),
    )


def sync_item_translations(conn, item_id: int) -> None:
    row = conn.execute("SELECT * FROM menu_items WHERE id = ?", (item_id,)).fetchone()
    if not row:
        return
    upsert_item_translation(conn, item_id, "en", row["name_en"], row["description_en"])
    upsert_item_translation(conn, item_id, "kh", row["name_km"] or row["name_en"], row["description_km"] or row["description_en"])
    upsert_item_translation(conn, item_id, "zh", row["name_zh"] or row["name_en"], row["description_zh"] or row["description_en"])
