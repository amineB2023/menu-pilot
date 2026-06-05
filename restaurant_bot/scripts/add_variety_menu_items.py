from __future__ import annotations

from restaurant_bot import database
from restaurant_bot.services import menu_service, restaurant_service


CATEGORIES = [
    ("Combo Sets", "ឈុតមុខម្ហូប", "套餐", 90),
    ("Chicken & Snacks", "មាន់ និងអាហារសម្រន់", "鸡肉和小吃", 91),
    ("Sides", "ម្ហូបបន្ថែម", "配菜", 92),
    ("Desserts", "បង្អែម", "甜点", 93),
]


ITEMS = [
    (
        "Combo Sets",
        "Sweet Chilli Family Combo",
        "ឈុតគ្រួសារ Sweet Chilli",
        "Sweet Chilli 家庭套餐",
        "A generous sharing set with chicken, rice, fries, and drinks.",
        "ឈុតចែករំលែកមានមាន់ បាយ ដំឡូងបារាំង និងភេសជ្ជៈ។",
        "适合分享的套餐，含鸡肉、米饭、薯条和饮料。",
        999,
    ),
    (
        "Combo Sets",
        "Student Lunch Combo",
        "ឈុតអាហារថ្ងៃត្រង់សិស្ស",
        "学生午餐套餐",
        "Quick lunch set with rice, chicken, and one iced tea.",
        "ឈុតអាហារថ្ងៃត្រង់រហ័ស មានបាយ មាន់ និងតែទឹកកកមួយ។",
        "快捷午餐套餐，含米饭、鸡肉和一杯冰茶。",
        450,
    ),
    (
        "Chicken & Snacks",
        "Spicy Chicken Wings",
        "ស្លាបមាន់ហឹរ",
        "香辣鸡翅",
        "Crispy wings tossed with Sweet Chilli spicy sauce.",
        "ស្លាបមាន់បំពងស្រួយលាយទឹកជ្រលក់ហឹរ Sweet Chilli។",
        "酥脆鸡翅配 Sweet Chilli 香辣酱。",
        395,
    ),
    (
        "Chicken & Snacks",
        "Crispy Chicken Nuggets",
        "ណាហ្គេតមាន់ស្រួយ",
        "香脆鸡块",
        "Golden chicken nuggets served with dipping sauce.",
        "ណាហ្គេតមាន់ពណ៌មាស ជាមួយទឹកជ្រលក់។",
        "金黄鸡块，配蘸酱。",
        275,
    ),
    (
        "Sides",
        "Cheesy Fries",
        "ដំឡូងបារាំងឈីស",
        "芝士薯条",
        "Crispy fries with creamy cheese topping.",
        "ដំឡូងបារាំងស្រួយជាមួយឈីស។",
        "酥脆薯条配浓郁芝士。",
        225,
    ),
    (
        "Sides",
        "Garlic Bread Bites",
        "នំបុ័ងខ្ទឹមស",
        "蒜香面包块",
        "Warm garlic bread bites for sharing.",
        "នំបុ័ងខ្ទឹមសក្តៅៗសម្រាប់ចែករំលែក។",
        "热蒜香面包块，适合分享。",
        175,
    ),
    (
        "Drinks",
        "Passion Fruit Iced Tea",
        "តែទឹកកកផាសិន",
        "百香果冰茶",
        "Refreshing iced tea with passion fruit.",
        "តែទឹកកកស្រស់ជាមួយរសជាតិផាសិន។",
        "清爽百香果冰茶。",
        150,
    ),
    (
        "Drinks",
        "Lemon Soda",
        "សូដាក្រូចឆ្មា",
        "柠檬苏打",
        "Bright lemon soda served cold.",
        "សូដាក្រូចឆ្មាត្រជាក់ស្រស់។",
        "冰爽柠檬苏打。",
        125,
    ),
    (
        "Desserts",
        "Mango Pudding",
        "ពូឌីងស្វាយ",
        "芒果布丁",
        "Smooth mango pudding with a light creamy finish.",
        "ពូឌីងស្វាយទន់រលោងមានរសជាតិផ្អែមស្រាល។",
        "顺滑芒果布丁，口感清甜。",
        185,
    ),
    (
        "Desserts",
        "Chocolate Brownie Cup",
        "ប្រោននីសូកូឡាកែវ",
        "巧克力布朗尼杯",
        "Rich brownie cup for a quick sweet treat.",
        "ប្រោននីសូកូឡាសម្បូររសជាតិ សម្រាប់បង្អែមរហ័ស។",
        "浓郁巧克力布朗尼杯。",
        210,
    ),
]


def ensure_category(category_by_name: dict[str, int], row: tuple[str, str, str, int], restaurant_id: int) -> int:
    name_en, name_km, name_zh, sort_order = row
    if name_en in category_by_name:
        return category_by_name[name_en]
    category_id = menu_service.create_category(name_en, name_km, name_zh, sort_order, restaurant_id=restaurant_id)
    category_by_name[name_en] = category_id
    return category_id


def main() -> None:
    database.init_db()
    restaurant = restaurant_service.get_deployment_restaurant()
    if not restaurant:
        raise RuntimeError("No active restaurant found. Check RESTAURANT_SLUG/settings.")
    restaurant_id = int(restaurant["id"])

    with database.get_connection() as conn:
        existing_categories = conn.execute(
            "SELECT id, name_en FROM menu_categories WHERE restaurant_id = ?",
            (restaurant_id,),
        ).fetchall()
        category_by_name = {row["name_en"]: int(row["id"]) for row in existing_categories}

    for category in CATEGORIES:
        ensure_category(category_by_name, category, restaurant_id)

    added = 0
    updated = 0
    with database.get_connection() as conn:
        for category_name, name_en, name_km, name_zh, desc_en, desc_km, desc_zh, price_cents in ITEMS:
            category_id = category_by_name[category_name]
            row = conn.execute(
                "SELECT id FROM menu_items WHERE restaurant_id = ? AND name_en = ?",
                (restaurant_id, name_en),
            ).fetchone()
            if row:
                item_id = int(row["id"])
                conn.execute(
                    """
                    UPDATE menu_items
                    SET category_id = ?, name_km = ?, name_zh = ?,
                        description_en = ?, description_km = ?, description_zh = ?,
                        price_cents = ?, is_active = 1, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (category_id, name_km, name_zh, desc_en, desc_km, desc_zh, price_cents, item_id),
                )
                updated += 1
            else:
                cur = conn.execute(
                    """
                    INSERT INTO menu_items (
                        restaurant_id, category_id, name_en, name_km, name_zh,
                        description_en, description_km, description_zh, price_cents, is_active
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                    """,
                    (restaurant_id, category_id, name_en, name_km, name_zh, desc_en, desc_km, desc_zh, price_cents),
                )
                item_id = int(cur.lastrowid)
                added += 1
            for language, name, description in (
                ("en", name_en, desc_en),
                ("kh", name_km, desc_km),
                ("zh", name_zh, desc_zh),
            ):
                menu_service.upsert_item_translation(conn, item_id, language, name, description)

    print(f"Added {added} item(s), updated {updated} item(s) for {restaurant['name']}.")


if __name__ == "__main__":
    main()
