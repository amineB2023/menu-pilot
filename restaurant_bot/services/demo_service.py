from __future__ import annotations

from restaurant_bot.database import get_connection


DEMO_CUSTOMERS = [
    (900001001, "Demo Customer One", "demo_customer_one", "en"),
    (900001002, "Demo Customer Two", "demo_customer_two", "zh"),
]


def reset_demo_data(restaurant_id: int) -> dict[str, int]:
    with get_connection() as conn:
        order_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM orders WHERE restaurant_id = ?",
                (restaurant_id,),
            ).fetchone()[0]
        )
        cart_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM carts WHERE restaurant_id = ?",
                (restaurant_id,),
            ).fetchone()[0]
        )
        loyalty_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM user_loyalty_points WHERE restaurant_id = ?",
                (restaurant_id,),
            ).fetchone()[0]
        )
        redemption_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM reward_redemptions WHERE restaurant_id = ?",
                (restaurant_id,),
            ).fetchone()[0]
        )

        conn.execute("DELETE FROM orders WHERE restaurant_id = ?", (restaurant_id,))
        conn.execute("DELETE FROM carts WHERE restaurant_id = ?", (restaurant_id,))
        conn.execute("DELETE FROM reward_redemptions WHERE restaurant_id = ?", (restaurant_id,))
        conn.execute("DELETE FROM user_loyalty_points WHERE restaurant_id = ?", (restaurant_id,))

        for telegram_id, full_name, username, language in DEMO_CUSTOMERS:
            conn.execute(
                """
                INSERT INTO users (
                    telegram_id, full_name, username, language, preferred_restaurant_id
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    full_name = excluded.full_name,
                    username = excluded.username,
                    language = excluded.language,
                    preferred_restaurant_id = excluded.preferred_restaurant_id
                """,
                (telegram_id, full_name, username, language, restaurant_id),
            )

    return {
        "orders_deleted": order_count,
        "carts_deleted": cart_count,
        "loyalty_balances_deleted": loyalty_count,
        "reward_redemptions_deleted": redemption_count,
        "sample_customers_created": len(DEMO_CUSTOMERS),
    }
