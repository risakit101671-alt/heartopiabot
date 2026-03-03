import asyncio
import logging
import random
from typing import Optional, Dict, List
from aiogram.filters import StateFilter
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from typing import Union
import asyncpg
import os


API_TOKEN = '8394242496:AAGuBC6Lz5YkHfyRHvIlHGiLhxecjMTYlrQ'         
ADMIN_CHAT_ID = 5211249049 
SUPPORT_LINK = 'https://t.me/heart2heartopiachannel/11'  # замените на реальную ссылку на пост         
CHANNEL_LINK = 'https://t.me/heart2heartopiachannel'
CHAT_LINK = 'https://t.me/heartopia_girls'  # замените на реальную ссылку на ваш чат
DB_CONFIG = {
    'user': os.getenv('DB_USER', 'bothost_db_e613db7d7af0'),
    'password': os.getenv('DB_PASSWORD', 'ewVm6ihLRyY--KD1TUJj-SQfsdjhQj0JyyEmbT3-OIY'),
    'database': os.getenv('DB_NAME', 'bothost_db_e613db7d7af0'),
    'host': os.getenv('DB_HOST', 'node1.pghost.ru'),
    'port': os.getenv('DB_PORT', '32788'),
    'server_settings': {'client_encoding': 'UTF8'},
}
logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

ALL_BADGES = [
    ('shining', 'искорка'),
    ('shining', 'пинки пай'),
    ('shining', 'эпплджек'),
    ('shining', 'рарити'),
    ('shining', 'флаттершай'),
    ('shining', 'радуга'),
    ('shining', 'спайк'),
    ('nebula', 'искорка'),
    ('nebula', 'пинки пай'),
    ('nebula', 'эпплджек'),
    ('nebula', 'рарити'),
    ('nebula', 'флаттершай'),
    ('nebula', 'радуга'),
    ('nebula', 'спайк'),
    ('rainbow_flower', 'искорка'),
    ('rainbow_flower', 'пинки пай'),
    ('rainbow_flower', 'эпплджек'),
    ('rainbow_flower', 'рарити'),
    ('rainbow_flower', 'флаттершай'),
    ('rainbow_flower', 'радуга'),
    ('rainbow_flower', 'спайк')
]


class Database:
    def __init__(self, config):
        self.config = config
        self.pool = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(**self.config)
    # Принудительно устанавливаем кодировку клиента UTF-8 для всех соединений
        async with self.pool.acquire() as conn:
            await conn.execute("SET client_encoding TO 'UTF8'")
    logging.info("Кодировка клиента БД принудительно установлена в UTF-8")
    async def close(self):
        await self.pool.close()

    async def register_user(self, user_id: int, telegram_username: str, username: str,
                            uid: str, server: str, chat_id: int, notes: str = ''):
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO users (user_id, telegram_username, username, uid, server, chat_id, notes)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (user_id) DO UPDATE SET
                    telegram_username = EXCLUDED.telegram_username,
                    username = EXCLUDED.username,
                    uid = EXCLUDED.uid,
                    server = EXCLUDED.server,
                    chat_id = EXCLUDED.chat_id,
                    notes = EXCLUDED.notes,
                    updated_at = CURRENT_TIMESTAMP
            ''', user_id, telegram_username, username, uid, server, chat_id, notes)
    async def get_user_duplicates_list(self, user_id: int) -> List[Dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT ub.badge_id, ub.quantity, b.collection, b.character_name
                FROM user_badges ub
                JOIN badges b ON ub.badge_id = b.badge_id
                WHERE ub.user_id = $1 AND ub.quantity > 1
            ''', user_id)
            return [dict(r) for r in rows]

    async def update_telegram_username(self, user_id: int, new_username: str):
        async with self.pool.acquire() as conn:
            await conn.execute('UPDATE users SET telegram_username = $1 WHERE user_id = $2', new_username, user_id)

    async def get_user(self, user_id: int) -> Optional[Dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT * FROM users WHERE user_id = $1', user_id)
            return dict(row) if row else None

    async def user_exists(self, user_id: int) -> bool:
        async with self.pool.acquire() as conn:
            return await conn.fetchval('SELECT EXISTS(SELECT 1 FROM users WHERE user_id = $1)', user_id)

    async def update_profile_photo(self, user_id: int, file_id: str):
        async with self.pool.acquire() as conn:
            await conn.execute('UPDATE users SET profile_photo = $1 WHERE user_id = $2', file_id, user_id)

    async def delete_profile_photo(self, user_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute('UPDATE users SET profile_photo = NULL WHERE user_id = $1', user_id)

    # ---------- Значки (справочник) ----------
    async def get_badge_id(self, collection: str, character: str) -> Optional[int]:
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
            'SELECT badge_id FROM badges WHERE collection = $1 AND character_name = $2',
            collection, character.lower()
        )

    async def get_badge_by_id(self, badge_id: int) -> Optional[Dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT * FROM badges WHERE badge_id = $1', badge_id)
            return dict(row) if row else None
    # ---------- Инвентарь ----------
    async def add_or_update_user_badge(self, user_id: int, badge_id: int, quantity: int, trade_notes: str = ''):
        try:
            async with self.pool.acquire() as conn:
                await conn.execute('''
                    INSERT INTO user_badges (user_id, badge_id, quantity, trade_notes)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (user_id, badge_id) DO UPDATE SET
                        quantity = EXCLUDED.quantity,
                        trade_notes = EXCLUDED.trade_notes,
                        updated_at = CURRENT_TIMESTAMP
                ''', user_id, badge_id, quantity, trade_notes)
            logging.info(f"БД: запись для user_id={user_id}, badge_id={badge_id} обновлена (quantity={quantity})")
        except Exception as e:
            logging.error(f"БД ошибка в add_or_update_user_badge: {e}")
            raise



    async def get_user_badges(self, user_id: int, only_duplicates: bool = False) -> List[Dict]:
        async with self.pool.acquire() as conn:
            query = '''
                SELECT ub.*, b.collection, b.character_name
                FROM user_badges ub
                JOIN badges b ON ub.badge_id = b.badge_id
                WHERE ub.user_id = $1
            '''
            if only_duplicates:
                query += ' AND ub.quantity > 1'
            rows = await conn.fetch(query, user_id)
            return [dict(r) for r in rows]

    async def decrease_duplicate(self, user_id: int, badge_id: int, amount: int = 1):
        async with self.pool.acquire() as conn:
            await conn.execute('''
                UPDATE user_badges SET quantity = quantity - $1
                WHERE user_id = $2 AND badge_id = $3 AND quantity >= $1
            ''', amount, user_id, badge_id)
    # ---------- Вишлист ----------
    async def add_to_wishlist(self, user_id: int, badge_id: int, priority: int = 3):
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO wishlist (user_id, badge_id, priority)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, badge_id) DO UPDATE SET priority = EXCLUDED.priority
            ''', user_id, badge_id, priority)

    async def remove_from_wishlist(self, user_id: int, badge_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute('DELETE FROM wishlist WHERE user_id = $1 AND badge_id = $2', user_id, badge_id)

    async def get_wishlist(self, user_id: int) -> List[Dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT w.*, b.collection, b.character_name
                FROM wishlist w
                JOIN badges b ON w.badge_id = b.badge_id
                WHERE w.user_id = $1
                ORDER BY b.collection, b.sort_order
            ''', user_id)
            result = []
            for r in rows:
                d = dict(r)
                if isinstance(d.get('character_name'), bytes):
                    d['character_name'] = d['character_name'].decode('utf-8')
                if isinstance(d.get('collection'), bytes):
                    d['collection'] = d['collection'].decode('utf-8')
                result.append(d)
            return result

    async def get_wishlist_progress(self, user_id: int) -> Dict:
        async with self.pool.acquire() as conn:
            count = await conn.fetchval('SELECT COUNT(*) FROM wishlist WHERE user_id = $1', user_id)
            return {'filled': count or 0, 'total': 21, 'percentage': (count or 0) * 100 // 21}

    async def get_available_for_wishlist(self, user_id: int) -> List[Dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT collection, character_name, badge_id FROM badges
                    WHERE (collection, character_name) NOT IN (
                    SELECT b.collection, b.character_name
                    FROM wishlist w
                    JOIN badges b ON w.badge_id = b.badge_id
                    WHERE w.user_id = $1
                )
                ORDER BY collection, sort_order
            ''', user_id)
            return [dict(r) for r in rows]
  # ---------- Поиск анкет ----------
    async def find_random_profile(self, user_id: int, excluded_ids: Optional[List[int]] = None) -> Optional[Dict]:
        if excluded_ids is None:
            excluded_ids = []
        async with self.pool.acquire() as conn:
            user_server = await conn.fetchval('SELECT server FROM users WHERE user_id = $1', user_id)
            if not user_server:
                logging.warning(f"User {user_id} has no server")
                return None

        # Сначала ищем по вишлисту, исключая уже просмотренные
            rows = await conn.fetch('''
                SELECT DISTINCT u.user_id, u.telegram_username, u.username, u.uid, u.server, u.notes, u.profile_photo
                FROM users u
                JOIN user_badges ub ON u.user_id = ub.user_id
                JOIN wishlist w ON ub.badge_id = w.badge_id AND w.user_id = $1
                WHERE u.user_id != $1 AND u.server = $2 AND ub.quantity > 1
                  AND u.user_id NOT IN (SELECT unnest($3::bigint[]))
            ''', user_id, user_server, excluded_ids)
            logging.info(f"find_random_profile (wishlist) for user {user_id}: found {len(rows)} rows")
            if rows:
                chosen = random.choice(rows)
                logging.info(f"Chosen user (wishlist): {chosen['user_id']}")
                return dict(chosen)

        # Затем ищем любого с дубликатами, исключая уже просмотренные
            rows = await conn.fetch('''
                SELECT DISTINCT u.user_id, u.telegram_username, u.username, u.uid, u.server, u.notes, u.profile_photo
                FROM users u
                JOIN user_badges ub ON u.user_id = ub.user_id
                WHERE u.user_id != $1 AND u.server = $2 AND ub.quantity > 1
                  AND u.user_id NOT IN (SELECT unnest($3::bigint[]))
            ''', user_id, user_server, excluded_ids)
            logging.info(f"find_random_profile (any duplicates) for user {user_id}: found {len(rows)} rows")
            if not rows:
                return None
            chosen = random.choice(rows)
            logging.info(f"Chosen user (any): {chosen['user_id']}")
            return dict(chosen)
        
    async def create_trade(self, user1_id: int, user2_id: int,
                       user1_collection: Optional[str], user1_character: Optional[str],
                       user2_collection: Optional[str], user2_character: Optional[str],
                       user1_quantity: int = 1, user2_quantity: int = 1) -> int:
        async with self.pool.acquire() as conn:
            trade_id = await conn.fetchval('''
                INSERT INTO trades
                    (user1_id, user2_id,
                     user1_collection, user1_character, user1_quantity,
                     user2_collection, user2_character, user2_quantity,
                     initiator_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $1)
                RETURNING trade_id
            ''', user1_id, user2_id,
                user1_collection, user1_character, user1_quantity,
                user2_collection, user2_character, user2_quantity)
            return trade_id
        
    async def add_notification(self, user_id: int, type: str, content: str):
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO notifications (user_id, type, content)
                VALUES ($1, $2, $3)
        ''', user_id, type, content)
            
    async def update_trade_status(self, trade_id: int, status: str):
        async with self.pool.acquire() as conn:
            if status == 'completed':
                await conn.execute('UPDATE trades SET status = $1, completed_at = CURRENT_TIMESTAMP WHERE trade_id = $2',
                                   status, trade_id)
            else:
                await conn.execute('UPDATE trades SET status = $1, completed_at = NULL WHERE trade_id = $2',
                                   status, trade_id)


    async def confirm_trade_by_user(self, trade_id: int, user_id: int):
        async with self.pool.acquire() as conn:
            trade = await self.get_trade(trade_id)
            if not trade:
                return
            if user_id == trade['user1_id']:
                await conn.execute('UPDATE trades SET confirmed_by_user1 = TRUE WHERE trade_id = $1', trade_id)
            elif user_id == trade['user2_id']:
                await conn.execute('UPDATE trades SET confirmed_by_user2 = TRUE WHERE trade_id = $1', trade_id)
            else:
                return
        updated_trade = await self.get_trade(trade_id)
        if updated_trade['confirmed_by_user1'] and updated_trade['confirmed_by_user2']:
            await self.complete_trade(trade_id)

    async def complete_trade(self, trade_id: int):
        async with self.pool.acquire() as conn:
            trade = await self.get_trade(trade_id)
            if not trade:
                return

        # Обмен от user1 к user2
            if trade['user1_collection'] and trade['user1_character']:
                badge1_id = await self.get_badge_id(trade['user1_collection'], trade['user1_character'])
                if badge1_id:
                    # Уменьшаем у user1
                    await self.decrease_duplicate(trade['user1_id'], badge1_id, trade['user1_quantity'])
                # Увеличиваем у user2
                    await self.add_or_update_user_badge(trade['user2_id'], badge1_id, trade['user1_quantity'])

        # Обмен от user2 к user1
            if trade['user2_collection'] and trade['user2_character']:
                badge2_id = await self.get_badge_id(trade['user2_collection'], trade['user2_character'])
                if badge2_id:
                    await self.decrease_duplicate(trade['user2_id'], badge2_id, trade['user2_quantity'])
                    await self.add_or_update_user_badge(trade['user1_id'], badge2_id, trade['user2_quantity'])

            await conn.execute('UPDATE trades SET status = $1, completed_at = CURRENT_TIMESTAMP WHERE trade_id = $2',
                               'completed', trade_id)

    async def get_trade(self, trade_id: int) -> Optional[Dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT * FROM trades WHERE trade_id = $1', trade_id)
            return dict(row) if row else None
        
    async def get_trade_with_confirmation(self, trade_id: int) -> Optional[Dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT * FROM trades WHERE trade_id = $1', trade_id)
            return dict(row) if row else None
        
    async def delete_user(self, user_id: int):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Удаляем уведомления
                await conn.execute('DELETE FROM notifications WHERE user_id = $1', user_id)
            # Удаляем вишлист
                await conn.execute('DELETE FROM wishlist WHERE user_id = $1', user_id)
            # Удаляем инвентарь (это вызовет триггеры обновления статистики, но user_stats ещё есть)
                await conn.execute('DELETE FROM user_badges WHERE user_id = $1', user_id)
            # Удаляем обмены, где пользователь участник
                await conn.execute('DELETE FROM trades WHERE user1_id = $1 OR user2_id = $1', user_id)
            # Теперь удаляем статистику
                await conn.execute('DELETE FROM user_stats WHERE user_id = $1', user_id)
            # И наконец пользователя
                await conn.execute('DELETE FROM users WHERE user_id = $1', user_id)
db = Database(DB_CONFIG) 
 # ================== СОСТОЯНИЯ FSM ==================
class Register(StatesGroup):
    waiting_for_username = State()
    waiting_for_server = State()
    waiting_for_uid = State()
    waiting_for_notes = State()

class AddInventory(StatesGroup):
    choosing_collection = State()
    choosing_character = State()
    entering_quantity = State()

class AddWishlist(StatesGroup):
    choosing_collection = State()
    choosing_character = State()
    choosing_priority = State()

class TradeOffer(StatesGroup):
    choosing_own_badge = State()
    choosing_target_badge = State()

class TradeOffer(StatesGroup):
    choosing_own_badge = State()
    entering_own_quantity = State()   # новое состояние
    choosing_target_badge = State()
    entering_target_quantity = State()   # новое состояние

class Feedback(StatesGroup):
    waiting_for_type = State()
    waiting_for_text = State()

class ProfilePhoto(StatesGroup):
    waiting_for_photo = State()

# Добавить новое состояние в EditProfile
class EditProfile(StatesGroup):
    choosing_field = State()
    waiting_for_new_username = State()
    waiting_for_new_server = State()
    waiting_for_new_uid = State()
    waiting_for_new_notes = State()
    waiting_for_new_contact = State()   # новое состояние   
class ConfirmDelete(StatesGroup):
    waiting_for_confirmation = State()
# ================== КЛАВИАТУРЫ ==================
def main_keyboard(is_registered: bool = True):
    if not is_registered:
        return ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📝 Регистрация")]],
            resize_keyboard=True
        )
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Искать значки")],
            [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="📞 Обратная связь")]
        ],
        resize_keyboard=True
    )


def get_collections_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    collections = [
        ("✨ Shining", "shining"),
        ("🌌 Nebula", "nebula"),
        ("🌈 Rainbow Flower", "rainbow_flower")
    ]
    for name, key in collections:
        builder.button(text=name, callback_data=f"coll:{key}")
    builder.button(text="❌ Отмена", callback_data="cancel_inventory")  # добавлено
    builder.adjust(1)
    return builder.as_markup()

def get_characters_keyboard(collection: str, available_chars: List[str] = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    characters = available_chars or ['искорка', 'пинки пай', 'эпплджек', 'рарити', 'флаттершай', 'радуга', 'спайк']
    for ch in characters:
        builder.button(text=ch.capitalize(), callback_data=f"char:{collection}:{ch}")
    builder.button(text="🔙 Назад", callback_data="back_to_collections")
    builder.adjust(2)
    return builder.as_markup()

def get_servers_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=s)] for s in ['SEA', 'Global', 'TW,HK,MO']],
        resize_keyboard=True
    )

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True
    )

def get_edit_profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📝 Никнейм", callback_data="edit_username")],
            [InlineKeyboardButton(text="🌍 Сервер", callback_data="edit_server")],
            [InlineKeyboardButton(text="🆔 UID", callback_data="edit_uid")],
            [InlineKeyboardButton(text="📌 Заметка", callback_data="edit_notes")],
            [InlineKeyboardButton(text="📞 Юзернейм", callback_data="edit_contact")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="settings_profile")]
        ]
    )


@dp.callback_query(F.data == "delete_profile")
async def delete_profile_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "⚠️ Вы уверены, что хотите удалить свой профиль?\n"
        "Все ваши данные (инвентарь, вишлист, история обменов) будут безвозвратно удалены.\n\n"
        "Для подтверждения отправьте слово `ДА` (без кавычек) или нажмите /cancel для отмены.",
        parse_mode="Markdown"
    )
    await state.set_state(ConfirmDelete.waiting_for_confirmation)

async def show_main_menu(chat_id: int, user_id: int):
    registered = await db.user_exists(user_id)
    support_button = InlineKeyboardMarkup(
        inline_keyboard=[
                        [
                InlineKeyboardButton(text="❤️ Поддержать автора", url=SUPPORT_LINK),
                InlineKeyboardButton(text="💬 Чат", url=CHAT_LINK)
            ]

        ]
    )
    try:
        photo = FSInputFile("welcome.jpg")
        await bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=f" пожаловать в бота для обмена значками Heartopia!\n\n"
                    f"📢 Присоединяйся в канал и следи за обновами: {CHANNEL_LINK}\n\n"
                    f"Здесь вы можете находить людей для обмена дубликатами и договариваться о бартере.\n\n"
                    f"Так же добавляйся в чат для поиска друзей, туториалов и новостей💕💕",
                    
            reply_markup=support_button
        )
    except Exception as e:
        logging.error(f"Ошибка отправки фото: {e}")
        await bot.send_message(
            chat_id=chat_id,
            text=f"Добро пожаловать в бота для обмена значками Heartopia!\n\n"
                 f"📢 Присоединяйся в канал и следи за обновами: {CHANNEL_LINK}\n\n"
                 f"Здесь вы можете находить людей для обмена дубликатами и договариваться о бартере.\n\n"
                f"Так же добавляйся в чат для поиска друзей, туториалов и новостей💕💕",
            reply_markup=support_button
        )
    await bot.send_message(chat_id, "Выберите действие:", reply_markup=main_keyboard(registered))

async def perform_search(user_id: int, chat_id: int, state: FSMContext):
    data = await state.get_data()
    viewed = data.get('viewed_user_ids', [])
    logging.info(f"Viewed users so far: {viewed}")

    profile = await db.find_random_profile(user_id, excluded_ids=viewed)
    if not profile:
        await bot.send_message(chat_id, "Больше нет новых анкет. Попробуйте позже.")
        # Сбрасываем просмотренные для новой попытки (необязательно)
        await state.update_data(viewed_user_ids=[])
        return

    duplicates = await db.get_user_duplicates_list(profile['user_id'])
    wishlist = await db.get_wishlist(user_id)
    wishlist_badge_ids = {w['badge_id'] for w in wishlist}

    dup_lines = []
    for d in duplicates:
        star = " ⭐" if d['badge_id'] in wishlist_badge_ids else ""
        dup_lines.append(f"• {d['collection']} - {d['character_name']} (x{d['quantity']-1}){star}")
    dup_text = "\n".join(dup_lines) if dup_lines else "Нет дубликатов"

    progress = await db.get_wishlist_progress(user_id)

    caption = (
    f"👤 {profile['username']}\n"
    f"🔔 {profile['telegram_username'] or 'Не указан'}\n"
    f"🆔 UID: <code>{profile['uid']}</code>\n"
    f"🌍 Сервер: {profile['server']}\n"
    f"📝 Заметка: {profile.get('notes', '—')}\n\n"
    f"Есть для обмена:\n{dup_text}\n\n"
    f"📋 Ваш вишлист: {progress['filled']}/21"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👍 Предложить обмен", callback_data=f"trade_offer:{profile['user_id']}"),
                InlineKeyboardButton(text="👎 Другая анкета", callback_data="next_profile")
            ]
        ]
    )

    viewed.append(profile['user_id'])
    await state.update_data(viewed_user_ids=viewed)

    if profile.get('profile_photo'):
        await bot.send_photo(chat_id, photo=profile['profile_photo'], caption=caption, parse_mode="HTML", reply_markup=keyboard)
    else:
        await bot.send_message(chat_id, caption, parse_mode="HTML", reply_markup=keyboard)
# ================== ХЕНДЛЕРЫ ==================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    registered = await db.user_exists(user_id)
    support_button = InlineKeyboardMarkup(
        inline_keyboard=[
                        [
                InlineKeyboardButton(text="❤️ Поддержать автора", url=SUPPORT_LINK),
                InlineKeyboardButton(text="💬 Чат", url=CHAT_LINK)
            ]

        ]
    )

    try:
        photo = FSInputFile("welcome.jpg")
        await message.answer_photo(
            photo=photo,
            caption=f"Добро пожаловать в бота для обмена значками Heartopia!\n\n"
                    f"📢 Присоединяйся в канал и следи за обновами: {CHANNEL_LINK}\n\n"
                    f"Здесь вы можете находить людей для обмена дубликатами и договариваться о бартере.\n\n"
                    f"Так же добавляйся в чат для поиска друзей, туториалов и новостей💕💕",
            reply_markup=support_button
        )
    except Exception as e:
        logging.error(f"Ошибка отправки фото: {e}")
        await message.answer(
            f"Добро пожаловать в бота для обмена значками Heartopia!\n\n"
            f"📢 Присоединяйся в канал и следи за обновами: {CHANNEL_LINK}\n\n"
            f"Здесь вы можете находить людей для обмена дубликатами и договариваться о бартере.\n\n"
            f"Так же добавляйся в чат для поиска друзей, туториалов и новостей💕💕",
        )

    await message.answer("Выберите действие:", reply_markup=main_keyboard(registered))

@dp.message(Command("cancel"), StateFilter(ConfirmDelete.waiting_for_confirmation))
async def cancel_delete(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Удаление отменено.")
    await settings_menu(message)

@dp.message(ConfirmDelete.waiting_for_confirmation, F.text)
async def delete_profile_confirm(message: Message, state: FSMContext):
    if message.text.strip().upper() == "ДА":
        user_id = message.from_user.id
        await db.delete_user(user_id)
        await state.clear()
        await message.answer(
            "✅ Ваш профиль и все данные успешно удалены.\n"
            "Для повторной регистрации используйте /start.",
            reply_markup=main_keyboard(False)
        )
        # Уведомление администратору (опционально)
        await bot.send_message(
            ADMIN_CHAT_ID,
            f"🔔 Пользователь @{message.from_user.username or 'anon'} (ID {user_id}) удалил свой профиль."
        )
    else:
        await message.answer("❌ Удаление отменено.")
        await state.clear()
        # Возвращаем пользователя в меню настроек
        await settings_menu(message)



# ---------- Регистрация ----------
@dp.message(F.text == "📝 Регистрация")
async def registration_start(message: Message, state: FSMContext):
    if await db.user_exists(message.from_user.id):
        await message.answer("Вы уже зарегистрированы!", reply_markup=main_keyboard(True))
        return
    await message.answer("Введите ваш никнейм в игре:", reply_markup=get_cancel_keyboard())
    await state.set_state(Register.waiting_for_username)

@dp.message(Register.waiting_for_username, F.text)
async def process_username(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Регистрация отменена.", reply_markup=main_keyboard(False))
        return
    await state.update_data(username=message.text.strip())
    await message.answer("Выберите ваш сервер:", reply_markup=get_servers_keyboard())
    await state.set_state(Register.waiting_for_server)

@dp.message(Register.waiting_for_server, F.text)
async def process_server(message: Message, state: FSMContext):
    if message.text not in ['SEA', 'Global', 'TW,HK,MO']:
        await message.answer("Пожалуйста, выберите сервер из списка.", reply_markup=get_servers_keyboard())
        return
    await state.update_data(server=message.text)
    await message.answer("Введите ваш UID (игровой идентификатор):", reply_markup=get_cancel_keyboard())
    await state.set_state(Register.waiting_for_uid)

@dp.message(Register.waiting_for_uid, F.text)
async def process_uid(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Регистрация отменена.", reply_markup=main_keyboard(False))
        return
    uid = message.text.strip()
    await state.update_data(uid=uid)
    await message.answer("Напишите заметку о себе (можно пропустить, отправив «-»):", reply_markup=get_cancel_keyboard())
    await state.set_state(Register.waiting_for_notes)

@dp.message(Register.waiting_for_notes, F.text)
async def process_notes(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Регистрация отменена.", reply_markup=main_keyboard(False))
        return
    notes = message.text.strip() if message.text != '-' else ''
    data = await state.get_data()
    try:
        await db.register_user(
            user_id=message.from_user.id,
            telegram_username=message.from_user.username or '',
            username=data['username'],
            uid=data['uid'],
            server=data['server'],
            chat_id=message.chat.id,
            notes=notes
        )
    except Exception as e:
        logging.error(f"Ошибка при регистрации: {e}")
        await message.answer("Произошла ошибка при регистрации. Попробуйте позже или обратитесь к администратору.")
        await state.clear()
        return
    await state.clear()
    await message.answer("Регистрация завершена! Теперь добавим ваши значки.")
    await start_add_inventory(message.from_user.id, state)

@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нет активного действия для отмены.")
        return
    await state.clear()
    registered = await db.user_exists(message.from_user.id)
    await message.answer("Действие отменено.", reply_markup=main_keyboard(registered))

async def start_add_inventory(user_id: int, state: FSMContext):
    await bot.send_message(user_id, "Выберите коллекцию, из которой у вас есть значки:", reply_markup=get_collections_keyboard())
    await state.set_state(AddInventory.choosing_collection)

@dp.callback_query(AddInventory.choosing_collection, F.data.startswith("coll:"))
async def inventory_choose_collection(callback: CallbackQuery, state: FSMContext):
    collection = callback.data.split(':')[1]
    await state.update_data(collection=collection)
    await callback.message.edit_text(
        f"Коллекция выбрана. Теперь выберите персонажа:",
        reply_markup=get_characters_keyboard(collection)
    )
    await state.set_state(AddInventory.choosing_character)

@dp.callback_query(AddInventory.choosing_character, F.data.startswith("char:"))
async def inventory_choose_character(callback: CallbackQuery, state: FSMContext):
    # Разбиваем строку на три части: префикс 'char', collection, character
    _, collection, character = callback.data.split(':')
    collection = collection.strip()
    character = character.strip()
    await state.update_data(collection=collection, character=character)
    await callback.message.edit_text(
        f"Персонаж: {character.capitalize()}\nВведите количество (0 — удалить, 1 — в коллекции, >1 — дубликаты):",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_inventory")]]
        )
    )
    await state.set_state(AddInventory.entering_quantity)   # <--- ЭТОЙ СТРОКИ НЕ ХВАТАЛО
@dp.message(AddInventory.entering_quantity, F.text)
async def inventory_enter_quantity(message: Message, state: FSMContext):
    try:
        qty = int(message.text)
        if qty < 0:
            raise ValueError
    except ValueError:
        await message.answer("Пожалуйста, введите целое число 0 или больше.")
        return

    data = await state.get_data()
    collection = data.get('collection')
    character = data.get('character')

    if not collection or not character:
        await message.answer("Ошибка: не выбрана коллекция или персонаж. Начните заново.")
        await state.clear()
        return

    logging.info(f"Ввод количества: {collection} - {character}, количество {qty}")

    badge_id = await db.get_badge_id(collection, character)
    if badge_id is None:
        await message.answer(f"Ошибка: значок {collection} - {character} не найден в справочнике.")
        return

    try:
        if qty == 0:
            # Удаляем запись
            async with db.pool.acquire() as conn:
                result = await conn.execute('DELETE FROM user_badges WHERE user_id = $1 AND badge_id = $2',
                                             message.from_user.id, badge_id)
                if result == "DELETE 0":
                    await message.answer(f"❌ Запись о значке {character} не найдена.")
                else:
                    await message.answer(f"✅ Значок {character} удалён из инвентаря.")
        else:
            await db.add_or_update_user_badge(
                user_id=message.from_user.id,
                badge_id=badge_id,
                quantity=qty
            )
            await message.answer(f"✅ Значок {character} добавлен (количество: {qty}).")
    except Exception as e:
        logging.error(f"Ошибка при сохранении значка: {e}", exc_info=True)
        await message.answer("Произошла ошибка при сохранении. Попробуйте позже.")
        return

    # Предлагаем дальнейшие действия
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить ещё", callback_data="inventory_add_more")],
            [InlineKeyboardButton(text="➡️ Перейти к вишлисту", callback_data="inventory_to_wishlist")]
        ]
    )
    await message.answer("Что дальше?", reply_markup=keyboard)
    await state.set_state(AddInventory.choosing_collection)

@dp.callback_query(F.data == "back_to_collections", StateFilter(AddInventory.choosing_character))
async def back_to_collections_in_inventory(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Выберите коллекцию:", reply_markup=get_collections_keyboard())
    await state.set_state(AddInventory.choosing_collection)
# Универсальный переход из инвентаря в вишлист
@dp.callback_query(F.data == "cancel_inventory", StateFilter('*'))
async def cancel_inventory(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Добавление значков отменено.")
    await callback.message.delete()
    await callback.message.answer("Возврат в меню.", reply_markup=main_keyboard(True))

# Переход к вишлисту после добавления инвентаря
@dp.callback_query(F.data == "inventory_to_wishlist", StateFilter(AddInventory.choosing_collection))
async def inventory_to_wishlist(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Переходим к вишлисту... ✨")
    await start_add_wishlist(callback.from_user.id, state)

# ДОБАВЛЯЕМ ОБРАБОТЧИК ДЛЯ "inventory_add_more"
@dp.callback_query(F.data == "inventory_add_more", StateFilter(AddInventory.choosing_collection))
async def inventory_add_more(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Выберите коллекцию:", reply_markup=get_collections_keyboard())
    await callback.answer()
# ---------- Добавление вишлиста ----------
async def start_add_wishlist(user_id: int, state: FSMContext):
    progress = await db.get_wishlist_progress(user_id)
    bar = "█" * (progress['filled'] // 2) + "░" * ((21 - progress['filled']) // 2)
    await bot.send_message(
        user_id,
        f"📋 Вишлист (прогресс: {progress['filled']}/21)\n{bar}\n\n"
        f"Выберите коллекцию для добавления в вишлист:",
        parse_mode="Markdown",
        reply_markup=get_collections_keyboard()
    )
    await state.set_state(AddWishlist.choosing_collection)

@dp.callback_query(AddWishlist.choosing_collection, F.data.startswith("coll:"))
async def wishlist_choose_collection(callback: CallbackQuery, state: FSMContext):
    collection = callback.data.split(':')[1]
    await state.update_data(collection=collection)

    available = await db.get_available_for_wishlist(callback.from_user.id)
    avail_in_coll = [a for a in available if a['collection'] == collection]

    if not avail_in_coll:
        progress = await db.get_wishlist_progress(callback.from_user.id)
        await callback.answer(
            f"В этой коллекции все значки уже добавлены! Прогресс: {progress['filled']}/21",
            show_alert=True
        )
        bar = "█" * (progress['filled'] // 2) + "░" * ((21 - progress['filled']) // 2)
        await callback.message.edit_text(
            f"📋 Вишлист (прогресс: {progress['filled']}/21)\n{bar}\n\n"
            f"Выберите другую коллекцию:",
            parse_mode="Markdown",
            reply_markup=get_collections_keyboard()
        )
        return

    builder = InlineKeyboardBuilder()
    for item in avail_in_coll:
        builder.button(
            text=item['character_name'].capitalize(),
            callback_data=f"wish_char:{collection}:{item['character_name']}"
        )
    builder.button(text="🔙 Назад", callback_data="back_to_wishlist_collections")
    builder.adjust(2)
    await callback.message.edit_text(
        f"Коллекция выбрана. Доступно {len(avail_in_coll)} персонажей:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(AddWishlist.choosing_character)

@dp.callback_query(AddWishlist.choosing_character, F.data.startswith("wish_char:"))
async def wishlist_choose_character(callback: CallbackQuery, state: FSMContext):
    _, collection, character = callback.data.split(':')
    await state.update_data(collection=collection, character=character)

    builder = InlineKeyboardBuilder()
    for priority in range(1, 6):
        emoji = "⭐" * priority
        builder.button(text=f"{emoji} {priority}", callback_data=f"priority:{priority}")
    builder.button(text="🔙 Назад", callback_data="back_to_characters")
    builder.adjust(5)

    await callback.message.edit_text(
        f"Выберите приоритет для значка {character.capitalize()} (1-5):",
        reply_markup=builder.as_markup()
    )
    await state.set_state(AddWishlist.choosing_priority)

@dp.callback_query(AddWishlist.choosing_priority, F.data.startswith("priority:"))
async def wishlist_set_priority(callback: CallbackQuery, state: FSMContext):
    priority = int(callback.data.split(':')[1])
    data = await state.get_data()
    badge_id = await db.get_badge_id(data['collection'], data['character'])
    if badge_id:
        await db.add_to_wishlist(callback.from_user.id, badge_id, priority)

    progress = await db.get_wishlist_progress(callback.from_user.id)
    await callback.answer(f"✅ Добавлено! Прогресс: {progress['filled']}/21")

    if progress['filled'] >= 21:
        await callback.message.edit_text(
            "🎉 Поздравляю! Ваш вишлист полностью заполнен!",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="✅ Завершить", callback_data="wishlist_done")]]
            )
        )
    else:
        bar = "█" * (progress['filled'] // 2) + "░" * ((21 - progress['filled']) // 2)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="➕ Добавить ещё", callback_data="wishlist_add_more")],
                [InlineKeyboardButton(text="✅ Завершить", callback_data="wishlist_done")]
            ]
        )
        await callback.message.edit_text(
            f"📋 Прогресс вишлиста: {progress['filled']}/21\n{bar}\n\nЖелаете добавить ещё?",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    await state.set_state(AddWishlist.choosing_collection)

@dp.callback_query(F.data == "wishlist_add_more")
async def wishlist_add_more(callback: CallbackQuery, state: FSMContext):
    progress = await db.get_wishlist_progress(callback.from_user.id)
    if progress['filled'] >= 21:
        await callback.answer("Вишлист уже полностью заполнен!", show_alert=True)
        return
    await callback.message.edit_text(
        f"📋 Вишлист (осталось {21 - progress['filled']} из 21)\n\nВыберите коллекцию:",
        parse_mode="Markdown",
        reply_markup=get_collections_keyboard()
    )
    await state.set_state(AddWishlist.choosing_collection)

@dp.callback_query(F.data == "wishlist_done")
async def wishlist_done(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.message.answer(
        "Отлично! Регистрация полностью завершена. Теперь вы можете искать людей для обмена.",
        reply_markup=main_keyboard(True)
    )

@dp.callback_query(F.data == "back_to_wishlist_collections")
async def back_to_wishlist_collections(callback: CallbackQuery, state: FSMContext):
    progress = await db.get_wishlist_progress(callback.from_user.id)
    bar = "█" * (progress['filled'] // 2) + "░" * ((21 - progress['filled']) // 2)
    await callback.message.edit_text(
        f"📋 Вишлист (прогресс: {progress['filled']}/21)\n{bar}\n\nВыберите коллекцию:",
        parse_mode="Markdown",
        reply_markup=get_collections_keyboard()
    )
    await state.set_state(AddWishlist.choosing_collection)

# ---------- Поиск анкет ----------
@dp.message(lambda msg: msg.text and "Искать значки" in msg.text)
async def search_profile(message: Message, state: FSMContext):
    logging.info(f"search_profile called by user {message.from_user.id}")
    # Сбрасываем список просмотренных при новом поиске
    await state.update_data(viewed_user_ids=[])
    await perform_search(message.from_user.id, message.chat.id, state)

@dp.callback_query(F.data.startswith("confirm_trade:"))
async def confirm_trade(callback: CallbackQuery):
    trade_id = int(callback.data.split(':')[1])
    trade = await db.get_trade_with_confirmation(trade_id)
    if not trade or trade['status'] != 'pending':
        await callback.answer("Это предложение уже неактуально.", show_alert=True)
        return
    # Проверяем, что пользователь является участником
    if callback.from_user.id not in (trade['user1_id'], trade['user2_id']):
        await callback.answer("Это не ваш обмен.", show_alert=True)
        return

    # Если пользователь уже подтверждал – сообщаем
    user_key = 'confirmed_by_user1' if callback.from_user.id == trade['user1_id'] else 'confirmed_by_user2'
    if trade[user_key]:
        await callback.answer("Вы уже подтвердили этот обмен.", show_alert=True)
        return
    await db.confirm_trade_by_user(trade_id, callback.from_user.id)
    await callback.answer("Вы подтвердили обмен. Ожидаем подтверждения второй стороны.", show_alert=True)

    # Проверяем, не завершился ли обмен после подтверждения
    updated_trade = await db.get_trade_with_confirmation(trade_id)
    if updated_trade['status'] == 'completed':
        # Если обмен завершён, уведомляем обоих
        await callback.message.edit_text("✅ Обмен успешно завершён! Значки обновлены.")
        # Уведомляем другого участника
        other_id = trade['user2_id'] if callback.from_user.id == trade['user1_id'] else trade['user1_id']
        other_user = await db.get_user(other_id)
        if other_user and other_user.get('chat_id'):
            await bot.send_message(
                other_user['chat_id'],
                "🎉 Обмен завершён! Обе стороны подтвердили."
            )
    else:
        # Если ещё не завершён, сообщаем другому участнику, что его сторона подтвердила
        other_id = trade['user2_id'] if callback.from_user.id == trade['user1_id'] else trade['user1_id']
        other_user = await db.get_user(other_id)
        if other_user and other_user.get('chat_id'):
            await bot.send_message(
                other_user['chat_id'],
                f"🔔 Пользователь @{callback.from_user.username or 'anon'} подтвердил обмен. Осталось ваше подтверждение.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[
                        InlineKeyboardButton(text="✅ Подтвердить обмен", callback_data=f"confirm_trade:{trade_id}")
                    ]]
                )
            )

@dp.callback_query(F.data == "next_profile")
async def next_profile(callback: CallbackQuery, state: FSMContext):
    logging.info(f"next_profile called by user {callback.from_user.id}")
    await callback.answer()
    await perform_search(callback.from_user.id, callback.message.chat.id, state)
# ---------- Предложение обмена ----------
@dp.callback_query(F.data.startswith("trade_offer:"))
async def trade_offer_start(callback: CallbackQuery, state: FSMContext):
    target_user_id = int(callback.data.split(':')[1])
    await state.update_data(target_user_id=target_user_id)

    my_duplicates = await db.get_user_duplicates_list(callback.from_user.id)
    builder = InlineKeyboardBuilder()

    if my_duplicates:
        for dup in my_duplicates:
            btn_text = f"{dup['collection']} - {dup['character_name']} (x{dup['quantity']-1})"
            builder.button(text=btn_text, callback_data=f"own_badge:{dup['badge_id']}")

    builder.button(text="🎁 Ничего (подарок)", callback_data="own_nothing")
    builder.button(text="❌ Отмена", callback_data="cancel_trade")
    builder.adjust(1)

    # Удаляем старое сообщение (анкету с фото)
    await callback.message.delete()
    # Отправляем новое текстовое сообщение
    await callback.message.answer(
        "Выберите значок, который вы готовы отдать:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(TradeOffer.choosing_own_badge)

@dp.callback_query(TradeOffer.choosing_own_badge, (F.data.startswith("own_badge:")) | (F.data == "own_nothing"))
async def trade_choose_own(callback: CallbackQuery, state: FSMContext):
    if callback.data == "own_nothing":
        # Если подарок, сразу переходим к выбору целевого значка (количество = 0)
        await state.update_data(own_collection=None, own_character=None, own_quantity=0)
        data = await state.get_data()
        target_duplicates = await db.get_user_duplicates_list(data['target_user_id'])
        if not target_duplicates:
            await callback.answer("У этого пользователя больше нет дубликатов.", show_alert=True)
            await state.clear()
            return
        builder = InlineKeyboardBuilder()
        for dup in target_duplicates:
            btn_text = f"{dup['collection']} - {dup['character_name']} (x{dup['quantity']-1})"
            builder.button(text=btn_text, callback_data=f"target_badge:{dup['badge_id']}")
        builder.button(text="🎁 Ничего (подарок)", callback_data="target_nothing")
        builder.button(text="❌ Отмена", callback_data="cancel_trade")
        builder.adjust(1)
        await callback.message.edit_text(
            "Выберите значок, который вы хотите получить:",
            reply_markup=builder.as_markup()
        )
        await state.set_state(TradeOffer.choosing_target_badge)
    else:
        own_badge_id = int(callback.data.split(':')[1])
        my_duplicates = await db.get_user_duplicates_list(callback.from_user.id)
        my_dup = next((dup for dup in my_duplicates if dup['badge_id'] == own_badge_id), None)
        if not my_dup:
            await callback.answer("Ошибка: у вас больше нет этого значка.", show_alert=True)
            return
        await state.update_data(
            own_badge_id=own_badge_id,
            own_collection=my_dup['collection'],
            own_character=my_dup['character_name'],
            own_max_quantity=my_dup['quantity'] - 1
        )
        await callback.message.edit_text(
            f"Вы выбрали: {my_dup['collection']} - {my_dup['character_name']}\n"
            f"У вас доступно для обмена: {my_dup['quantity']-1} шт.\n"
            f"Введите количество, которое хотите отдать (0 — отмена):"
        )
        await state.set_state(TradeOffer.entering_own_quantity)

@dp.message(TradeOffer.entering_own_quantity, F.text)
async def trade_enter_own_quantity(message: Message, state: FSMContext):
    try:
        qty = int(message.text)
        if qty < 0:
            raise ValueError
    except ValueError:
        await message.answer("Пожалуйста, введите целое неотрицательное число.")
        return

    data = await state.get_data()
    max_qty = data.get('own_max_quantity', 0)
    if qty > max_qty:
        await message.answer(f"У вас только {max_qty} дубликатов для обмена. Введите меньшее число.")
        return

    await state.update_data(own_quantity=qty)
    # Переходим к показу целевых значков
    target_duplicates = await db.get_user_duplicates_list(data['target_user_id'])
    if not target_duplicates:
        await message.answer("У этого пользователя больше нет дубликатов.")
        await state.clear()
        return
    builder = InlineKeyboardBuilder()
    for dup in target_duplicates:
        btn_text = f"{dup['collection']} - {dup['character_name']} (x{dup['quantity']-1})"
        builder.button(text=btn_text, callback_data=f"target_badge:{dup['badge_id']}")
    builder.button(text="🎁 Ничего (подарок)", callback_data="target_nothing")
    builder.button(text="❌ Отмена", callback_data="cancel_trade")
    builder.adjust(1)
    await message.answer(
        "Выберите значок, который вы хотите получить:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(TradeOffer.choosing_target_badge)

@dp.callback_query(TradeOffer.choosing_target_badge, (F.data.startswith("target_badge:")) | (F.data == "target_nothing"))
async def trade_choose_target(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if callback.data == "target_nothing":
        await state.update_data(target_collection=None, target_character=None, target_quantity=0)
        await finalize_trade(callback, state)
    else:
        target_badge_id = int(callback.data.split(':')[1])
        target_duplicates = await db.get_user_duplicates_list(data['target_user_id'])
        target_dup = next((dup for dup in target_duplicates if dup['badge_id'] == target_badge_id), None)
        if not target_dup:
            await callback.answer("Ошибка: у пользователя больше нет этого значка.", show_alert=True)
            return
        await state.update_data(
            target_badge_id=target_badge_id,
            target_collection=target_dup['collection'],
            target_character=target_dup['character_name'],
            target_max_quantity=target_dup['quantity'] - 1
        )
        await callback.message.edit_text(
            f"Вы выбрали: {target_dup['collection']} - {target_dup['character_name']}\n"
            f"У пользователя доступно для обмена: {target_dup['quantity']-1} шт.\n"
            f"Введите количество, которое хотите получить (0 — отмена):"
        )
        await state.set_state(TradeOffer.entering_target_quantity)

@dp.message(TradeOffer.entering_target_quantity, F.text)
async def trade_enter_target_quantity(message: Message, state: FSMContext):
    try:
        qty = int(message.text)
        if qty < 0:
            raise ValueError
    except ValueError:
        await message.answer("Пожалуйста, введите целое неотрицательное число.")
        return

    data = await state.get_data()
    max_qty = data.get('target_max_quantity', 0)
    if qty > max_qty:
        await message.answer(f"У пользователя только {max_qty} дубликатов. Введите меньшее число.")
        return

    await state.update_data(target_quantity=qty)
    # Вызов финализации
    await finalize_trade(message, state)
    # ... остальная логика

async def finalize_trade(event: Union[CallbackQuery, Message], state: FSMContext):
    data = await state.get_data()
    trade_id = await db.create_trade(
        user1_id=event.from_user.id,
        user2_id=data['target_user_id'],
        user1_collection=data.get('own_collection'),
        user1_character=data.get('own_character'),
        user2_collection=data.get('target_collection'),
        user2_character=data.get('target_character'),
        user1_quantity=data.get('own_quantity', 0),
        user2_quantity=data.get('target_quantity', 0)
    )
    await state.clear()
    if isinstance(event, CallbackQuery):
        await event.message.edit_text("✅ Предложение отправлено! Ожидайте ответа.")
    else:
        await event.answer("✅ Предложение отправлено! Ожидайте ответа.")

    target_user = await db.get_user(data['target_user_id'])
    if target_user and target_user.get('chat_id'):
        initiator = event.from_user.username or f"ID {event.from_user.id}"
        await bot.send_message(
            target_user['chat_id'],
            f"🔔 Вам поступило предложение обмена от @{initiator}!",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📦 Посмотреть предложение", callback_data=f"view_trade:{trade_id}")]
                ]
            )
        )
    await db.add_notification(
        user_id=data['target_user_id'],
        type='trade_offer',
        content=f"Предложение обмена от @{initiator}"
    )
# ---------- Просмотр и принятие обмена ----------
@dp.callback_query(F.data.startswith("view_trade:"))
async def view_trade(callback: CallbackQuery):
    trade_id = int(callback.data.split(':')[1])
    trade = await db.get_trade_with_confirmation(trade_id)
    if not trade or trade['status'] != 'pending':
        await callback.answer("Это предложение уже неактуально.", show_alert=True)
        return

    user_id = callback.from_user.id
    # Определяем, кто из участников текущий пользователь
    if user_id == trade['user1_id']:
        user_role = "инициатор"
        other_id = trade['user2_id']
        my_confirmed = trade['confirmed_by_user1']
        other_confirmed = trade['confirmed_by_user2']
        my_badge = f"{trade['user1_collection']} - {trade['user1_character']} (x{trade['user1_quantity']})" if trade['user1_collection'] else "🎁 Ничего (подарок)"
        other_badge = f"{trade['user2_collection']} - {trade['user2_character']} (x{trade['user2_quantity']})" if trade['user2_collection'] else "🎁 Ничего (подарок)"
    elif user_id == trade['user2_id']:
        user_role = "получатель"
        other_id = trade['user1_id']
        my_confirmed = trade['confirmed_by_user2']
        other_confirmed = trade['confirmed_by_user1']
        my_badge = f"{trade['user1_collection']} - {trade['user1_character']} (x{trade['user1_quantity']})" if trade['user1_collection'] else "🎁 Ничего (подарок)"
        other_badge = f"{trade['user2_collection']} - {trade['user2_character']} (x{trade['user2_quantity']})" if trade['user2_collection'] else "🎁 Ничего (подарок)"
    else:
        await callback.answer("Это не ваш обмен.", show_alert=True)
        return

    text = (
        f"Предложение обмена:\n"
        f"Вы отдаёте: {my_badge}\n"
        f"Получаете: {other_badge}\n\n"
        f"Статус:\n"
        f"✅ Вы подтвердили: {'да' if my_confirmed else 'нет'}\n"
        f"✅ Другая сторона подтвердила: {'да' if other_confirmed else 'нет'}"
    )

    keyboard_buttons = []
    if not my_confirmed:
        keyboard_buttons.append([InlineKeyboardButton(text="✅ Подтвердить обмен", callback_data=f"confirm_trade:{trade_id}")])
    if not (my_confirmed and other_confirmed):
        keyboard_buttons.append([InlineKeyboardButton(text="❌ Отклонить обмен", callback_data=f"reject_trade:{trade_id}")])
    keyboard_buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_trades")])  # если есть такое меню

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await callback.message.edit_text(text, reply_markup=keyboard)
@dp.callback_query(F.data.startswith("accept_trade:"))
async def accept_trade(callback: CallbackQuery):
    trade_id = int(callback.data.split(':')[1])
    trade = await db.get_trade_with_confirmation(trade_id)
    if not trade or trade['status'] != 'pending':
        await callback.answer("Ошибка: предложение уже обработано.")
        return
    if callback.from_user.id != trade['user2_id']:
        await callback.answer("Это не ваше предложение.")
        return

    # Отмечаем подтверждение от второго
    await db.confirm_trade_by_user(trade_id, callback.from_user.id)

    await callback.answer("Вы приняли предложение. Теперь ожидайте подтверждения от другой стороны.", show_alert=True)
    await callback.message.delete()

    # Уведомляем первого участника, что его предложение принято и нужно подтвердить
    initiator = await db.get_user(trade['user1_id'])
    if initiator and initiator.get('chat_id'):
        await bot.send_message(
            initiator['chat_id'],
            f"✅ Ваше предложение обмена принято пользователем @{callback.from_user.username or 'anon'}!\n"
            f"Теперь подтвердите, что обмен состоялся.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(text="✅ Подтвердить обмен", callback_data=f"confirm_trade:{trade_id}")
                ]]
            )
        )
    # Добавляем уведомление в БД
    await db.add_notification(
        trade['user1_id'],
        'trade_accepted',
        f"Пользователь @{callback.from_user.username or 'anon'} принял ваше предложение. Подтвердите обмен."
    )

@dp.callback_query(F.data.startswith("reject_trade:"))
async def reject_trade(callback: CallbackQuery):
    trade_id = int(callback.data.split(':')[1])
    trade = await db.get_trade(trade_id)
    if not trade:
        await callback.answer("Обмен не найден.", show_alert=True)
        return

    # Определяем, кто отклонил
    if callback.from_user.id == trade['user1_id']:
        other_id = trade['user2_id']
    elif callback.from_user.id == trade['user2_id']:
        other_id = trade['user1_id']
    else:
        await callback.answer("Это не ваш обмен.", show_alert=True)
        return

    await db.update_trade_status(trade_id, 'rejected')
    await callback.answer("Предложение отклонено.")
    await callback.message.delete()

    # Уведомляем другого участника
    other_user = await db.get_user(other_id)
    if other_user and other_user.get('chat_id'):
        await bot.send_message(
            other_user['chat_id'],
            f"❌ Ваше предложение обмена было отклонено пользователем @{callback.from_user.username or 'anon'}."
        )
    # Добавляем уведомление в БД
    await db.add_notification(
        other_id,
        'trade_rejected',
        f"Ваше предложение обмена отклонено пользователем @{callback.from_user.username or 'anon'}."
    )

@dp.callback_query(F.data == "cancel_trade", StateFilter('*'))
async def cancel_trade(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.message.answer("Действие отменено.", reply_markup=main_keyboard(True))

@dp.message(F.text == "⚙️ Настройки")
async def settings_menu(message: Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📦 Инвентарь", callback_data="settings_inventory")],
            [InlineKeyboardButton(text="⭐ Вишлист", callback_data="settings_wishlist")],
            [InlineKeyboardButton(text="🖼 Фото профиля", callback_data="settings_photo")],
            [InlineKeyboardButton(text="👤 Профиль", callback_data="settings_profile")],
            [InlineKeyboardButton(text="❌ Удалить профиль", callback_data="delete_profile")],  # новая кнопка
            [InlineKeyboardButton(text="🔙 Назад", callback_data="settings_back")]
        ]
    )
    await message.answer("Настройки:", reply_markup=keyboard)

@dp.callback_query(F.data == "settings_inventory")
async def settings_inventory(callback: CallbackQuery):
    badges = await db.get_user_badges(callback.from_user.id)
    if not badges:
        text = "У вас пока нет значков."
    else:
        text = "Ваши значки:\n" + "\n".join(
            f"• {b['collection']} - {b['character_name']}: {b['quantity']} шт." for b in badges
        )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить / изменить", callback_data="edit_inventory")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_settings")]
        ]
    )
    await callback.message.edit_text(text, reply_markup=keyboard)

# ДОБАВЛЯЕМ ОБРАБОТЧИК edit_inventory
@dp.callback_query(F.data == "edit_inventory")
async def edit_inventory(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    # Запускаем процесс добавления инвентаря заново
    await start_add_inventory(callback.from_user.id, state)

@dp.callback_query(F.data == "settings_wishlist")
async def settings_wishlist(callback: CallbackQuery):
    wish = await db.get_wishlist(callback.from_user.id)
    logging.info(f"Wishlist raw data: {wish}")
    progress = await db.get_wishlist_progress(callback.from_user.id)
    bar = "█" * (progress['filled'] // 2) + "░" * ((21 - progress['filled']) // 2)

    if not wish:
        text = f"📋 Ваш вишлист\n{bar} {progress['filled']}/21\n\nВишлист пока пуст. Добавьте значки, которые хотите получить!"
    else:
        shining = [f"• {w['character_name']} (⭐ {w['priority']})" for w in wish if w['collection'] == 'shining']
        nebula  = [f"• {w['character_name']} (⭐ {w['priority']})" for w in wish if w['collection'] == 'nebula']
        rainbow = [f"• {w['character_name']} (⭐ {w['priority']})" for w in wish if w['collection'] == 'rainbow_flower']
        text = f"📋 Ваш вишлист\n{bar} {progress['filled']}/21\n\n"
        if shining:
            text += "✨ Shining:\n" + "\n".join(shining) + "\n\n"
        if nebula:
            text += "🌌 Nebula:\n" + "\n".join(nebula) + "\n\n"
        if rainbow:
            text += "🌈 Rainbow Flower:\n" + "\n".join(rainbow) + "\n\n"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить", callback_data="edit_wishlist_add")],
            [InlineKeyboardButton(text="🗑 Удалить", callback_data="edit_wishlist_remove")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_settings")]
        ]
    )

    try:
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise

@dp.callback_query(F.data == "edit_wishlist_add")
async def edit_wishlist_add(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await start_add_wishlist(callback.from_user.id, state)

@dp.callback_query(F.data == "edit_wishlist_remove")
async def wishlist_remove_start(callback: CallbackQuery):
    wish = await db.get_wishlist(callback.from_user.id)
    if not wish:
        await callback.answer("Вишлист пуст, удалять нечего", show_alert=True)
        return
    builder = InlineKeyboardBuilder()
    for item in wish:
        btn_text = f"{item['collection']} - {item['character_name']}"
        builder.button(text=btn_text, callback_data=f"remove_wish:{item['badge_id']}")
    builder.button(text="🔙 Назад", callback_data="back_to_settings")
    builder.adjust(1)

    await callback.message.edit_text(
        "Выберите значок для удаления из вишлиста:",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data.startswith("remove_wish:"))
async def wishlist_remove(callback: CallbackQuery):
    badge_id = int(callback.data.split(':')[1])
    await db.remove_from_wishlist(callback.from_user.id, badge_id)
    progress = await db.get_wishlist_progress(callback.from_user.id)
    await callback.answer(f"✅ Удалено! Осталось {progress['filled']}/21")
    await settings_wishlist(callback)

@dp.callback_query(F.data == "settings_photo")
async def settings_photo(callback: CallbackQuery, state: FSMContext):
    user = await db.get_user(callback.from_user.id)
    status = "✅ Фото установлено" if user.get('profile_photo') else "❌ Фото не загружено"
    keyboard_buttons = []
    if user.get('profile_photo'):
        keyboard_buttons.append([InlineKeyboardButton(text="🗑 Удалить фото", callback_data="delete_photo")])
    keyboard_buttons.append([InlineKeyboardButton(text="📸 Загрузить фото", callback_data="upload_photo")])
    keyboard_buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_settings")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await callback.message.edit_text(f"Фото профиля\n{status}", reply_markup=keyboard)

@dp.callback_query(F.data == "upload_photo")
async def upload_photo_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Отправьте фото (как обычное изображение).")
    await state.set_state(ProfilePhoto.waiting_for_photo)

@dp.message(ProfilePhoto.waiting_for_photo, F.photo)
async def upload_photo_handler(message: Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    await db.update_profile_photo(message.from_user.id, file_id)
    await state.clear()
    await message.answer("✅ Фото профиля обновлено!")

@dp.callback_query(F.data == "delete_photo")
async def delete_photo(callback: CallbackQuery):
    await db.delete_profile_photo(callback.from_user.id)
    await callback.answer("Фото удалено")
    await settings_photo(callback, None)

@dp.callback_query(F.data == "settings_profile")
async def settings_profile(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    if not user:
        await callback.answer("Ошибка профиля")
        return
    text = (
        f"🔔 {user['telegram_username'] or 'Не указан'}\n"
        f"👤 {user['username']}\n"
        f"🆔 UID: `{user['uid']}`\n"
        f"🌍 Сервер: {user['server']}\n"
        f"📝 Заметка: {user.get('notes', '—')}\n"
    )
    # ДОБАВЛЯЕМ ФОТО, ЕСЛИ ОНО ЕСТЬ
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Редактировать профиль", callback_data="edit_profile")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_settings")]
        ]
    )
    if user.get('profile_photo'):
        await callback.message.answer_photo(
            photo=user['profile_photo'],
            caption=text,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        # Удаляем предыдущее сообщение, если оно было текстовым
        await callback.message.delete()
    else:
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)

# НОВЫЙ РАЗДЕЛ: РЕДАКТИРОВАНИЕ ПРОФИЛЯ

@dp.callback_query(F.data == "edit_profile")
async def edit_profile_start(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await show_edit_profile_menu(callback.from_user.id, state)

async def show_edit_profile_menu(user_id: int, state: FSMContext):
    await bot.send_message(user_id, "Что вы хотите изменить?", reply_markup=get_edit_profile_keyboard())
    await state.set_state(EditProfile.choosing_field)

@dp.callback_query(EditProfile.choosing_field, F.data.startswith("edit_"))
async def edit_profile_field(callback: CallbackQuery, state: FSMContext):
    field = callback.data.split('_')[1]  # username, server, uid, notes, contact
    await state.update_data(edit_field=field)
    prompts = {
        "username": "Введите новый никнейм:",
        "server": "Выберите новый сервер:",
        "uid": "Введите новый UID:",
        "notes": "Введите новую заметку о себе:",
        "contact": "Введите новый контактный юзернейм (можно @ или любой текст):"
    }
    if field == "server":
        await callback.message.answer(prompts[field], reply_markup=get_servers_keyboard())
        await callback.message.delete()
        await state.set_state(EditProfile.waiting_for_new_server)
    elif field == "contact":
        await callback.message.answer(prompts[field], reply_markup=get_cancel_keyboard())
        await callback.message.delete()
        await state.set_state(EditProfile.waiting_for_new_contact)
    else:
        await callback.message.answer(prompts[field], reply_markup=get_cancel_keyboard())
        await callback.message.delete()
        if field == "username":
            await state.set_state(EditProfile.waiting_for_new_username)
        elif field == "uid":
            await state.set_state(EditProfile.waiting_for_new_uid)
        elif field == "notes":
            await state.set_state(EditProfile.waiting_for_new_notes)



@dp.message(EditProfile.waiting_for_new_username, F.text)
async def edit_username(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await show_edit_profile_menu(message.from_user.id, state)
        return
    new_username = message.text.strip()
    user = await db.get_user(message.from_user.id)
    if not user:
        await message.answer("Ошибка: пользователь не найден.")
        await state.clear()
        return
    await db.register_user(
        user_id=message.from_user.id,
        telegram_username=message.from_user.username or '',
        username=new_username,
        uid=user['uid'],
        server=user['server'],
        chat_id=message.chat.id,
        notes=user.get('notes', '')
    )
    await state.clear()
    await message.answer("✅ Никнейм обновлён!\n\nЧто вы хотите изменить?", reply_markup=get_edit_profile_keyboard())
    await state.set_state(EditProfile.choosing_field)

@dp.callback_query(EditProfile.choosing_field, F.data == "edit_contact")
async def edit_contact_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите новый контактный юзернейм (можно @ или любой текст):", reply_markup=get_cancel_keyboard())
    await callback.message.delete()
    await state.set_state(EditProfile.waiting_for_new_contact)

@dp.message(EditProfile.waiting_for_new_contact, F.text)
async def edit_contact_process(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await show_edit_profile_menu(message.from_user.id, state)
        return
    new_contact = message.text.strip()
    await db.update_telegram_username(message.from_user.id, new_contact)
    await state.clear()
    await message.answer("✅ Контактный юзернейм обновлён!\n\nЧто вы хотите изменить?", reply_markup=get_edit_profile_keyboard())
    await state.set_state(EditProfile.choosing_field)


@dp.message(EditProfile.waiting_for_new_server, F.text)
async def edit_server(message: Message, state: FSMContext):
    if message.text not in ['SEA', 'Global', 'TW,HK,MO']:
        await message.answer("Пожалуйста, выберите сервер из списка.", reply_markup=get_servers_keyboard())
        return
    new_server = message.text
    user = await db.get_user(message.from_user.id)
    if not user:
        await message.answer("Ошибка: пользователь не найден.")
        await state.clear()
        return
    await db.register_user(
        user_id=message.from_user.id,
        telegram_username=message.from_user.username or '',
        username=user['username'],
        uid=user['uid'],
        server=new_server,
        chat_id=message.chat.id,
        notes=user.get('notes', '')
    )
    await state.clear()
    await message.answer("✅ Сервер обновлён!\n\nЧто вы хотите изменить?", reply_markup=get_edit_profile_keyboard())
    await state.set_state(EditProfile.choosing_field)


@dp.message(EditProfile.waiting_for_new_uid, F.text)
async def edit_uid(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await show_edit_profile_menu(message.from_user.id, state)
        return
    new_uid = message.text.strip()
    user = await db.get_user(message.from_user.id)
    if not user:
        await message.answer("Ошибка: пользователь не найден.")
        await state.clear()
        return
    await db.register_user(
        user_id=message.from_user.id,
        telegram_username=message.from_user.username or '',
        username=user['username'],
        uid=new_uid,
        server=user['server'],
        chat_id=message.chat.id,
        notes=user.get('notes', '')
    )
    await state.clear()
    await message.answer("✅ UID обновлён!\n\nЧто вы хотите изменить?", reply_markup=get_edit_profile_keyboard())
    await state.set_state(EditProfile.choosing_field)



@dp.message(EditProfile.waiting_for_new_notes, F.text)
async def edit_notes(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await show_edit_profile_menu(message.from_user.id, state)
        return
    new_notes = message.text.strip() if message.text != '-' else ''
    user = await db.get_user(message.from_user.id)
    if not user:
        await message.answer("Ошибка: пользователь не найден.")
        await state.clear()
        return
    await db.register_user(
        user_id=message.from_user.id,
        telegram_username=message.from_user.username or '',
        username=user['username'],
        uid=user['uid'],
        server=user['server'],
        chat_id=message.chat.id,
        notes=new_notes
    )
    await state.clear()
    await message.answer("✅ Заметка обновлена!\n\nЧто вы хотите изменить?", reply_markup=get_edit_profile_keyboard())
    await state.set_state(EditProfile.choosing_field)

@dp.callback_query(F.data == "back_to_settings")
async def back_to_settings(callback: CallbackQuery):
    await callback.answer()
    await callback.message.delete()
    await show_main_menu(callback.message.chat.id, callback.from_user.id)
# ---------- Обратная связь ----------

@dp.message(lambda msg: msg.text and "Обратная связь" in msg.text)
async def feedback_start(message: Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚠️ Пожаловаться", callback_data="feedback_complain")],
            [InlineKeyboardButton(text="❓ Задать вопрос", callback_data="feedback_question")]
        ]
    )
    await message.answer("Выберите тип обращения:", reply_markup=keyboard)


@dp.callback_query(F.data == "settings_back")
async def settings_back(callback: CallbackQuery):
    await callback.answer()
    await callback.message.delete()
    await show_main_menu(callback.message.chat.id, callback.from_user.id)


@dp.callback_query(F.data.startswith("feedback_"))
async def feedback_type(callback: CallbackQuery, state: FSMContext):
    ftype = callback.data.split('_')[1]  # complain / question
    await state.update_data(feedback_type=ftype)
    await callback.message.edit_text("Опишите вашу проблему или вопрос (одним сообщением):")
    await state.set_state(Feedback.waiting_for_text)

@dp.message(Feedback.waiting_for_text, F.text)
async def feedback_text(message: Message, state: FSMContext):
    data = await state.get_data()
    ftype = data['feedback_type']
    user_link = f"@{message.from_user.username}" if message.from_user.username else f"ID {message.from_user.id}"
    text = f"🔔 {ftype.upper()} от {user_link}:\n\n{message.text}"
    await bot.send_message(ADMIN_CHAT_ID, text)
    await message.answer("✅ Ваше сообщение отправлено администратору. Спасибо!")
    await state.clear()
async def on_startup():
    await db.connect()
    logging.info("Бот запущен")

async def on_shutdown():
    await db.close()
    logging.info("Бот остановлен")

async def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())

@dp.message()
async def fallback_handler(message: Message, state: FSMContext):
    current_state = await state.get_state()
    logging.warning(f"Необработанное сообщение от {message.from_user.id}: {message.text}, состояние: {current_state}")
    registered = await db.user_exists(message.from_user.id)
    await message.answer(
        "Я не понимаю эту команду. Пожалуйста, воспользуйтесь кнопками.",
        reply_markup=main_keyboard(registered)
    )
