from __future__ import annotations

from restaurant_bot.database import get_connection
from restaurant_bot.services import restaurant_service


def points_for_order(order: dict, restaurant: dict | None = None) -> int:
    restaurant = restaurant or restaurant_service.get_restaurant(int(order["restaurant_id"]))
    if not restaurant or not restaurant.get("loyalty_enabled"):
        return 0
    cents_per_point = int(restaurant.get("loyalty_cents_per_point") or 100)
    if cents_per_point <= 0:
        cents_per_point = 100
    return int(order["subtotal_cents"]) // cents_per_point


def get_points(user_id: int, restaurant_id: int) -> int:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT points
            FROM user_loyalty_points
            WHERE user_id = ? AND restaurant_id = ?
            """,
            (user_id, restaurant_id),
        ).fetchone()
    return int(row["points"]) if row else 0


def change_points(user_id: int, restaurant_id: int, delta: int) -> int:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO user_loyalty_points (restaurant_id, user_id, points)
            VALUES (?, ?, ?)
            ON CONFLICT(restaurant_id, user_id)
            DO UPDATE SET points = MAX(0, points + excluded.points),
                          updated_at = CURRENT_TIMESTAMP
            """,
            (restaurant_id, user_id, delta),
        )
        row = conn.execute(
            """
            SELECT points FROM user_loyalty_points
            WHERE restaurant_id = ? AND user_id = ?
            """,
            (restaurant_id, user_id),
        ).fetchone()
    return int(row["points"]) if row else 0


def award_order_points(order: dict, restaurant: dict | None = None) -> dict:
    restaurant = restaurant or restaurant_service.get_restaurant(int(order["restaurant_id"]))
    points = points_for_order(order, restaurant)
    if points <= 0 or int(order.get("loyalty_points_awarded") or 0) > 0:
        return {"awarded": 0, "balance": get_points(int(order["user_id"]), int(order["restaurant_id"]))}

    with get_connection() as conn:
        current_order = conn.execute(
            "SELECT loyalty_points_awarded FROM orders WHERE id = ?",
            (order["id"],),
        ).fetchone()
        if not current_order or int(current_order["loyalty_points_awarded"] or 0) > 0:
            return {"awarded": 0, "balance": get_points(int(order["user_id"]), int(order["restaurant_id"]))}
        conn.execute(
            """
            INSERT INTO user_loyalty_points (restaurant_id, user_id, points)
            VALUES (?, ?, ?)
            ON CONFLICT(restaurant_id, user_id)
            DO UPDATE SET points = points + excluded.points,
                          updated_at = CURRENT_TIMESTAMP
            """,
            (order["restaurant_id"], order["user_id"], points),
        )
        conn.execute(
            """
            UPDATE orders
            SET loyalty_points_awarded = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (points, order["id"]),
        )
        row = conn.execute(
            """
            SELECT points
            FROM user_loyalty_points
            WHERE user_id = ? AND restaurant_id = ?
            """,
            (order["user_id"], order["restaurant_id"]),
        ).fetchone()
    return {"awarded": points, "balance": int(row["points"]) if row else points}
