# White-Label Telegram Restaurant Bot

This project is a reusable template for selling:

> Your restaurant's own Telegram ordering bot

It is **not** a public food marketplace. Each deployment is for exactly one restaurant, with its own Telegram bot token, menu, staff group, logo, KHQR, and settings.

## Deployment Model

For each restaurant:

1. Copy this project folder.
2. Create a new Telegram bot with BotFather.
3. Create or edit `.env`.
4. Run the bot once to initialize SQLite.
5. Add that restaurant's menu, photos, KHQR, and settings.
6. Give the restaurant their own bot link.

Customers of one restaurant never see another restaurant.

## Current Architecture

The database keeps a `restaurants` table internally because it is useful for white-label settings and safe migrations. Runtime behavior is still single-restaurant:

- The active deployment restaurant is selected by `RESTAURANT_SLUG` in `.env`.
- `/start` never shows a restaurant picker.
- Menus are filtered to the deployment restaurant.
- Carts and orders are filtered to the deployment restaurant.
- Staff notifications go to the deployment restaurant's `staff_group_id`.
- `/admin` manages only the deployment restaurant.

## Environment

Copy `.env.example` to `.env` and edit:

```text
BOT_TOKEN=123456789:replace_with_your_bot_token
ADMIN_IDS=111111111,222222222
STAFF_GROUP_ID=-1001234567890
RESTAURANT_SLUG=sweet-chilli
RESTAURANT_NAME=Sweet Chilli
RESTAURANT_PHONE=+855 12 345 678
RESTAURANT_ADDRESS=Phnom Penh, Cambodia
RESTAURANT_CURRENCY_SYMBOL=$
RESTAURANT_DEFAULT_LANGUAGE=en
MINIAPP_URL=https://your-domain.example/app
```

`ADMIN_IDS` are assigned as owners for the deployment restaurant during setup/migration.

## Run

```bash
py -3.12 -m pip install -r requirements.txt
copy .env.example .env
py -3.12 -m restaurant_bot.bot
```

On Linux/macOS, use `python3` instead of `py -3.12`.

## Mini App Milestone 1

The Mini App customer browsing experience is served by FastAPI and React/Vite.

Backend API:

```powershell
py -3.12 -m uvicorn restaurant_bot.api.main:app --host 127.0.0.1 --port 8000 --reload
```

Frontend development server:

```powershell
cd miniapp
npm install
npm run dev
```

Production-style frontend build:

```powershell
cd miniapp
npm run build
```

FastAPI serves the built app at:

```text
/app
```

Set `MINIAPP_URL` in `.env` to the public HTTPS URL for the Mini App, for example:

```text
MINIAPP_URL=https://your-domain.example/app
```

Milestone 1 includes:

- Telegram Mini App `initData` validation on the backend
- `GET /api/config`
- `GET /api/menu/categories`
- `GET /api/menu/items`
- `GET /api/menu/items/{item_id}`
- React pages for Home, Categories, Item List, and Item Detail
- Bot `🍽 Open Menu` WebApp button when `MINIAPP_URL` is configured

Milestone 1 does not include cart, checkout, KHQR upload, rewards redemption, or repeat ordering inside the Mini App yet.

## Customer Flow

1. Customer sends `/start`.
2. Bot asks for language.
3. Bot opens the restaurant's main menu.
4. Customer browses categories and items.
5. Customer adds items to cart.
6. Customer chooses pickup or delivery.
7. Customer sends location/address, phone, and notes.
8. Order goes only to this restaurant's staff group.
9. Staff updates status with buttons.
10. Customer receives the status update.

## Admin Flow

Use:

```text
/admin
```

The dashboard manages only the restaurant configured by `.env`:

`/admin` and `/demo_reset` are hidden from the normal customer command menu. They are registered only for Telegram IDs listed in `ADMIN_IDS`.

- Menu Management
- Categories
- Photos
- Sold Out Items
- Loyalty Rewards
- KHQR Payment
- Promotions
- Orders
- Sales
- Restaurant Settings

Restaurant Settings supports:

- Name
- Logo file ID
- Phone
- Address
- Currency symbol
- Staff group ID
- Delivery on/off
- Pickup on/off
- KHQR image
- KHQR payment on/off
- Loyalty on/off
- Repeat orders on/off
- Loyalty earning rate, for example `$1.00 = 1 point`

Demo maintenance:

```text
/demo_reset
```

`/demo_reset` is admin-only. It clears orders, carts, and loyalty point balances for the current deployment restaurant, then recreates two sample customer profiles. It does **not** delete menu categories, menu items, translations, photos, KHQR image, restaurant settings, or admins.

## KHQR Payment Verification

The bot supports optional KHQR payment screenshot verification.

Admin setup:

1. Open `/admin`.
2. Open `Restaurant Settings`.
3. Upload/change `KHQR image`.
4. Turn `KHQR payment` on.

Customer flow:

1. Customer completes checkout details.
2. Bot asks for payment method:
   - Pay with KHQR
   - Pay cash on delivery / pickup
3. If KHQR is selected, the bot sends the restaurant KHQR image and total amount.
4. Customer uploads a payment screenshot.
5. The order is sent to the staff group with payment status `pending`.

Staff flow:

- `Confirm payment` marks `payment_status = paid`, stores who confirmed it, and notifies the customer.
- `Reject payment` marks `payment_status = rejected` and asks the customer to upload again or switch to cash.
- Normal order buttons remain available: Accept, Preparing, Ready, Delivered, Cancel.

Cash orders use:

- `payment_method = cash`
- `payment_status = unpaid`

## Creating A New Restaurant Bot

Recommended clean deployment:

1. Copy the project folder.
2. Delete `restaurant_bot/data/restaurant.db` in the new copy if you want a clean database.
3. Create a new Telegram bot token.
4. Edit `.env`:
   - `BOT_TOKEN`
   - `RESTAURANT_SLUG`
   - `RESTAURANT_NAME`
   - `RESTAURANT_PHONE`
   - `RESTAURANT_ADDRESS`
   - `STAFF_GROUP_ID`
   - `ADMIN_IDS`
5. Run `py -3.12 -m restaurant_bot.bot`.
6. Open `/admin` and add categories, menu items, item photos, KHQR, and settings.

If you keep an existing database and only change `RESTAURANT_SLUG`, startup creates a new deployment restaurant record and seeds the starter menu for it. Old restaurant data remains in the database but is not shown to customers because runtime queries use the deployment slug.

## Demo Script

Use this flow when showing the bot to a restaurant owner.

Before the demo:

1. Back up `restaurant_bot/data/restaurant.db`.
2. Start the bot.
3. Send `/admin` from an admin Telegram account.
4. Confirm the restaurant name, phone, address, staff group, pickup/delivery, KHQR, and loyalty settings.
5. Send `/demo_reset` to clear old demo orders, carts, and loyalty balances.

Customer demo:

1. Send `/start`.
2. Pick a language.
3. Open `View Menu`.
4. Open a category and view an item photo/description.
5. Add two items to cart.
6. Open `My Cart`, change quantity, then checkout.
7. Choose pickup or delivery.
8. Share phone number and add a short note.
9. Choose cash or KHQR.
10. For KHQR, upload a test screenshot.

Staff demo:

1. Open the staff group.
2. Show the order message with customer, items, total, payment status, and action buttons.
3. If KHQR was used, tap `Confirm payment`.
4. Tap `Accept`, `Preparing`, `Ready`, and `Delivered`.
5. Show the customer receiving automatic updates.
6. If loyalty is enabled, show the customer point balance after payment/completion.
7. Tap `Reorder last order` from the customer menu to show repeat ordering.

Admin demo:

1. Open `/admin`.
2. Toggle a menu item as sold out.
3. Show that the item remains visible but cannot be added.
4. Open `KHQR Payment` and show enable/upload/status.
5. Open `Loyalty Rewards` and show the editable earning rate.
6. Open `Restaurant Settings` and show branding/settings controls.

## Troubleshooting

Bot does not respond:

- Confirm `BOT_TOKEN` is correct in `.env`.
- Restart the bot after changing `.env`.
- Make sure only one copy of the same bot token is polling.

Admin cannot open `/admin`:

- Confirm the admin Telegram numeric ID is listed in `ADMIN_IDS`.
- Separate multiple IDs with commas and no spaces if possible.
- Restart the bot so startup can sync admins into the database.

Staff group does not receive orders:

- Add the bot to the staff group.
- Make sure the bot can post messages in the group.
- Confirm `STAFF_GROUP_ID` is the group ID, usually starting with `-100`.
- Update it in `/admin` -> `Restaurant Settings` if needed.

KHQR button does not appear:

- Open `/admin` -> `KHQR Payment`.
- Enable KHQR payment.
- Upload a KHQR image. If KHQR is enabled but the image is missing, customers will see a clear warning when they tap KHQR.

Orders fail at checkout:

- Make sure pickup or delivery is enabled in `Restaurant Settings`.
- Delivery orders need a shared location or typed address.
- Phone numbers must contain 8 to 15 digits.
- Empty carts cannot checkout.
- Sold out or disabled items are skipped from carts/orders.

Loyalty points do not show:

- Enable loyalty in `/admin` -> `Loyalty Rewards`.
- Set the earning rate, for example `1.00`.
- Points are awarded once when KHQR payment is confirmed or when a cash/unpaid order is marked delivered.

Database looks stale after editing `.env`:

- `RESTAURANT_SLUG` selects the active deployment restaurant.
- If you changed the slug, startup may create a new restaurant record.
- Existing data is preserved and hidden from customers unless it belongs to the active slug.

## Deployment Checklist For A New Restaurant

Use this checklist before handing the bot to a paying restaurant.

Technical setup:

- Create a fresh project copy for the restaurant.
- Create a Telegram bot with BotFather.
- Create the restaurant staff group.
- Add the bot to the staff group.
- Get the staff group ID.
- Fill `.env` with the new bot token, restaurant slug/name/contact details, staff group ID, and admin IDs.
- Install dependencies with `py -3.12 -m pip install -r requirements.txt`.
- Run `py -3.12 -m restaurant_bot.bot` once to initialize the database.

Restaurant configuration:

- Open `/admin`.
- Check restaurant name, phone, address, currency, pickup, delivery, and staff group.
- Upload logo if used.
- Upload KHQR image if KHQR payment is offered.
- Enable or disable KHQR payment.
- Enable or disable loyalty.
- Set loyalty earning rate.
- Add real categories, menu items, translations, prices, and photos.
- Mark unavailable items as sold out instead of deleting them.

Acceptance test:

- Run `/demo_reset`.
- Place one cash order.
- Place one KHQR order and confirm payment.
- Verify staff group receives both orders.
- Verify customer receives status updates.
- Mark one order delivered and confirm loyalty points if enabled.
- Test `Reorder last order`.
- Test sold out item behavior.
- Back up the final `restaurant.db`.

## Final QA Checklist

Run this before a client demo or live handoff.

Configuration:

- `.env` has the correct `BOT_TOKEN`.
- `ADMIN_IDS` contains the owner/admin Telegram IDs.
- `STAFF_GROUP_ID` points to the restaurant staff group.
- `RESTAURANT_SLUG`, name, phone, address, currency, and default language are correct.
- Bot is added to the staff group and can send messages.

Customer flow:

- `/start` opens language selection.
- Main menu opens after language selection.
- Categories show correctly.
- Menu items show price, description, photo if present, and sold out status.
- Available items can be added to cart.
- Sold out or disabled items cannot be added.
- Cart quantity increase, decrease, remove, clear, and checkout work.
- Pickup checkout works.
- Delivery checkout accepts shared location or typed address.
- Invalid phone numbers are rejected.
- Cash order reaches the staff group.
- KHQR order shows the payment image and asks for screenshot when enabled.
- KHQR missing-image warning is clear when enabled without an uploaded image.
- Customer receives order summary.
- Customer can reorder the last delivered order.

Staff flow:

- Staff group receives full order details.
- Payment confirm/reject buttons work.
- Accept, Preparing, Ready, Delivered, and Cancel buttons work.
- Customer receives automatic status updates.
- Loyalty points appear after paid/completed orders when loyalty is enabled.

Admin flow:

- `/admin` opens only for configured admins.
- Menu item add/edit/photo flows work.
- Categories can be added, edited, disabled, and reordered.
- Sold out toggle works.
- KHQR Payment menu can enable/disable and upload/change the image.
- Loyalty Rewards can enable/disable and edit the earning rate.
- Restaurant Settings edits branding, contact details, currency, staff group, pickup, delivery, and repeat orders.
- `/demo_reset` clears orders/carts/loyalty balances without deleting menu/settings/photos.

Data safety:

- Back up `restaurant_bot/data/restaurant.db` before the demo.
- Confirm menu/categories/photos still exist after `/demo_reset`.
- Confirm today orders and sales summary are clean after `/demo_reset`.
- Keep a post-setup backup for the client.

## Backup Instructions

The main database file is:

```text
restaurant_bot/data/restaurant.db
```

Manual PowerShell backup:

```powershell
Copy-Item -LiteralPath "restaurant_bot\data\restaurant.db" -Destination "restaurant_bot\data\restaurant.backup.db"
```

Timestamped PowerShell backup:

```powershell
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
Copy-Item -LiteralPath "restaurant_bot\data\restaurant.db" -Destination "restaurant_bot\data\restaurant-$stamp.db"
```

Recommended backup moments:

- Before `/demo_reset`.
- Before editing menus in bulk.
- Before deploying updates.
- After final restaurant setup.
- Daily for live restaurants.

Restore a backup by stopping the bot, copying the backup file back to `restaurant_bot/data/restaurant.db`, and starting the bot again.

## Migration Notes

Existing Sweet Chilli data is preserved:

- Orders
- Carts
- Menu categories
- Menu items
- Translations
- Item photos
- Admin ownership

The migration adds restaurant scoping but no marketplace UI.

## Schema Highlights

- `restaurants` stores deployment restaurant branding and settings.
- `restaurant_admins` controls who can manage the deployment restaurant.
- `menu_categories.restaurant_id` scopes categories.
- `menu_items.restaurant_id` scopes menu items.
- `carts.restaurant_id` scopes carts.
- `orders.restaurant_id` scopes orders.
- `orders.payment_method` stores `cash` or `khqr`.
- `orders.payment_status` stores `unpaid`, `pending`, `paid`, or `rejected`.
- `orders.payment_screenshot_file_id` stores the Telegram screenshot file ID.
- `orders.payment_confirmed_by` and `orders.payment_confirmed_at` store staff verification details.
- `users.preferred_restaurant_id` is retained internally for compatibility, but customers cannot switch restaurants.

Prices are stored as cents.
