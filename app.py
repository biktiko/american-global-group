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

# Загрузка переменных окружения из .env файла
load_dotenv()

# 1) Загрузка env
load_dotenv()
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

# 4) Создать нужные таблицы, если их нет
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id      BIGINT      PRIMARY KEY,
    username     TEXT,
    first_name   TEXT,
    last_name    TEXT,
    phone_number VARCHAR(20),
    language     VARCHAR(2)  NOT NULL DEFAULT 'hy',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
""")
# cur.execute("""
# CREATE TABLE IF NOT EXISTS user_actions (
#     action_id   BIGSERIAL   PRIMARY KEY,
#     user_id     BIGINT      NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
#     action_type TEXT        NOT NULL,
#     action_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
#     payload     JSONB
# );
# """)

def save_user_db(user, phone=None):
    """
    Сохраняет или обновляет запись о пользователе.
    Если запись уже есть — обновляет username/имя/фамилию/телефон и last_seen_at.
    """
    cur.execute("""
        INSERT INTO users (
            user_id, username, first_name, last_name, phone_number, last_seen_at
        ) VALUES (
            %s, %s, %s, %s, %s, NOW()
        )
        ON CONFLICT (user_id) DO UPDATE SET
            username     = EXCLUDED.username,
            first_name   = EXCLUDED.first_name,
            last_name    = EXCLUDED.last_name,
            phone_number = COALESCE(EXCLUDED.phone_number, users.phone_number),
            last_seen_at = NOW();
    """, (
        user.id,
        user.username,
        user.first_name,
        user.last_name,
        phone
    ))
    conn.commit()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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
    await query.message.reply_text(MESSAGES["language_set"][lang])

# Функция обработки команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    # Сохраняем пользователя (номер ещё неизвестен — передаём None)
    save_user_db(user)
    # user = update.message.from_user.id
    lang = user_languages.get(user.id, "hy")
    
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

    print('direction', direction)
    print('template example', template_example)
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
    # Список администраторов (обновите с вашими реальными ID)
    admin_ids = [1915281004, 856633845]  
    user_id = update.message.from_user.id

    if user_id not in admin_ids:
        await update.message.reply_text(MESSAGES["no_permission"]["hy"], parse_mode='HTML')
        return

    if not context.args:
        await update.message.reply_text(MESSAGES["specify_broadcast_text"]["hy"], parse_mode='HTML')
        return

    broadcast_text = ' '.join(context.args)

    parts = [p.strip() for p in broadcast_text.split('|')]
    messages_by_lang = {}
    image_url = None
    percent = None
    ids = []
    default_message = None

    for part in parts:
        low = part.lower()
        if low.startswith('hy:'):
            messages_by_lang['hy'] = part[3:].strip()
        elif low.startswith('en:'):
            messages_by_lang['en'] = part[3:].strip()
        elif low.endswith('%') and low[:-1].isdigit():
            try:
                percent = int(low[:-1])
            except ValueError:
                percent = None
        elif low.rstrip('%').isdigit() and percent is None:
            percent = int(low.rstrip('%'))
        elif low.startswith('ids='):
            try:
                ids = [int(x) for x in low.split('=',1)[1].split(',') if x.strip()]
            except ValueError:
                ids = []
        elif part.startswith('http://') or part.startswith('https://'):
            image_url = part
        else:
            default_message = part if default_message is None else default_message + ' | ' + part

    if not messages_by_lang:
        if default_message is None:
            await update.message.reply_text(MESSAGES["specify_broadcast_text"]["hy"], parse_mode='HTML')
            return
        messages_by_lang = {'hy': default_message, 'en': default_message}
    else:
        for lang in ('hy', 'en'):
            if lang not in messages_by_lang and default_message:
                messages_by_lang[lang] = default_message

    if percent is not None and (percent <= 0 or percent > 100):
        await update.message.reply_text(MESSAGES["broadcast_invalid_percent"]["hy"], parse_mode='HTML')
        return

    cur.execute("SELECT user_id FROM users")
    all_users = [row[0] for row in cur.fetchall()]

    if ids:
        recipients = [uid for uid in all_users if uid in ids]
        if not recipients:
            await update.message.reply_text(MESSAGES["broadcast_invalid_ids"]["hy"], parse_mode='HTML')
            return
    else:
        recipients = all_users

    if percent is not None:
        import random
        k = max(1, int(len(recipients) * percent / 100))
        recipients = random.sample(recipients, k)

    await broadcast_message(context.application, messages_by_lang, recipients, image_url=image_url)

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
    # удаляем custom-клавиатуру и возвращаем commands-menu
    await update.message.reply_text(
        MESSAGES["contact_saved"]["hy"],
        reply_markup=ReplyKeyboardRemove()
    )


# Обработка ввода waybill пользователем
async def handle_waybill(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    lang = user_languages.get(user_id, "hy")
    direction = user_choices.get(user_id)

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