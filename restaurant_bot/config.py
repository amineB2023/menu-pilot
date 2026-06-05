from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv() -> bool:
        return False


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "restaurant.db"


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: set[int]
    staff_group_id: int | None
    restaurant_name: str
    restaurant_phone: str
    restaurant_address: str
    miniapp_url: str | None


def _parse_admin_ids(raw: str) -> set[int]:
    admin_ids: set[int] = set()
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            admin_ids.add(int(item))
        except ValueError:
            raise ValueError(f"Invalid ADMIN_IDS value: {item!r}") from None
    return admin_ids


def load_settings() -> Settings:
    load_dotenv()

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError("BOT_TOKEN is required. Copy .env.example to .env and set your token.")

    staff_group_raw = os.getenv("STAFF_GROUP_ID", "").strip()
    staff_group_id = int(staff_group_raw) if staff_group_raw else None

    return Settings(
        bot_token=bot_token,
        admin_ids=_parse_admin_ids(os.getenv("ADMIN_IDS", "")),
        staff_group_id=staff_group_id,
        restaurant_name=os.getenv("RESTAURANT_NAME", "Simple Restaurant").strip(),
        restaurant_phone=os.getenv("RESTAURANT_PHONE", "+855 12 345 678").strip(),
        restaurant_address=os.getenv("RESTAURANT_ADDRESS", "Phnom Penh, Cambodia").strip(),
        miniapp_url=os.getenv("MINIAPP_URL", "").strip() or None,
    )
