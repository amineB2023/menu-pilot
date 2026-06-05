from __future__ import annotations

from datetime import datetime

from restaurant_bot.database import get_connection


AUDIENCE_LABELS = {
    "all": "All Customers",
    "inactive_7": "Inactive 7 Days",
    "inactive_30": "Inactive 30 Days",
    "loyalty": "Loyalty Members",
    "top": "Top Customers",
    "first_time": "First-Time Customers",
}


def audience_label(audience_type: str) -> str:
    return AUDIENCE_LABELS.get(audience_type, audience_type.replace("_", " ").title())


def list_audience(restaurant_id: int, audience_type: str) -> list[dict]:
    params: list[object] = [restaurant_id]
    if audience_type == "all":
        query = """
            SELECT u.telegram_id, u.full_name, u.username, u.language, COUNT(o.id) AS orders_count
            FROM users u
            JOIN orders o ON o.user_id = u.telegram_id AND o.restaurant_id = ?
            GROUP BY u.telegram_id
            ORDER BY MAX(o.created_at) DESC
        """
    elif audience_type in {"inactive_7", "inactive_30"}:
        days = 7 if audience_type == "inactive_7" else 30
        params.append(f"-{days} days")
        query = """
            SELECT u.telegram_id, u.full_name, u.username, u.language, MAX(o.created_at) AS last_order
            FROM users u
            JOIN orders o ON o.user_id = u.telegram_id AND o.restaurant_id = ?
            GROUP BY u.telegram_id
            HAVING datetime(last_order) < datetime('now', ?)
            ORDER BY last_order ASC
        """
    elif audience_type == "loyalty":
        query = """
            SELECT u.telegram_id, u.full_name, u.username, u.language, ulp.points
            FROM user_loyalty_points ulp
            JOIN users u ON u.telegram_id = ulp.user_id
            WHERE ulp.restaurant_id = ? AND ulp.points > 0
            ORDER BY ulp.points DESC
        """
    elif audience_type == "top":
        query = """
            SELECT u.telegram_id, u.full_name, u.username, u.language, SUM(o.subtotal_cents) AS total_spent
            FROM users u
            JOIN orders o ON o.user_id = u.telegram_id AND o.restaurant_id = ?
            WHERE o.status != 'cancelled'
            GROUP BY u.telegram_id
            ORDER BY total_spent DESC
            LIMIT 50
        """
    elif audience_type == "first_time":
        query = """
            SELECT u.telegram_id, u.full_name, u.username, u.language, COUNT(o.id) AS delivered_orders
            FROM users u
            JOIN orders o ON o.user_id = u.telegram_id AND o.restaurant_id = ?
            WHERE o.status = 'delivered'
            GROUP BY u.telegram_id
            HAVING delivered_orders = 1
            ORDER BY MAX(o.created_at) DESC
        """
    else:
        raise ValueError(f"Unsupported audience type: {audience_type}")

    with get_connection() as conn:
        return [dict(row) for row in conn.execute(query, tuple(params)).fetchall()]


def campaigns_sent_today(restaurant_id: int) -> int:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM promotion_campaigns
            WHERE restaurant_id = ?
              AND date(created_at, 'localtime') = date('now', 'localtime')
            """,
            (restaurant_id,),
        ).fetchone()
    return int(row["count"] if row else 0)


def create_campaign(
    restaurant_id: int,
    title: str,
    message: str,
    audience_type: str,
    target_count: int,
    sent_count: int,
    failed_count: int,
    blocked_count: int,
    created_by: int,
    photo_file_id: str | None = None,
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO promotion_campaigns (
                restaurant_id, title, message, photo_file_id, audience_type, target_count,
                sent_count, failed_count, blocked_count, created_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                restaurant_id,
                title,
                message,
                photo_file_id,
                audience_type,
                target_count,
                sent_count,
                failed_count,
                blocked_count,
                created_by,
            ),
        )
        return int(cur.lastrowid)


def list_campaigns(restaurant_id: int, limit: int = 10) -> list[dict]:
    with get_connection() as conn:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM promotion_campaigns
                WHERE restaurant_id = ?
                ORDER BY datetime(created_at) DESC, id DESC
                LIMIT ?
                """,
                (restaurant_id, limit),
            ).fetchall()
        ]


def format_campaign_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value
