from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from restaurant_bot.i18n import t
from restaurant_bot.services.menu_service import cents_to_usd
from restaurant_bot.services.order_service import STATUS_LABELS


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en"),
                InlineKeyboardButton(text="🇨🇳 中文", callback_data="lang:zh"),
                InlineKeyboardButton(text="🇰🇭 ខ្មែរ", callback_data="lang:kh"),
            ],
        ]
    )


def customer_reply_keyboard(language: str = "en") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(language, "view_menu")), KeyboardButton(text=t(language, "my_cart"))],
            [KeyboardButton(text=t(language, "order_status")), KeyboardButton(text=t(language, "reorder_last_order"))],
            [KeyboardButton(text=t(language, "rewards")), KeyboardButton(text=t(language, "contact"))],
            [KeyboardButton(text=t(language, "change_language"))],
        ],
        resize_keyboard=True,
    )


def main_menu_keyboard(language: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(language, "view_menu"), callback_data="menu:categories")],
            [InlineKeyboardButton(text=t(language, "my_cart"), callback_data="cart:view")],
            [
                InlineKeyboardButton(text=t(language, "order_status"), callback_data="order:status"),
                InlineKeyboardButton(text=t(language, "reorder_last_order"), callback_data="reorder:last"),
            ],
            [
                InlineKeyboardButton(text=t(language, "rewards"), callback_data="rewards:view"),
                InlineKeyboardButton(text=t(language, "contact"), callback_data="contact"),
            ],
            [InlineKeyboardButton(text=t(language, "change_language"), callback_data="language:change")],
        ]
    )


def miniapp_open_keyboard(miniapp_url: str, language: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🍽 Open Menu", web_app=WebAppInfo(url=miniapp_url))],
            [InlineKeyboardButton(text=t(language, "view_menu"), callback_data="menu:categories")],
        ]
    )


def rewards_keyboard(rewards: list[dict], points: int, language: str = "en") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for reward in rewards:
        name = reward.get("display_name") or reward["name_en"]
        lock = "🔒 " if points < int(reward["points_required"]) else ""
        builder.button(text=f"{lock}{name} — {reward['points_required']} pts", callback_data=f"reward:view:{reward['id']}")
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="🎟 My Rewards", callback_data="reward:mine"))
    builder.row(InlineKeyboardButton(text=t(language, "main_menu_button"), callback_data="main"))
    return builder.as_markup()


def reward_confirm_keyboard(reward_id: int, language: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Redeem", callback_data=f"reward:redeem:{reward_id}"),
                InlineKeyboardButton(text="❌ Cancel", callback_data="rewards:view"),
            ]
        ]
    )


def staff_reward_keyboard(redemption_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Mark Used", callback_data=f"staff:reward:{redemption_id}:used"),
                InlineKeyboardButton(text="❌ Reject", callback_data=f"staff:reward:{redemption_id}:cancelled"),
            ]
        ]
    )


def category_icon(name: str) -> str:
    lowered = name.lower()
    if "rice" in lowered:
        return "🍚"
    if "spaghetti" in lowered or "pasta" in lowered:
        return "🍝"
    if "drink" in lowered or "coffee" in lowered:
        return "🥤"
    if "add" in lowered:
        return "➕"
    if "morning" in lowered or "breakfast" in lowered:
        return "🌅"
    if "dessert" in lowered or "sweet" in lowered:
        return "🍰"
    return "🍽"


def categories_keyboard(categories: list[dict], language: str = "en") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in categories:
        name = category.get("display_name") or category["name_en"]
        builder.button(text=f"{category_icon(category['name_en'])} {name}", callback_data=f"cat:{category['id']}")
    max_len = max((len(str(category.get("display_name") or category["name_en"])) for category in categories), default=0)
    builder.adjust(1 if max_len > 16 else 2)
    builder.row(InlineKeyboardButton(text=t(language, "back"), callback_data="main"))
    return builder.as_markup()


def items_keyboard(items: list[dict], category_id: int, language: str = "en") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in items:
        name = item.get("display_name") or item["name_en"]
        sold_out = "" if item["is_active"] else " - ❌ Sold out"
        builder.button(
            text=f"{name} - {cents_to_usd(item['price_cents'])}{sold_out}",
            callback_data=f"item:{item['id']}",
        )
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text=t(language, "categories"), callback_data="menu:categories"))
    return builder.as_markup()


def item_detail_keyboard(item_id: int, category_id: int, language: str = "en", available: bool = True) -> InlineKeyboardMarkup:
    rows = []
    if available:
        rows.append([InlineKeyboardButton(text=t(language, "add_to_cart"), callback_data=f"cart:add:{item_id}")])
        rows.append(
            [
                InlineKeyboardButton(text="➖ Qty", callback_data=f"cart:dec:{item_id}"),
                InlineKeyboardButton(text="➕ Qty", callback_data=f"cart:inc:{item_id}"),
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ Back to Category", callback_data=f"cat:{category_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def after_add_to_cart_keyboard(category_id: int, language: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(language, "confirm_order_now"), callback_data="checkout:start")],
            [InlineKeyboardButton(text=t(language, "add_more_from_category"), callback_data=f"cat:{category_id}")],
            [InlineKeyboardButton(text=t(language, "my_cart"), callback_data="cart:view")],
        ]
    )


def cart_keyboard(items: list[dict], language: str = "en") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in items:
        item_id = item["menu_item_id"]
        name = item.get("display_name") or item["name_en"]
        builder.row(
            InlineKeyboardButton(text="➖ Decrease", callback_data=f"cart:dec:{item_id}"),
            InlineKeyboardButton(text="➕ Increase", callback_data=f"cart:inc:{item_id}"),
        )
        builder.row(InlineKeyboardButton(text=f"🗑 {t(language, 'remove', item=name)}", callback_data=f"cart:remove:{item_id}"))
    if items:
        builder.row(
            InlineKeyboardButton(text=t(language, "checkout"), callback_data="checkout:start"),
            InlineKeyboardButton(text=t(language, "clear_cart"), callback_data="cart:clear"),
        )
    builder.row(InlineKeyboardButton(text="⬅️ " + t(language, "view_menu"), callback_data="menu:categories"))
    return builder.as_markup()


def fulfillment_keyboard(language: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t(language, "pickup"), callback_data="checkout:pickup"),
                InlineKeyboardButton(text=t(language, "delivery"), callback_data="checkout:delivery"),
            ],
            [InlineKeyboardButton(text=t(language, "cancel"), callback_data="checkout:cancel")],
        ]
    )


def skip_notes_keyboard(language: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t(language, "skip_notes"), callback_data="checkout:skip_notes")]]
    )


def payment_method_keyboard(language: str = "en", khqr_enabled: bool = False) -> InlineKeyboardMarkup:
    rows = []
    if khqr_enabled:
        rows.append([InlineKeyboardButton(text=t(language, "pay_khqr"), callback_data="payment:khqr")])
    rows.append([InlineKeyboardButton(text=t(language, "pay_cash"), callback_data="payment:cash")])
    rows.append([InlineKeyboardButton(text=t(language, "cancel"), callback_data="checkout:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def payment_retry_keyboard(order_id: int, language: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(language, "upload_again"), callback_data=f"payment:retry:{order_id}")],
            [InlineKeyboardButton(text=t(language, "switch_to_cash"), callback_data=f"payment:cash_order:{order_id}")],
        ]
    )


def share_location_keyboard(language: str = "en") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t(language, "share_location"), request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder=t(language, "share_location_placeholder"),
    )


def share_phone_keyboard(language: str = "en") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t(language, "share_phone"), request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder=t(language, "share_phone_placeholder"),
    )


def saved_delivery_keyboard(language: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(language, "use_saved_delivery"), callback_data="checkout:delivery:saved")],
            [InlineKeyboardButton(text=t(language, "change_delivery_details"), callback_data="checkout:delivery:new")],
            [InlineKeyboardButton(text=t(language, "cancel"), callback_data="checkout:cancel")],
        ]
    )


def staff_status_keyboard(order_id: int, show_payment_buttons: bool = True) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Accept", callback_data=f"staff:status:{order_id}:accepted"),
        InlineKeyboardButton(text="👨‍🍳 Preparing", callback_data=f"staff:status:{order_id}:preparing"),
    )
    builder.row(
        InlineKeyboardButton(text="🎒 Ready", callback_data=f"staff:status:{order_id}:ready"),
        InlineKeyboardButton(text="🛵 Delivered", callback_data=f"staff:status:{order_id}:delivered"),
    )
    if show_payment_buttons:
        builder.row(
            InlineKeyboardButton(text="💳 Confirm Payment", callback_data=f"staff:payment:{order_id}:paid"),
            InlineKeyboardButton(text="❌ Reject Payment", callback_data=f"staff:payment:{order_id}:rejected"),
        )
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data=f"staff:status:{order_id}:cancelled"))
    return builder.as_markup()


def admin_dashboard_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🍽 Menu", callback_data="admin:menu"),
                InlineKeyboardButton(text="🗂 Categories", callback_data="admin:categories"),
            ],
            [
                InlineKeyboardButton(text="📸 Photos", callback_data="admin:photo"),
                InlineKeyboardButton(text="🔥 Sold Out", callback_data="admin:toggle"),
            ],
            [
                InlineKeyboardButton(text="🎁 Rewards", callback_data="admin:loyalty"),
                InlineKeyboardButton(text="💳 KHQR", callback_data="admin:khqr"),
            ],
            [
                InlineKeyboardButton(text="📋 Orders", callback_data="admin:orders_today"),
                InlineKeyboardButton(text="💰 Sales", callback_data="admin:sales_today"),
            ],
            [
                InlineKeyboardButton(text="📊 Reports", callback_data="admin:reports"),
                InlineKeyboardButton(text="📣 Promotions", callback_data="admin:promotions"),
            ],
            [InlineKeyboardButton(text="⚙️ Settings", callback_data="admin:settings")],
        ]
    )


def admin_menu_management_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Add menu item", callback_data="admin:add")],
            [InlineKeyboardButton(text="✏ Edit menu item", callback_data="admin:edit")],
            [InlineKeyboardButton(text="⬅ Back", callback_data="admin:dashboard")],
        ]
    )


def admin_settings_keyboard(restaurant: dict) -> InlineKeyboardMarkup:
    delivery = "On" if restaurant["delivery_enabled"] else "Off"
    pickup = "On" if restaurant["pickup_enabled"] else "Off"
    loyalty = "On" if restaurant["loyalty_enabled"] else "Off"
    repeat = "On" if restaurant["repeat_orders_enabled"] else "Off"
    khqr_payment = "On" if restaurant.get("khqr_payment_enabled") else "Off"
    loyalty_rate = cents_to_usd(int(restaurant.get("loyalty_cents_per_point") or 100), restaurant.get("currency_symbol") or "$")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Name", callback_data="admin:set:name")],
            [InlineKeyboardButton(text="Logo", callback_data="admin:set:logo_file_id")],
            [InlineKeyboardButton(text="Phone", callback_data="admin:set:phone")],
            [InlineKeyboardButton(text="Address", callback_data="admin:set:address")],
            [InlineKeyboardButton(text="Currency", callback_data="admin:set:currency_symbol")],
            [InlineKeyboardButton(text="Staff group", callback_data="admin:set:staff_group_id")],
            [InlineKeyboardButton(text=f"Delivery: {delivery}", callback_data="admin:toggle_setting:delivery_enabled")],
            [InlineKeyboardButton(text=f"Pickup: {pickup}", callback_data="admin:toggle_setting:pickup_enabled")],
            [InlineKeyboardButton(text=f"Loyalty: {loyalty}", callback_data="admin:toggle_setting:loyalty_enabled")],
            [InlineKeyboardButton(text=f"Loyalty rate: {loyalty_rate} = 1 point", callback_data="admin:set:loyalty_cents_per_point")],
            [InlineKeyboardButton(text=f"Repeat orders: {repeat}", callback_data="admin:toggle_setting:repeat_orders_enabled")],
            [InlineKeyboardButton(text="⬅ Back", callback_data="admin:dashboard")],
        ]
    )


def admin_loyalty_keyboard(restaurant: dict) -> InlineKeyboardMarkup:
    enabled = "On" if restaurant.get("loyalty_enabled") else "Off"
    rate = cents_to_usd(int(restaurant.get("loyalty_cents_per_point") or 100), restaurant.get("currency_symbol") or "$")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Enable/disable loyalty: {enabled}", callback_data="admin:toggle_setting:loyalty_enabled")],
            [InlineKeyboardButton(text=f"Edit earning rate: {rate} = 1 point", callback_data="admin:set:loyalty_cents_per_point")],
            [InlineKeyboardButton(text="➕ Add Reward", callback_data="admin:reward:add")],
            [InlineKeyboardButton(text="✏️ Edit Reward", callback_data="admin:reward:edit")],
            [InlineKeyboardButton(text="❌ Disable Reward", callback_data="admin:reward:disable")],
            [InlineKeyboardButton(text="📋 View Redemptions", callback_data="admin:reward:redemptions")],
            [InlineKeyboardButton(text="Back", callback_data="admin:dashboard")],
        ]
    )


def admin_rewards_keyboard(rewards: list[dict], prefix: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for reward in rewards:
        state = "On" if reward["is_active"] else "Off"
        builder.button(text=f"{reward['name_en']} ({reward['points_required']} pts, {state})", callback_data=f"{prefix}:{reward['id']}")
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="Cancel", callback_data="admin:cancel"))
    return builder.as_markup()


def admin_reward_fields_keyboard(reward_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="English name", callback_data=f"admin:rewardfield:{reward_id}:name_en")],
            [InlineKeyboardButton(text="Khmer name", callback_data=f"admin:rewardfield:{reward_id}:name_kh")],
            [InlineKeyboardButton(text="Chinese name", callback_data=f"admin:rewardfield:{reward_id}:name_zh")],
            [InlineKeyboardButton(text="English description", callback_data=f"admin:rewardfield:{reward_id}:description_en")],
            [InlineKeyboardButton(text="Khmer description", callback_data=f"admin:rewardfield:{reward_id}:description_kh")],
            [InlineKeyboardButton(text="Chinese description", callback_data=f"admin:rewardfield:{reward_id}:description_zh")],
            [InlineKeyboardButton(text="Points required", callback_data=f"admin:rewardfield:{reward_id}:points_required")],
            [InlineKeyboardButton(text="Expiry days", callback_data=f"admin:rewardfield:{reward_id}:expires_days")],
            [InlineKeyboardButton(text="Quantity limit", callback_data=f"admin:rewardfield:{reward_id}:quantity_limit")],
            [InlineKeyboardButton(text="Active on/off", callback_data=f"admin:rewardfield:{reward_id}:is_active")],
            [InlineKeyboardButton(text="Back", callback_data="admin:loyalty")],
        ]
    )


def admin_reports_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 Daily Report", callback_data="admin:report:today")],
            [InlineKeyboardButton(text="📆 Weekly Report", callback_data="admin:report:week")],
            [InlineKeyboardButton(text="🗓 Monthly Report", callback_data="admin:report:month")],
            [InlineKeyboardButton(text="📐 Custom Dates", callback_data="admin:report:custom")],
            [InlineKeyboardButton(text="📥 Export Orders", callback_data="admin:report:orders")],
            [InlineKeyboardButton(text="📈 Sales Analytics", callback_data="admin:report:sales")],
            [InlineKeyboardButton(text="👥 Customer Insights", callback_data="admin:report:customers")],
            [InlineKeyboardButton(text="🎁 Loyalty Report", callback_data="admin:report:loyalty")],
            [InlineKeyboardButton(text="⬅ Back", callback_data="admin:dashboard")],
        ]
    )


def admin_khqr_keyboard(restaurant: dict) -> InlineKeyboardMarkup:
    enabled = "On" if restaurant.get("khqr_payment_enabled") else "Off"
    has_image = "Uploaded" if restaurant.get("khqr_image_file_id") else "Missing"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Enable/disable KHQR: {enabled}", callback_data="admin:khqr:toggle")],
            [InlineKeyboardButton(text="Upload/change KHQR image", callback_data="admin:set:khqr_image_file_id")],
            [InlineKeyboardButton(text=f"Current KHQR status: {enabled}, image {has_image}", callback_data="admin:khqr:status")],
            [InlineKeyboardButton(text="Back", callback_data="admin:dashboard")],
        ]
    )


def admin_promotions_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📨 Send Promotion", callback_data="admin:promo:send")],
            [InlineKeyboardButton(text="👥 Audience", callback_data="admin:promo:audience")],
            [InlineKeyboardButton(text="📊 Promotion History", callback_data="admin:promo:history")],
            [InlineKeyboardButton(text="⚙️ Settings", callback_data="admin:promo:settings")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="admin:dashboard")],
        ]
    )


def promotion_audience_keyboard(filters_enabled: bool = True) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="👥 All Customers", callback_data="admin:promoaud:all")]]
    if filters_enabled:
        rows.extend(
            [
                [InlineKeyboardButton(text="💤 Inactive 7 Days", callback_data="admin:promoaud:inactive_7")],
                [InlineKeyboardButton(text="💤 Inactive 30 Days", callback_data="admin:promoaud:inactive_30")],
                [InlineKeyboardButton(text="⭐ Loyalty Members", callback_data="admin:promoaud:loyalty")],
                [InlineKeyboardButton(text="💰 Top Customers", callback_data="admin:promoaud:top")],
                [InlineKeyboardButton(text="🆕 First-Time Customers", callback_data="admin:promoaud:first_time")],
            ]
        )
    rows.append([InlineKeyboardButton(text="❌ Cancel", callback_data="admin:promotions")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def promotion_preview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Send", callback_data="admin:promoconfirm:send"),
                InlineKeyboardButton(text="✏️ Edit", callback_data="admin:promoconfirm:edit"),
            ],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="admin:promoconfirm:cancel")],
        ]
    )


def promotion_message_keyboard(miniapp_url: str | None = None, language: str = "en") -> InlineKeyboardMarkup:
    text = t(language, "view_menu")
    if miniapp_url:
        return InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=text, web_app=WebAppInfo(url=miniapp_url))]]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, callback_data="menu:categories")]]
    )


def promotion_settings_keyboard(restaurant: dict) -> InlineKeyboardMarkup:
    enabled = "On" if restaurant.get("promotions_enabled") else "Off"
    filters = "On" if restaurant.get("promotion_audience_filters_enabled") else "Off"
    max_per_day = int(restaurant.get("promotion_max_per_day") or 0)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Enable promotions: {enabled}", callback_data="admin:promo:toggle_enabled")],
            [InlineKeyboardButton(text=f"Max campaigns/day: {max_per_day}", callback_data="admin:promo:set_max")],
            [InlineKeyboardButton(text=f"Audience filters: {filters}", callback_data="admin:promo:toggle_filters")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="admin:promotions")],
        ]
    )


def admin_categories_keyboard(categories: list[dict], prefix: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in categories:
        builder.button(text=category.get("display_name") or category["name_en"], callback_data=f"{prefix}:{category['id']}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="Cancel", callback_data="admin:cancel"))
    return builder.as_markup()


def admin_items_keyboard(items: list[dict], prefix: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in items:
        state = "Available" if item["is_active"] else "Sold Out"
        builder.button(text=f"{item['name_en']} ({state})", callback_data=f"{prefix}:{item['id']}")
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="Cancel", callback_data="admin:cancel"))
    return builder.as_markup()


def admin_edit_fields_keyboard(item_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Change name", callback_data=f"admin:field:{item_id}:name_en")],
            [InlineKeyboardButton(text="Change Khmer name", callback_data=f"admin:field:{item_id}:name_km")],
            [InlineKeyboardButton(text="Change Chinese name", callback_data=f"admin:field:{item_id}:name_zh")],
            [InlineKeyboardButton(text="Change description", callback_data=f"admin:field:{item_id}:description_en")],
            [InlineKeyboardButton(text="Change Khmer description", callback_data=f"admin:field:{item_id}:description_km")],
            [InlineKeyboardButton(text="Change Chinese description", callback_data=f"admin:field:{item_id}:description_zh")],
            [InlineKeyboardButton(text="Change price", callback_data=f"admin:field:{item_id}:price_cents")],
            [InlineKeyboardButton(text="Change category", callback_data=f"admin:field:{item_id}:category_id")],
            [InlineKeyboardButton(text="Change photo", callback_data=f"admin:photoitem:{item_id}")],
            [InlineKeyboardButton(text="Enable/disable", callback_data=f"admin:toggleitem:{item_id}")],
            [InlineKeyboardButton(text="Back", callback_data="admin:edit")],
        ]
    )


def admin_category_management_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Add category", callback_data="admin:cat:add")],
            [InlineKeyboardButton(text="✏️ Edit category", callback_data="admin:cat:edit")],
            [InlineKeyboardButton(text="✅ Enable/disable category", callback_data="admin:cat:toggle")],
            [InlineKeyboardButton(text="🔢 Reorder categories", callback_data="admin:cat:reorder")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="admin:cancel")],
        ]
    )


def admin_category_fields_keyboard(category_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="English name", callback_data=f"admin:catfield:{category_id}:en")],
            [InlineKeyboardButton(text="Khmer name", callback_data=f"admin:catfield:{category_id}:kh")],
            [InlineKeyboardButton(text="Chinese name", callback_data=f"admin:catfield:{category_id}:zh")],
            [InlineKeyboardButton(text="Sort order", callback_data=f"admin:catfield:{category_id}:sort_order")],
            [InlineKeyboardButton(text="Back", callback_data="admin:categories")],
        ]
    )


def skip_photo_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Skip photo", callback_data="admin:skip_item_photo")]]
    )


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status.title())
