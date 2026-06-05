from __future__ import annotations

from restaurant_bot.database import get_connection
from restaurant_bot.services import restaurant_service


def default_restaurant_id() -> int:
    restaurant = restaurant_service.get_deployment_restaurant()
    if not restaurant:
        raise RuntimeError("No active restaurants configured.")
    return int(restaurant["id"])


def ensure_cart(user_id: int, restaurant_id: int | None = None) -> int:
    restaurant_id = restaurant_id or default_restaurant_id()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM carts WHERE user_id = ? AND restaurant_id = ?",
            (user_id, restaurant_id),
        ).fetchone()
        if row:
            return int(row["id"])
        cur = conn.execute(
            "INSERT INTO carts (user_id, restaurant_id) VALUES (?, ?)",
            (user_id, restaurant_id),
        )
        return int(cur.lastrowid)


def add_item(user_id: int, menu_item_id: int, quantity: int = 1, restaurant_id: int | None = None) -> None:
    restaurant_id = restaurant_id or default_restaurant_id()
    cart_id = ensure_cart(user_id, restaurant_id)
    with get_connection() as conn:
        item = conn.execute(
            """
            SELECT mi.id
            FROM menu_items mi
            JOIN menu_categories mc ON mc.id = mi.category_id
            WHERE mi.id = ?
              AND mi.restaurant_id = ?
              AND mc.restaurant_id = ?
              AND mi.is_active = 1
              AND mc.is_active = 1
            """,
            (menu_item_id, restaurant_id, restaurant_id),
        ).fetchone()
        if not item:
            raise ValueError("This item is not available for the selected restaurant.")
        conn.execute(
            """
            INSERT INTO cart_items (cart_id, menu_item_id, quantity)
            VALUES (?, ?, ?)
            ON CONFLICT(cart_id, menu_item_id)
            DO UPDATE SET quantity = quantity + excluded.quantity
            """,
            (cart_id, menu_item_id, quantity),
        )
        conn.execute("UPDATE carts SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (cart_id,))


def set_quantity(user_id: int, menu_item_id: int, quantity: int, restaurant_id: int | None = None) -> None:
    restaurant_id = restaurant_id or default_restaurant_id()
    cart_id = ensure_cart(user_id, restaurant_id)
    with get_connection() as conn:
        if quantity <= 0:
            conn.execute(
                "DELETE FROM cart_items WHERE cart_id = ? AND menu_item_id = ?",
                (cart_id, menu_item_id),
            )
        else:
            conn.execute(
                """
                UPDATE cart_items
                SET quantity = ?
                WHERE cart_id = ? AND menu_item_id = ?
                """,
                (quantity, cart_id, menu_item_id),
            )
        conn.execute("UPDATE carts SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (cart_id,))


def change_quantity(user_id: int, menu_item_id: int, delta: int, restaurant_id: int | None = None) -> None:
    item = get_cart_item(user_id, menu_item_id, restaurant_id)
    if not item:
        return
    set_quantity(user_id, menu_item_id, int(item["quantity"]) + delta, restaurant_id)


def remove_item(user_id: int, menu_item_id: int, restaurant_id: int | None = None) -> None:
    set_quantity(user_id, menu_item_id, 0, restaurant_id)


def clear_cart(user_id: int, restaurant_id: int | None = None) -> None:
    cart_id = ensure_cart(user_id, restaurant_id)
    with get_connection() as conn:
        conn.execute("DELETE FROM cart_items WHERE cart_id = ?", (cart_id,))
        conn.execute("UPDATE carts SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (cart_id,))


def get_cart_item(user_id: int, menu_item_id: int, restaurant_id: int | None = None) -> dict | None:
    cart_id = ensure_cart(user_id, restaurant_id)
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM cart_items WHERE cart_id = ? AND menu_item_id = ?",
            (cart_id, menu_item_id),
        ).fetchone()
        return dict(row) if row else None


def get_cart(user_id: int, language: str = "en", restaurant_id: int | None = None) -> dict:
    restaurant_id = restaurant_id or default_restaurant_id()
    cart_id = ensure_cart(user_id, restaurant_id)
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                ci.menu_item_id,
                ci.quantity,
                mi.name_en,
                mi.name_km,
                mi.name_zh,
                mc.name_en AS category_name,
                COALESCE(mit.name, mi.name_en) AS display_name,
                mi.price_cents,
                mi.is_active,
                mc.is_active AS category_active,
                (ci.quantity * mi.price_cents) AS line_total_cents
            FROM cart_items ci
            JOIN menu_items mi ON mi.id = ci.menu_item_id
            JOIN menu_categories mc ON mc.id = mi.category_id
            LEFT JOIN menu_item_translations mit
                ON mit.item_id = mi.id
               AND mit.language = ?
            WHERE ci.cart_id = ? AND mi.restaurant_id = ? AND mc.restaurant_id = ?
            ORDER BY mi.name_en
            """,
            (language, cart_id, restaurant_id, restaurant_id),
        ).fetchall()
    items = [dict(row) for row in rows if row["is_active"] and row["category_active"]]
    subtotal = sum(int(item["line_total_cents"]) for item in items)
    return {"cart_id": cart_id, "restaurant_id": restaurant_id, "items": items, "subtotal_cents": subtotal}
