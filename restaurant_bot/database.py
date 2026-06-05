from __future__ import annotations

import sqlite3
import os
from collections.abc import Iterable
from pathlib import Path

from restaurant_bot.config import DATA_DIR, DB_PATH, load_dotenv


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path = DB_PATH) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS restaurants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                logo_file_id TEXT,
                phone TEXT DEFAULT '',
                address TEXT DEFAULT '',
                currency_symbol TEXT NOT NULL DEFAULT '$',
                default_language TEXT NOT NULL DEFAULT 'en',
                khqr_image_file_id TEXT,
                khqr_payment_enabled INTEGER NOT NULL DEFAULT 0,
                staff_group_id INTEGER,
                delivery_enabled INTEGER NOT NULL DEFAULT 1,
                pickup_enabled INTEGER NOT NULL DEFAULT 1,
                loyalty_enabled INTEGER NOT NULL DEFAULT 0,
                loyalty_cents_per_point INTEGER NOT NULL DEFAULT 100,
                rewards_enabled INTEGER NOT NULL DEFAULT 0,
                repeat_orders_enabled INTEGER NOT NULL DEFAULT 1,
                promotions_enabled INTEGER NOT NULL DEFAULT 1,
                promotion_max_per_day INTEGER NOT NULL DEFAULT 3,
                promotion_audience_filters_enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS restaurant_admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                restaurant_id INTEGER NOT NULL,
                telegram_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('owner', 'manager', 'staff')),
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(restaurant_id, telegram_id),
                FOREIGN KEY (restaurant_id) REFERENCES restaurants(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                full_name TEXT,
                username TEXT,
                language TEXT DEFAULT 'en',
                preferred_restaurant_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS menu_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                restaurant_id INTEGER NOT NULL,
                name_en TEXT NOT NULL,
                name_km TEXT DEFAULT '',
                slug TEXT DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                UNIQUE(restaurant_id, name_en),
                FOREIGN KEY (restaurant_id) REFERENCES restaurants(id)
            );

            CREATE TABLE IF NOT EXISTS menu_category_translations (
                category_id INTEGER NOT NULL,
                language TEXT NOT NULL,
                name TEXT NOT NULL,
                PRIMARY KEY (category_id, language),
                FOREIGN KEY (category_id) REFERENCES menu_categories(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS menu_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                restaurant_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                name_en TEXT NOT NULL,
                name_km TEXT DEFAULT '',
                name_zh TEXT DEFAULT '',
                description_en TEXT NOT NULL DEFAULT '',
                description_km TEXT DEFAULT '',
                description_zh TEXT DEFAULT '',
                price_cents INTEGER NOT NULL CHECK(price_cents >= 0),
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (category_id) REFERENCES menu_categories(id)
            );

            CREATE TABLE IF NOT EXISTS menu_item_translations (
                item_id INTEGER NOT NULL,
                language TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                PRIMARY KEY (item_id, language),
                FOREIGN KEY (item_id) REFERENCES menu_items(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS menu_addon_translations (
                addon_name TEXT NOT NULL,
                language TEXT NOT NULL,
                translated_name TEXT NOT NULL,
                PRIMARY KEY (addon_name, language)
            );

            CREATE TABLE IF NOT EXISTS carts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                restaurant_id INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, restaurant_id),
                FOREIGN KEY (user_id) REFERENCES users(telegram_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS cart_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cart_id INTEGER NOT NULL,
                menu_item_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                UNIQUE(cart_id, menu_item_id),
                FOREIGN KEY (cart_id) REFERENCES carts(id) ON DELETE CASCADE,
                FOREIGN KEY (menu_item_id) REFERENCES menu_items(id)
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_code TEXT NOT NULL UNIQUE,
                restaurant_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                customer_name TEXT,
                phone TEXT NOT NULL,
                fulfillment_type TEXT NOT NULL CHECK(fulfillment_type IN ('pickup', 'delivery')),
                address TEXT,
                latitude REAL,
                longitude REAL,
                notes TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                payment_method TEXT NOT NULL DEFAULT 'cash' CHECK(payment_method IN ('cash', 'khqr')),
                payment_status TEXT NOT NULL DEFAULT 'unpaid' CHECK(payment_status IN ('unpaid', 'pending', 'paid', 'rejected')),
                payment_screenshot_file_id TEXT,
                payment_confirmed_by INTEGER,
                payment_confirmed_at TEXT,
                loyalty_points_awarded INTEGER NOT NULL DEFAULT 0,
                subtotal_cents INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                menu_item_id INTEGER,
                item_name TEXT NOT NULL,
                unit_price_cents INTEGER NOT NULL,
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                line_total_cents INTEGER NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
                FOREIGN KEY (menu_item_id) REFERENCES menu_items(id)
            );

            CREATE TABLE IF NOT EXISTS order_status_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                changed_by INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_loyalty_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                restaurant_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                points INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(restaurant_id, user_id),
                FOREIGN KEY (restaurant_id) REFERENCES restaurants(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS rewards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                restaurant_id INTEGER NOT NULL,
                name_en TEXT NOT NULL,
                name_kh TEXT DEFAULT '',
                name_zh TEXT DEFAULT '',
                description_en TEXT DEFAULT '',
                description_kh TEXT DEFAULT '',
                description_zh TEXT DEFAULT '',
                points_required INTEGER NOT NULL CHECK(points_required > 0),
                is_active INTEGER NOT NULL DEFAULT 1,
                quantity_limit INTEGER,
                expires_days INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (restaurant_id) REFERENCES restaurants(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS reward_redemptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                restaurant_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                reward_id INTEGER NOT NULL,
                voucher_code TEXT NOT NULL UNIQUE,
                points_spent INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'used', 'expired', 'cancelled')),
                redeemed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                used_at TEXT,
                used_by INTEGER,
                FOREIGN KEY (restaurant_id) REFERENCES restaurants(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id) ON DELETE CASCADE,
                FOREIGN KEY (reward_id) REFERENCES rewards(id)
            );

            CREATE TABLE IF NOT EXISTS promotion_campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                restaurant_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                photo_file_id TEXT,
                audience_type TEXT NOT NULL,
                target_count INTEGER NOT NULL DEFAULT 0,
                sent_count INTEGER NOT NULL DEFAULT 0,
                failed_count INTEGER NOT NULL DEFAULT 0,
                blocked_count INTEGER NOT NULL DEFAULT 0,
                created_by INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (restaurant_id) REFERENCES restaurants(id) ON DELETE CASCADE
            );
            """
        )
        migrate_white_label_schema(conn)
        ensure_menu_item_image_column(conn)
        ensure_menu_translation_columns(conn)
    seed_data()
    seed_menu_translations()


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def scalar(conn: sqlite3.Connection, query: str, params: tuple[object, ...] = ()) -> object:
    row = conn.execute(query, params).fetchone()
    return row[0] if row else None


def slugify(value: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "restaurant"


def get_default_restaurant_seed() -> dict[str, object]:
    load_dotenv()
    staff_group_raw = os.getenv("STAFF_GROUP_ID", "").strip()
    staff_group_id = int(staff_group_raw) if staff_group_raw else None
    name = os.getenv("RESTAURANT_NAME", "Sweet Chilli").strip() or "Sweet Chilli"
    return {
        "slug": os.getenv("RESTAURANT_SLUG", slugify(name)).strip() or "sweet-chilli",
        "name": name,
        "phone": os.getenv("RESTAURANT_PHONE", "+855 12 345 678").strip(),
        "address": os.getenv("RESTAURANT_ADDRESS", "Phnom Penh, Cambodia").strip(),
        "currency_symbol": os.getenv("RESTAURANT_CURRENCY_SYMBOL", "$").strip() or "$",
        "default_language": os.getenv("RESTAURANT_DEFAULT_LANGUAGE", "en").strip() or "en",
        "staff_group_id": staff_group_id,
    }


def ensure_default_restaurant(conn: sqlite3.Connection) -> int:
    seed = get_default_restaurant_seed()
    row = conn.execute("SELECT id FROM restaurants WHERE slug = ?", (seed["slug"],)).fetchone()
    if row:
        restaurant_id = int(row["id"])
        conn.execute(
            """
            UPDATE restaurants
            SET name = COALESCE(NULLIF(name, ''), ?),
                phone = COALESCE(NULLIF(phone, ''), ?),
                address = COALESCE(NULLIF(address, ''), ?),
                currency_symbol = COALESCE(NULLIF(currency_symbol, ''), ?),
                default_language = COALESCE(NULLIF(default_language, ''), ?),
                staff_group_id = COALESCE(staff_group_id, ?)
            WHERE id = ?
            """,
            (
                seed["name"],
                seed["phone"],
                seed["address"],
                seed["currency_symbol"],
                seed["default_language"],
                seed["staff_group_id"],
                restaurant_id,
            ),
        )
        return restaurant_id

    cur = conn.execute(
        """
        INSERT INTO restaurants (
            slug, name, phone, address, currency_symbol, default_language, staff_group_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            seed["slug"],
            seed["name"],
            seed["phone"],
            seed["address"],
            seed["currency_symbol"],
            seed["default_language"],
            seed["staff_group_id"],
        ),
    )
    return int(cur.lastrowid)


def seed_default_restaurant_admins(conn: sqlite3.Connection, restaurant_id: int) -> None:
    load_dotenv()
    for raw_id in os.getenv("ADMIN_IDS", "").split(","):
        raw_id = raw_id.strip()
        if not raw_id:
            continue
        try:
            telegram_id = int(raw_id)
        except ValueError:
            continue
        conn.execute(
            """
            INSERT INTO restaurant_admins (restaurant_id, telegram_id, role)
            VALUES (?, ?, 'owner')
            ON CONFLICT(restaurant_id, telegram_id) DO NOTHING
            """,
            (restaurant_id, telegram_id),
        )


def migrate_white_label_schema(conn: sqlite3.Connection) -> None:
    restaurant_id = ensure_default_restaurant(conn)
    seed_default_restaurant_admins(conn, restaurant_id)

    user_columns = table_columns(conn, "users")
    if "preferred_restaurant_id" not in user_columns:
        conn.execute("ALTER TABLE users ADD COLUMN preferred_restaurant_id INTEGER")
    conn.execute(
        "UPDATE users SET preferred_restaurant_id = COALESCE(preferred_restaurant_id, ?)",
        (restaurant_id,),
    )

    category_columns = table_columns(conn, "menu_categories")
    needs_category_rebuild = "restaurant_id" not in category_columns
    if needs_category_rebuild:
        conn.commit()
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute(
            """
            CREATE TABLE menu_categories_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                restaurant_id INTEGER NOT NULL,
                name_en TEXT NOT NULL,
                name_km TEXT DEFAULT '',
                slug TEXT DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                UNIQUE(restaurant_id, name_en),
                FOREIGN KEY (restaurant_id) REFERENCES restaurants(id)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO menu_categories_new (
                id, restaurant_id, name_en, name_km, slug, sort_order, is_active
            )
            SELECT id, ?, name_en, name_km, COALESCE(slug, ''), sort_order, is_active
            FROM menu_categories
            """,
            (restaurant_id,),
        )
        conn.execute("DROP TABLE menu_categories")
        conn.execute("ALTER TABLE menu_categories_new RENAME TO menu_categories")
        conn.execute("PRAGMA foreign_keys = ON")

    item_columns = table_columns(conn, "menu_items")
    if "restaurant_id" not in item_columns:
        conn.execute("ALTER TABLE menu_items ADD COLUMN restaurant_id INTEGER")
    conn.execute(
        "UPDATE menu_items SET restaurant_id = COALESCE(restaurant_id, ?)",
        (restaurant_id,),
    )

    order_columns = table_columns(conn, "orders")
    if "restaurant_id" not in order_columns:
        conn.execute("ALTER TABLE orders ADD COLUMN restaurant_id INTEGER")
    conn.execute(
        "UPDATE orders SET restaurant_id = COALESCE(restaurant_id, ?)",
        (restaurant_id,),
    )

    restaurant_columns = table_columns(conn, "restaurants")
    if "khqr_payment_enabled" not in restaurant_columns:
        conn.execute("ALTER TABLE restaurants ADD COLUMN khqr_payment_enabled INTEGER NOT NULL DEFAULT 0")
    if "loyalty_cents_per_point" not in restaurant_columns:
        conn.execute("ALTER TABLE restaurants ADD COLUMN loyalty_cents_per_point INTEGER NOT NULL DEFAULT 100")
    if "promotions_enabled" not in restaurant_columns:
        conn.execute("ALTER TABLE restaurants ADD COLUMN promotions_enabled INTEGER NOT NULL DEFAULT 1")
    if "promotion_max_per_day" not in restaurant_columns:
        conn.execute("ALTER TABLE restaurants ADD COLUMN promotion_max_per_day INTEGER NOT NULL DEFAULT 3")
    if "promotion_audience_filters_enabled" not in restaurant_columns:
        conn.execute("ALTER TABLE restaurants ADD COLUMN promotion_audience_filters_enabled INTEGER NOT NULL DEFAULT 1")

    order_columns = table_columns(conn, "orders")
    if "payment_method" not in order_columns:
        conn.execute("ALTER TABLE orders ADD COLUMN payment_method TEXT NOT NULL DEFAULT 'cash'")
    if "payment_status" not in order_columns:
        conn.execute("ALTER TABLE orders ADD COLUMN payment_status TEXT NOT NULL DEFAULT 'unpaid'")
    if "payment_screenshot_file_id" not in order_columns:
        conn.execute("ALTER TABLE orders ADD COLUMN payment_screenshot_file_id TEXT")
    if "payment_confirmed_by" not in order_columns:
        conn.execute("ALTER TABLE orders ADD COLUMN payment_confirmed_by INTEGER")
    if "payment_confirmed_at" not in order_columns:
        conn.execute("ALTER TABLE orders ADD COLUMN payment_confirmed_at TEXT")
    if "loyalty_points_awarded" not in order_columns:
        conn.execute("ALTER TABLE orders ADD COLUMN loyalty_points_awarded INTEGER NOT NULL DEFAULT 0")

    cart_columns = table_columns(conn, "carts")
    needs_cart_rebuild = "restaurant_id" not in cart_columns
    if needs_cart_rebuild:
        conn.commit()
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute(
            """
            CREATE TABLE carts_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                restaurant_id INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, restaurant_id),
                FOREIGN KEY (user_id) REFERENCES users(telegram_id) ON DELETE CASCADE,
                FOREIGN KEY (restaurant_id) REFERENCES restaurants(id)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO carts_new (id, user_id, restaurant_id, created_at, updated_at)
            SELECT id, user_id, ?, created_at, updated_at
            FROM carts
            """,
            (restaurant_id,),
        )
        conn.execute("DROP TABLE carts")
        conn.execute("ALTER TABLE carts_new RENAME TO carts")
        conn.execute("PRAGMA foreign_keys = ON")


def ensure_menu_item_image_column(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(menu_items)").fetchall()
    }
    if "image_file_id" not in columns:
        conn.execute("ALTER TABLE menu_items ADD COLUMN image_file_id TEXT")


def ensure_menu_translation_columns(conn: sqlite3.Connection) -> None:
    category_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(menu_categories)").fetchall()
    }
    if "slug" not in category_columns:
        conn.execute("ALTER TABLE menu_categories ADD COLUMN slug TEXT DEFAULT ''")

    item_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(menu_items)").fetchall()
    }
    if "name_zh" not in item_columns:
        conn.execute("ALTER TABLE menu_items ADD COLUMN name_zh TEXT DEFAULT ''")
    if "description_zh" not in item_columns:
        conn.execute("ALTER TABLE menu_items ADD COLUMN description_zh TEXT DEFAULT ''")


def seed_data() -> None:
    categories = [
        ("Rice", "បាយ", 1),
        ("Noodles", "មី/គុយទាវ", 2),
        ("Drinks", "ភេសជ្ជៈ", 3),
        ("Desserts", "បង្អែម", 4),
    ]
    items = [
        ("Rice", "Bai Sach Chrouk", "បាយសាច់ជ្រូក", "Grilled pork with rice, pickles, and broth.", 250),
        ("Rice", "Fried Rice", "បាយឆា", "Wok-fried rice with egg and vegetables.", 275),
        ("Noodles", "Kuy Teav", "គុយទាវ", "Cambodian noodle soup with herbs and broth.", 250),
        ("Drinks", "Iced Coffee", "កាហ្វេទឹកកក", "Cambodian iced coffee with sweet milk.", 125),
        ("Drinks", "Passion Soda", "សូដាផាសិន", "Refreshing passion fruit soda.", 150),
        ("Desserts", "Mango Sticky Rice", "បាយដំណើបស្វាយ", "Sweet sticky rice with ripe mango.", 200),
    ]

    with get_connection() as conn:
        restaurant_id = ensure_default_restaurant(conn)
        conn.executemany(
            """
            INSERT OR IGNORE INTO menu_categories (restaurant_id, name_en, name_km, sort_order)
            VALUES (?, ?, ?, ?)
            """,
            [(restaurant_id, name_en, name_km, sort_order) for name_en, name_km, sort_order in categories],
        )
        category_rows = conn.execute(
            "SELECT id, name_en FROM menu_categories WHERE restaurant_id = ?",
            (restaurant_id,),
        ).fetchall()
        category_ids = {row["name_en"]: row["id"] for row in category_rows}
        for category_name, name_en, name_km, description, price_cents in items:
            exists = conn.execute(
                "SELECT id FROM menu_items WHERE restaurant_id = ? AND name_en = ?",
                (restaurant_id, name_en),
            ).fetchone()
            if exists:
                continue
            conn.execute(
                """
                INSERT INTO menu_items (
                    restaurant_id, category_id, name_en, name_km, description_en, description_km, price_cents
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (restaurant_id, category_ids[category_name], name_en, name_km, description, "", price_cents),
            )


def seed_menu_translations() -> None:
    category_translations = {
        "Super Rice Set": {"en": "Super Rice Set", "kh": "ឈុតបាយពិសេស", "zh": "超级套餐饭"},
        "Spaghetti": {"en": "Spaghetti", "kh": "ស្ប៉ាហ្គេទី", "zh": "意大利面"},
        "Morning Options": {"en": "Morning Options", "kh": "ជម្រើសពេលព្រឹក", "zh": "早餐选择"},
        "Add-ons": {"en": "Add-ons", "kh": "បន្ថែម", "zh": "附加选项"},
        "Rice": {"en": "Rice", "kh": "បាយ", "zh": "米饭"},
        "Noodles": {"en": "Noodles", "kh": "មី", "zh": "面条"},
        "Drinks": {"en": "Drinks", "kh": "ភេសជ្ជៈ", "zh": "饮料"},
        "Desserts": {"en": "Desserts", "kh": "បង្អែម", "zh": "甜点"},
    }
    item_translations = {
        "Super Rice Set": ("ឈុតបាយពិសេស", "超级套餐饭", "បន្ថែមភេសជ្ជៈ +$0.50", "加饮料 +$0.50"),
        "Fried BBQ with Sunny": ("សាច់អាំងចៀនជាមួយស៊ុតចៀន", "烤肉配煎蛋", "", ""),
        "SC Grilled Chicken with Golden Eggs": ("មាន់អាំង Sweet Chilli ជាមួយស៊ុតមាស", "Sweet Chilli 烤鸡配金蛋", "", ""),
        "Chicken Pop with Golden Eggs": ("មាន់បំពងជាមួយស៊ុតមាស", "鸡块配金蛋", "", ""),
        "Fried Chicken with Rolling Eggs": ("មាន់បំពងជាមួយស៊ុតរុំ", "炸鸡配蛋卷", "", ""),
        "Hot Chicken Basil": ("មាន់បាស៊ីលហឹរ", "罗勒辣鸡", "", ""),
        "Fried BBQ with Rolling Eggs": ("សាច់អាំងចៀនជាមួយស៊ុតរុំ", "烤肉配蛋卷", "", ""),
        "Fried Chicken Burrito": ("ប៊ូរីតូមាន់បំពង", "炸鸡卷饼", "", ""),
        "Spaghetti": ("ស្ប៉ាហ្គេទី", "意大利面", "", ""),
        "Hello Sunny": ("សួស្តីថ្ងៃភ្លឺ", "阳光早餐", "", ""),
        "Hello Sunrise": ("សួស្តីព្រះអាទិត្យរះ", "日出早餐", "", ""),
        "Simply Morning": ("ពេលព្រឹកសាមញ្ញ", "简单早餐", "", ""),
    }
    addon_translations = {
        "Egg": {"en": "Egg", "kh": "ស៊ុត", "zh": "鸡蛋"},
        "Sausage": {"en": "Sausage", "kh": "សាច់ក្រក", "zh": "香肠"},
        "Rolling Egg": {"en": "Rolling Egg", "kh": "ស៊ុតរុំ", "zh": "蛋卷"},
        "Drink": {"en": "Drink", "kh": "ភេសជ្ជៈ", "zh": "饮料"},
    }

    with get_connection() as conn:
        restaurant_id = ensure_default_restaurant(conn)
        for category_name, translations in category_translations.items():
            row = conn.execute(
                "SELECT id FROM menu_categories WHERE restaurant_id = ? AND name_en = ?",
                (restaurant_id, category_name),
            ).fetchone()
            if not row:
                continue
            category_id = row["id"]
            slug = category_name.lower().replace("&", "and").replace(" ", "-")
            conn.execute(
                "UPDATE menu_categories SET slug = COALESCE(NULLIF(slug, ''), ?) WHERE id = ?",
                (slug, category_id),
            )
            for language, name in translations.items():
                conn.execute(
                    """
                    INSERT INTO menu_category_translations (category_id, language, name)
                    VALUES (?, ?, ?)
                    ON CONFLICT(category_id, language) DO UPDATE SET name = excluded.name
                    """,
                    (category_id, language, name),
                )

        for item_name, (kh_name, zh_name, kh_description, zh_description) in item_translations.items():
            row = conn.execute(
                "SELECT id, description_en FROM menu_items WHERE restaurant_id = ? AND name_en = ?",
                (restaurant_id, item_name),
            ).fetchone()
            if not row:
                continue
            item_id = row["id"]
            en_description = row["description_en"] or "Add a drink for +$0.50"
            if item_name == "Super Rice Set":
                en_description = "Add a drink for +$0.50"
            conn.execute(
                """
                UPDATE menu_items
                SET name_km = COALESCE(NULLIF(name_km, ''), ?),
                    name_zh = COALESCE(NULLIF(name_zh, ''), ?),
                    description_km = COALESCE(NULLIF(description_km, ''), ?),
                    description_zh = COALESCE(NULLIF(description_zh, ''), ?)
                WHERE id = ?
                """,
                (kh_name, zh_name, kh_description, zh_description, item_id),
            )
            translations = {
                "en": (item_name, en_description),
                "kh": (kh_name, kh_description or en_description),
                "zh": (zh_name, zh_description or en_description),
            }
            for language, (name, description) in translations.items():
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

        for addon_name, translations in addon_translations.items():
            for language, translated_name in translations.items():
                conn.execute(
                    """
                    INSERT INTO menu_addon_translations (addon_name, language, translated_name)
                    VALUES (?, ?, ?)
                    ON CONFLICT(addon_name, language) DO UPDATE SET
                        translated_name = excluded.translated_name
                    """,
                    (addon_name, language, translated_name),
                )


def execute(query: str, params: Iterable[object] = ()) -> int:
    with get_connection() as conn:
        cur = conn.execute(query, tuple(params))
        return int(cur.lastrowid)
