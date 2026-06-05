from __future__ import annotations

import re

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove, User

from restaurant_bot import keyboards
from restaurant_bot.config import load_settings
from restaurant_bot.database import get_connection
from restaurant_bot.i18n import TRANSLATIONS, h, normalize_lang, status_label, t
from restaurant_bot.services import cart_service, loyalty_service, menu_service, order_service, restaurant_service, reward_service


router = Router(name="customer")


class Checkout(StatesGroup):
    waiting_for_delivery_location = State()
    waiting_for_phone = State()
    waiting_for_notes = State()
    waiting_for_payment_screenshot = State()


def upsert_user(event: Message | CallbackQuery, language: str | None = None) -> None:
    user = event.from_user
    if not user:
        return
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (telegram_id, full_name, username, language)
            VALUES (?, ?, ?, COALESCE(?, 'en'))
            ON CONFLICT(telegram_id)
            DO UPDATE SET full_name = excluded.full_name,
                username = excluded.username,
                language = COALESCE(excluded.language, users.language)
            """,
            (user.id, user.full_name, user.username, language),
        )


def get_user_language(user_id: int) -> str:
    with get_connection() as conn:
        row = conn.execute("SELECT language FROM users WHERE telegram_id = ?", (user_id,)).fetchone()
    return normalize_lang(row["language"] if row else "en")


def language_for(event: Message | CallbackQuery) -> str:
    return get_user_language(event.from_user.id)


def current_restaurant_for_user(user_id: int) -> dict | None:
    return restaurant_service.resolve_user_restaurant(user_id)


def main_menu_text(restaurant: dict, language: str) -> str:
    return t(language, "main_menu", restaurant_name=h(restaurant["name"]))


def customer_main_menu_markup(language: str):
    settings = load_settings()
    if settings.miniapp_url:
        return keyboards.miniapp_open_keyboard(settings.miniapp_url, language)
    return keyboards.main_menu_keyboard(language)


def button_key(text: str) -> str | None:
    for language in TRANSLATIONS:
        for key in ("view_menu", "my_cart", "order_status", "reorder_last_order", "rewards", "contact", "change_language"):
            if text == t(language, key):
                return key
    return None


def item_name(item: dict, language: str) -> str:
    if item.get("display_name"):
        return str(item["display_name"])
    if language == "kh" and item.get("name_km"):
        return str(item["name_km"])
    if language == "zh" and item.get("name_zh"):
        return str(item["name_zh"])
    return str(item["name_en"])


def money(cents: int, restaurant: dict | None) -> str:
    currency = (restaurant or {}).get("currency_symbol") or "$"
    return menu_service.cents_to_usd(cents, currency)


def latest_order_contact(user_id: int, restaurant_id: int) -> dict:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT phone, address, latitude, longitude
            FROM orders
            WHERE user_id = ? AND restaurant_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (user_id, restaurant_id),
        ).fetchone()
    return dict(row) if row else {}


def has_delivery_details(details: dict) -> bool:
    return bool(details.get("address") or (details.get("latitude") is not None and details.get("longitude") is not None))


def saved_delivery_text(details: dict, language: str) -> str:
    phone = details.get("phone") or t(language, "not_saved")
    if details.get("address"):
        address = details["address"]
    elif details.get("latitude") is not None and details.get("longitude") is not None:
        address = t(language, "location_shared")
    else:
        address = t(language, "not_saved")
    return (
        f"<b>{h(t(language, 'saved_delivery_title'))}</b>\n\n"
        f"{h(t(language, 'saved_delivery_intro'))}\n\n"
        f"📍 <b>{h(t(language, 'address_label'))}:</b> {h(address)}\n"
        f"📞 <b>{h(t(language, 'phone_label'))}:</b> {h(phone)}"
    )


async def ask_order_notes(message: Message | None, state: FSMContext, language: str) -> None:
    if not message:
        return
    await state.set_state(Checkout.waiting_for_notes)
    await message.answer(t(language, "notes_question"), reply_markup=ReplyKeyboardRemove())
    await message.answer(t(language, "notes_optional"), reply_markup=keyboards.skip_notes_keyboard(language))


def format_cart(cart: dict, language: str, restaurant: dict) -> str:
    if not cart["items"]:
        return t(language, "cart_empty")
    lines = [f"🛒 <b>{h(t(language, 'cart_title'))}</b>", ""]
    for index, item in enumerate(cart["items"], start=1):
        icon = keyboards.category_icon(item.get("category_name") or item.get("name_en") or "")
        lines.extend(
            [
                f"{index}. {icon} <b>{h(item_name(item, language))}</b>",
                f"   Qty: {item['quantity']} × {money(item['price_cents'], restaurant)} = <b>{money(item['line_total_cents'], restaurant)}</b>",
                "",
            ]
        )
    lines.extend(["━━━━━━━━━━━━━━", f"💰 <b>{h(t(language, 'total_label'))}:</b> {money(cart['subtotal_cents'], restaurant)}"])
    return "\n".join(lines)


def build_reorder_cart(user_id: int, language: str, restaurant: dict) -> tuple[str, object]:
    if not restaurant.get("repeat_orders_enabled"):
        return t(language, "reorder_unavailable"), keyboards.main_menu_keyboard(language)

    order = order_service.get_latest_reorderable_order_for_user(user_id, restaurant_id=restaurant["id"])
    if not order:
        return t(language, "reorder_no_orders"), keyboards.main_menu_keyboard(language)

    available_items: list[tuple[int, int]] = []
    skipped_names: list[str] = []
    for order_item in order["items"]:
        menu_item_id = order_item.get("menu_item_id")
        fallback_name = str(order_item.get("item_name") or "Item")
        if not menu_item_id:
            skipped_names.append(fallback_name)
            continue
        item = menu_service.get_item(
            int(menu_item_id),
            active_only=False,
            language=language,
            restaurant_id=restaurant["id"],
        )
        if not item or not item["is_active"] or not item.get("category_active"):
            skipped_names.append(fallback_name)
            continue
        available_items.append((int(menu_item_id), int(order_item["quantity"])))

    if not available_items:
        return t(language, "reorder_all_unavailable"), keyboards.main_menu_keyboard(language)

    cart_service.clear_cart(user_id, restaurant["id"])
    for menu_item_id, quantity in available_items:
        try:
            cart_service.add_item(user_id, menu_item_id, quantity=quantity, restaurant_id=restaurant["id"])
        except ValueError:
            item = next((old_item for old_item in order["items"] if old_item.get("menu_item_id") == menu_item_id), None)
            skipped_names.append(str((item or {}).get("item_name") or "Item"))

    cart = cart_service.get_cart(user_id, language=language, restaurant_id=restaurant["id"])
    if not cart["items"]:
        return t(language, "reorder_all_unavailable"), keyboards.main_menu_keyboard(language)

    lines = [h(t(language, "reorder_added"))]
    if skipped_names:
        unique_skipped = list(dict.fromkeys(skipped_names))
        lines.append("")
        lines.append(h(t(language, "reorder_skipped", items=", ".join(unique_skipped))))
    lines.extend(["", format_cart(cart, language, restaurant)])
    return "\n".join(lines), keyboards.cart_keyboard(cart["items"], language)


def format_order_summary(
    order: dict,
    language: str,
    restaurant: dict | None = None,
    include_customer: bool = False,
) -> str:
    fulfillment = t(language, order["fulfillment_type"])
    address = order.get("address")
    if order.get("latitude") is not None and order.get("longitude") is not None:
        address = t(language, "location_shared")
    notes = order.get("notes") or t(language, "no_notes")
    lines = [
        f"🧾 <b>{h(t(language, 'order_label'))}:</b> {h(order['order_code'])}",
        f"📌 <b>{h(t(language, 'status_label'))}:</b> {h(status_label(order['status'], language))}",
        f"💳 <b>{h(t(language, 'payment_method_label'))}:</b> {h(order.get('payment_method') or 'cash')} / {h(order.get('payment_status') or 'unpaid')}",
        "",
    ]
    if include_customer:
        phone = order.get("phone") or t(language, "phone_not_required")
        lines.extend(
            [
                f"👤 <b>{h(t(language, 'customer_label'))}:</b> {h(order.get('customer_name') or 'Customer')}",
                f"📞 <b>{h(t(language, 'phone_label'))}:</b> {h(phone)}",
                f"🚚 <b>{h(t(language, 'type_label'))}:</b> {h(fulfillment.title())}",
            ]
        )
    if address:
        lines.append(f"📍 <b>{h(t(language, 'address_label'))}:</b> {h(address)}")
    lines.extend(["🍽 <b>{}</b>:".format(h(t(language, "items_label")))])
    for item in order["items"]:
        lines.append(f"• {item['quantity']} × {h(item['item_name'])} — {money(item['line_total_cents'], restaurant)}")
    lines.extend(
        [
            "",
            f"📝 <b>{h(t(language, 'notes_label'))}:</b> {h(notes)}",
            f"💰 <b>{h(t(language, 'total_label'))}:</b> {money(order['subtotal_cents'], restaurant)}",
        ]
    )
    if restaurant:
        lines.extend(["", f"Thank you for ordering from <b>{h(restaurant['name'])}</b>!"])
    return "\n".join(lines)


def format_staff_order(order: dict, restaurant: dict) -> str:
    customer = order.get("customer_name") or "Customer"
    phone = order.get("phone") or "Not required for pickup"
    lines = [
        "🚨 <b>New Order</b>",
        f"🧾 <b>{h(order['order_code'])}</b>",
        "",
        f"👤 <b>Customer:</b> {h(customer)}",
        f"📞 <b>Phone:</b> {h(phone)}",
        f"🚚 <b>Type:</b> {h(order['fulfillment_type'].title())}",
    ]
    if order.get("address"):
        lines.append(f"📍 <b>Address:</b> {h(order['address'])}")
    if order.get("latitude") is not None and order.get("longitude") is not None:
        lines.append(f"📍 <b>Location:</b> https://maps.google.com/?q={h(order['latitude'])},{h(order['longitude'])}")
    lines.extend(["", "🍽 <b>Items:</b>"])
    for item in order["items"]:
        lines.append(f"• {item['quantity']} × {h(item['item_name'])} — {money(item['line_total_cents'], restaurant)}")
    lines.extend(["", f"📝 <b>Notes:</b> {h(order.get('notes') or 'No notes')}"])
    payment_text = f"{h((order.get('payment_method') or 'cash').upper())} - {h(order.get('payment_status') or 'unpaid')}"
    lines.append(f"💳 <b>Payment:</b> {payment_text}")
    if order.get("payment_status") == "pending":
        lines.append("⚠️ <b>Payment pending verification.</b>")
    lines.append(f"💰 <b>Total:</b> {money(order['subtotal_cents'], restaurant)}")
    lines.append(f"📌 <b>Status:</b> {h(keyboards.status_label(order['status']))}")
    return "\n".join(lines)


def format_order_update(order: dict, language: str) -> str:
    friendly = t(language, f"status_message_{order['status']}")
    return (
        f"📦 <b>{h(t(language, 'order_update_title'))}</b>\n\n"
        f"🧾 <b>{h(t(language, 'order_label'))}:</b> {h(order['order_code'])}\n"
        f"📌 <b>{h(t(language, 'status_label'))}:</b> {h(status_label(order['status'], language))}\n\n"
        f"{h(friendly)}"
    )


async def safe_edit_or_answer(message: Message, text: str, reply_markup=None) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        await message.answer(text, reply_markup=reply_markup)


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    upsert_user(message)
    restaurant = restaurant_service.get_deployment_restaurant()
    if restaurant:
        restaurant_service.set_user_preferred_restaurant(message.from_user.id, restaurant["id"])
    await message.answer(t("en", "choose_language"), reply_markup=keyboards.language_keyboard())


@router.callback_query(F.data.startswith("lang:"))
async def choose_language(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    language = callback.data.split(":", 1)[1]
    upsert_user(callback, language)
    restaurant = current_restaurant_for_user(callback.from_user.id)
    await callback.answer(t(language, "language_saved"))
    if not restaurant:
        if callback.message:
            await callback.message.answer("No active restaurants are configured.")
        return
    if callback.message:
        await safe_edit_or_answer(callback.message, main_menu_text(restaurant, language), customer_main_menu_markup(language))
        await callback.message.answer(t(language, "language_saved"), reply_markup=keyboards.customer_reply_keyboard(language))


@router.message(Command("language"))
async def language_command(message: Message, state: FSMContext) -> None:
    await state.clear()
    upsert_user(message)
    await message.answer(t(language_for(message), "choose_language"), reply_markup=keyboards.language_keyboard())


@router.callback_query(F.data == "language:change")
async def language_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message:
        await callback.message.answer(t(language_for(callback), "choose_language"), reply_markup=keyboards.language_keyboard())


@router.callback_query(F.data == "main")
async def show_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    language = language_for(callback)
    restaurant = current_restaurant_for_user(callback.from_user.id)
    await callback.answer()
    if callback.message and restaurant:
        await safe_edit_or_answer(callback.message, main_menu_text(restaurant, language), customer_main_menu_markup(language))


@router.message(Command("menu"))
async def menu_command(message: Message) -> None:
    language = language_for(message)
    restaurant = current_restaurant_for_user(message.from_user.id)
    if not restaurant:
        await message.answer("This bot is not configured for a restaurant yet.")
        return
    categories = menu_service.list_categories(language=language, restaurant_id=restaurant["id"])
    await message.answer(t(language, "category_menu"), reply_markup=keyboards.categories_keyboard(categories, language))


@router.message(Command("cart"))
async def cart_command(message: Message) -> None:
    language = language_for(message)
    restaurant = current_restaurant_for_user(message.from_user.id)
    if not restaurant:
        await message.answer("This bot is not configured for a restaurant yet.")
        return
    cart = cart_service.get_cart(message.from_user.id, language=language, restaurant_id=restaurant["id"])
    await message.answer(format_cart(cart, language, restaurant), reply_markup=keyboards.cart_keyboard(cart["items"], language))


@router.message(Command("orders"))
async def orders_command(message: Message) -> None:
    language = language_for(message)
    restaurant = current_restaurant_for_user(message.from_user.id)
    if not restaurant:
        await message.answer("This bot is not configured for a restaurant yet.")
        return
    order = order_service.get_latest_order_for_user(message.from_user.id, restaurant_id=restaurant["id"])
    if not order:
        await message.answer(t(language, "no_orders"), reply_markup=keyboards.customer_reply_keyboard(language))
        return
    await message.answer(format_order_summary(order, language, restaurant), reply_markup=keyboards.customer_reply_keyboard(language))


@router.message(Command("reorder"))
async def reorder_command(message: Message) -> None:
    language = language_for(message)
    restaurant = current_restaurant_for_user(message.from_user.id)
    if not restaurant:
        await message.answer("This bot is not configured for a restaurant yet.")
        return
    text, reply_markup = build_reorder_cart(message.from_user.id, language, restaurant)
    await message.answer(text, reply_markup=reply_markup)


@router.message(Command("contact"))
async def contact_command(message: Message) -> None:
    language = language_for(message)
    restaurant = current_restaurant_for_user(message.from_user.id)
    if not restaurant:
        await message.answer("This bot is not configured for a restaurant yet.")
        return
    await message.answer(
        t(
            language,
            "contact_restaurant",
            restaurant_name=h(restaurant["name"]),
            phone=h(restaurant.get("phone") or ""),
            address=h(restaurant.get("address") or ""),
        ),
        reply_markup=keyboards.customer_reply_keyboard(language),
    )


async def rewards_text(user_id: int, language: str, restaurant: dict) -> str:
    if not restaurant.get("loyalty_enabled"):
        return "🎁 <b>{}</b>\n\n{}".format(h(t(language, "rewards")), h(t(language, "rewards_unavailable")))
    points = loyalty_service.get_points(user_id, restaurant["id"])
    rewards = reward_service.list_rewards(restaurant["id"], active_only=True)
    lines = [
        f"🎁 <b>{h(t(language, 'your_rewards_title'))}</b>",
        "",
        f"⭐ <b>{h(t(language, 'your_points'))}:</b> {points}",
        "",
        f"<b>{h(t(language, 'available_rewards'))}:</b>",
    ]
    if not rewards:
        lines.append(h(t(language, "no_rewards")))
    for reward in rewards:
        name, _description = reward_service.display_reward(reward, language)
        prefix = "🔒 " if points < int(reward["points_required"]) else ""
        lines.append(f"{prefix}🎁 {h(name)} — {reward['points_required']} pts")
    return "\n".join(lines)


def rewards_reply_markup(user_id: int, language: str, restaurant: dict):
    rewards = reward_service.list_rewards(restaurant["id"], active_only=True)
    points = loyalty_service.get_points(user_id, restaurant["id"])
    for reward in rewards:
        name, description = reward_service.display_reward(reward, language)
        reward["display_name"] = name
        reward["display_description"] = description
    return keyboards.rewards_keyboard(rewards, points, language)


@router.message(Command("rewards"))
async def rewards_command(message: Message) -> None:
    language = language_for(message)
    restaurant = current_restaurant_for_user(message.from_user.id)
    if not restaurant:
        await message.answer("This bot is not configured for a restaurant yet.")
        return
    await message.answer(await rewards_text(message.from_user.id, language, restaurant), reply_markup=rewards_reply_markup(message.from_user.id, language, restaurant))


@router.message(StateFilter(None), F.text)
async def customer_text_menu(message: Message, state: FSMContext) -> None:
    key = button_key(message.text or "")
    if key is None:
        return
    if key == "view_menu":
        await menu_command(message)
    elif key == "my_cart":
        await cart_command(message)
    elif key == "order_status":
        await orders_command(message)
    elif key == "reorder_last_order":
        await reorder_command(message)
    elif key == "rewards":
        await rewards_command(message)
    elif key == "contact":
        await contact_command(message)
    elif key == "change_language":
        await language_command(message, state)


@router.callback_query(F.data == "menu:categories")
async def show_categories(callback: CallbackQuery) -> None:
    language = language_for(callback)
    restaurant = current_restaurant_for_user(callback.from_user.id)
    await callback.answer()
    if not callback.message or not restaurant:
        return
    categories = menu_service.list_categories(language=language, restaurant_id=restaurant["id"])
    await safe_edit_or_answer(callback.message, t(language, "category_menu"), keyboards.categories_keyboard(categories, language))


@router.callback_query(F.data.startswith("cat:"))
async def show_category_items(callback: CallbackQuery) -> None:
    category_id = int(callback.data.split(":")[1])
    language = language_for(callback)
    restaurant = current_restaurant_for_user(callback.from_user.id)
    await callback.answer()
    if not callback.message or not restaurant:
        return
    category = menu_service.get_category(category_id, restaurant_id=restaurant["id"])
    items = menu_service.list_items(category_id=category_id, active_only=False, language=language, restaurant_id=restaurant["id"])
    if not category:
        await safe_edit_or_answer(callback.message, t(language, "no_category"), keyboards.main_menu_keyboard(language))
        return
    if not items:
        categories = menu_service.list_categories(language=language, restaurant_id=restaurant["id"])
        await safe_edit_or_answer(
            callback.message,
            t(language, "no_items", category=h(category["name_en"])),
            keyboards.categories_keyboard(categories, language),
        )
        return
    await safe_edit_or_answer(
        callback.message,
        t(language, "category_items", category=h(category["name_en"])),
        keyboards.items_keyboard(items, category_id, language),
    )


@router.callback_query(F.data.startswith("item:"))
async def show_item_detail(callback: CallbackQuery) -> None:
    item_id = int(callback.data.split(":")[1])
    language = language_for(callback)
    restaurant = current_restaurant_for_user(callback.from_user.id)
    await callback.answer()
    if not callback.message or not restaurant:
        return
    item = menu_service.get_item(item_id, active_only=False, language=language, restaurant_id=restaurant["id"])
    if not item:
        await safe_edit_or_answer(callback.message, t(language, "item_unavailable"), keyboards.main_menu_keyboard(language))
        return
    description = item.get("display_description") or item["description_en"]
    price_missing = int(item["price_cents"]) <= 0
    sold_out = not item["is_active"] or not item.get("category_active")
    lines = [
        f"🍽 <b>{h(item_name(item, language))}</b>",
        "",
    ]
    if price_missing:
        lines.append(f"💬 <b>{h(t(language, 'ask_staff_price').replace('💬 ', ''))}</b>")
    else:
        lines.append(f"💰 <b>{h(t(language, 'item_price_label'))}:</b> {money(item['price_cents'], restaurant)}")
    lines.append(f"📝 <b>{h(t(language, 'item_description_label'))}:</b> {h(description)}")
    if sold_out:
        lines.extend(["", f"❌ <b>{h(t(language, 'sold_out_today').replace('❌ ', ''))}</b>"])
    elif restaurant.get("loyalty_enabled") and not price_missing:
        points = loyalty_service.points_for_order({"subtotal_cents": item["price_cents"], "restaurant_id": restaurant["id"]}, restaurant)
        if points:
            lines.extend(["", h(t(language, "loyalty_earn_line", points=points))])
    text = "\n".join(lines)
    reply_markup = keyboards.item_detail_keyboard(
        item_id,
        item["category_id"],
        language,
        available=bool(not sold_out and not price_missing),
    )
    if item.get("image_file_id"):
        await callback.message.answer_photo(item["image_file_id"], caption=text, reply_markup=reply_markup)
        return
    await safe_edit_or_answer(callback.message, text, reply_markup)


@router.callback_query(F.data.startswith("cart:add:"))
async def add_to_cart(callback: CallbackQuery) -> None:
    item_id = int(callback.data.split(":")[2])
    language = language_for(callback)
    restaurant = current_restaurant_for_user(callback.from_user.id)
    if not restaurant:
        await callback.answer("Choose a restaurant first.", show_alert=True)
        return
    item = menu_service.get_item(item_id, active_only=False, language=language, restaurant_id=restaurant["id"])
    if not item:
        await callback.answer(t(language, "not_available"), show_alert=True)
        return
    if not item["is_active"] or int(item["price_cents"]) <= 0 or not item.get("category_active"):
        await callback.answer(t(language, "sold_out"), show_alert=True)
        return
    try:
        cart_service.add_item(callback.from_user.id, item_id, restaurant_id=restaurant["id"])
    except ValueError:
        await callback.answer(t(language, "sold_out"), show_alert=True)
        return
    await callback.answer(t(language, "added_to_cart", item=item_name(item, language)))
    cart = cart_service.get_cart(callback.from_user.id, language=language, restaurant_id=restaurant["id"])
    text = (
        f"✅ <b>{h(item_name(item, language))}</b> {h(t(language, 'added_to_order_short'))}\n\n"
        f"🛒 {h(t(language, 'current_total'))}: <b>{money(cart['subtotal_cents'], restaurant)}</b>\n\n"
        f"{h(t(language, 'after_add_prompt'))}"
    )
    if callback.message:
        await callback.message.answer(
            text,
            reply_markup=keyboards.after_add_to_cart_keyboard(int(item["category_id"]), language),
        )


@router.callback_query(F.data == "cart:view")
async def show_cart(callback: CallbackQuery) -> None:
    language = language_for(callback)
    restaurant = current_restaurant_for_user(callback.from_user.id)
    await callback.answer()
    if not callback.message or not restaurant:
        return
    cart = cart_service.get_cart(callback.from_user.id, language=language, restaurant_id=restaurant["id"])
    await safe_edit_or_answer(callback.message, format_cart(cart, language, restaurant), keyboards.cart_keyboard(cart["items"], language))


@router.callback_query(F.data == "reorder:last")
async def reorder_last_order(callback: CallbackQuery) -> None:
    language = language_for(callback)
    restaurant = current_restaurant_for_user(callback.from_user.id)
    await callback.answer()
    if not callback.message or not restaurant:
        return
    text, reply_markup = build_reorder_cart(callback.from_user.id, language, restaurant)
    await safe_edit_or_answer(callback.message, text, reply_markup)


@router.callback_query(F.data.startswith("cart:inc:"))
async def increase_cart_item(callback: CallbackQuery) -> None:
    restaurant = current_restaurant_for_user(callback.from_user.id)
    if restaurant:
        cart_service.change_quantity(callback.from_user.id, int(callback.data.split(":")[2]), 1, restaurant["id"])
    await show_cart(callback)


@router.callback_query(F.data.startswith("cart:dec:"))
async def decrease_cart_item(callback: CallbackQuery) -> None:
    restaurant = current_restaurant_for_user(callback.from_user.id)
    if restaurant:
        cart_service.change_quantity(callback.from_user.id, int(callback.data.split(":")[2]), -1, restaurant["id"])
    await show_cart(callback)


@router.callback_query(F.data.startswith("cart:remove:"))
async def remove_cart_item(callback: CallbackQuery) -> None:
    restaurant = current_restaurant_for_user(callback.from_user.id)
    if restaurant:
        cart_service.remove_item(callback.from_user.id, int(callback.data.split(":")[2]), restaurant["id"])
    await show_cart(callback)


@router.callback_query(F.data == "cart:clear")
async def clear_cart(callback: CallbackQuery) -> None:
    restaurant = current_restaurant_for_user(callback.from_user.id)
    if restaurant:
        cart_service.clear_cart(callback.from_user.id, restaurant["id"])
    await show_cart(callback)


@router.callback_query(F.data == "checkout:start")
async def start_checkout(callback: CallbackQuery, state: FSMContext) -> None:
    language = language_for(callback)
    restaurant = current_restaurant_for_user(callback.from_user.id)
    if not restaurant:
        await callback.answer("Choose a restaurant first.", show_alert=True)
        return
    cart = cart_service.get_cart(callback.from_user.id, language=language, restaurant_id=restaurant["id"])
    if not cart["items"]:
        await callback.answer(t(language, "empty_cart_alert"), show_alert=True)
        return
    await state.clear()
    await state.update_data(restaurant_id=restaurant["id"])
    await callback.answer()
    if callback.message:
        await safe_edit_or_answer(callback.message, t(language, "fulfillment_question"), keyboards.fulfillment_keyboard(language))


@router.callback_query(F.data == "checkout:cancel")
async def cancel_checkout(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    language = language_for(callback)
    restaurant = current_restaurant_for_user(callback.from_user.id)
    await callback.answer(t(language, "checkout_cancelled"))
    if callback.message and restaurant:
        await safe_edit_or_answer(callback.message, main_menu_text(restaurant, language), customer_main_menu_markup(language))


@router.callback_query(F.data.in_({"checkout:pickup", "checkout:delivery"}))
async def choose_fulfillment(callback: CallbackQuery, state: FSMContext) -> None:
    fulfillment_type = callback.data.split(":")[1]
    language = language_for(callback)
    restaurant = current_restaurant_for_user(callback.from_user.id)
    if not restaurant:
        await callback.answer("Choose a restaurant first.", show_alert=True)
        return
    if fulfillment_type == "delivery" and not restaurant["delivery_enabled"]:
        await callback.answer("Delivery is not available for this restaurant.", show_alert=True)
        return
    if fulfillment_type == "pickup" and not restaurant["pickup_enabled"]:
        await callback.answer("Pickup is not available for this restaurant.", show_alert=True)
        return
    saved_contact = latest_order_contact(callback.from_user.id, restaurant["id"])
    saved_phone = saved_contact.get("phone") or ""
    await state.update_data(fulfillment_type=fulfillment_type, restaurant_id=restaurant["id"], saved_phone=saved_phone)
    await callback.answer()
    if fulfillment_type == "delivery":
        if has_delivery_details(saved_contact):
            await state.update_data(
                saved_address=saved_contact.get("address"),
                saved_latitude=saved_contact.get("latitude"),
                saved_longitude=saved_contact.get("longitude"),
            )
            if callback.message:
                await safe_edit_or_answer(
                    callback.message,
                    saved_delivery_text(saved_contact, language),
                    keyboards.saved_delivery_keyboard(language),
                )
            return
        await state.set_state(Checkout.waiting_for_delivery_location)
        if callback.message:
            await callback.message.answer(t(language, "delivery_location"), reply_markup=keyboards.share_location_keyboard(language))
    else:
        await state.update_data(phone=saved_phone)
        await ask_order_notes(callback.message, state, language)


@router.callback_query(F.data == "checkout:delivery:saved")
async def use_saved_delivery(callback: CallbackQuery, state: FSMContext) -> None:
    language = language_for(callback)
    data = await state.get_data()
    await state.update_data(
        address=data.get("saved_address"),
        latitude=data.get("saved_latitude"),
        longitude=data.get("saved_longitude"),
    )
    saved_phone = data.get("saved_phone") or ""
    await callback.answer()
    if saved_phone:
        await state.update_data(phone=saved_phone)
        await ask_order_notes(callback.message, state, language)
        return
    await state.set_state(Checkout.waiting_for_phone)
    if callback.message:
        await callback.message.answer(t(language, "phone_after_location"), reply_markup=keyboards.share_phone_keyboard(language))


@router.callback_query(F.data == "checkout:delivery:new")
async def change_delivery_details(callback: CallbackQuery, state: FSMContext) -> None:
    language = language_for(callback)
    await callback.answer()
    await state.set_state(Checkout.waiting_for_delivery_location)
    if callback.message:
        await callback.message.answer(t(language, "delivery_location"), reply_markup=keyboards.share_location_keyboard(language))


@router.message(Checkout.waiting_for_delivery_location)
async def receive_delivery_location(message: Message, state: FSMContext) -> None:
    language = language_for(message)
    if message.location:
        await state.update_data(latitude=message.location.latitude, longitude=message.location.longitude, address=None)
    elif message.text and len(message.text.strip()) >= 5:
        await state.update_data(address=message.text.strip(), latitude=None, longitude=None)
    else:
        await message.answer(t(language, "delivery_location_invalid"))
        return
    data = await state.get_data()
    if data.get("saved_phone"):
        await state.update_data(phone=data["saved_phone"])
        await ask_order_notes(message, state, language)
        return
    await state.set_state(Checkout.waiting_for_phone)
    await message.answer(t(language, "phone_after_location"), reply_markup=keyboards.share_phone_keyboard(language))


def normalize_phone(raw: str) -> str | None:
    cleaned = re.sub(r"[^\d+]", "", raw)
    digits = re.sub(r"\D", "", cleaned)
    if 8 <= len(digits) <= 15:
        return cleaned
    return None


@router.message(Checkout.waiting_for_phone)
async def receive_phone(message: Message, state: FSMContext) -> None:
    language = language_for(message)
    raw_phone = message.contact.phone_number if message.contact else message.text or ""
    phone = normalize_phone(raw_phone)
    if not phone:
        await message.answer(t(language, "phone_invalid"))
        return
    await state.update_data(phone=phone)
    await ask_order_notes(message, state, language)


@router.callback_query(F.data == "checkout:skip_notes")
async def skip_notes(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    await ask_payment_method(callback.message, state, notes="", user=callback.from_user)


@router.message(Checkout.waiting_for_notes)
async def receive_notes(message: Message, state: FSMContext, bot: Bot) -> None:
    await ask_payment_method(message, state, notes=(message.text or "").strip(), user=message.from_user)


async def ask_payment_method(message: Message | None, state: FSMContext, notes: str, user: User | None) -> None:
    if not message or not user:
        return
    language = get_user_language(user.id)
    restaurant = current_restaurant_for_user(user.id)
    if not restaurant:
        await message.answer("Restaurant is not available.")
        await state.clear()
        return
    cart = cart_service.get_cart(user.id, language=language, restaurant_id=restaurant["id"])
    if not cart["items"]:
        await message.answer(t(language, "cart_empty"), reply_markup=keyboards.main_menu_keyboard(language))
        await state.clear()
        return
    await state.update_data(notes=notes, restaurant_id=restaurant["id"])
    khqr_enabled = bool(restaurant.get("khqr_payment_enabled"))
    await message.answer(
        f"{t(language, 'payment_question')}\n"
        f"{h(t(language, 'payment_total'))}: <b>{money(cart['subtotal_cents'], restaurant)}</b>",
        reply_markup=keyboards.payment_method_keyboard(language, khqr_enabled=khqr_enabled),
    )


@router.callback_query(F.data == "payment:cash")
async def choose_cash_payment(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    data = await state.get_data()
    await finalize_order(
        callback.message,
        state,
        bot,
        notes=data.get("notes", ""),
        user=callback.from_user,
        payment_method="cash",
        payment_status="unpaid",
    )


@router.callback_query(F.data == "payment:khqr")
async def choose_khqr_payment(callback: CallbackQuery, state: FSMContext) -> None:
    language = language_for(callback)
    restaurant = current_restaurant_for_user(callback.from_user.id)
    if not restaurant or not restaurant.get("khqr_payment_enabled"):
        await callback.answer(t(language, "khqr_unavailable"), show_alert=True)
        return
    if not restaurant.get("khqr_image_file_id"):
        await callback.answer(t(language, "khqr_image_missing"), show_alert=True)
        return
    cart = cart_service.get_cart(callback.from_user.id, language=language, restaurant_id=restaurant["id"])
    await state.update_data(payment_method="khqr", restaurant_id=restaurant["id"])
    await state.set_state(Checkout.waiting_for_payment_screenshot)
    await callback.answer()
    caption = (
        f"<b>{h(t(language, 'khqr_payment_title'))}</b>\n"
        f"{h(t(language, 'payment_total'))}: <b>{money(cart['subtotal_cents'], restaurant)}</b>\n\n"
        f"{h(t(language, 'upload_payment_screenshot'))}"
    )
    if callback.message:
        await callback.message.answer_photo(restaurant["khqr_image_file_id"], caption=caption)


@router.message(Checkout.waiting_for_payment_screenshot, F.photo)
async def receive_payment_screenshot(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    existing_order_id = data.get("retry_order_id")
    file_id = message.photo[-1].file_id
    if existing_order_id:
        order = order_service.update_payment_screenshot(int(existing_order_id), file_id)
        restaurant = restaurant_service.get_restaurant(order["restaurant_id"])
        await state.clear()
        await message.answer(t(get_user_language(message.from_user.id), "payment_pending"), reply_markup=keyboards.customer_reply_keyboard(get_user_language(message.from_user.id)))
        if not await notify_staff_about_order(bot, order, restaurant):
            await message.answer(t(get_user_language(message.from_user.id), "staff_not_configured"))
        return
    await finalize_order(
        message,
        state,
        bot,
        notes=data.get("notes", ""),
        user=message.from_user,
        payment_method="khqr",
        payment_status="pending",
        payment_screenshot_file_id=file_id,
    )


@router.message(Checkout.waiting_for_payment_screenshot)
async def receive_payment_screenshot_invalid(message: Message) -> None:
    await message.answer(t(language_for(message), "payment_screenshot_invalid"))


@router.callback_query(F.data.startswith("payment:retry:"))
async def retry_payment_screenshot(callback: CallbackQuery, state: FSMContext) -> None:
    order_id = int(callback.data.split(":")[2])
    order = order_service.get_order(order_id)
    if not order or order["user_id"] != callback.from_user.id:
        await callback.answer("Order not found.", show_alert=True)
        return
    await state.clear()
    await state.update_data(retry_order_id=order_id)
    await state.set_state(Checkout.waiting_for_payment_screenshot)
    await callback.answer()
    if callback.message:
        await callback.message.answer(t(language_for(callback), "upload_payment_screenshot"))


@router.callback_query(F.data.startswith("payment:cash_order:"))
async def switch_rejected_order_to_cash(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    order_id = int(callback.data.split(":")[2])
    order = order_service.get_order(order_id)
    if not order or order["user_id"] != callback.from_user.id:
        await callback.answer("Order not found.", show_alert=True)
        return
    order = order_service.switch_payment_to_cash(order_id)
    restaurant = restaurant_service.get_restaurant(order["restaurant_id"])
    await state.clear()
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            f"{t(language_for(callback), 'order_placed')}\n\n"
            + format_order_summary(order, language_for(callback), restaurant),
            reply_markup=keyboards.customer_reply_keyboard(language_for(callback)),
        )
    if callback.message and not await notify_staff_about_order(bot, order, restaurant):
        await callback.message.answer(t(language_for(callback), "staff_not_configured"))


async def finalize_order(
    message: Message | None,
    state: FSMContext,
    bot: Bot,
    notes: str,
    user: User | None,
    payment_method: str = "cash",
    payment_status: str = "unpaid",
    payment_screenshot_file_id: str | None = None,
) -> None:
    if not message or not user:
        return
    language = get_user_language(user.id)
    data = await state.get_data()
    selected_restaurant = current_restaurant_for_user(user.id)
    restaurant_id = int(data.get("restaurant_id") or (selected_restaurant or {}).get("id") or 0)
    restaurant = restaurant_service.get_restaurant(restaurant_id)
    if not restaurant:
        await message.answer("Restaurant is not available.")
        await state.clear()
        return
    try:
        order = order_service.create_order(
            user_id=user.id,
            customer_name=user.full_name,
            phone=data.get("phone") or "",
            fulfillment_type=data["fulfillment_type"],
            restaurant_id=restaurant_id,
            address=data.get("address"),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            notes=notes,
            language=language,
            payment_method=payment_method,
            payment_status=payment_status,
            payment_screenshot_file_id=payment_screenshot_file_id,
        )
    except ValueError as exc:
        error_text = str(exc)
        if "empty cart" in error_text.lower():
            error_text = t(language, "cart_empty")
        elif "delivery orders require" in error_text.lower():
            error_text = t(language, "delivery_location_invalid")
        await message.answer(h(error_text), reply_markup=keyboards.main_menu_keyboard(language))
        await state.clear()
        return

    await state.clear()
    await message.answer(
        f"{t(language, 'order_placed')}\n\n" + format_order_summary(order, language, restaurant),
        reply_markup=keyboards.customer_reply_keyboard(language),
    )

    if not await notify_staff_about_order(bot, order, restaurant):
        await message.answer(t(language, "staff_not_configured"))


async def notify_staff_about_order(bot: Bot, order: dict, restaurant: dict | None) -> bool:
    if not restaurant:
        return False
    if restaurant.get("staff_group_id"):
        staff_message = await bot.send_message(
            restaurant["staff_group_id"],
            format_staff_order(order, restaurant),
            reply_markup=keyboards.staff_status_keyboard(
                order["id"],
                show_payment_buttons=order.get("payment_method") == "khqr" and order.get("payment_status") == "pending",
            ),
        )
        if order.get("payment_screenshot_file_id"):
            await bot.send_photo(
                restaurant["staff_group_id"],
                order["payment_screenshot_file_id"],
                caption=f"Payment screenshot for order {h(order['order_code'])}",
                reply_to_message_id=staff_message.message_id,
            )
        return True
    else:
        return False


@router.callback_query(F.data == "order:status")
async def order_status(callback: CallbackQuery) -> None:
    language = language_for(callback)
    restaurant = current_restaurant_for_user(callback.from_user.id)
    await callback.answer()
    if not callback.message or not restaurant:
        return
    order = order_service.get_latest_order_for_user(callback.from_user.id, restaurant_id=restaurant["id"])
    if not order:
        await safe_edit_or_answer(callback.message, t(language, "no_orders"), keyboards.main_menu_keyboard(language))
        return
    await safe_edit_or_answer(callback.message, format_order_summary(order, language, restaurant), keyboards.main_menu_keyboard(language))


@router.callback_query(F.data == "rewards:view")
async def rewards_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    language = language_for(callback)
    restaurant = current_restaurant_for_user(callback.from_user.id)
    if not callback.message or not restaurant:
        return
    await safe_edit_or_answer(
        callback.message,
        await rewards_text(callback.from_user.id, language, restaurant),
        rewards_reply_markup(callback.from_user.id, language, restaurant),
    )


@router.callback_query(F.data.startswith("reward:view:"))
async def reward_detail(callback: CallbackQuery) -> None:
    language = language_for(callback)
    restaurant = current_restaurant_for_user(callback.from_user.id)
    if not callback.message or not restaurant:
        await callback.answer()
        return
    reward_id = int(callback.data.split(":")[2])
    reward = reward_service.get_reward(reward_id, restaurant["id"])
    if not reward or not reward["is_active"]:
        await callback.answer(t(language, "no_rewards"), show_alert=True)
        return
    points = loyalty_service.get_points(callback.from_user.id, restaurant["id"])
    if points < int(reward["points_required"]):
        await callback.answer(t(language, "not_enough_points"), show_alert=True)
        return
    name, _description = reward_service.display_reward(reward, language)
    remaining = points - int(reward["points_required"])
    text = (
        f"🎟 <b>{h(t(language, 'redeem_reward_title'))}</b>\n\n"
        f"<b>{h(t(language, 'reward_label'))}:</b> {h(name)}\n"
        f"<b>{h(t(language, 'cost_label'))}:</b> {reward['points_required']} pts\n"
        f"<b>{h(t(language, 'your_points'))}:</b> {points}\n"
        f"<b>{h(t(language, 'remaining_after_redeem'))}:</b> {remaining}"
    )
    await callback.answer()
    await safe_edit_or_answer(callback.message, text, keyboards.reward_confirm_keyboard(reward_id, language))


@router.callback_query(F.data.startswith("reward:redeem:"))
async def redeem_reward(callback: CallbackQuery, bot: Bot) -> None:
    language = language_for(callback)
    restaurant = current_restaurant_for_user(callback.from_user.id)
    if not callback.message or not restaurant:
        await callback.answer()
        return
    reward_id = int(callback.data.split(":")[2])
    try:
        redemption = reward_service.redeem_reward(callback.from_user.id, restaurant["id"], reward_id)
    except ValueError as exc:
        await callback.answer(h(str(exc)), show_alert=True)
        return
    name, _description = reward_service.display_reward(redemption, language)
    valid = f"{redemption['expires_days']} {t(language, 'days')}" if redemption.get("expires_days") else "-"
    text = (
        f"🎉 <b>{h(t(language, 'reward_redeemed_title'))}</b>\n\n"
        f"🎁 <b>{h(t(language, 'reward_label'))}:</b> {h(name)}\n"
        f"🎟 <b>{h(t(language, 'voucher_label'))}:</b> {h(redemption['voucher_code'])}\n"
        f"📅 <b>{h(t(language, 'valid_for'))}:</b> {h(valid)}\n"
        f"📌 <b>{h(t(language, 'status_label'))}:</b> {h(t(language, 'pending_use'))}"
    )
    await callback.answer()
    await safe_edit_or_answer(callback.message, text, keyboards.main_menu_keyboard(language))
    if restaurant.get("staff_group_id"):
        await bot.send_message(
            restaurant["staff_group_id"],
            "🎁 <b>Reward Redemption</b>\n\n"
            f"👤 <b>Customer:</b> {h(callback.from_user.full_name)}\n"
            f"🎁 <b>Reward:</b> {h(name)}\n"
            f"🎟 <b>Voucher:</b> {h(redemption['voucher_code'])}",
            reply_markup=keyboards.staff_reward_keyboard(redemption["id"]),
        )


@router.callback_query(F.data == "reward:mine")
async def my_reward_redemptions(callback: CallbackQuery) -> None:
    language = language_for(callback)
    restaurant = current_restaurant_for_user(callback.from_user.id)
    await callback.answer()
    if not callback.message or not restaurant:
        return
    redemptions = reward_service.list_user_redemptions(callback.from_user.id, restaurant["id"])
    lines = [f"🎟 <b>{h(t(language, 'my_rewards'))}</b>", ""]
    if not redemptions:
        lines.append(h(t(language, "no_vouchers")))
    for redemption in redemptions[:10]:
        name, _description = reward_service.display_reward(redemption, language)
        lines.append(f"• {h(name)} — {h(redemption['voucher_code'])} ({h(redemption['status'])})")
    await safe_edit_or_answer(callback.message, "\n".join(lines), keyboards.main_menu_keyboard(language))


@router.callback_query(F.data == "contact")
async def contact_restaurant(callback: CallbackQuery) -> None:
    await callback.answer()
    language = language_for(callback)
    restaurant = current_restaurant_for_user(callback.from_user.id)
    if not callback.message or not restaurant:
        return
    text = t(
        language,
        "contact_restaurant",
        restaurant_name=h(restaurant["name"]),
        phone=h(restaurant.get("phone") or ""),
        address=h(restaurant.get("address") or ""),
    )
    await safe_edit_or_answer(callback.message, text, keyboards.main_menu_keyboard(language))
