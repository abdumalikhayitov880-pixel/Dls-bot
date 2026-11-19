import asyncio
import json
import logging
import sqlite3
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InputMediaPhoto,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

TOKEN = "9236358410:AAHRU7nfXlg25PxSkPKoe7pvmjRhBmhO454"
ADMIN_ID = 1130978177

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()

# --- BAZA BILAN ISHLASH ---
conn = sqlite3.connect("dls_ads.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    max_price INTEGER DEFAULT 100000,
    search_offset INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS ads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id INTEGER,
    seller_username TEXT,
    photos_json TEXT,
    price INTEGER,
    description TEXT,
    phone TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

PRICE_LIMITS = [
    20000,
    30000,
    50000,
    100000,
    200000,
    500000,
    1000000,
    2000000,
]


# --- FSM HOLATLAR ---
class PostAdState(StatesGroup):
    waiting_photos = State()
    waiting_price = State()
    waiting_description = State()
    waiting_phone = State()


class CustomMaxPriceState(StatesGroup):
    waiting_max_price = State()


class ManageAdState(StatesGroup):
    choosing_ad = State()
    choosing_action = State()


class AdminBroadcastState(StatesGroup):
    waiting_text = State()


# --- YORDAMCHI FUNKSIYALAR ---
def format_price(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " so'm"


def ensure_user(user_id: int, username: str | None, full_name: str):
    uname = username or "Mavjud emas"
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users (user_id, username, full_name, max_price, search_offset) VALUES (?, ?, ?, ?, 0)",
            (user_id, uname, full_name, 100000),
        )
        conn.commit()
    else:
        cursor.execute(
            "UPDATE users SET username = ?, full_name = ? WHERE user_id = ?",
            (uname, full_name, user_id),
        )
        conn.commit()


def get_user_max_price(user_id: int) -> int:
    cursor.execute("SELECT max_price FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    return row[0] if row and row[0] else 100000


def get_user_offset(user_id: int) -> int:
    cursor.execute("SELECT search_offset FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    return row[0] if row and row[0] is not None else 0


def set_user_offset(user_id: int, offset: int):
    cursor.execute("UPDATE users SET search_offset = ? WHERE user_id = ?", (max(0, offset), user_id))
    conn.commit()


def get_main_menu(user_id: int) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="➕ Akkount joylash"), KeyboardButton(text="🔍 Akkount qidirish")],
        [KeyboardButton(text="💰 Summani o'zgartirish"), KeyboardButton(text="📂 Mening e'lonlarim")],
    ]
    if user_id == ADMIN_ID:
        rows.append([KeyboardButton(text="🛠 Admin panel")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def get_photos_done_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Rasmlar tayyor")],
            [KeyboardButton(text="🏠 Asosiy menyu")],
        ],
        resize_keyboard=True,
    )


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🏠 Asosiy menyu")]],
        resize_keyboard=True,
    )


def get_price_limits_keyboard() -> ReplyKeyboardMarkup:
    rows = []
    row = []
    for p in PRICE_LIMITS:
        row.append(KeyboardButton(text=format_price(p)))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([KeyboardButton(text="✍️ Qo'lda summa kiritish")])
    rows.append([KeyboardButton(text="🔍 Akkount qidirish"), KeyboardButton(text="🏠 Asosiy menyu")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def get_search_results_keyboard(has_more: bool) -> ReplyKeyboardMarkup:
    rows = []
    if has_more:
        rows.append([KeyboardButton(text="➡️ Keyingi akkountlar")])
    rows.append([KeyboardButton(text="💰 Summani o'zgartirish"), KeyboardButton(text="🏠 Asosiy menyu")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def get_admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="📋 Oxirgi e'lonlar")],
            [KeyboardButton(text="📢 Xabar yuborish"), KeyboardButton(text="🏠 Asosiy menyu")],
        ],
        resize_keyboard=True,
    )


async def send_ad_card(chat_id: int, ad_row: tuple):
    ad_id, seller_id, seller_uname, photos_json, price, desc, phone, is_active, created_at = ad_row
    photos = json.loads(photos_json) if photos_json else []
    uname_str = f"@{seller_uname}" if seller_uname and seller_uname != "Mavjud emas" else "Username yo'q"
    status_str = "🟢 Faol" if is_active else "🔴 Yopilgan"

    caption = (
        f"⚽️ <b>DLS AKKOUNT #{ad_id}</b> ({status_str})\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💵 <b>Narxi:</b> {format_price(price)}\n"
        f"📝 <b>Izoh:</b> {desc}\n"
        f"📞 <b>Telefon:</b> <code>{phone}</code>\n"
        f"👤 <b>Sotuvchi:</b> {uname_str} (ID: <code>{seller_id}</code>)"
    )

    if len(photos) == 1:
        await bot.send_photo(
            chat_id=chat_id,
            photo=photos[0],
            caption=caption,
            parse_mode="HTML",
        )
    elif len(photos) > 1:
        media = [InputMediaPhoto(media=pid) for pid in photos]
        media[0].caption = caption
        media[0].parse_mode = "HTML"
        await bot.send_media_group(chat_id=chat_id, media=media)
    else:
        await bot.send_message(
            chat_id=chat_id,
            text=caption,
            parse_mode="HTML",
        )


async def show_search_batch(chat_id: int, user_id: int, offset: int):
    max_price = get_user_max_price(user_id)
    cursor.execute(
        """
        SELECT id, seller_id, seller_username, photos_json, price, description, phone, is_active, created_at
        FROM ads
        WHERE is_active = 1 AND price <= ?
        ORDER BY id DESC
        LIMIT 3 OFFSET ?
        """,
        (max_price, offset),
    )
    rows = cursor.fetchall()

    if not rows:
        if offset == 0:
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"😔 Hozircha <b>{format_price(max_price)}</b> gacha bo'lgan faol DLS akkauntlar topilmadi.\n"
                    f"Pastdagi <b>«💰 Summani o'zgartirish»</b> tugmasi orqali limitni oshirishingiz mumkin."
                ),
                reply_markup=get_main_menu(user_id),
                parse_mode="HTML",
            )
        else:
            set_user_offset(user_id, 0)
            await bot.send_message(
                chat_id=chat_id,
                text="✅ Ushbu summa chegarasidagi boshqa akkountlar qolmadi.",
                reply_markup=get_main_menu(user_id),
            )
        return

    new_offset = offset + len(rows)
    set_user_offset(user_id, new_offset)

    cursor.execute(
        "SELECT COUNT(*) FROM ads WHERE is_active = 1 AND price <= ? AND id < ?",
        (max_price, rows[-1][0]),
    )
    has_more = cursor.fetchone()[0] > 0

    await bot.send_message(
        chat_id=chat_id,
        text=f"🔎 <b>Qidiruv natijalari</b> (Max: <b>{format_price(max_price)}</b>) — {offset + 1}..{offset + len(rows)}:",
        parse_mode="HTML",
    )

    for ad_row in rows:
        await send_ad_card(chat_id, ad_row)

    await bot.send_message(
        chat_id=chat_id,
        text="👇 Kerakli tugmani bosing:",
        reply_markup=get_search_results_keyboard(has_more),
)
          @router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    ensure_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    set_user_offset(message.from_user.id, 0)
    max_p = get_user_max_price(message.from_user.id)

    await message.answer(
        f"Assalomu alaykum, <b>{message.from_user.first_name}</b>! 👋\n\n"
        f"Bu bot orqali <b>DLS (Dream League Soccer)</b> akkauntlarini sotishingiz yoki byudjetingizga mosini topishingiz mumkin.\n"
        f"Joriy maksimal qidiruv summangiz: <b>{format_price(max_p)}</b>",
        reply_markup=get_main_menu(message.from_user.id),
        parse_mode="HTML",
    )


@router.message(F.text == "🏠 Asosiy menyu")
async def back_to_main(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyu:", reply_markup=get_main_menu(message.from_user.id))


# --- AKKOUNT JOYLASH ---
@router.message(F.text == "➕ Akkount joylash")
async def start_post_ad(message: Message, state: FSMContext):
    ensure_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    await state.clear()
    await state.update_data(photos=[])
    await state.set_state(PostAdState.waiting_photos)
    await message.answer(
        "📸 Akkountingiz <b>rasmlarini</b> yuboring (tarkib, reyting, coin/gem ko'ringan rasmlar).\n"
        "Bir nechta rasm tashlashingiz mumkin. Tugatgach pastdagi <b>«✅ Rasmlar tayyor»</b> tugmasini bosing.",
        reply_markup=get_photos_done_keyboard(),
        parse_mode="HTML",
    )


@router.message(PostAdState.waiting_photos, F.photo)
async def collect_ad_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    photos: list = data.get("photos", [])
    if len(photos) >= 10:
        await message.answer("⚠️ Bitta e'longa eng ko'pi bilan 10 ta rasm qo'shish mumkin. «✅ Rasmlar tayyor» tugmasini bosing.")
        return

    file_id = message.photo[-1].file_id
    photos.append(file_id)
    await state.update_data(photos=photos)
    await message.answer(f"✅ {len(photos)}-rasm qabul qilindi. Yana rasm tashlang yoki «✅ Rasmlar tayyor» tugmasini bosing.")


@router.message(PostAdState.waiting_photos, F.text == "✅ Rasmlar tayyor")
async def finish_ad_photos(message: Message, state: FSMContext):
    data = await state.get_data()
    photos: list = data.get("photos", [])
    if not photos:
        await message.answer("❌ Kamida 1 ta rasm yuborishingiz kerak!")
        return

    await state.set_state(PostAdState.waiting_price)
    await message.answer(
        "💵 Qancha so'mga sotmoqchisiz? (Faqat raqamda kiriting, masalan: <code>75000</code>):",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML",
    )


@router.message(PostAdState.waiting_photos)
async def invalid_photo_input(message: Message):
    await message.answer("Iltimos, akkount rasmini yuboring yoki «✅ Rasmlar tayyor» tugmasini bosing.")


@router.message(PostAdState.waiting_price)
async def collect_ad_price(message: Message, state: FSMContext):
    cleaned = (message.text or "").replace(" ", "").replace(",", "").strip()
    if not cleaned.isdigit():
        await message.answer("❌ Iltimos, narxni faqat raqamda kiriting (masalan: <code>50000</code>):", parse_mode="HTML")
        return

    price = int(cleaned)
    if price < 1000 or price > 100_000_000:
        await message.answer("❌ Narx 1 000 so'mdan 100 000 000 so'mgacha bo'lishi kerak. Qaytadan kiriting:")
        return

    await state.update_data(price=price)
    await state.set_state(PostAdState.waiting_description)
    await message.answer(
        "📝 Izoh yozing akkountingizga (masalan: 88+ tarkib, max o'yinchilar, login/parol tayyor):",
        reply_markup=get_cancel_keyboard(),
    )


@router.message(PostAdState.waiting_description)
async def collect_ad_description(message: Message, state: FSMContext):
    desc = (message.text or "").strip()
    if len(desc) < 3:
        await message.answer("❌ Izoh juda qisqa. Akkount haqida kichik ma'lumot yozing:")
        return

    await state.update_data(description=desc[:500])
    await state.set_state(PostAdState.waiting_phone)
    await message.answer(
        "📞 Telefon raqamingizni qoldiring (masalan: <code>+998901234567</code>):",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML",
    )


@router.message(PostAdState.waiting_phone)
async def collect_ad_phone(message: Message, state: FSMContext):
    phone = (message.text or "").strip()
    digits_only = "".join(ch for ch in phone if ch.isdigit())
    if len(digits_only) < 9:
        await message.answer("❌ Telefon raqam noto'g'ri kiritildi. Qaytadan kiriting:")
        return

    data = await state.get_data()
    photos = data.get("photos", [])
    price = data.get("price")
    desc = data.get("description")

    seller_id = message.from_user.id
    seller_uname = message.from_user.username or "Mavjud emas"

    cursor.execute(
        """
        INSERT INTO ads (seller_id, seller_username, photos_json, price, description, phone, is_active)
        VALUES (?, ?, ?, ?, ?, ?, 1)
        """,
        (seller_id, seller_uname, json.dumps(photos), price, desc, phone),
    )
    conn.commit()
    ad_id = cursor.lastrowid
    await state.clear()

    await message.answer(
        f"✅ Tabriklaymiz! <b>#{ad_id}</b>-raqamli akkount e'loningiz reklamaga chiqarildi!",
        reply_markup=get_main_menu(seller_id),
        parse_mode="HTML",
    )

    cursor.execute(
        "SELECT id, seller_id, seller_username, photos_json, price, description, phone, is_active, created_at FROM ads WHERE id = ?",
        (ad_id,),
    )
    created_ad = cursor.fetchone()
    if created_ad:
        await send_ad_card(seller_id, created_ad)


# --- SUMMA LIMITI VA QIDIRUV ---
@router.message(F.text == "💰 Summani o'zgartirish")
async def ask_max_price(message: Message, state: FSMContext):
    await state.clear()
    ensure_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    current = get_user_max_price(message.from_user.id)
    await message.answer(
        f"💳 <b>Maximum qancha summalik akkountlar kerak?</b>\n"
        f"Hozirgi tanlangan summa: <b>{format_price(current)}</b>\n\n"
        f"Pastdagi tugmalardan birini tanlang yoki <b>«✍️ Qo'lda summa kiritish»</b> ni bosing:",
        reply_markup=get_price_limits_keyboard(),
        parse_mode="HTML",
    )


@router.message(F.text == "✍️ Qo'lda summa kiritish")
async def custom_max_price_start(message: Message, state: FSMContext):
    await state.set_state(CustomMaxPriceState.waiting_max_price)
    await message.answer(
        "✍️ Maximum qancha so'mlik akkountlar kerakligini raqamda yozing (masalan: <code>150000</code>):",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML",
    )


@router.message(CustomMaxPriceState.waiting_max_price)
async def custom_max_price_save(message: Message, state: FSMContext):
    cleaned = (message.text or "").replace(" ", "").replace(",", "").strip()
    if not cleaned.isdigit():
        await message.answer("❌ Iltimos, faqat raqam kiriting (masalan: <code>150000</code>):", parse_mode="HTML")
        return

    new_max = int(cleaned)
    if new_max < 1000 or new_max > 100_000_000:
        await message.answer("❌ Summa 1 000 so'mdan 100 000 000 so'mgacha bo'lishi kerak. Qaytadan kiriting:")
        return

    user_id = message.from_user.id
    ensure_user(user_id, message.from_user.username, message.from_user.full_name)
    cursor.execute("UPDATE users SET max_price = ?, search_offset = 0 WHERE user_id = ?", (new_max, user_id))
    conn.commit()
    await state.clear()

    await message.answer(
        f"✅ Maksimal summa <b>{format_price(new_max)}</b> qilib saqlandi!\n"
        f"Endi <b>«🔍 Akkount qidirish»</b> tugmasini bosib e'lonlarni ko'rishingiz mumkin.",
        reply_markup=get_main_menu(user_id),
        parse_mode="HTML",
    )


@router.message(F.text.in_([format_price(p) for p in PRICE_LIMITS]))
async def set_preset_max_price(message: Message, state: FSMContext):
    await state.clear()
    digits = "".join(ch for ch in (message.text or "") if ch.isdigit())
    if not digits.isdigit():
        return

    new_max = int(digits)
    user_id = message.from_user.id
    ensure_user(user_id, message.from_user.username, message.from_user.full_name)
    cursor.execute("UPDATE users SET max_price = ?, search_offset = 0 WHERE user_id = ?", (new_max, user_id))
    conn.commit()

    await message.answer(
        f"✅ Maksimal summa <b>{format_price(new_max)}</b> qilib saqlandi!\n"
        f"Endi <b>«🔍 Akkount qidirish»</b> tugmasini bosib e'lonlarni ko'rishingiz mumkin.",
        reply_markup=get_main_menu(user_id),
        parse_mode="HTML",
    )


@router.message(F.text == "🔍 Akkount qidirish")
async def search_ads_msg(message: Message, state: FSMContext):
    await state.clear()
    ensure_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    set_user_offset(message.from_user.id, 0)
    await show_search_batch(message.chat.id, message.from_user.id, offset=0)


@router.message(F.text == "➡️ Keyingi akkountlar")
async def search_next_ads_msg(message: Message, state: FSMContext):
    await state.clear()
    ensure_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    current_offset = get_user_offset(message.from_user.id)
    await show_search_batch(message.chat.id, message.from_user.id, offset=current_offset)
# --- MENING E'LONLARIM ---
@router.message(F.text == "📂 Mening e'lonlarim")
async def my_ads(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    cursor.execute(
        "SELECT id, price, description, is_active FROM ads WHERE seller_id = ? ORDER BY id DESC LIMIT 15",
        (user_id,),
    )
    rows = cursor.fetchall()

    if not rows:
        await message.answer("Sizda hali joylangan akkount e'lonlari yo'q.", reply_markup=get_main_menu(user_id))
        return

    lines = ["📂 <b>Sizning e'lonlaringiz:</b>\n"]
    kb_rows = []
    for ad_id, price, desc, is_active in rows:
        st = "🟢 Faol" if is_active else "🔴 Yopilgan"
        lines.append(f"• <b>#{ad_id}</b> | {st} | <b>{format_price(price)}</b> — {desc}")
        kb_rows.append([KeyboardButton(text=f"#{ad_id}")])
    kb_rows.append([KeyboardButton(text="🏠 Asosiy menyu")])

    await state.set_state(ManageAdState.choosing_ad)
    await message.answer(
        "\n".join(lines) + "\n\nBoshqarish uchun pastdan e'lon raqamini tanlang:",
        reply_markup=ReplyKeyboardMarkup(keyboard=kb_rows, resize_keyboard=True),
        parse_mode="HTML",
    )


@router.message(ManageAdState.choosing_ad)
async def choose_my_ad(message: Message, state: FSMContext):
    txt = (message.text or "").strip().lstrip("#")
    if not txt.isdigit():
        await message.answer("Iltimos, pastdagi tugmalardan e'lon raqamini tanlang yoki «🏠 Asosiy menyu» ni bosing.")
        return

    ad_id = int(txt)
    user_id = message.from_user.id
    cursor.execute("SELECT id, price, description, is_active FROM ads WHERE id = ? AND seller_id = ?", (ad_id, user_id))
    row = cursor.fetchone()
    if not row:
        await message.answer("❌ Bunday e'lon topilmadi. Qaytadan tanlang:")
        return

    await state.update_data(manage_ad_id=ad_id)
    await state.set_state(ManageAdState.choosing_action)
    st = "🟢 Faol" if row[3] else "🔴 Yopilgan"
    toggle_btn = "🔴 Yopish" if row[3] else "🟢 Faollashtirish"

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=toggle_btn), KeyboardButton(text="🗑 O'chirish")],
            [KeyboardButton(text="🏠 Asosiy menyu")],
        ],
        resize_keyboard=True,
    )
    await message.answer(
        f"📌 <b>#{row[0]}</b> ({st})\n💵 Narx: <b>{format_price(row[1])}</b>\n📝 {row[2]}\n\nAmalni tanlang:",
        reply_markup=kb,
        parse_mode="HTML",
    )


@router.message(ManageAdState.choosing_action, F.text.in_(["🔴 Yopish", "🟢 Faollashtirish"]))
async def toggle_my_ad_reply(message: Message, state: FSMContext):
    data = await state.get_data()
    ad_id = data.get("manage_ad_id")
    user_id = message.from_user.id
    if not ad_id:
        await state.clear()
        await message.answer("Asosiy menyu:", reply_markup=get_main_menu(user_id))
        return

    cursor.execute("SELECT is_active FROM ads WHERE id = ? AND seller_id = ?", (ad_id, user_id))
    row = cursor.fetchone()
    if row:
        new_st = 0 if row[0] == 1 else 1
        cursor.execute("UPDATE ads SET is_active = ? WHERE id = ?", (new_st, ad_id))
        conn.commit()
        label = "🟢 Faol" if new_st else "🔴 Yopilgan"
        await message.answer(f"✅ #{ad_id}-e'lon holati o'zgardi: {label}", reply_markup=get_main_menu(user_id))
    await state.clear()


@router.message(ManageAdState.choosing_action, F.text == "🗑 O'chirish")
async def delete_my_ad_reply(message: Message, state: FSMContext):
    data = await state.get_data()
    ad_id = data.get("manage_ad_id")
    user_id = message.from_user.id
    if ad_id:
        cursor.execute("DELETE FROM ads WHERE id = ? AND seller_id = ?", (ad_id, user_id))
        conn.commit()
        await message.answer(f"🗑 #{ad_id}-e'lon o'chirildi.", reply_markup=get_main_menu(user_id))
    await state.clear()


# --- ADMIN PANEL ---
@router.message(F.text == "🛠 Admin panel")
async def admin_panel(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await message.answer("🛠 <b>Admin panel:</b>", reply_markup=get_admin_menu(), parse_mode="HTML")


@router.message(F.text == "📊 Statistika")
async def admin_stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    cursor.execute("SELECT COUNT(*) FROM users")
    users_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM ads")
    total_ads = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM ads WHERE is_active = 1")
    active_ads = cursor.fetchone()[0]

    await message.answer(
        f"📊 <b>Bot statistikasi:</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{users_count}</b> ta\n"
        f"📢 Jami e'lonlar: <b>{total_ads}</b> ta\n"
        f"🟢 Faol e'lonlar: <b>{active_ads}</b> ta",
        parse_mode="HTML",
    )


@router.message(F.text == "📋 Oxirgi e'lonlar")
async def admin_recent_ads(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    cursor.execute(
        "SELECT id, seller_id, price, description, is_active FROM ads ORDER BY id DESC LIMIT 10"
    )
    rows = cursor.fetchall()
    if not rows:
        await message.answer("Hozircha e'lonlar yo'q.")
        return

    text_lines = ["📋 <b>Oxirgi 10 ta e'lon:</b>\n"]
    for ad_id, seller_id, price, desc, is_active in rows:
        st = "🟢" if is_active else "🔴"
        text_lines.append(f"{st} <b>#{ad_id}</b> | ID: <code>{seller_id}</code> | <b>{format_price(price)}</b>\n{desc}\n")

    await message.answer("\n".join(text_lines), parse_mode="HTML")


@router.message(F.text == "📢 Xabar yuborish")
async def admin_broadcast_start(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminBroadcastState.waiting_text)
    await message.answer(
        "Barcha foydalanuvchilarga yuboriladigan xabar matnini yozing:",
        reply_markup=get_cancel_keyboard(),
    )


@router.message(AdminBroadcastState.waiting_text)
async def admin_broadcast_send(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    text_to_send = message.text or ""
    await state.clear()

    cursor.execute("SELECT user_id FROM users")
    user_ids = [r[0] for r in cursor.fetchall()]

    sent_ok = 0
    for uid in user_ids:
        try:
            await bot.send_message(uid, text_to_send)
            sent_ok += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass

    await message.answer(
        f"✅ Xabar yuborildi: <b>{sent_ok}</b> / {len(user_ids)} ta foydalanuvchiga.",
        reply_markup=get_admin_menu(),
        parse_mode="HTML",
    )


async def main():
    dp.include_router(router)
    try:
        await bot.delete_webhook(drop_pending_updates=True, request_timeout=30)
    except Exception as e:
        logging.warning(f"Webhookni tozalashda ogohlantirish: {e}")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
