from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, Message

from restaurant_bot.config import load_settings
from restaurant_bot import keyboards
from restaurant_bot.i18n import h
from restaurant_bot.services import demo_service, menu_service, order_service, promotion_service, report_service, restaurant_service, reward_service


router = Router(name="admin")


class AddItem(StatesGroup):
    waiting_for_name = State()
    waiting_for_name_km = State()
    waiting_for_name_zh = State()
    waiting_for_description = State()
    waiting_for_description_km = State()
    waiting_for_description_zh = State()
    waiting_for_price = State()
    waiting_for_photo = State()


class EditItem(StatesGroup):
    waiting_for_value = State()


class ItemPhoto(StatesGroup):
    waiting_for_photo = State()


class AddCategory(StatesGroup):
    waiting_for_name_en = State()
    waiting_for_name_kh = State()
    waiting_for_name_zh = State()
    waiting_for_sort_order = State()


class EditCategory(StatesGroup):
    waiting_for_value = State()


class RestaurantSetting(StatesGroup):
    waiting_for_value = State()
    waiting_for_photo = State()


class AddReward(StatesGroup):
    waiting_for_name_en = State()
    waiting_for_name_kh = State()
    waiting_for_name_zh = State()
    waiting_for_description_en = State()
    waiting_for_description_kh = State()
    waiting_for_description_zh = State()
    waiting_for_points = State()
    waiting_for_expiry = State()
    waiting_for_quantity = State()


class EditReward(StatesGroup):
    waiting_for_value = State()


class ReportCustom(StatesGroup):
    waiting_for_dates = State()


class PromotionFlow(StatesGroup):
    waiting_for_message = State()
    waiting_for_max_per_day = State()


def is_admin(user_id: int) -> bool:
    return bool(restaurant_service.list_admin_restaurants(user_id))


async def reject_if_not_admin(event: Message | CallbackQuery) -> bool:
    if event.from_user and is_admin(event.from_user.id):
        return False
    if isinstance(event, CallbackQuery):
        await event.answer("Admin access only.", show_alert=True)
    else:
        await event.answer("Admin access only.")
    return True


def admin_restaurant(user_id: int) -> dict | None:
    preferred = restaurant_service.get_user_preferred_restaurant(user_id)
    preferred_id = int(preferred["id"]) if preferred else None
    return restaurant_service.get_admin_restaurant(user_id, preferred_id)


def admin_dashboard_text(restaurant: dict) -> str:
    return f"⚙️ <b>Admin Dashboard</b>\n🍽 <b>{h(restaurant['name'])}</b>\n\nChoose what you want to manage:"


async def show_dashboard(target: Message | CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = target.from_user.id
    restaurant = admin_restaurant(user_id)
    if not restaurant:
        if isinstance(target, CallbackQuery):
            await target.answer("Admin access only.", show_alert=True)
        else:
            await target.answer("Admin access only.")
        return
    restaurant_service.set_user_preferred_restaurant(user_id, restaurant["id"])
    text = admin_dashboard_text(restaurant)
    if isinstance(target, CallbackQuery):
        await target.answer()
        if target.message:
            await target.message.edit_text(text, reply_markup=keyboards.admin_dashboard_keyboard())
    else:
        await target.answer(text, reply_markup=keyboards.admin_dashboard_keyboard())


@router.message(Command("admin"))
async def admin_dashboard(message: Message, state: FSMContext) -> None:
    await show_dashboard(message, state)


@router.message(Command("demo_reset"))
async def demo_reset(message: Message, state: FSMContext) -> None:
    if await reject_if_not_admin(message):
        return
    await state.clear()
    restaurant = admin_restaurant(message.from_user.id)
    if not restaurant:
        await message.answer("Admin access only.")
        return
    result = demo_service.reset_demo_data(restaurant["id"])
    await message.answer(
        "<b>Demo mode reset complete</b>\n\n"
        f"<b>Restaurant:</b> {h(restaurant['name'])}\n"
        f"<b>Orders deleted:</b> {result['orders_deleted']}\n"
        f"<b>Carts deleted:</b> {result['carts_deleted']}\n"
        f"<b>Loyalty balances deleted:</b> {result['loyalty_balances_deleted']}\n"
        f"<b>Reward redemptions deleted:</b> {result.get('reward_redemptions_deleted', 0)}\n"
        f"<b>Sample customers ready:</b> {result['sample_customers_created']}\n\n"
        "Menu, settings, photos, KHQR, categories, and admins were not changed.",
        reply_markup=keyboards.admin_dashboard_keyboard(),
    )


@router.callback_query(F.data == "admin:dashboard")
async def admin_dashboard_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await show_dashboard(callback, state)


@router.callback_query(F.data == "admin:cancel")
async def admin_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await show_dashboard(callback, state)


@router.callback_query(F.data == "admin:menu")
async def menu_management(callback: CallbackQuery) -> None:
    if await reject_if_not_admin(callback):
        return
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("Menu management", reply_markup=keyboards.admin_menu_management_keyboard())


@router.callback_query(F.data == "admin:promotions")
async def promotions_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if await reject_if_not_admin(callback):
        return
    await state.clear()
    restaurant = admin_restaurant(callback.from_user.id)
    if not restaurant:
        await callback.answer("Admin access only.", show_alert=True)
        return
    enabled = "Enabled" if restaurant.get("promotions_enabled") else "Disabled"
    filters = "Enabled" if restaurant.get("promotion_audience_filters_enabled") else "Disabled"
    text = (
        "📣 <b>Promotions</b>\n\n"
        f"<b>Status:</b> {enabled}\n"
        f"<b>Audience filters:</b> {filters}\n"
        f"<b>Max campaigns/day:</b> {int(restaurant.get('promotion_max_per_day') or 0)}\n\n"
        "Send marketing campaigns to customers who have ordered from this restaurant."
    )
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(text, reply_markup=keyboards.admin_promotions_keyboard())


@router.callback_query(F.data == "admin:promo:send")
async def promotion_send_start(callback: CallbackQuery, state: FSMContext) -> None:
    if await reject_if_not_admin(callback):
        return
    restaurant = admin_restaurant(callback.from_user.id)
    if not restaurant:
        await callback.answer("Admin access only.", show_alert=True)
        return
    if not restaurant.get("promotions_enabled"):
        await callback.answer("Promotions are disabled in settings.", show_alert=True)
        return
    max_per_day = int(restaurant.get("promotion_max_per_day") or 0)
    sent_today = promotion_service.campaigns_sent_today(int(restaurant["id"]))
    if max_per_day > 0 and sent_today >= max_per_day:
        await callback.answer(f"Daily promotion limit reached ({max_per_day}).", show_alert=True)
        return
    await state.clear()
    await state.update_data(restaurant_id=restaurant["id"])
    await state.set_state(PromotionFlow.waiting_for_message)
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "📨 <b>Send Promotion</b>\n\n"
            "Send the promotion message now.\n\n"
            "You can send text, emojis, formatted text, or a photo with caption."
        )


@router.message(PromotionFlow.waiting_for_message)
async def promotion_receive_message(message: Message, state: FSMContext) -> None:
    if await reject_if_not_admin(message):
        return
    content = message.caption or message.text or ""
    photo_file_id = message.photo[-1].file_id if message.photo else None
    if not content.strip() and not photo_file_id:
        await message.answer("Please send text or a photo with an optional caption.")
        return
    title = next((line.strip() for line in content.splitlines() if line.strip()), "Photo promotion")
    if len(title) > 80:
        title = title[:77] + "..."
    restaurant = admin_restaurant(message.from_user.id)
    await state.update_data(
        restaurant_id=restaurant["id"],
        source_chat_id=message.chat.id,
        source_message_id=message.message_id,
        message_text=content.strip() or "[Photo promotion]",
        title=title,
        photo_file_id=photo_file_id,
    )
    await message.answer(
        "👥 <b>Choose audience</b>",
        reply_markup=keyboards.promotion_audience_keyboard(bool(restaurant.get("promotion_audience_filters_enabled"))),
    )


@router.callback_query(F.data == "admin:promo:audience")
async def promotion_audience_info(callback: CallbackQuery) -> None:
    if await reject_if_not_admin(callback):
        return
    restaurant = admin_restaurant(callback.from_user.id)
    if not restaurant:
        await callback.answer("Admin access only.", show_alert=True)
        return
    lines = ["👥 <b>Promotion Audiences</b>", ""]
    for audience_type, label in promotion_service.AUDIENCE_LABELS.items():
        if audience_type != "all" and not restaurant.get("promotion_audience_filters_enabled"):
            continue
        count = len(promotion_service.list_audience(int(restaurant["id"]), audience_type))
        lines.append(f"<b>{h(label)}:</b> {count} customers")
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("\n".join(lines), reply_markup=keyboards.admin_promotions_keyboard())


@router.callback_query(F.data.startswith("admin:promoaud:"))
async def promotion_choose_audience(callback: CallbackQuery, state: FSMContext) -> None:
    if await reject_if_not_admin(callback):
        return
    audience_type = callback.data.split(":", 2)[2]
    data = await state.get_data()
    restaurant = admin_restaurant(callback.from_user.id)
    if not data.get("source_message_id") or not restaurant:
        await callback.answer("Please create a promotion message first.", show_alert=True)
        return
    if audience_type != "all" and not restaurant.get("promotion_audience_filters_enabled"):
        await callback.answer("Audience filters are disabled.", show_alert=True)
        return
    recipients = promotion_service.list_audience(int(restaurant["id"]), audience_type)
    await state.update_data(audience_type=audience_type, target_count=len(recipients))
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "📣 <b>Promotion Preview</b>\n\n"
            f"<b>Audience:</b> {h(promotion_service.audience_label(audience_type))}\n"
            f"<b>Recipients:</b> {len(recipients)} customers\n\n"
            "<b>Message:</b>"
        )
        await callback.bot.copy_message(
            chat_id=callback.message.chat.id,
            from_chat_id=int(data["source_chat_id"]),
            message_id=int(data["source_message_id"]),
        )
        await callback.message.answer("Send this promotion?", reply_markup=keyboards.promotion_preview_keyboard())


@router.callback_query(F.data == "admin:promoconfirm:edit")
async def promotion_edit(callback: CallbackQuery, state: FSMContext) -> None:
    if await reject_if_not_admin(callback):
        return
    await state.set_state(PromotionFlow.waiting_for_message)
    await callback.answer()
    if callback.message:
        await callback.message.answer("Send the updated promotion message.")


@router.callback_query(F.data == "admin:promoconfirm:cancel")
async def promotion_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    if await reject_if_not_admin(callback):
        return
    await state.clear()
    await callback.answer("Promotion cancelled.")
    if callback.message:
        await callback.message.edit_text("Promotion cancelled.", reply_markup=keyboards.admin_promotions_keyboard())


@router.callback_query(F.data == "admin:promoconfirm:send")
async def promotion_confirm_send(callback: CallbackQuery, state: FSMContext) -> None:
    if await reject_if_not_admin(callback):
        return
    data = await state.get_data()
    restaurant = admin_restaurant(callback.from_user.id)
    if not restaurant or not data.get("source_message_id") or not data.get("audience_type"):
        await callback.answer("Promotion draft expired. Please create it again.", show_alert=True)
        return
    if not restaurant.get("promotions_enabled"):
        await callback.answer("Promotions are disabled.", show_alert=True)
        return
    max_per_day = int(restaurant.get("promotion_max_per_day") or 0)
    sent_today = promotion_service.campaigns_sent_today(int(restaurant["id"]))
    if max_per_day > 0 and sent_today >= max_per_day:
        await callback.answer(f"Daily promotion limit reached ({max_per_day}).", show_alert=True)
        return

    recipients = promotion_service.list_audience(int(restaurant["id"]), str(data["audience_type"]))
    sent = failed = blocked = 0
    await callback.answer("Sending promotion...")
    if callback.message:
        await callback.message.edit_text(f"📣 Sending promotion to {len(recipients)} customers...")
    miniapp_url = load_settings().miniapp_url
    for recipient in recipients:
        try:
            await callback.bot.copy_message(
                chat_id=int(recipient["telegram_id"]),
                from_chat_id=int(data["source_chat_id"]),
                message_id=int(data["source_message_id"]),
                reply_markup=keyboards.promotion_message_keyboard(miniapp_url, recipient.get("language") or "en"),
            )
            sent += 1
            await asyncio.sleep(0.08)
        except TelegramRetryAfter as exc:
            await asyncio.sleep(float(exc.retry_after) + 0.5)
            failed += 1
        except TelegramForbiddenError:
            blocked += 1
        except TelegramBadRequest:
            failed += 1

    promotion_service.create_campaign(
        restaurant_id=int(restaurant["id"]),
        title=str(data.get("title") or "Promotion"),
        message=str(data.get("message_text") or ""),
        photo_file_id=data.get("photo_file_id"),
        audience_type=str(data["audience_type"]),
        target_count=len(recipients),
        sent_count=sent,
        failed_count=failed,
        blocked_count=blocked,
        created_by=callback.from_user.id,
    )
    await state.clear()
    if callback.message:
        await callback.message.answer(
            "📊 <b>Promotion Sent</b>\n\n"
            f"<b>Delivered:</b> {sent}\n"
            f"<b>Failed:</b> {failed}\n"
            f"<b>Blocked:</b> {blocked}",
            reply_markup=keyboards.admin_promotions_keyboard(),
        )


@router.callback_query(F.data == "admin:promo:history")
async def promotion_history(callback: CallbackQuery) -> None:
    if await reject_if_not_admin(callback):
        return
    restaurant = admin_restaurant(callback.from_user.id)
    campaigns = promotion_service.list_campaigns(int(restaurant["id"]), limit=10)
    if not campaigns:
        text = "📊 <b>Promotion History</b>\n\nNo campaigns yet."
    else:
        lines = ["📊 <b>Promotion History</b>", ""]
        for campaign in campaigns:
            lines.append(
                f"<b>{h(campaign['title'])}</b>\n"
                f"Audience: {h(promotion_service.audience_label(campaign['audience_type']))}\n"
                f"Sent: {campaign['sent_count']}/{campaign['target_count']} "
                f"(failed {campaign['failed_count']}, blocked {campaign['blocked_count']})\n"
                f"Date: {h(promotion_service.format_campaign_date(campaign['created_at']))}\n"
            )
        text = "\n".join(lines)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(text, reply_markup=keyboards.admin_promotions_keyboard())


@router.callback_query(F.data == "admin:promo:settings")
async def promotion_settings(callback: CallbackQuery) -> None:
    if await reject_if_not_admin(callback):
        return
    restaurant = admin_restaurant(callback.from_user.id)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            "⚙️ <b>Promotion Settings</b>",
            reply_markup=keyboards.promotion_settings_keyboard(restaurant),
        )


@router.callback_query(F.data.in_({"admin:promo:toggle_enabled", "admin:promo:toggle_filters"}))
async def promotion_toggle_setting(callback: CallbackQuery) -> None:
    if await reject_if_not_admin(callback):
        return
    restaurant = admin_restaurant(callback.from_user.id)
    field = "promotions_enabled" if callback.data.endswith("toggle_enabled") else "promotion_audience_filters_enabled"
    restaurant_service.update_restaurant_field(int(restaurant["id"]), field, 0 if restaurant.get(field) else 1)
    restaurant = restaurant_service.get_restaurant(int(restaurant["id"]))
    await callback.answer("Setting updated.")
    if callback.message:
        await callback.message.edit_text(
            "⚙️ <b>Promotion Settings</b>",
            reply_markup=keyboards.promotion_settings_keyboard(restaurant),
        )


@router.callback_query(F.data == "admin:promo:set_max")
async def promotion_set_max(callback: CallbackQuery, state: FSMContext) -> None:
    if await reject_if_not_admin(callback):
        return
    restaurant = admin_restaurant(callback.from_user.id)
    await state.update_data(restaurant_id=restaurant["id"])
    await state.set_state(PromotionFlow.waiting_for_max_per_day)
    await callback.answer()
    if callback.message:
        await callback.message.answer("Send the maximum number of promotion campaigns allowed per day. Use 0 for no limit.")


@router.message(PromotionFlow.waiting_for_max_per_day)
async def promotion_receive_max(message: Message, state: FSMContext) -> None:
    if await reject_if_not_admin(message):
        return
    try:
        value = int((message.text or "").strip())
    except ValueError:
        await message.answer("Please send a whole number, for example 3.")
        return
    if value < 0 or value > 100:
        await message.answer("Please send a value from 0 to 100.")
        return
    data = await state.get_data()
    restaurant_service.update_restaurant_field(int(data["restaurant_id"]), "promotion_max_per_day", value)
    await state.clear()
    await message.answer("Promotion limit updated.", reply_markup=keyboards.admin_promotions_keyboard())


def loyalty_status_text(restaurant: dict) -> str:
    enabled = "Enabled" if restaurant.get("loyalty_enabled") else "Disabled"
    rate = menu_service.cents_to_usd(int(restaurant.get("loyalty_cents_per_point") or 100), restaurant["currency_symbol"])
    return (
        "<b>Loyalty Rewards</b>\n\n"
        f"<b>Status:</b> {enabled}\n"
        f"<b>Earning rate:</b> {rate} = 1 point"
    )


@router.callback_query(F.data == "admin:loyalty")
async def loyalty_rewards(callback: CallbackQuery) -> None:
    if await reject_if_not_admin(callback):
        return
    restaurant = admin_restaurant(callback.from_user.id)
    await callback.answer()
    if callback.message and restaurant:
        await callback.message.edit_text(loyalty_status_text(restaurant), reply_markup=keyboards.admin_loyalty_keyboard(restaurant))


@router.callback_query(F.data == "admin:reward:add")
async def add_reward_start(callback: CallbackQuery, state: FSMContext) -> None:
    if await reject_if_not_admin(callback):
        return
    restaurant = admin_restaurant(callback.from_user.id)
    await state.clear()
    await state.update_data(restaurant_id=restaurant["id"])
    await state.set_state(AddReward.waiting_for_name_en)
    await callback.answer()
    if callback.message:
        await callback.message.answer("Send the English reward name.")


@router.message(AddReward.waiting_for_name_en)
async def add_reward_name_en(message: Message, state: FSMContext) -> None:
    await state.update_data(name_en=(message.text or "").strip())
    await state.set_state(AddReward.waiting_for_name_kh)
    await message.answer("Send the Khmer reward name, or '-' to skip.")


@router.message(AddReward.waiting_for_name_kh)
async def add_reward_name_kh(message: Message, state: FSMContext) -> None:
    await state.update_data(name_kh="" if message.text == "-" else (message.text or "").strip())
    await state.set_state(AddReward.waiting_for_name_zh)
    await message.answer("Send the Chinese reward name, or '-' to skip.")


@router.message(AddReward.waiting_for_name_zh)
async def add_reward_name_zh(message: Message, state: FSMContext) -> None:
    await state.update_data(name_zh="" if message.text == "-" else (message.text or "").strip())
    await state.set_state(AddReward.waiting_for_description_en)
    await message.answer("Send the English description, or '-' to skip.")


@router.message(AddReward.waiting_for_description_en)
async def add_reward_description_en(message: Message, state: FSMContext) -> None:
    await state.update_data(description_en="" if message.text == "-" else (message.text or "").strip())
    await state.set_state(AddReward.waiting_for_description_kh)
    await message.answer("Send the Khmer description, or '-' to skip.")


@router.message(AddReward.waiting_for_description_kh)
async def add_reward_description_kh(message: Message, state: FSMContext) -> None:
    await state.update_data(description_kh="" if message.text == "-" else (message.text or "").strip())
    await state.set_state(AddReward.waiting_for_description_zh)
    await message.answer("Send the Chinese description, or '-' to skip.")


@router.message(AddReward.waiting_for_description_zh)
async def add_reward_description_zh(message: Message, state: FSMContext) -> None:
    await state.update_data(description_zh="" if message.text == "-" else (message.text or "").strip())
    await state.set_state(AddReward.waiting_for_points)
    await message.answer("Send points required, for example 20.")


@router.message(AddReward.waiting_for_points)
async def add_reward_points(message: Message, state: FSMContext) -> None:
    try:
        points = int((message.text or "").strip())
    except ValueError:
        await message.answer("Please send a whole number.")
        return
    if points <= 0:
        await message.answer("Points must be greater than zero.")
        return
    await state.update_data(points_required=points)
    await state.set_state(AddReward.waiting_for_expiry)
    await message.answer("Send expiry days, or '-' for no expiry.")


@router.message(AddReward.waiting_for_expiry)
async def add_reward_expiry(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if raw == "-":
        expires_days = None
    else:
        try:
            expires_days = int(raw)
        except ValueError:
            await message.answer("Please send a number of days, or '-'.")
            return
    await state.update_data(expires_days=expires_days)
    await state.set_state(AddReward.waiting_for_quantity)
    await message.answer("Send quantity limit, or '-' for unlimited.")


@router.message(AddReward.waiting_for_quantity)
async def add_reward_quantity(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if raw == "-":
        quantity_limit = None
    else:
        try:
            quantity_limit = int(raw)
        except ValueError:
            await message.answer("Please send a number, or '-'.")
            return
    data = await state.get_data()
    reward_id = reward_service.create_reward(
        restaurant_id=int(data["restaurant_id"]),
        name_en=data["name_en"],
        name_kh=data["name_kh"],
        name_zh=data["name_zh"],
        description_en=data["description_en"],
        description_kh=data["description_kh"],
        description_zh=data["description_zh"],
        points_required=int(data["points_required"]),
        expires_days=data.get("expires_days"),
        quantity_limit=quantity_limit,
    )
    await state.clear()
    await message.answer(f"Reward added: #{reward_id} {data['name_en']}", reply_markup=keyboards.admin_dashboard_keyboard())


@router.callback_query(F.data.in_({"admin:reward:edit", "admin:reward:disable"}))
async def choose_reward(callback: CallbackQuery) -> None:
    if await reject_if_not_admin(callback):
        return
    restaurant = admin_restaurant(callback.from_user.id)
    rewards = reward_service.list_rewards(restaurant["id"], active_only=False)
    prefix = "admin:rewardedit" if callback.data.endswith("edit") else "admin:rewarddisable"
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("Choose a reward.", reply_markup=keyboards.admin_rewards_keyboard(rewards, prefix))


@router.callback_query(F.data.startswith("admin:rewardedit:"))
async def edit_reward_fields(callback: CallbackQuery) -> None:
    reward_id = int(callback.data.split(":")[2])
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("Choose reward field.", reply_markup=keyboards.admin_reward_fields_keyboard(reward_id))


@router.callback_query(F.data.startswith("admin:rewarddisable:"))
async def disable_reward(callback: CallbackQuery) -> None:
    if await reject_if_not_admin(callback):
        return
    restaurant = admin_restaurant(callback.from_user.id)
    reward_id = int(callback.data.split(":")[2])
    reward = reward_service.get_reward(reward_id, restaurant["id"])
    if not reward:
        await callback.answer("Reward not found.", show_alert=True)
        return
    reward_service.update_reward(reward_id, restaurant["id"], "is_active", 0 if reward["is_active"] else 1)
    await callback.answer("Reward status updated.")
    rewards = reward_service.list_rewards(restaurant["id"], active_only=False)
    if callback.message:
        await callback.message.edit_text("Choose a reward.", reply_markup=keyboards.admin_rewards_keyboard(rewards, "admin:rewarddisable"))


@router.callback_query(F.data.startswith("admin:rewardfield:"))
async def edit_reward_field(callback: CallbackQuery, state: FSMContext) -> None:
    if await reject_if_not_admin(callback):
        return
    _, _, reward_id, field = callback.data.split(":")
    restaurant = admin_restaurant(callback.from_user.id)
    if field == "is_active":
        reward = reward_service.get_reward(int(reward_id), restaurant["id"])
        reward_service.update_reward(int(reward_id), restaurant["id"], "is_active", 0 if reward["is_active"] else 1)
        await callback.answer("Reward status updated.")
        if callback.message:
            await callback.message.edit_text("Choose reward field.", reply_markup=keyboards.admin_reward_fields_keyboard(int(reward_id)))
        return
    await state.update_data(restaurant_id=restaurant["id"], reward_id=int(reward_id), field=field)
    await state.set_state(EditReward.waiting_for_value)
    await callback.answer()
    if callback.message:
        await callback.message.answer("Send new value. Use '-' to clear optional expiry/quantity/description.")


@router.message(EditReward.waiting_for_value)
async def edit_reward_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    field = data["field"]
    raw = (message.text or "").strip()
    value: object = "" if raw == "-" else raw
    if field in {"points_required", "expires_days", "quantity_limit"}:
        if raw == "-" and field != "points_required":
            value = None
        else:
            try:
                value = int(raw)
            except ValueError:
                await message.answer("Please send a whole number.")
                return
    reward_service.update_reward(int(data["reward_id"]), int(data["restaurant_id"]), field, value)
    await state.clear()
    await message.answer("Reward updated.", reply_markup=keyboards.admin_dashboard_keyboard())


@router.callback_query(F.data == "admin:reward:redemptions")
async def view_redemptions(callback: CallbackQuery) -> None:
    if await reject_if_not_admin(callback):
        return
    restaurant = admin_restaurant(callback.from_user.id)
    redemptions = reward_service.list_recent_redemptions(restaurant["id"])
    lines = ["<b>Recent Reward Redemptions</b>", ""]
    if not redemptions:
        lines.append("No redemptions yet.")
    for item in redemptions:
        lines.append(f"{item['voucher_code']} - {h(item['name_en'])} - {item['status']}")
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("\n".join(lines), reply_markup=keyboards.admin_dashboard_keyboard())


@router.callback_query(F.data == "admin:khqr")
async def khqr_shortcut(callback: CallbackQuery) -> None:
    if await reject_if_not_admin(callback):
        return
    restaurant = admin_restaurant(callback.from_user.id)
    await callback.answer()
    if callback.message and restaurant:
        await callback.message.edit_text(khqr_status_text(restaurant), reply_markup=keyboards.admin_khqr_keyboard(restaurant))


def khqr_status_text(restaurant: dict) -> str:
    enabled = "Enabled" if restaurant.get("khqr_payment_enabled") else "Disabled"
    image = "Uploaded" if restaurant.get("khqr_image_file_id") else "Missing"
    return (
        "<b>KHQR Payment</b>\n\n"
        f"<b>Status:</b> {enabled}\n"
        f"<b>KHQR image:</b> {image}"
    )


@router.callback_query(F.data == "admin:khqr:toggle")
async def toggle_khqr_payment(callback: CallbackQuery) -> None:
    if await reject_if_not_admin(callback):
        return
    restaurant = admin_restaurant(callback.from_user.id)
    restaurant_service.update_restaurant_field(
        restaurant["id"],
        "khqr_payment_enabled",
        0 if restaurant.get("khqr_payment_enabled") else 1,
    )
    restaurant = restaurant_service.get_restaurant(restaurant["id"])
    await callback.answer("KHQR setting updated.")
    if callback.message:
        await callback.message.edit_text(khqr_status_text(restaurant), reply_markup=keyboards.admin_khqr_keyboard(restaurant))


@router.callback_query(F.data == "admin:khqr:status")
async def show_khqr_status(callback: CallbackQuery) -> None:
    if await reject_if_not_admin(callback):
        return
    restaurant = admin_restaurant(callback.from_user.id)
    await callback.answer()
    if callback.message and restaurant:
        await callback.message.edit_text(khqr_status_text(restaurant), reply_markup=keyboards.admin_khqr_keyboard(restaurant))


@router.callback_query(F.data == "admin:add")
async def add_item_start(callback: CallbackQuery, state: FSMContext) -> None:
    if await reject_if_not_admin(callback):
        return
    restaurant = admin_restaurant(callback.from_user.id)
    categories = menu_service.list_categories(active_only=True, restaurant_id=restaurant["id"])
    await state.clear()
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            "Choose a category for the new item.",
            reply_markup=keyboards.admin_categories_keyboard(categories, "admin:addcat"),
        )


@router.callback_query(F.data.startswith("admin:addcat:"))
async def add_item_category(callback: CallbackQuery, state: FSMContext) -> None:
    if await reject_if_not_admin(callback):
        return
    restaurant = admin_restaurant(callback.from_user.id)
    category_id = int(callback.data.split(":")[2])
    await state.update_data(category_id=category_id, restaurant_id=restaurant["id"])
    await state.set_state(AddItem.waiting_for_name)
    await callback.answer()
    if callback.message:
        await callback.message.answer("Send the item name in English.")


@router.message(AddItem.waiting_for_name)
async def add_item_name(message: Message, state: FSMContext) -> None:
    if await reject_if_not_admin(message):
        return
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer("Please send a clear item name.")
        return
    await state.update_data(name_en=name)
    await state.set_state(AddItem.waiting_for_name_km)
    await message.answer("Send the Khmer item name, or '-' to skip.")


@router.message(AddItem.waiting_for_name_km)
async def add_item_name_km(message: Message, state: FSMContext) -> None:
    await state.update_data(name_km="" if message.text == "-" else (message.text or "").strip())
    await state.set_state(AddItem.waiting_for_name_zh)
    await message.answer("Send the Chinese item name, or '-' to skip.")


@router.message(AddItem.waiting_for_name_zh)
async def add_item_name_zh(message: Message, state: FSMContext) -> None:
    await state.update_data(name_zh="" if message.text == "-" else (message.text or "").strip())
    await state.set_state(AddItem.waiting_for_description)
    await message.answer("Send the English item description.")


@router.message(AddItem.waiting_for_description)
async def add_item_description(message: Message, state: FSMContext) -> None:
    description = (message.text or "").strip()
    if len(description) < 3:
        await message.answer("Please send a short description.")
        return
    await state.update_data(description_en=description)
    await state.set_state(AddItem.waiting_for_description_km)
    await message.answer("Send the Khmer item description, or '-' to skip.")


@router.message(AddItem.waiting_for_description_km)
async def add_item_description_km(message: Message, state: FSMContext) -> None:
    await state.update_data(description_km="" if message.text == "-" else (message.text or "").strip())
    await state.set_state(AddItem.waiting_for_description_zh)
    await message.answer("Send the Chinese item description, or '-' to skip.")


@router.message(AddItem.waiting_for_description_zh)
async def add_item_description_zh(message: Message, state: FSMContext) -> None:
    await state.update_data(description_zh="" if message.text == "-" else (message.text or "").strip())
    await state.set_state(AddItem.waiting_for_price)
    await message.answer("Send the price, for example 2.50.")


def parse_price_to_cents(raw: str) -> int | None:
    try:
        value = round(float(raw.strip().replace("$", "")) * 100)
    except ValueError:
        return None
    return value if value >= 0 else None


@router.message(AddItem.waiting_for_price)
async def add_item_price(message: Message, state: FSMContext) -> None:
    price_cents = parse_price_to_cents(message.text or "")
    if price_cents is None:
        await message.answer("Please send a valid price, for example 2.50.")
        return
    data = await state.get_data()
    item_id = menu_service.create_item(
        restaurant_id=int(data["restaurant_id"]),
        category_id=int(data["category_id"]),
        name_en=data["name_en"],
        name_km=data["name_km"],
        name_zh=data["name_zh"],
        description_en=data["description_en"],
        description_km=data["description_km"],
        description_zh=data["description_zh"],
        price_cents=price_cents,
    )
    await state.update_data(item_id=item_id)
    await state.set_state(AddItem.waiting_for_photo)
    await message.answer("Send an optional item photo, or tap Skip photo.", reply_markup=keyboards.skip_photo_keyboard())


@router.message(AddItem.waiting_for_photo, F.photo)
async def add_item_optional_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    menu_service.update_item(int(data["item_id"]), "image_file_id", message.photo[-1].file_id)
    await state.clear()
    await message.answer(f"Added menu item #{data['item_id']}: {data['name_en']}", reply_markup=keyboards.admin_dashboard_keyboard())


@router.callback_query(F.data == "admin:skip_item_photo")
async def skip_item_photo(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    await callback.answer("Skipped photo.")
    if callback.message:
        await callback.message.answer(f"Added menu item #{data['item_id']}: {data['name_en']}", reply_markup=keyboards.admin_dashboard_keyboard())


@router.callback_query(F.data == "admin:edit")
async def edit_item_start(callback: CallbackQuery, state: FSMContext) -> None:
    if await reject_if_not_admin(callback):
        return
    restaurant = admin_restaurant(callback.from_user.id)
    items = menu_service.list_items(active_only=False, restaurant_id=restaurant["id"])
    await state.clear()
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("Choose an item to edit.", reply_markup=keyboards.admin_items_keyboard(items, "admin:edititem"))


@router.callback_query(F.data.startswith("admin:edititem:"))
async def edit_item_fields(callback: CallbackQuery) -> None:
    if await reject_if_not_admin(callback):
        return
    restaurant = admin_restaurant(callback.from_user.id)
    item_id = int(callback.data.split(":")[2])
    item = menu_service.get_item(item_id, restaurant_id=restaurant["id"])
    await callback.answer()
    if callback.message and item:
        await callback.message.edit_text(f"Editing {item['name_en']}. Choose a field.", reply_markup=keyboards.admin_edit_fields_keyboard(item_id))


@router.callback_query(F.data.startswith("admin:field:"))
async def edit_item_field(callback: CallbackQuery, state: FSMContext) -> None:
    if await reject_if_not_admin(callback):
        return
    _, _, item_id, field = callback.data.split(":")
    restaurant = admin_restaurant(callback.from_user.id)
    if field == "category_id":
        await state.update_data(item_id=int(item_id), field=field, restaurant_id=restaurant["id"])
        categories = menu_service.list_categories(active_only=False, restaurant_id=restaurant["id"])
        await callback.answer()
        if callback.message:
            await callback.message.edit_text("Choose the new category.", reply_markup=keyboards.admin_categories_keyboard(categories, "admin:itemcat"))
        return
    await state.update_data(item_id=int(item_id), field=field, restaurant_id=restaurant["id"])
    await state.set_state(EditItem.waiting_for_value)
    await callback.answer()
    if callback.message:
        await callback.message.answer("Send the new price." if field == "price_cents" else "Send the new value.")


@router.callback_query(F.data.startswith("admin:itemcat:"))
async def edit_item_category(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    menu_service.update_item(int(data["item_id"]), "category_id", int(callback.data.split(":")[2]))
    await state.clear()
    await callback.answer("Item category updated.")
    if callback.message:
        await callback.message.edit_text("Item updated.", reply_markup=keyboards.admin_dashboard_keyboard())


@router.message(EditItem.waiting_for_value)
async def edit_item_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    field = data["field"]
    raw_value = (message.text or "").strip()
    value: object = raw_value
    if field == "price_cents":
        parsed = parse_price_to_cents(raw_value)
        if parsed is None:
            await message.answer("Please send a valid price.")
            return
        value = parsed
    elif len(raw_value) < 1:
        await message.answer("Please send a value.")
        return
    menu_service.update_item(int(data["item_id"]), field, value)
    await state.clear()
    await message.answer("Item updated.", reply_markup=keyboards.admin_dashboard_keyboard())


@router.callback_query(F.data == "admin:toggle")
async def toggle_item_start(callback: CallbackQuery, state: FSMContext) -> None:
    if await reject_if_not_admin(callback):
        return
    restaurant = admin_restaurant(callback.from_user.id)
    items = menu_service.list_items(active_only=False, restaurant_id=restaurant["id"])
    await state.clear()
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("Choose an item to mark Available or Sold Out.", reply_markup=keyboards.admin_items_keyboard(items, "admin:toggleitem"))


@router.callback_query(F.data.startswith("admin:toggleitem:"))
async def toggle_item(callback: CallbackQuery) -> None:
    if await reject_if_not_admin(callback):
        return
    restaurant = admin_restaurant(callback.from_user.id)
    item_id = int(callback.data.split(":")[2])
    item = menu_service.get_item(item_id, restaurant_id=restaurant["id"])
    if not item:
        await callback.answer("Item not found.", show_alert=True)
        return
    menu_service.set_item_active(item_id, not bool(item["is_active"]))
    await callback.answer("Item marked Available." if not item["is_active"] else "Item marked Sold Out.")
    items = menu_service.list_items(active_only=False, restaurant_id=restaurant["id"])
    if callback.message:
        await callback.message.edit_text("Choose an item to mark Available or Sold Out.", reply_markup=keyboards.admin_items_keyboard(items, "admin:toggleitem"))


@router.callback_query(F.data == "admin:photo")
async def add_item_photo_start(callback: CallbackQuery, state: FSMContext) -> None:
    if await reject_if_not_admin(callback):
        return
    restaurant = admin_restaurant(callback.from_user.id)
    items = menu_service.list_items(active_only=False, restaurant_id=restaurant["id"])
    await state.clear()
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("Choose an item to update its photo.", reply_markup=keyboards.admin_items_keyboard(items, "admin:photoitem"))


@router.callback_query(F.data.startswith("admin:photoitem:"))
async def choose_item_photo(callback: CallbackQuery, state: FSMContext) -> None:
    restaurant = admin_restaurant(callback.from_user.id)
    item_id = int(callback.data.split(":")[2])
    item = menu_service.get_item(item_id, restaurant_id=restaurant["id"])
    if not item:
        await callback.answer("Item not found.", show_alert=True)
        return
    await state.update_data(item_id=item_id, item_name=item["name_en"])
    await state.set_state(ItemPhoto.waiting_for_photo)
    await callback.answer()
    if callback.message:
        await callback.message.answer(f"Send a photo for {item['name_en']}.")


@router.message(ItemPhoto.waiting_for_photo, F.photo)
async def receive_item_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    menu_service.update_item(int(data["item_id"]), "image_file_id", message.photo[-1].file_id)
    await state.clear()
    await message.answer(f"Photo updated successfully.\nItem: {data['item_name']}", reply_markup=keyboards.admin_dashboard_keyboard())


@router.message(ItemPhoto.waiting_for_photo)
async def receive_item_photo_invalid(message: Message) -> None:
    await message.answer("Please send a photo.")


@router.callback_query(F.data == "admin:categories")
async def manage_categories(callback: CallbackQuery, state: FSMContext) -> None:
    if await reject_if_not_admin(callback):
        return
    await state.clear()
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("Manage categories", reply_markup=keyboards.admin_category_management_keyboard())


@router.callback_query(F.data == "admin:cat:add")
async def add_category_start(callback: CallbackQuery, state: FSMContext) -> None:
    if await reject_if_not_admin(callback):
        return
    restaurant = admin_restaurant(callback.from_user.id)
    await state.update_data(restaurant_id=restaurant["id"])
    await state.set_state(AddCategory.waiting_for_name_en)
    await callback.answer()
    if callback.message:
        await callback.message.answer("Send the English category name.")


@router.message(AddCategory.waiting_for_name_en)
async def add_category_name_en(message: Message, state: FSMContext) -> None:
    await state.update_data(name_en=(message.text or "").strip())
    await state.set_state(AddCategory.waiting_for_name_kh)
    await message.answer("Send the Khmer category name, or '-' to skip.")


@router.message(AddCategory.waiting_for_name_kh)
async def add_category_name_kh(message: Message, state: FSMContext) -> None:
    await state.update_data(name_kh="" if message.text == "-" else (message.text or "").strip())
    await state.set_state(AddCategory.waiting_for_name_zh)
    await message.answer("Send the Chinese category name, or '-' to skip.")


@router.message(AddCategory.waiting_for_name_zh)
async def add_category_name_zh(message: Message, state: FSMContext) -> None:
    await state.update_data(name_zh="" if message.text == "-" else (message.text or "").strip())
    await state.set_state(AddCategory.waiting_for_sort_order)
    await message.answer("Send sort order number, or 0.")


@router.message(AddCategory.waiting_for_sort_order)
async def add_category_sort_order(message: Message, state: FSMContext) -> None:
    try:
        sort_order = int((message.text or "0").strip())
    except ValueError:
        await message.answer("Please send a number.")
        return
    data = await state.get_data()
    category_id = menu_service.create_category(
        restaurant_id=int(data["restaurant_id"]),
        name_en=data["name_en"],
        name_km=data["name_kh"],
        name_zh=data["name_zh"],
        sort_order=sort_order,
    )
    await state.clear()
    await message.answer(f"Category added: {data['name_en']} (#{category_id})", reply_markup=keyboards.admin_category_management_keyboard())


async def show_category_picker(callback: CallbackQuery, prefix: str, title: str) -> None:
    restaurant = admin_restaurant(callback.from_user.id)
    categories = menu_service.list_categories(active_only=False, restaurant_id=restaurant["id"])
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(title, reply_markup=keyboards.admin_categories_keyboard(categories, prefix))


@router.callback_query(F.data == "admin:cat:edit")
async def edit_category_start(callback: CallbackQuery) -> None:
    if await reject_if_not_admin(callback):
        return
    await show_category_picker(callback, "admin:catedit", "Choose a category to edit.")


@router.callback_query(F.data.startswith("admin:catedit:"))
async def edit_category_fields(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("Choose a category field.", reply_markup=keyboards.admin_category_fields_keyboard(int(callback.data.split(":")[2])))


@router.callback_query(F.data.startswith("admin:catfield:"))
async def edit_category_field(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, category_id, field = callback.data.split(":")
    await state.update_data(category_id=int(category_id), field=field)
    await state.set_state(EditCategory.waiting_for_value)
    await callback.answer()
    if callback.message:
        await callback.message.answer("Send the new value.")


@router.message(EditCategory.waiting_for_value)
async def edit_category_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    field = data["field"]
    value = (message.text or "").strip()
    if field == "sort_order":
        try:
            menu_service.update_category(int(data["category_id"]), "sort_order", int(value))
        except ValueError:
            await message.answer("Please send a number.")
            return
    elif field in {"en", "kh", "zh"}:
        menu_service.update_category_translation(int(data["category_id"]), field, value)
    await state.clear()
    await message.answer("Category updated.", reply_markup=keyboards.admin_category_management_keyboard())


@router.callback_query(F.data == "admin:cat:toggle")
async def toggle_category_start(callback: CallbackQuery) -> None:
    if await reject_if_not_admin(callback):
        return
    await show_category_picker(callback, "admin:cattoggle", "Choose a category to enable or disable.")


@router.callback_query(F.data.startswith("admin:cattoggle:"))
async def toggle_category(callback: CallbackQuery) -> None:
    restaurant = admin_restaurant(callback.from_user.id)
    category_id = int(callback.data.split(":")[2])
    category = menu_service.get_category(category_id, restaurant_id=restaurant["id"])
    if not category:
        await callback.answer("Category not found.", show_alert=True)
        return
    menu_service.set_category_active(category_id, not bool(category["is_active"]))
    await show_category_picker(callback, "admin:cattoggle", "Choose a category to enable or disable.")


@router.callback_query(F.data == "admin:cat:reorder")
async def reorder_category_start(callback: CallbackQuery) -> None:
    if await reject_if_not_admin(callback):
        return
    await show_category_picker(callback, "admin:catreorder", "Choose a category to reorder.")


@router.callback_query(F.data.startswith("admin:catreorder:"))
async def reorder_category_choose(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(category_id=int(callback.data.split(":")[2]), field="sort_order")
    await state.set_state(EditCategory.waiting_for_value)
    await callback.answer()
    if callback.message:
        await callback.message.answer("Send the new sort order number.")


@router.callback_query(F.data == "admin:orders_today")
async def today_orders(callback: CallbackQuery) -> None:
    if await reject_if_not_admin(callback):
        return
    restaurant = admin_restaurant(callback.from_user.id)
    orders = order_service.list_today_orders(restaurant_id=restaurant["id"])
    if not orders:
        text = "No orders today."
    else:
        lines = ["Today's orders:"]
        for order in orders[:20]:
            lines.append(f"{order['order_code']} - {keyboards.status_label(order['status'])} - {menu_service.cents_to_usd(order['subtotal_cents'], restaurant['currency_symbol'])}")
        text = "\n".join(lines)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(text, reply_markup=keyboards.admin_dashboard_keyboard())


@router.callback_query(F.data == "admin:sales_today")
async def sales_today(callback: CallbackQuery) -> None:
    if await reject_if_not_admin(callback):
        return
    restaurant = admin_restaurant(callback.from_user.id)
    summary = order_service.sales_summary_today(restaurant_id=restaurant["id"])
    text = (
        "💰 <b>Today’s Sales Summary</b>\n\n"
        f"🧾 <b>Orders:</b> {summary['order_count']}\n"
        f"❌ <b>Cancelled:</b> {summary['cancelled_count']}\n"
        f"💳 <b>Paid KHQR:</b> {summary['khqr_paid_count']}\n"
        f"💵 <b>Cash Orders:</b> {summary['cash_order_count']}\n"
        f"🎁 <b>Loyalty Points Issued:</b> {summary['loyalty_points_issued']}\n"
        f"💰 <b>Sales:</b> {menu_service.cents_to_usd(summary['sales_cents'], restaurant['currency_symbol'])}"
    )
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(text, reply_markup=keyboards.admin_dashboard_keyboard())


@router.callback_query(F.data == "admin:reports")
async def reports_menu(callback: CallbackQuery) -> None:
    if await reject_if_not_admin(callback):
        return
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            "<b>Reports</b>\n\nChoose timeframe or report type:",
            reply_markup=keyboards.admin_reports_keyboard(),
        )


@router.callback_query(F.data.startswith("admin:report:"))
async def export_report(callback: CallbackQuery, state: FSMContext) -> None:
    if await reject_if_not_admin(callback):
        return
    restaurant = admin_restaurant(callback.from_user.id)
    kind = callback.data.split(":")[2]
    if kind == "custom":
        await state.clear()
        await state.update_data(restaurant_id=restaurant["id"])
        await state.set_state(ReportCustom.waiting_for_dates)
        await callback.answer()
        if callback.message:
            await callback.message.answer("Send custom dates as: YYYY-MM-DD to YYYY-MM-DD")
        return
    await state.clear()
    await callback.answer("Generating report...")
    try:
        path, period = report_service.generate_xlsx_report(restaurant, kind)
    except ModuleNotFoundError:
        if callback.message:
            await callback.message.answer("openpyxl is not installed. Run: py -3.12 -m pip install -r requirements.txt")
        return
    if callback.message:
        await callback.message.answer_document(
            FSInputFile(path),
            caption=(
                "📄 <b>Report Ready</b>\n\n"
                f"Restaurant: {h(restaurant['name'])}\n"
                f"Period: {h(period)}"
            ),
        )


@router.message(ReportCustom.waiting_for_dates)
async def export_custom_report(message: Message, state: FSMContext) -> None:
    if await reject_if_not_admin(message):
        return
    raw = (message.text or "").strip()
    try:
        start_raw, end_raw = [part.strip() for part in raw.split("to", 1)]
        start = datetime.fromisoformat(start_raw)
        end = datetime.fromisoformat(end_raw) + timedelta(days=1)
    except ValueError:
        await message.answer("Please send dates as: YYYY-MM-DD to YYYY-MM-DD")
        return
    restaurant = admin_restaurant(message.from_user.id)
    period = f"{start.date()} to {(end - timedelta(days=1)).date()}"
    await state.clear()
    try:
        path, period = report_service.generate_xlsx_report(restaurant, "custom", start=start, end=end, period_label=period)
    except ModuleNotFoundError:
        await message.answer("openpyxl is not installed. Run: py -3.12 -m pip install -r requirements.txt")
        return
    await message.answer_document(
        FSInputFile(path),
        caption=(
            "📄 <b>Report Ready</b>\n\n"
            f"Restaurant: {h(restaurant['name'])}\n"
            f"Period: {h(period)}"
        ),
    )


@router.callback_query(F.data == "admin:settings")
async def settings_start(callback: CallbackQuery) -> None:
    if await reject_if_not_admin(callback):
        return
    restaurant = admin_restaurant(callback.from_user.id)
    await callback.answer()
    if callback.message and restaurant:
        await callback.message.edit_text("Restaurant settings", reply_markup=keyboards.admin_settings_keyboard(restaurant))


@router.callback_query(F.data.startswith("admin:toggle_setting:"))
async def toggle_restaurant_setting(callback: CallbackQuery) -> None:
    if await reject_if_not_admin(callback):
        return
    field = callback.data.split(":")[2]
    restaurant = admin_restaurant(callback.from_user.id)
    restaurant_service.update_restaurant_field(restaurant["id"], field, 0 if restaurant[field] else 1)
    restaurant = restaurant_service.get_restaurant(restaurant["id"])
    await callback.answer("Setting updated.")
    if callback.message:
        await callback.message.edit_text("Restaurant settings", reply_markup=keyboards.admin_settings_keyboard(restaurant))


@router.callback_query(F.data.startswith("admin:set:"))
async def edit_restaurant_setting(callback: CallbackQuery, state: FSMContext) -> None:
    if await reject_if_not_admin(callback):
        return
    field = callback.data.split(":")[2]
    restaurant = admin_restaurant(callback.from_user.id)
    await state.update_data(restaurant_id=restaurant["id"], field=field)
    await callback.answer()
    if field in {"logo_file_id", "khqr_image_file_id"}:
        await state.set_state(RestaurantSetting.waiting_for_photo)
        if callback.message:
            await callback.message.answer("Send the image now.")
        return
    await state.set_state(RestaurantSetting.waiting_for_value)
    if callback.message:
        if field == "loyalty_cents_per_point":
            await callback.message.answer("Send the spend amount needed to earn 1 point, for example 1.00.")
        else:
            await callback.message.answer("Send the new value.")


@router.message(RestaurantSetting.waiting_for_photo, F.photo)
async def receive_restaurant_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    restaurant_service.update_restaurant_field(int(data["restaurant_id"]), data["field"], message.photo[-1].file_id)
    await state.clear()
    await message.answer("Restaurant image updated.", reply_markup=keyboards.admin_dashboard_keyboard())


@router.message(RestaurantSetting.waiting_for_value)
async def receive_restaurant_setting(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    field = data["field"]
    value: object = (message.text or "").strip()
    if field == "staff_group_id":
        try:
            value = int(str(value))
        except ValueError:
            await message.answer("Please send a numeric staff group ID.")
            return
    if field == "loyalty_cents_per_point":
        parsed = parse_price_to_cents(str(value))
        if parsed is None or parsed <= 0:
            await message.answer("Please send the spend amount for 1 point, for example 1.00.")
            return
        value = parsed
    if field == "currency_symbol" and not value:
        await message.answer("Please send a currency symbol.")
        return
    restaurant_service.update_restaurant_field(int(data["restaurant_id"]), field, value)
    await state.clear()
    await message.answer("Restaurant setting updated.", reply_markup=keyboards.admin_dashboard_keyboard())
