from __future__ import annotations

import os

from restaurant_bot.config import load_dotenv
from restaurant_bot.database import get_connection


RESTAURANT_FIELDS = {
    "name",
    "logo_file_id",
    "phone",
    "address",
    "currency_symbol",
    "default_language",
    "khqr_image_file_id",
    "khqr_payment_enabled",
    "staff_group_id",
    "delivery_enabled",
    "pickup_enabled",
    "loyalty_enabled",
    "loyalty_cents_per_point",
    "rewards_enabled",
    "repeat_orders_enabled",
    "promotions_enabled",
    "promotion_max_per_day",
    "promotion_audience_filters_enabled",
    "is_active",
}


def list_restaurants(active_only: bool = True) -> list[dict]:
    query = "SELECT * FROM restaurants"
    params: list[object] = []
    if active_only:
        query += " WHERE is_active = 1"
    query += " ORDER BY name"
    with get_connection() as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def get_restaurant(restaurant_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM restaurants WHERE id = ?", (restaurant_id,)).fetchone()
    return dict(row) if row else None


def get_restaurant_by_slug(slug: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM restaurants WHERE slug = ?", (slug,)).fetchone()
    return dict(row) if row else None


def deployment_slug() -> str:
    load_dotenv()
    return os.getenv("RESTAURANT_SLUG", "sweet-chilli").strip() or "sweet-chilli"


def get_deployment_restaurant() -> dict | None:
    restaurant = get_restaurant_by_slug(deployment_slug())
    if restaurant and restaurant["is_active"]:
        return restaurant
    restaurants = list_restaurants(active_only=True)
    return restaurants[0] if restaurants else None


def get_user_preferred_restaurant(user_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT r.*
            FROM users u
            JOIN restaurants r ON r.id = u.preferred_restaurant_id
            WHERE u.telegram_id = ? AND r.is_active = 1
            """,
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


def set_user_preferred_restaurant(user_id: int, restaurant_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (telegram_id, preferred_restaurant_id)
            VALUES (?, ?)
            ON CONFLICT(telegram_id) DO NOTHING
            """,
            (user_id, restaurant_id),
        )
        conn.execute(
            """
            UPDATE users
            SET preferred_restaurant_id = ?
            WHERE telegram_id = ?
            """,
            (restaurant_id, user_id),
        )


def resolve_user_restaurant(user_id: int) -> dict | None:
    restaurant = get_deployment_restaurant()
    if not restaurant:
        return None
    set_user_preferred_restaurant(user_id, restaurant["id"])
    return restaurant


def list_admin_restaurants(telegram_id: int) -> list[dict]:
    restaurant = get_deployment_restaurant()
    if not restaurant:
        return []
    with get_connection() as conn:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT r.*, ra.role
                FROM restaurant_admins ra
                JOIN restaurants r ON r.id = ra.restaurant_id
                WHERE ra.telegram_id = ? AND r.id = ? AND r.is_active = 1
                ORDER BY r.name
                """,
                (telegram_id, restaurant["id"]),
            ).fetchall()
        ]


def is_restaurant_admin(telegram_id: int, restaurant_id: int) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM restaurant_admins
            WHERE telegram_id = ? AND restaurant_id = ?
            """,
            (telegram_id, restaurant_id),
        ).fetchone()
    return row is not None


def get_admin_restaurant(telegram_id: int, preferred_restaurant_id: int | None = None) -> dict | None:
    restaurants = list_admin_restaurants(telegram_id)
    if not restaurants:
        return None
    return restaurants[0]


def update_restaurant_field(restaurant_id: int, field: str, value: object) -> None:
    if field not in RESTAURANT_FIELDS:
        raise ValueError(f"Unsupported restaurant field: {field}")
    with get_connection() as conn:
        conn.execute(
            f"UPDATE restaurants SET {field} = ? WHERE id = ?",
            (value, restaurant_id),
        )


def create_restaurant(
    slug: str,
    name: str,
    phone: str = "",
    address: str = "",
    currency_symbol: str = "$",
    default_language: str = "en",
    staff_group_id: int | None = None,
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO restaurants (
                slug, name, phone, address, currency_symbol, default_language, staff_group_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (slug, name, phone, address, currency_symbol, default_language, staff_group_id),
        )
        return int(cur.lastrowid)


def add_restaurant_admin(restaurant_id: int, telegram_id: int, role: str = "manager") -> None:
    if role not in {"owner", "manager", "staff"}:
        raise ValueError("Invalid restaurant admin role.")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO restaurant_admins (restaurant_id, telegram_id, role)
            VALUES (?, ?, ?)
            ON CONFLICT(restaurant_id, telegram_id) DO UPDATE SET role = excluded.role
            """,
            (restaurant_id, telegram_id, role),
        )
