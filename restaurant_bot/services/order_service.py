from __future__ import annotations

import random
from datetime import datetime

from restaurant_bot.database import get_connection
from restaurant_bot.services import cart_service, restaurant_service


VALID_STATUSES = {"pending", "accepted", "preparing", "ready", "delivered", "cancelled"}
PAYMENT_METHODS = {"cash", "khqr"}
PAYMENT_STATUSES = {"unpaid", "pending", "paid", "rejected"}
STATUS_LABELS = {
    "pending": "Pending",
    "accepted": "Accepted",
    "preparing": "Preparing",
    "ready": "Ready",
    "delivered": "Delivered",
    "cancelled": "Cancelled",
}


def generate_order_code() -> str:
    today = datetime.now().strftime("%Y%m%d")
    return f"ORD-{today}-{random.randint(1000, 9999)}"


def create_order(
    user_id: int,
    customer_name: str,
    phone: str,
    fulfillment_type: str,
    restaurant_id: int | None = None,
    address: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    notes: str | None = None,
    language: str = "en",
    payment_method: str = "cash",
    payment_status: str | None = None,
    payment_screenshot_file_id: str | None = None,
) -> dict:
    restaurant_id = restaurant_id or cart_service.default_restaurant_id()
    restaurant = restaurant_service.get_restaurant(restaurant_id)
    if not restaurant:
        raise ValueError("Restaurant not found.")
    if fulfillment_type == "delivery" and not restaurant["delivery_enabled"]:
        raise ValueError("Delivery is not available for this restaurant.")
    if fulfillment_type == "pickup" and not restaurant["pickup_enabled"]:
        raise ValueError("Pickup is not available for this restaurant.")

    cart = cart_service.get_cart(user_id, language=language, restaurant_id=restaurant_id)
    if not cart["items"]:
        raise ValueError("Cannot create an order from an empty cart.")
    if fulfillment_type == "delivery" and not (address or (latitude is not None and longitude is not None)):
        raise ValueError("Delivery orders require an address or shared location.")
    if payment_method not in PAYMENT_METHODS:
        raise ValueError("Invalid payment method.")
    payment_status = payment_status or ("pending" if payment_method == "khqr" else "unpaid")
    if payment_status not in PAYMENT_STATUSES:
        raise ValueError("Invalid payment status.")
    if payment_method == "khqr" and not payment_screenshot_file_id:
        raise ValueError("KHQR payment requires a payment screenshot.")

    with get_connection() as conn:
        order_code = generate_order_code()
        while conn.execute("SELECT id FROM orders WHERE order_code = ?", (order_code,)).fetchone():
            order_code = generate_order_code()

        cur = conn.execute(
            """
            INSERT INTO orders (
                order_code, restaurant_id, user_id, customer_name, phone, fulfillment_type, address,
                latitude, longitude, notes, payment_method, payment_status, payment_screenshot_file_id, subtotal_cents
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_code,
                restaurant_id,
                user_id,
                customer_name,
                phone,
                fulfillment_type,
                address,
                latitude,
                longitude,
                notes,
                payment_method,
                payment_status,
                payment_screenshot_file_id,
                cart["subtotal_cents"],
            ),
        )
        order_id = int(cur.lastrowid)
        conn.executemany(
            """
            INSERT INTO order_items (
                order_id, menu_item_id, item_name, unit_price_cents, quantity, line_total_cents
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    order_id,
                    item["menu_item_id"],
                    item.get("display_name") or item["name_en"],
                    item["price_cents"],
                    item["quantity"],
                    item["line_total_cents"],
                )
                for item in cart["items"]
            ],
        )
        conn.execute(
            "INSERT INTO order_status_logs (order_id, status) VALUES (?, ?)",
            (order_id, "pending"),
        )
    cart_service.clear_cart(user_id, restaurant_id)
    order = get_order(order_id)
    if not order:
        raise RuntimeError("Order was created but could not be loaded.")
    return order


def get_order(order_id: int, restaurant_id: int | None = None) -> dict | None:
    with get_connection() as conn:
        if restaurant_id is None:
            row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM orders WHERE id = ? AND restaurant_id = ?",
                (order_id, restaurant_id),
            ).fetchone()
        if not row:
            return None
        items = conn.execute(
            "SELECT * FROM order_items WHERE order_id = ? ORDER BY id",
            (order_id,),
        ).fetchall()
    order = dict(row)
    order["items"] = [dict(item) for item in items]
    return order


def get_order_by_code(order_code: str, restaurant_id: int | None = None) -> dict | None:
    with get_connection() as conn:
        if restaurant_id is None:
            row = conn.execute("SELECT id FROM orders WHERE order_code = ?", (order_code,)).fetchone()
        else:
            row = conn.execute(
                "SELECT id FROM orders WHERE order_code = ? AND restaurant_id = ?",
                (order_code, restaurant_id),
            ).fetchone()
    return get_order(int(row["id"]), restaurant_id=restaurant_id) if row else None


def get_latest_order_for_user(user_id: int, restaurant_id: int | None = None) -> dict | None:
    with get_connection() as conn:
        if restaurant_id is None:
            row = conn.execute(
                "SELECT id FROM orders WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
                (user_id,),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT id FROM orders
                WHERE user_id = ? AND restaurant_id = ?
                ORDER BY created_at DESC, id DESC LIMIT 1
                """,
                (user_id, restaurant_id),
            ).fetchone()
    return get_order(int(row["id"]), restaurant_id=restaurant_id) if row else None


def get_latest_reorderable_order_for_user(user_id: int, restaurant_id: int | None = None) -> dict | None:
    with get_connection() as conn:
        if restaurant_id is None:
            row = conn.execute(
                """
                SELECT id FROM orders
                WHERE user_id = ? AND status = 'delivered'
                ORDER BY created_at DESC, id DESC LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT id FROM orders
                WHERE user_id = ? AND restaurant_id = ? AND status = 'delivered'
                ORDER BY created_at DESC, id DESC LIMIT 1
                """,
                (user_id, restaurant_id),
            ).fetchone()
    return get_order(int(row["id"]), restaurant_id=restaurant_id) if row else None


def update_order_status(order_id: int, status: str, changed_by: int | None = None) -> dict:
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid order status: {status}")
    with get_connection() as conn:
        existing = conn.execute("SELECT id FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not existing:
            raise ValueError("Order not found.")
        conn.execute(
            "UPDATE orders SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, order_id),
        )
        conn.execute(
            "INSERT INTO order_status_logs (order_id, status, changed_by) VALUES (?, ?, ?)",
            (order_id, status, changed_by),
        )
    order = get_order(order_id)
    if not order:
        raise RuntimeError("Order status was updated but order could not be loaded.")
    return order


def update_payment_status(order_id: int, payment_status: str, changed_by: int | None = None) -> dict:
    if payment_status not in PAYMENT_STATUSES:
        raise ValueError(f"Invalid payment status: {payment_status}")
    with get_connection() as conn:
        existing = conn.execute("SELECT id FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not existing:
            raise ValueError("Order not found.")
        confirmed_at_sql = "CURRENT_TIMESTAMP" if payment_status == "paid" else "NULL"
        conn.execute(
            f"""
            UPDATE orders
            SET payment_status = ?,
                payment_confirmed_by = ?,
                payment_confirmed_at = {confirmed_at_sql},
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (payment_status, changed_by if payment_status == "paid" else None, order_id),
        )
    order = get_order(order_id)
    if not order:
        raise RuntimeError("Payment status was updated but order could not be loaded.")
    return order


def update_payment_screenshot(order_id: int, file_id: str) -> dict:
    with get_connection() as conn:
        existing = conn.execute("SELECT id FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not existing:
            raise ValueError("Order not found.")
        conn.execute(
            """
            UPDATE orders
            SET payment_method = 'khqr',
                payment_status = 'pending',
                payment_screenshot_file_id = ?,
                payment_confirmed_by = NULL,
                payment_confirmed_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (file_id, order_id),
        )
    order = get_order(order_id)
    if not order:
        raise RuntimeError("Payment screenshot was updated but order could not be loaded.")
    return order


def switch_payment_to_cash(order_id: int) -> dict:
    with get_connection() as conn:
        existing = conn.execute("SELECT id FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not existing:
            raise ValueError("Order not found.")
        conn.execute(
            """
            UPDATE orders
            SET payment_method = 'cash',
                payment_status = 'unpaid',
                payment_confirmed_by = NULL,
                payment_confirmed_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (order_id,),
        )
    order = get_order(order_id)
    if not order:
        raise RuntimeError("Payment method was updated but order could not be loaded.")
    return order


def list_today_orders(restaurant_id: int | None = None) -> list[dict]:
    with get_connection() as conn:
        params: list[object] = []
        query = """
            SELECT *
            FROM orders
            WHERE date(created_at, 'localtime') = date('now', 'localtime')
        """
        if restaurant_id is not None:
            query += " AND restaurant_id = ?"
            params.append(restaurant_id)
        query += " ORDER BY created_at DESC"
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def sales_summary_today(restaurant_id: int | None = None) -> dict:
    with get_connection() as conn:
        params: list[object] = []
        query = """
            SELECT
                COUNT(*) AS order_count,
                COALESCE(SUM(CASE WHEN status != 'cancelled' THEN subtotal_cents ELSE 0 END), 0) AS sales_cents,
                COALESCE(SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END), 0) AS cancelled_count,
                COALESCE(SUM(CASE WHEN payment_method = 'khqr' AND payment_status = 'paid' THEN 1 ELSE 0 END), 0) AS khqr_paid_count,
                COALESCE(SUM(CASE WHEN payment_method = 'cash' AND status != 'cancelled' THEN 1 ELSE 0 END), 0) AS cash_order_count,
                COALESCE(SUM(loyalty_points_awarded), 0) AS loyalty_points_issued
            FROM orders
            WHERE date(created_at, 'localtime') = date('now', 'localtime')
        """
        if restaurant_id is not None:
            query += " AND restaurant_id = ?"
            params.append(restaurant_id)
        row = conn.execute(query, params).fetchone()
    return dict(row)
