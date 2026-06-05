from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from restaurant_bot import keyboards
from restaurant_bot.handlers.customer import format_order_update, format_staff_order, get_user_language
from restaurant_bot.i18n import t
from restaurant_bot.services import loyalty_service, order_service, restaurant_service, reward_service


router = Router(name="staff")


@router.callback_query(F.data.startswith("staff:reward:"))
async def update_reward_redemption(callback: CallbackQuery, bot: Bot) -> None:
    _prefix, _kind, redemption_id_raw, status = callback.data.split(":")
    redemption_id = int(redemption_id_raw)
    try:
        if status == "used":
            redemption = reward_service.mark_redemption_used(redemption_id, callback.from_user.id)
        else:
            redemption = reward_service.reject_redemption(redemption_id, callback.from_user.id)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer("Reward redemption updated.")
    if callback.message:
        await callback.message.edit_text(
            "🎁 <b>Reward Redemption</b>\n\n"
            f"👤 <b>Customer:</b> {redemption.get('full_name') or redemption['user_id']}\n"
            f"🎁 <b>Reward:</b> {redemption['name_en']}\n"
            f"🎟 <b>Voucher:</b> {redemption['voucher_code']}\n"
            f"📌 <b>Status:</b> {redemption['status']}"
        )
    language = get_user_language(redemption["user_id"])
    if redemption["status"] == "used":
        await bot.send_message(
            redemption["user_id"],
            f"🎉 <b>{t(language, 'reward_used_title')}</b>\n\n{t(language, 'reward_used_message')}",
        )
    elif redemption["status"] == "cancelled":
        await bot.send_message(redemption["user_id"], t(language, "reward_rejected"))


@router.callback_query(F.data.startswith("staff:payment:"))
async def update_payment_status(callback: CallbackQuery, bot: Bot) -> None:
    parts = callback.data.split(":")
    order_id = int(parts[2])
    requested_status = parts[3]
    payment_status = "paid" if requested_status == "paid" else "rejected"
    try:
        order = order_service.update_payment_status(order_id, payment_status, callback.from_user.id)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    restaurant = restaurant_service.get_restaurant(order["restaurant_id"])
    await callback.answer("Payment updated.")
    if callback.message:
        await callback.message.edit_text(
            format_staff_order(order, restaurant or {"name": "Restaurant", "currency_symbol": "$"}),
            reply_markup=keyboards.staff_status_keyboard(
                order["id"],
                show_payment_buttons=order.get("payment_method") == "khqr" and order.get("payment_status") == "pending",
            ),
        )

    language = get_user_language(order["user_id"])
    if payment_status == "paid":
        loyalty = loyalty_service.award_order_points(order, restaurant)
        text = t(language, "payment_paid")
        if loyalty["awarded"]:
            text += "\n" + t(language, "loyalty_points_update", earned=loyalty["awarded"], balance=loyalty["balance"])
        await bot.send_message(order["user_id"], text)
    else:
        await bot.send_message(
            order["user_id"],
            t(language, "payment_rejected"),
            reply_markup=keyboards.payment_retry_keyboard(order["id"], language),
        )


@router.callback_query(F.data.startswith("staff:status:"))
async def update_order_status(callback: CallbackQuery, bot: Bot) -> None:
    parts = callback.data.split(":")
    order_id = int(parts[2])
    status = parts[3]
    try:
        order = order_service.update_order_status(order_id, status, callback.from_user.id)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    await callback.answer(f"Order marked as {keyboards.status_label(status)}.")
    restaurant = restaurant_service.get_restaurant(order["restaurant_id"])
    if callback.message:
        await callback.message.edit_text(
            format_staff_order(order, restaurant or {"name": "Restaurant", "currency_symbol": "$"}),
            reply_markup=keyboards.staff_status_keyboard(
                order["id"],
                show_payment_buttons=order.get("payment_method") == "khqr" and order.get("payment_status") == "pending",
            ),
        )

    language = get_user_language(order["user_id"])
    text = format_order_update(order, language)
    if status == "delivered":
        loyalty = loyalty_service.award_order_points(order, restaurant)
        if loyalty["awarded"]:
            text += "\n\n" + t(language, "loyalty_points_update", earned=loyalty["awarded"], balance=loyalty["balance"])
    await bot.send_message(order["user_id"], text)
