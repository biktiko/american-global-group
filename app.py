import gspread
from google.oauth2.service_account import Credentials
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
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
import sqlite3

# Загрузка переменных окружения из .env файла
load_dotenv()

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

# Сообщения на двух языках
MESSAGES = {
    "start": {
        "hy": "Բարի գալուստ Ամերիքան Գլոբալ Գրուփի առաքանիների ընթացքին հետևելու բոտ։\n\nԸնդամենը մուտքագրելով առաքանիների անհատական կոդը (waybill number)՝ կարող եք տեսնել կարգավիճակը",
        "en": "Welcome to the American Global Group Package Tracking Bot!\n\nSimply enter your package’s waybill number to check its status."
    },
    "choose_route": {
        "hy": "Ընտրեք ուղղությունը։",
        "en": "Select a shipping route."
    },
    "where_to_find": {
        "Air AM to USA": {
            "hy": "Գործարքի ստացականի վերին ձախ անկյունում կգտնեք 11 նիշանոց նույնականացման համար։",
            "en": "Check the top-left corner of your receipt for an 11-digit identification number."
        },
        "Air USA to AM": {
            "hy": "Գործարքի ստացականի վերին աջ անկյունում կգտնեք 12 նիշանոց նույնականացման համար։",
            "en": "Check the top-right corner of your receipt for a 12-digit identification number."
        },
        "Ocean USA to AM": {
            "hy": "Գործարքի ստացականի վերին աջ անկյունում կգտնեք 12 նիշանոց նույնականացման համար։",
            "en": "Check the top-right corner of your receipt for a 12-digit identification number."
        },
    },
    "not_found": {
        "Air AM to USA": {
            "hy": "Հարգելի՛ hաճախորդ, խնդրում ենք համոզվել, որ մուտքագրել եք ծանրոցի ճիշտ համարը։ \n\n Եթե վստահ եք, որ ծանրոցը ուղարկվել է, և չեք կարողանում հետևել բեռին, խնդրում ենք կապվել մեր հաճախորդների սպասարկման բաժնի հետ։",
            "en": "No package with the provided information was found. \n\n Please ensure you have entered the correct code. \n\n If you are sure that the package has been shipped but cannot track it, please contact our customer service team for assistance."
        },
        "Air USA to AM": {
            "hy": "Հարգելի՛ hաճախորդ, խնդրում ենք համոզվել, որ մուտքագրել եք ծանրոցի ճիշտ համարը։ Հիշեցում՝ ծանրոցի կարգավիճակը հասանելի կլինի հետևելու համար, եթե այն արդեն ուղարկվել է պահեստից մոտակա թռիչքով կամ կոնտեյներային բարձումով։ \n\n Եթե վստահ եք, որ ծանրոցը ուղարկվել է, և չեք կարողանում հետևել բեռին, խնդրում ենք կապվել մեր հաճախորդների սպասարկման բաժնի հետ։",
            "en": "Dear customer, please ensure you have entered the correct waybill number. \n\n Package tracking will be available only if the package has been shipped from the warehouse by the next available flight or container loading. \n\n If you are sure that the package has been shipped but cannot track it, please contact our customer service team for assistance."
        },
        "Ocean USA to AM": {
            "hy": "Հարգելի՛ hաճախորդ, խնդրում ենք համոզվել, որ մուտքագրել եք ծանրոցի ճիշտ համարը։ Հիշեցում՝ ծանրոցի կարգավիճակը հասանելի կլինի հետևելու համար, եթե այն արդեն ուղարկվել է պահեստից մոտակա թռիչքով կամ կոնտեյներային բարձումով։ \n\n Եթե վստահ եք, որ ծանրոցը ուղարկվել է, և չեք կարողանում հետևել բեռին, խնդրում ենք կապվել մեր հաճախորդների սպասարկման բաժնի հետ։",
            "en": "Dear customer, please ensure you have entered the correct waybill number. \n\n Package tracking will be available only if the package has been shipped from the warehouse by the next available flight or container loading. \n\n If you are sure that the package has been shipped but cannot track it, please contact our customer service team for assistance."
        }
    },
    "social_links": {
        "hy": "",
        "en": ""
    },
    "language_prompt": {
        "hy": "Ընտրեք լեզուն / Choose your language:",
        "en": "Select your language:"
    },
    "language_set": {
        "hy": "Լեզուն ընտրված է հայերեն:",
        "en": "Language set to English."
    },
    "error": {
        "hy": "Ինչ-որ սխալ տեղի ունեցավ:",
        "en": "An error occurred:"
    },
    "select_waybill_first": {
        "hy": "Խնդրում ենք նախ ընտրել ուղղությունը։",
        "en": "Please select a direction first."
    },
    "route_not_active": {
        "hy": "Տվյալ ուղղությունը դեռևս ակտիվ չէ։",
        "en": "This route is not active yet."
    },
    "missing_waybill_column": {
        "hy": "Սխալ: 'waybill' սյունը բացակայում է աղյուսակում։",
        "en": "Error: 'waybill' column is missing in the table."
    },
    "enter_waybill": {
        "hy": "Մուտքագրեք ծանրոցի անհատական կոդը ամբողջությամբ, ինչպես գրված է հաստատող փաստաթղթի վրա։ Օրինակ՝ ",
        "en": "Enter your package’s waybill number exactly as written on the receipt. Example: "
    },
}

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

# Инициализация базы данных
conn = sqlite3.connect('users.db')
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)''')
conn.commit()

def add_user(user_id):
    c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()

# Установка языка
async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("Հայերեն", callback_data="set_lang_hy")],
        [InlineKeyboardButton("English", callback_data="set_lang_en")]
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
    user_id = update.message.from_user.id
    lang = user_languages.get(user_id, "hy")
    
    # Сохранение пользователя
    add_user(user_id)
    
    keyboard = [
        [InlineKeyboardButton("Air Shipments from Armenia to the USA" if lang == "en" else "Օդային առաքում Հայաստանից ԱՄՆ", callback_data="Air AM to USA")],
        [InlineKeyboardButton("Air Shipments from the USA to Armenia" if lang == "en" else "Օդային առաքում ԱՄՆ-ից Հայաստան", callback_data="Air USA to AM")],
        [InlineKeyboardButton("Ocean shipments from the USA to Armenia" if lang == "en" else "Ծովային առաքում ԱՄՆ-ից Հայաստան", callback_data="Ocean USA to AM")],
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
        [InlineKeyboardButton("📍 Where to Find" if lang == "en" else "📍 Որտե՞ղ փնտրել", callback_data="where_to_find")]
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
        [InlineKeyboardButton("Air Shipments from Armenia to the USA" if lang == "en" else "Օդային առաքում Հայաստանից ԱՄՆ", callback_data="Air AM to USA")],
        [InlineKeyboardButton("Air Shipments from the USA to Armenia" if lang == "en" else "Օդային առաքում ԱՄՆ-ից Հայաստան", callback_data="Air USA to AM")],
        [InlineKeyboardButton("Ocean shipments from the USA to Armenia" if lang == "en" else "Ծովային առաքում ԱՄՆ-ից Հայաստան", callback_data="Ocean USA to AM")],
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
        # Определение переводов статусов для каждого маршрута
        parcel_status_translations = {
            "Air AM to USA": {
                "ՀՀ գրասենյակում": "In the Armenian Office",
                "ՀՀ մաքսային ձևակերպում": "In the Armenian Customs Office",
                "Ուղարկված ՀՀ-ից": "Sent from Armenia",
                "ԱՄՆ մաքսային մարմին": "In the American Customs Office",
                "ԱՄՆ գրասենյակում": "In the American Office"
            },
            "Air USA to AM": {
                "Ուղարկված ԱՄՆ-իցն": "Sent from the USA",
                "ՀՀ գրասենյակում": "In the Armenian Office",
                "Կանգնեցված ՀՀ մաքսայինի կողմից": "Held by the Armenian Customs Service",
                "ՀՀ մաքսային տերմինալ": "In the Armenian Customs Office"
            },
            "Ocean USA to AM": {
                "Ուղարկված ԱՄՆ-ից": "Sent from the USA",
                "ՀՀ գրասենյակում": "In the Armenian Office",
                "Կանգնեցված ՀՀ մաքսայինի կողմից": "Held by the Armenian Customs Service",
                "ՀՀ մաքսային տերմինալ": "In the Armenian Customs Office"
            }
        }

        if route == "Air AM to USA":
            # Column indices (0-based): B=1, C=2, V=21, Z=25, Y=24, AA=26, AB=27
            order_date = get_cell(row, 2)
            home_delivery_value = get_cell(row, 21)
            try:
                if int(home_delivery_value) > 0:
                    home_delivery = "Առաքում տուն պատվիրված է" if lang == "hy" else "Home delivery is ordered"
                else:
                    home_delivery = "Առաքում տուն պատվիրված չէ" if lang == "hy" else "Home delivery is not ordered"
            except ValueError:
                home_delivery = "Առաքում տուն պատվիրված չէ" if lang == "hy" else "Home delivery is not ordered"  # По умолчанию

            parcel_status = get_cell(row, 25)
            estimated_delivery = get_cell(row, 24)
            aa = get_cell(row, 26).lower()
            ab = get_cell(row, 27)
            ac = get_cell(row, 28)

            # Получение перевода статуса
            parcel_status_en = parcel_status_translations[route].get(parcel_status, parcel_status)

            # Отображение даты заказа
            if lang == "hy":
                response += f"Գործարքի ամսաթիվ: {order_date}\n"
                response += f"{home_delivery}\n"
            else:
                response += f"Order Date: {order_date}\n"
                response += f"{home_delivery}\n"

            # Проверка столбца AA
            if aa in ['true', 'yes', '1', '✓']:
                if lang == "hy":
                    response += f"Ստացված է հաճախորդի կողմից: {ab}\n" if ab else "Ստացված է հաճախորդի կողմից:\n"
                else:
                    response += f"Received by the Customer: {ab}\n" if ab else "Received by the Customer:\n"
            else:
                if lang == "hy":
                    response += f"Առաքման կարգավիճակ:{parcel_status}\n"
                    response += f"Ժամանման նախատեսվող ամսաթիվ դեպի ԱՄՆ գրասենյակ: {estimated_delivery}\n"
                else:
                    response += f"Parcel Status: {parcel_status_en}\n"
                    response += f"Estimated Delivery Date to the American Office:{estimated_delivery}\n"
            
            if len(ac)>0:
                response += f"\n{ac}\n"
            
        elif route == "Air USA to AM":
            # Column indices: B=1, C=2, R=17, V=21, U=20, X=23
            order_date = get_cell(row, 2)
            home_delivery_value = get_cell(row, 17)
            try:
                if int(home_delivery_value) > 0:
                    home_delivery = "Առաքում տուն պատվիրված է" if lang == "hy" else "Home delivery is ordered"
                else:
                    home_delivery = "Առաքում տուն պատվիրված չէ" if lang == "hy" else "Home delivery is not ordered"
            except ValueError:
                try:
                    if home_delivery_value.upper() == "YES":
                        home_delivery = "Առաքում տուն պատվիրված է" if lang == "hy" else "Home delivery is ordered"
                    else:
                        home_delivery = "Առաքում տուն պատվիրված չէ" if lang == "hy" else "Home delivery is not ordered"
                except Exception as e:
                    home_delivery = "Առաքում տուն պատվիրված չէ" if lang == "hy" else "Home delivery is not ordered"


            parcel_status = get_cell(row, 21)
            estimated_delivery = get_cell(row, 20)
            x = get_cell(row, 23).lower()
            y = get_cell(row, 24)

            # Получение перевода статуса
            parcel_status_en = parcel_status_translations[route].get(parcel_status, parcel_status)

            # Отображение даты заказа
            if lang == "hy":
                response += f"Գործարքի ամսաթիվ:{order_date}\n"
                response += f"{home_delivery}\n"
            else:
                response += f"Order Date: {order_date}\n"
                response += f"{home_delivery}\n"

            # Проверка столбца X
            if x in ["yes", "true", "1", "✓"]:
                if lang == "hy":
                    response += f"Ստացված է հաճախորդի կողմից:\n"
                else:
                    response += f"Received by the Customer:\n"
            else:
                if lang == "hy":
                    response += f"Առաքման կարգավիճակ: {parcel_status}\n"
                    response += f"Ժամանման նախատեսվող ամսաթիվ դեպի Երևանյան գրասենյակ: {estimated_delivery}\n"
                else:
                    response += f"Parcel Status: {parcel_status_en}\n"
                    response += f"Estimated Delivery Date to the Armenian Office: {estimated_delivery}\n"

            if len(y)>0:
                response += f"\n{y}\n"
            
        elif route == "Ocean USA to AM":
            # Column indices: B=1, C=2, Q=16, AC=28, AB=27, AE=30
            order_date = get_cell(row, 2)
            home_delivery_value = get_cell(row, 16)
            try:
                if int(home_delivery_value) > 0:
                    home_delivery = "Առաքում տուն պատվիրված է" if lang == "hy" else "Home delivery is ordered"
                else:
                    home_delivery = "Առաքում տուն պատվիրված չէ" if lang == "hy" else "Home delivery is not ordered"
            except ValueError:
                try:
                    if home_delivery_value.upper() == "YES":
                        home_delivery = "Առաքում տուն պատվիրված է" if lang == "hy" else "Home delivery is ordered"
                    else:
                        home_delivery = "Առաքում տուն պատվիրված չէ" if lang == "hy" else "Home delivery is not ordered"
                except Exception as e:
                    home_delivery = "Առաքում տուն պատվիրված չէ" if lang == "hy" else "Home delivery is not ordered"


            parcel_status = get_cell(row, 28)
            estimated_delivery = get_cell(row, 27)
            ae = get_cell(row, 30).lower()
            ag = get_cell(row, 32)

            # Получение перевода статуса
            parcel_status_en = parcel_status_translations[route].get(parcel_status, parcel_status)

            # Отображение даты заказа
            if lang == "hy":
                response += f"Գործարքի ամսաթիվ: {order_date}\n"
                response += f"{home_delivery}\n"
            else:
                response += f"Order Date: {order_date}\n"
                response += f"{home_delivery}\n"

            # Проверка столбца AE
            if ae in ["yes", "true", "1", "✓"]:
                if lang == "hy":
                    response += f"Ստացված է հաճախորդի կողմից:\n"
                else:
                    response += f"Received by the Customer:\n"
            else:
                if lang == "hy":
                    response += f"Առաքման կարգավիճակ: {parcel_status}\n"
                    response += f"Ժամանման նախատեսվող ամսաթիվ դեպի Երևանյան գրասենյակ: {estimated_delivery}\n"
                else:
                    response += f"Parcel Status: {parcel_status_en}\n"
                    response += f"Estimated Delivery Date to the Armenian Office: {estimated_delivery}\n"
            
            if len(ag)>0:
                response += f"\n{ag}\n"

        else:
            response = "Unsupported route."
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

# Функция для отправки сообщений всем пользователям (Broadcast)
async def broadcast_message(application, message_text, image_url=None):
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    for user in users:
        try:
            if image_url:
                await application.bot.send_photo(chat_id=user[0], photo=image_url, caption=message_text)
            else:
                await application.bot.send_message(chat_id=user[0], text=message_text)
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение пользователю {user[0]}: {e}")

# Обработчик команды /broadcast (должен быть доступен только администраторам)
async def broadcast_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Список администраторов (обновите с вашими реальными ID)
    admin_ids = [1915281004, 856633845]  
    user_id = update.message.from_user.id

    if user_id not in admin_ids:
        await update.message.reply_text("У вас нет прав для использования этой команды.", parse_mode='HTML')
        return

    if not context.args:
        await update.message.reply_text("Пожалуйста, укажите текст для рассылки. Пример: /broadcast Привет всем!", parse_mode='HTML')
        return

    # Объединяем все аргументы в одну строку
    broadcast_text = ' '.join(context.args)
    
    # Разделяем текст и URL изображения по разделителю '|'
    if "|" in broadcast_text:
        message, image_url = broadcast_text.split("|", 1)
        message = message.strip()
        image_url = image_url.strip()
    else:
        message = broadcast_text
        image_url = None

    # Отправка сообщений всем пользователям
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    for user in users:
        try:
            if image_url:
                await context.application.bot.send_photo(chat_id=user[0], photo=image_url, caption=message)
            else:
                await context.application.bot.send_message(chat_id=user[0], text=message)
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение пользователю {user[0]}: {e}")

    await update.message.reply_text("Рассылка выполнена.", parse_mode='HTML')

# Установка команд для меню
async def set_bot_commands(application):
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("setlanguage", "Change the language"),
        BotCommand("broadcast", "Broadcast a message to all users")  # Добавлена команда broadcast
    ]
    await application.bot.set_my_commands(commands)

# Обработка ввода waybill пользователем
async def handle_waybill(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    lang = user_languages.get(user_id, "hy")
    direction = user_choices.get(user_id)

    # Определение клавиатуры для выбора направления
    direction_keyboard = [
        [InlineKeyboardButton("Air Shipments from Armenia to the USA" if lang == "en" else "Օդային առաքում Հայաստանից ԱՄՆ", callback_data="Air AM to USA")],
        [InlineKeyboardButton("Air Shipments from the USA to Armenia" if lang == "en" else "Օդային առաքում ԱՄՆ-ից Հայաստան", callback_data="Air USA to AM")],
        [InlineKeyboardButton("Ocean shipments from the USA to Armenia" if lang == "en" else "Ծովային առաքում ԱՄՆ-ից Հայաստան", callback_data="Ocean USA to AM")],
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
            if direction == "Air AM to USA":
                display_name = "Air Shipments from Armenia to the USA" if lang == "en" else "Օդային առաքում Հայաստանից ԱՄՆ"
            elif direction == "Air USA to AM":
                display_name = "Air Shipments from the USA to Armenia" if lang == "en" else "Օդային առաքում ԱՄՆ-ից Հայաստան"
            elif direction == "Ocean USA to AM":
                display_name = "Ocean shipments from the USA to Armenia" if lang == "en" else "Ծովային առաքում ԱՄՆ-ից Հայաստան"
            else:
                display_name = "Unknown direction" if lang == "en" else "Հասկանալի ուղղություն չի գտնվել"

            # Создание сообщения с выбранным направлением
            selected_direction_message = (
                f"{ 'Selected direction: ' if lang == 'en' else 'Ընտրած ուղղություն՝ ' }{display_name}\n\n"
            )

            # Получение сообщения "not_found"
            not_found_message = MESSAGES['not_found'][direction][lang]

            # Получение сообщения "choose direction again"
            choose_direction_message = "Change a direction" if lang == "en" else "Փոխել ուղղությունը"

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
    application.add_handler(CallbackQueryHandler(handle_set_language, pattern="^set_lang_"))
    application.add_handler(CallbackQueryHandler(handle_direction, pattern="^(Air AM to USA|Air USA to AM|Ocean USA to AM)$"))
    application.add_handler(CallbackQueryHandler(handle_where_to_find, pattern="^where_to_find$"))
    application.add_handler(CallbackQueryHandler(handle_change_direction, pattern="^change_direction$"))  # Добавлен обработчик change_direction
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_waybill))
    application.add_handler(CommandHandler("broadcast", broadcast_handler))  # Добавлен обработчик команды broadcast

    # Установка команд
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(set_bot_commands(application))

    # Запуск бота
    application.run_polling()
