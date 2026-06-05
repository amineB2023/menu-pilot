from __future__ import annotations

import random

from restaurant_bot.database import get_connection
from restaurant_bot.services import loyalty_service


def display_reward(reward: dict, language: str = "en") -> tuple[str, str]:
    if language == "kh":
        return reward.get("name_kh") or reward["name_en"], reward.get("description_kh") or reward.get("description_en") or ""
    if language == "zh":
        return reward.get("name_zh") or reward["name_en"], reward.get("description_zh") or reward.get("description_en") or ""
    return reward["name_en"], reward.get("description_en") or ""


def list_rewards(restaurant_id: int, active_only: bool = True) -> list[dict]:
    query = "SELECT * FROM rewards WHERE restaurant_id = ?"
    params: list[object] = [restaurant_id]
    if active_only:
        query += " AND is_active = 1"
    query += " ORDER BY points_required, name_en"
    with get_connection() as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def get_reward(reward_id: int, restaurant_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM rewards WHERE id = ? AND restaurant_id = ?",
            (reward_id, restaurant_id),
        ).fetchone()
    return dict(row) if row else None


def create_reward(
    restaurant_id: int,
    name_en: str,
    name_kh: str,
    name_zh: str,
    description_en: str,
    description_kh: str,
    description_zh: str,
    points_required: int,
    expires_days: int | None = None,
    quantity_limit: int | None = None,
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO rewards (
                restaurant_id, name_en, name_kh, name_zh,
                description_en, description_kh, description_zh,
                points_required, expires_days, quantity_limit
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                restaurant_id,
                name_en,
                name_kh,
                name_zh,
                description_en,
                description_kh,
                description_zh,
                points_required,
                expires_days,
                quantity_limit,
            ),
        )
        return int(cur.lastrowid)


def update_reward(reward_id: int, restaurant_id: int, field: str, value: object) -> None:
    allowed = {
        "name_en",
        "name_kh",
        "name_zh",
        "description_en",
        "description_kh",
        "description_zh",
        "points_required",
        "is_active",
        "expires_days",
        "quantity_limit",
    }
    if field not in allowed:
        raise ValueError("Unsupported reward field.")
    with get_connection() as conn:
        conn.execute(
            f"UPDATE rewards SET {field} = ? WHERE id = ? AND restaurant_id = ?",
            (value, reward_id, restaurant_id),
        )


def generate_voucher_code() -> str:
    with get_connection() as conn:
        while True:
            code = f"MP-RW-{random.randint(1000, 9999)}"
            if not conn.execute("SELECT id FROM reward_redemptions WHERE voucher_code = ?", (code,)).fetchone():
                return code


def redeem_reward(user_id: int, restaurant_id: int, reward_id: int) -> dict:
    reward = get_reward(reward_id, restaurant_id)
    if not reward or not reward["is_active"]:
        raise ValueError("Reward is not available.")
    points_required = int(reward["points_required"])
    current_points = loyalty_service.get_points(user_id, restaurant_id)
    if current_points < points_required:
        raise ValueError("Not enough points.")
    if reward.get("quantity_limit") is not None:
        with get_connection() as conn:
            used_count = conn.execute(
                """
                SELECT COUNT(*) FROM reward_redemptions
                WHERE restaurant_id = ? AND reward_id = ? AND status != 'cancelled'
                """,
                (restaurant_id, reward_id),
            ).fetchone()[0]
        if int(used_count) >= int(reward["quantity_limit"]):
            raise ValueError("Reward limit reached.")

    voucher_code = generate_voucher_code()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO user_loyalty_points (restaurant_id, user_id, points)
            VALUES (?, ?, ?)
            ON CONFLICT(restaurant_id, user_id)
            DO UPDATE SET points = points - excluded.points,
                          updated_at = CURRENT_TIMESTAMP
            """,
            (restaurant_id, user_id, points_required),
        )
        cur = conn.execute(
            """
            INSERT INTO reward_redemptions (
                restaurant_id, user_id, reward_id, voucher_code, points_spent
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (restaurant_id, user_id, reward_id, voucher_code, points_required),
        )
        redemption_id = int(cur.lastrowid)
    redemption = get_redemption(redemption_id, restaurant_id)
    if not redemption:
        raise RuntimeError("Redemption created but not found.")
    return redemption


def get_redemption(redemption_id: int, restaurant_id: int | None = None) -> dict | None:
    query = """
        SELECT rr.*, r.name_en, r.name_kh, r.name_zh, r.description_en,
               r.description_kh, r.description_zh, r.expires_days,
               u.full_name, u.username
        FROM reward_redemptions rr
        JOIN rewards r ON r.id = rr.reward_id
        LEFT JOIN users u ON u.telegram_id = rr.user_id
        WHERE rr.id = ?
    """
    params: list[object] = [redemption_id]
    if restaurant_id is not None:
        query += " AND rr.restaurant_id = ?"
        params.append(restaurant_id)
    with get_connection() as conn:
        row = conn.execute(query, params).fetchone()
    return dict(row) if row else None


def list_user_redemptions(user_id: int, restaurant_id: int) -> list[dict]:
    with get_connection() as conn:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT rr.*, r.name_en, r.name_kh, r.name_zh, r.expires_days
                FROM reward_redemptions rr
                JOIN rewards r ON r.id = rr.reward_id
                WHERE rr.user_id = ? AND rr.restaurant_id = ?
                ORDER BY rr.redeemed_at DESC, rr.id DESC
                """,
                (user_id, restaurant_id),
            ).fetchall()
        ]


def list_recent_redemptions(restaurant_id: int, limit: int = 20) -> list[dict]:
    with get_connection() as conn:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT rr.*, r.name_en, u.full_name
                FROM reward_redemptions rr
                JOIN rewards r ON r.id = rr.reward_id
                LEFT JOIN users u ON u.telegram_id = rr.user_id
                WHERE rr.restaurant_id = ?
                ORDER BY rr.redeemed_at DESC, rr.id DESC
                LIMIT ?
                """,
                (restaurant_id, limit),
            ).fetchall()
        ]


def mark_redemption_used(redemption_id: int, used_by: int | None = None) -> dict:
    with get_connection() as conn:
        row = conn.execute("SELECT restaurant_id FROM reward_redemptions WHERE id = ?", (redemption_id,)).fetchone()
        if not row:
            raise ValueError("Redemption not found.")
        conn.execute(
            """
            UPDATE reward_redemptions
            SET status = 'used', used_at = CURRENT_TIMESTAMP, used_by = ?
            WHERE id = ? AND status = 'pending'
            """,
            (used_by, redemption_id),
        )
        restaurant_id = int(row["restaurant_id"])
    redemption = get_redemption(redemption_id, restaurant_id)
    if not redemption:
        raise RuntimeError("Redemption updated but not found.")
    return redemption


def reject_redemption(redemption_id: int, used_by: int | None = None) -> dict:
    refund: tuple[int, int, int] | None = None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM reward_redemptions WHERE id = ?",
            (redemption_id,),
        ).fetchone()
        if not row:
            raise ValueError("Redemption not found.")
        if row["status"] == "pending":
            conn.execute(
                """
                UPDATE reward_redemptions
                SET status = 'cancelled', used_at = CURRENT_TIMESTAMP, used_by = ?
                WHERE id = ?
                """,
                (used_by, redemption_id),
            )
            refund = (int(row["user_id"]), int(row["restaurant_id"]), int(row["points_spent"]))
        restaurant_id = int(row["restaurant_id"])
    if refund:
        loyalty_service.change_points(*refund)
    redemption = get_redemption(redemption_id, restaurant_id)
    if not redemption:
        raise RuntimeError("Redemption updated but not found.")
    return redemption
