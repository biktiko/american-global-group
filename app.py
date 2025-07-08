import gspread
from google.oauth2.service_account import Credentials
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
import asyncio
import logging
import os
from dotenv import load_dotenv
import psycopg2
from urllib.parse import urlparse
from messages_file import MESSAGES
import queries
import time
import re

# 1) Загрузка env
load_dotenv()
TIMEZONE = os.getenv("TIMEZONE", "UTC")
os.environ["TZ"] = TIMEZONE
try:
    time.tzset()
except AttributeError:
    pass

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    logging.error("DATABASE_URL не задан!")
    exit(1)

# 2) Распарсить URL
result = urlparse(DATABASE_URL)

# 3) Подключиться к Postgres
conn = psycopg2.connect(
    dbname=result.path.lstrip("/"),
    user=result.username,
    password=result.password,
    host=result.hostname,
    port=result.port,
    sslmode="require"
)
conn.autocommit = True
cur = conn.cursor()
cur.execute(f"SET TIME ZONE '{TIMEZONE}'")
# 4) Создать нужные таблицы, если их нет
cur.execute(queries.CREATE_USERS_TABLE)

# Таблица для логирования действий пользователей
cur.execute(queries.CREATE_LOGS_TABLE)

# Таблица для сохранения всех рассылок
cur.execute(queries.CREATE_BROADCASTS_TABLE)
cur.execute(queries.CREATE_ADMINS_TABLE)

def save_user_db(user, phone=None, language=None):
    """
    Сохраняет или обновляет запись о пользователе.
    Если запись уже есть — обновляет username/имя/фамилию/телефон и last_seen_at.
    """
    cur.execute(
        queries.INSERT_USER,
        (
            user.id,
            user.username,
            user.first_name,
            user.last_name,
            phone,
            language,
        ),
    )
    conn.commit()

# Функция для записи действия пользователя в таблицу logs
def log_action(user_id, action, details=None):
    try:
        cur.execute(
            queries.INSERT_LOG,
            (user_id, action, details),
        )
        conn.commit()
        logger.info(f"User {user_id}: {action} {details if details else ''}")
    except Exception as e:
        logger.error(f"Failed to log action '{action}' for user {user_id}: {e}")


# Функция для сохранения информации о рассылке
def save_broadcast(admin_id, recipients, message_hy=None, message_en=None):
    try:
        cur.execute(
            queries.INSERT_BROADCAST,
            (admin_id, message_hy, message_en, recipients),
        )
        conn.commit()
        logger.info(f"Broadcast by {admin_id}: hy='{message_hy}' en='{message_en}' to {recipients}")
    except Exception as e:
        logger.error(f"Failed to save broadcast by {admin_id}: {e}")

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

import base64

# Получение credentials из переменной окружения
credentials_base64 = os.getenv("GOOGLE_CREDENTIALS")
if not credentials_base64:
    logger.error("GOOGLE_CREDENTIALS не установлены в переменных окружения.")
    exit(1)

# Декодирование и запись в файл
with open("credentials.json", "wb") as f:
    f.write(base64.b64decode(credentials_base64))

# Загрузка токена бота из переменных окружения для безопасности
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN не установлен в переменных окружения.")
    exit(1)

# Путь к файлу с учетными данными Google
credentials_path = 'credentials.json'

# Настройка доступа к Google Sheets
creds = Credentials.from_service_account_file(
    credentials_path, scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
client = gspread.authorize(creds)

# Ссылки на таблицы Google Sheets
files = {
    "Air AM to USA": {"id": "1V8foxDTTOXzzw0dnJ3TIIjWrQHSU-oGOD0nRrDn3By8", "sheet": "List"},
    "Air USA to AM": {"id": "181OmCbyhfun3SdmQe7KPvlKpNnnLcl1aVzP7A2eYgSc", "sheet": "Sheet1"},
    "Ocean USA to AM": {"id": "1svNBQ6UtvR5jLsJJNDCx1YpCMfL4YB70sXz9lz9rJ18", "sheet": "Data"}
}

# Хранение данных пользователей
user_choices = {}
user_languages = {}

# Функция для безопасного доступа к ячейкам
def get_cell(row, index):
    return row[index].strip() if len(row) > index else ''

# Функция для создания клавиатуры социальных ссылок
def get_social_links_keyboard():
    buttons = [
        InlineKeyboardButton("📘 Facebook", url="https://www.facebook.com/AGGArmenia"),
        InlineKeyboardButton("📸 Instagram", url="https://www.instagram.com/americanglobalgroup_"),
        InlineKeyboardButton("🌐 Website", url="https://AmericanGlobalGroup.com")
    ]
    return InlineKeyboardMarkup([buttons])

# Функция для получения контактной информации
def get_contact_info():
    contact_text = (
        "📞 Armenia: +374 43 33 44 44\n"
        "📞 USA: +1 424 333-4444\n"
    )
    return contact_text

# Установка языка
async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton(MESSAGES["languages"]["hy"], callback_data="set_lang_hy")],
        [InlineKeyboardButton(MESSAGES["languages"]["en"], callback_data="set_lang_en")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(MESSAGES["language_prompt"]["hy"], reply_markup=reply_markup)

# Обработка установки языка
async def handle_set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang = "hy" if query.data == "set_lang_hy" else "en"
    user_languages[user_id] = lang
    save_user_db(query.from_user, language=lang)
    log_action(user_id, 'set_language', lang)
    await query.message.reply_text(MESSAGES["language_set"][lang])

# Функция обработки команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    cur.execute("SELECT language FROM users WHERE user_id=%s", (user.id,))
    row = cur.fetchone()
    lang = row[0] if row else "hy"
    user_languages[user.id] = lang

    # Сохраняем или обновляем пользователя, не перезаписывая язык
    save_user_db(user, language=lang)
    log_action(user.id, 'start')
    
    # Сохранение пользователя
    
    keyboard = [
        [InlineKeyboardButton(MESSAGES["route_names"]["Air AM to USA"][lang], callback_data="Air AM to USA")],
        [InlineKeyboardButton(MESSAGES["route_names"]["Air USA to AM"][lang], callback_data="Air USA to AM")],
        [InlineKeyboardButton(MESSAGES["route_names"]["Ocean USA to AM"][lang], callback_data="Ocean USA to AM")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"{MESSAGES['start'][lang]}",
        reply_markup=reply_markup
    )

# Обработка выбора направления
async def handle_direction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    direction = query.data
    user_choices[user_id] = direction
    lang = user_languages.get(user_id, "hy")
    route_message = MESSAGES["where_to_find"].get(direction, {}).get(lang, "Error")
    log_action(user_id, 'choose_direction', direction)
    
    # Создание кнопки "Where to Find"
    keyboard = [
        [InlineKeyboardButton(MESSAGES["where_to_find_button"][lang], callback_data="where_to_find")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    template_example = direction
    if direction == "Air AM to USA":
        template_example = "10500009346"
    elif direction == "Air USA to AM":
        template_example = "AM00017664US"
    elif direction == "Ocean USA to AM":
        template_example = "AM00017664US"

    logger.info(f"User {user_id} chose direction {direction}")
    # Отправляем одно сообщение с инструкцией и кнопкой
    await query.message.reply_text(
        f"{MESSAGES['enter_waybill'][lang]}{template_example}",
        reply_markup=reply_markup
    )

# Обработчик кнопки "Change Direction"
async def handle_change_direction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang = user_languages.get(user_id, "hy")
    log_action(user_id, 'change_direction')

    # Создание клавиатуры с направлениями
    keyboard = [
        [InlineKeyboardButton(MESSAGES["route_names"]["Air AM to USA"][lang], callback_data="Air AM to USA")],
        [InlineKeyboardButton(MESSAGES["route_names"]["Air USA to AM"][lang], callback_data="Air USA to AM")],
        [InlineKeyboardButton(MESSAGES["route_names"]["Ocean USA to AM"][lang], callback_data="Ocean USA to AM")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Отправка сообщения с выбором направления
    await query.message.reply_text(
        MESSAGES["choose_route"][lang],
        reply_markup=reply_markup
    )

# Логика извлечения данных
def extract_data(route, row, lang):
    response = ""
    try:
        parcel_status_translations = MESSAGES["parcel_status_translations"]

        if route == "Air AM to USA":
            # Column indices (0-based): B=1, C=2, V=21, Z=25, Y=24, AA=26, AB=27
            order_date = get_cell(row, 2)
            home_delivery_value = get_cell(row, 21)
            try:
                if int(home_delivery_value) > 0:
                    home_delivery = MESSAGES["home_delivery_ordered"][lang]
                else:
                    home_delivery = MESSAGES["home_delivery_not_ordered"][lang]
            except ValueError:
                home_delivery = MESSAGES["home_delivery_not_ordered"][lang]

            parcel_status = get_cell(row, 25)
            estimated_delivery = get_cell(row, 24)
            aa = get_cell(row, 26).lower()
            ab = get_cell(row, 27)
            ac = get_cell(row, 28)

            # Получение перевода статуса
            parcel_status_en = parcel_status_translations[route].get(parcel_status, parcel_status)

            # Отображение даты заказа
            response += f"{MESSAGES['order_date'][lang]}: {order_date}\n"
            response += f"{home_delivery}\n"

            # Проверка столбца AA
            if aa in ['true', 'yes', '1', '✓']:
                response += f"{MESSAGES['received_by_customer'][lang]}: {ab}\n" if ab else f"{MESSAGES['received_by_customer'][lang]}:\n"
            else:
                status = parcel_status if lang == "hy" else parcel_status_en
                response += f"{MESSAGES['parcel_status'][lang]}: {status}\n"
                response += f"{MESSAGES['estimated_delivery_date_usa_office'][lang]}: {estimated_delivery}\n"
            
            if len(ac)>0:
                response += f"\n{ac}\n"
            
        elif route == "Air USA to AM":
            # Column indices: B=1, C=2, R=17, V=21, U=20, X=23
            order_date = get_cell(row, 2)
            home_delivery_value = get_cell(row, 17)
            try:
                if int(home_delivery_value) > 0:
                    home_delivery = MESSAGES["home_delivery_ordered"][lang]
                else:
                    home_delivery = MESSAGES["home_delivery_not_ordered"][lang]
            except ValueError:
                try:
                    if home_delivery_value.upper() == "YES":
                        home_delivery = MESSAGES["home_delivery_ordered"][lang]
                    else:
                        home_delivery = MESSAGES["home_delivery_not_ordered"][lang]
                except Exception as e:
                    home_delivery = MESSAGES["home_delivery_not_ordered"][lang]


            parcel_status = get_cell(row, 21)
            estimated_delivery = get_cell(row, 20)
            x = get_cell(row, 23).lower()
            y = get_cell(row, 24)

            # Получение перевода статуса
            parcel_status_en = parcel_status_translations[route].get(parcel_status, parcel_status)

            # Отображение даты заказа
            response += f"{MESSAGES['order_date'][lang]}: {order_date}\n"
            response += f"{home_delivery}\n"

            # Проверка столбца X
            if x in ["yes", "true", "1", "✓"]:
                response += f"{MESSAGES['received_by_customer'][lang]}:\n"
            else:
                status = parcel_status if lang == "hy" else parcel_status_en
                response += f"{MESSAGES['parcel_status'][lang]}: {status}\n"
                response += f"{MESSAGES['estimated_delivery_date_am_office'][lang]}: {estimated_delivery}\n"

            if len(y)>0:
                response += f"\n{y}\n"
            
        elif route == "Ocean USA to AM":
            # Column indices: B=1, C=2, Q=16, AC=28, AB=27, AE=30
            order_date = get_cell(row, 2)
            home_delivery_value = get_cell(row, 16)
            try:
                if int(home_delivery_value) > 0:
                    home_delivery = MESSAGES["home_delivery_ordered"][lang]
                else:
                    home_delivery = MESSAGES["home_delivery_not_ordered"][lang]
            except ValueError:
                try:
                    if home_delivery_value.upper() == "YES":
                        home_delivery = MESSAGES["home_delivery_ordered"][lang]
                    else:
                        home_delivery = MESSAGES["home_delivery_not_ordered"][lang]
                except Exception as e:
                    home_delivery = MESSAGES["home_delivery_not_ordered"][lang]


            parcel_status = get_cell(row, 28)
            estimated_delivery = get_cell(row, 27)
            ae = get_cell(row, 30).lower()
            ag = get_cell(row, 32)

            # Получение перевода статуса
            parcel_status_en = parcel_status_translations[route].get(parcel_status, parcel_status)

            # Отображение даты заказа
            response += f"{MESSAGES['order_date'][lang]}: {order_date}\n"
            response += f"{home_delivery}\n"

            # Проверка столбца AE
            if ae in ["yes", "true", "1", "✓"]:
                response += f"{MESSAGES['received_by_customer'][lang]}:\n"
            else:
                status = parcel_status if lang == "hy" else parcel_status_en
                response += f"{MESSAGES['parcel_status'][lang]}: {status}\n"
                response += f"{MESSAGES['estimated_delivery_date_am_office'][lang]}: {estimated_delivery}\n"
            
            if len(ag)>0:
                response += f"\n{ag}\n"

        else:
            response = MESSAGES["unsupported_route"]["hy"]
            return response, None
        
        # Добавление контактной информации
        contact_info = get_contact_info()
        response += f"\n{contact_info}"
        # Создание клавиатуры социальных ссылок
        social_keyboard = get_social_links_keyboard()

    except IndexError as ie:
        logger.error(f"IndexError: {ie} for route {route} and row {row}")
        response = MESSAGES["error"][lang]
        social_keyboard = None
    except ValueError as ve:
        logger.error(f"ValueError: {ve} for route {route} and row {row}")
        response = MESSAGES["error"][lang]
        social_keyboard = None
    except Exception as e:
        logger.error(f"Unexpected error: {e} for route {route} and row {row}")
        response = f"{MESSAGES['error'][lang]} {e}"
        social_keyboard = None

    return response, social_keyboard

# Функция для отправки сообщений пользователям
async def broadcast_message(application, messages_by_lang, user_ids, image_url=None):
    for uid in user_ids:
        lang = user_languages.get(uid, "hy")
        text = messages_by_lang.get(lang) or messages_by_lang.get("hy") or next(iter(messages_by_lang.values()))
        try:
            if image_url:
                await application.bot.send_photo(chat_id=uid, photo=image_url, caption=text)
            else:
                await application.bot.send_message(chat_id=uid, text=text)
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение пользователю {uid}: {e}")

# Обработчик команды /broadcast (должен быть доступен только администраторам)
async def broadcast_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    # Проверяем, что пользователь — админ
    cur.execute("SELECT admin_id FROM admins")
    admin_ids = [r[0] for r in cur.fetchall()]
    if user_id not in admin_ids:
        await update.message.reply_text(MESSAGES["no_permission"]["hy"], parse_mode='HTML')
        return

    # Получаем полный текст после команды
    full_text = update.message.text or ""
    parts = full_text.split(' ', 1)
    if len(parts) < 2 or not parts[1].strip():
        await update.message.reply_text(MESSAGES["specify_broadcast_text"]["hy"], parse_mode='HTML')
        return
    args_text = parts[1]

    # Извлекаем ids=
    ids = []
    m_ids = re.search(r'\bids\s*=\s*([\d,]+)', args_text, re.IGNORECASE)
    if m_ids:
        ids = [int(x) for x in m_ids.group(1).split(',') if x]
        args_text = re.sub(r'\bids\s*=\s*[\d,]+', '', args_text, flags=re.IGNORECASE)

    # Извлекаем URL изображения
    image_url = None
    m_url = re.search(r'(https?://\S+)', args_text)
    if m_url:
        image_url = m_url.group(1)
        args_text = args_text.replace(image_url, '')

    # Извлекаем процент
    percent = None
    m_pct = re.search(r'(\d{1,3})\s*%', args_text)
    if m_pct:
        percent = int(m_pct.group(1))
        args_text = args_text.replace(m_pct.group(0), '')

    # Парсим сообщения по языкам
    messages_by_lang = {}
    # hy:
    m_hy = re.search(r'hy:(.*?)(?=(\|en:|$))', args_text, re.DOTALL | re.IGNORECASE)
    if m_hy:
        messages_by_lang['hy'] = m_hy.group(1).strip()
    # en:
    m_en = re.search(r'en:(.*?)(?=(\|hy:|$))', args_text, re.DOTALL | re.IGNORECASE)
    if m_en:
        messages_by_lang['en'] = m_en.group(1).strip()

    # Любой оставшийся текст принимаем как default_message
    default_message = None
    leftover = re.sub(r'(hy:.*?)(?=(\|en:|$))', '', args_text, flags=re.DOTALL | re.IGNORECASE)
    leftover = re.sub(r'(en:.*?)(?=(\|hy:|$))', '', leftover, flags=re.DOTALL | re.IGNORECASE)
    leftover = leftover.replace('|', '').strip()
    if leftover:
        default_message = leftover

    # Если ни одного языка не задано — используем default для обоих
    if not messages_by_lang:
        if default_message is None:
            await update.message.reply_text(MESSAGES["specify_broadcast_text"]["hy"], parse_mode='HTML')
            return
        messages_by_lang = {'hy': default_message, 'en': default_message}
    else:
        # Дополняем недостающий язык
        for lang in ('hy', 'en'):
            if lang not in messages_by_lang:
                messages_by_lang[lang] = default_message or next(iter(messages_by_lang.values()))

    # Проверка валидности процента
    if percent is not None and (percent <= 0 or percent > 100):
        await update.message.reply_text(MESSAGES["broadcast_invalid_percent"]["hy"], parse_mode='HTML')
        return

    # Получаем всех пользователей и их языки
    cur.execute("SELECT user_id, language FROM users ORDER BY last_seen_at DESC")
    rows = cur.fetchall()
    all_users = [r[0] for r in rows]
    db_langs = {r[0]: r[1] for r in rows}
    user_languages.update(db_langs)

    # Фильтрация по ids, если указаны
    if ids:
        recipients_ordered = [uid for uid in all_users if uid in ids]
        if not recipients_ordered:
            await update.message.reply_text(MESSAGES["broadcast_invalid_ids"]["hy"], parse_mode='HTML')
            return
    else:
        recipients_ordered = all_users

    # Фильтрация по проценту
    if percent is not None:
        k = max(1, int(len(recipients_ordered) * percent / 100))
        recipients = recipients_ordered[:k]
    else:
        recipients = recipients_ordered

    # Сохраняем рассылку и логируем
    save_broadcast(user_id, recipients, messages_by_lang.get('hy'), messages_by_lang.get('en'))
    log_action(user_id, 'broadcast', f"{messages_by_lang} -> {recipients}")

    # Отправляем
    await broadcast_message(context.application, messages_by_lang, recipients, image_url=image_url)

    # Подтверждаем админу
    await update.message.reply_text(MESSAGES["broadcast_done"]["hy"], parse_mode='HTML')

# Установка команд для меню
async def set_bot_commands(application):
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("setlanguage", "Change the language"),
        BotCommand("broadcast", "Broadcast a message to all users"),
        BotCommand("sharecontact", "Share your phone number")
    ]
    await application.bot.set_my_commands(commands)

async def share_contact_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    user_id = update.message.from_user.id
    lang = user_languages.get(user_id, "hy")
    log_action(user_id, 'share_contact_request')

    kb = [
        [ KeyboardButton(MESSAGES['share'][lang], request_contact=True) ]
    ]

    reply_markup = ReplyKeyboardMarkup(
        kb,
        one_time_keyboard=True,
        resize_keyboard=True
    )
   
    await update.message.reply_text(
        MESSAGES['share_phone'][lang],
        reply_markup=reply_markup
    )

async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    contact = update.message.contact
    user = update.effective_user
    save_user_db(user, phone=contact.phone_number)
    log_action(user.id, 'share_contact', contact.phone_number)
    # удаляем custom-клавиатуру и возвращаем commands-menu
    await update.message.reply_text(
        MESSAGES["contact_saved"]["hy"],
        reply_markup=ReplyKeyboardRemove()
    )

async def prompt_phone_if_needed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Запрос номера телефона у пользователя, если он не сохранён."""
    user_id = update.message.from_user.id
    cur.execute("SELECT phone_number FROM users WHERE user_id=%s", (user_id,))
    row = cur.fetchone()
    phone = row[0] if row else None
    if not phone:
        await share_contact_request(update, context)


# Обработка ввода waybill пользователем
async def handle_waybill(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    lang = user_languages.get(user_id, "hy")
    direction = user_choices.get(user_id)
    log_action(user_id, 'enter_waybill', update.message.text.strip())

    # Определение клавиатуры для выбора направления
    direction_keyboard = [
        [InlineKeyboardButton(MESSAGES["route_names"]["Air AM to USA"][lang], callback_data="Air AM to USA")],
        [InlineKeyboardButton(MESSAGES["route_names"]["Air USA to AM"][lang], callback_data="Air USA to AM")],
        [InlineKeyboardButton(MESSAGES["route_names"]["Ocean USA to AM"][lang], callback_data="Ocean USA to AM")],
    ]
    direction_reply_markup = InlineKeyboardMarkup(direction_keyboard)

    if not direction:
        # Если направление не выбрано, предложить выбрать направление
        await update.message.reply_text(
            MESSAGES["select_waybill_first"][lang],
            reply_markup=direction_reply_markup
        )
        return

    waybill = update.message.text.strip()
    file_info = files.get(direction)

    if not file_info:
        await update.message.reply_text(
            MESSAGES["route_not_active"][lang]
        )
        return

    # Извлечение данных из Google Sheets
    sheet_id = file_info["id"]
    sheet_name = file_info["sheet"]

    try:
        sheet = client.open_by_key(sheet_id).worksheet(sheet_name)
        data = sheet.get_all_values()

        headers = data[0]  # Заголовки таблицы
        rows = data[1:]    # Данные без заголовков

        # Поиск индекса столбца "waybill"
        waybill_index = headers.index("waybill") if "waybill" in headers else None
        if waybill_index is None:
            await update.message.reply_text(
                MESSAGES["missing_waybill_column"][lang]
            )
            return

        # Поиск строки с указанным waybill
        found = False
        for row in rows:
            if len(row) > waybill_index and row[waybill_index].strip() == waybill:
                result, buttons = extract_data(direction, row, lang)
                if buttons:
                    await update.message.reply_text(result, reply_markup=buttons, parse_mode='HTML')
                else:
                    await update.message.reply_text(result, parse_mode='HTML')
                found = True
                break

        # Если waybill не найден
        if not found:
            # Определение отображаемого названия направления
            if direction in MESSAGES["route_names"]:
                display_name = MESSAGES["route_names"][direction][lang]
            else:
                display_name = MESSAGES["route_names"]["unknown"][lang]

            # Создание сообщения с выбранным направлением
            selected_direction_message = (
                f"{MESSAGES['selected_direction'][lang]}{display_name}\n\n"
            )

            # Получение сообщения "not_found"
            not_found_message = MESSAGES['not_found'][direction][lang]

            # Получение сообщения "choose direction again"
            choose_direction_message = MESSAGES["change_direction"][lang]

            # Получение контактной информации
            contact_info = get_contact_info()

            # Создание полного сообщения
            full_message = (
                f"{not_found_message}\n\n"
                f"{contact_info}\n"
                f"{selected_direction_message}"
                f"{choose_direction_message}"
            )

            # Отправка полного сообщения с клавиатурой выбора направления
            await update.message.reply_text(
                full_message,
                reply_markup=direction_reply_markup
            )

        # После обработки запроса предлагаем поделиться номером телефона при его отсутствии
        await prompt_phone_if_needed(update, context)

    except Exception as e:
        logger.error(f"Error processing waybill for user {user_id}: {e}")
        await update.message.reply_text(
            f"{MESSAGES['error'][lang]} {e}"
        )


# Обработка кнопки "Where to Find"
async def handle_where_to_find(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    direction = user_choices.get(user_id)
    lang = user_languages.get(user_id, "hy")
    log_action(user_id, 'where_to_find')
    if direction:
        message = MESSAGES["where_to_find"].get(direction, {}).get(lang, "Error")
        await query.message.reply_text(message)
    else:
        await query.message.reply_text(
            MESSAGES["select_waybill_first"][lang]
        )

# Запуск бота с настройкой команд
if __name__ == "__main__":
    # Создаём приложение
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Установка обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setlanguage", set_language))
    application.add_handler(CommandHandler("sharecontact", share_contact_request))
    application.add_handler(MessageHandler(filters.CONTACT, contact_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_waybill))
    application.add_handler(CallbackQueryHandler(handle_set_language, pattern="^set_lang_"))
    application.add_handler(CallbackQueryHandler(handle_direction, pattern="^(Air AM to USA|Air USA to AM|Ocean USA to AM)$"))
    application.add_handler(CallbackQueryHandler(handle_where_to_find, pattern="^where_to_find$"))
    application.add_handler(CallbackQueryHandler(handle_change_direction, pattern="^change_direction$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_waybill))
    application.add_handler(CommandHandler("broadcast", broadcast_handler))  

    # Установка команд
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(set_bot_commands(application))

    # Запуск бота
    application.run_polling()