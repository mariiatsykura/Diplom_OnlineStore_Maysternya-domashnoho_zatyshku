import shopify
import telebot
from rapidfuzz import fuzz, process
from telebot import types
from bs4 import BeautifulSoup
import requests
from oauthlib.oauth2 import WebApplicationClient
import threading
import sqlite3 as sqlite

conn = sqlite.connect('shop_database.db', check_same_thread=False)
cursor = conn.cursor()
# Thread-local storage for the SQLite connection
thread_local = threading.local()

def get_db_connection():
    if not hasattr(thread_local, "connection"):
        thread_local.connection = sqlite.connect('shop_database.db', check_same_thread=False)
    return thread_local.connection

def get_db_cursor():
    return get_db_connection().cursor()

conn = get_db_connection()
cursor = get_db_cursor()

# Create tables if they don't exist
cursor.execute('''
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    question TEXT,
    answered INTEGER DEFAULT 0,
    answer TEXT
)
''')
conn.commit()

# Initialize bot
TOKEN = '7461766827:AAHDhjJyClqVxRjsh2XX5huKAyuxnw2UYVE'
bot = telebot.TeleBot(token=TOKEN)

# Initialize Shopify API client
api_version = '2024-04'
shop_name = "homecomfortworkshop"
access_token = "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"

shop_url = f"https://{shop_name}.myshopify.com/admin/api/{api_version}"
shopify.Session.setup(api_key="", secret="")


def activate_shopify_session():
    session = shopify.Session(shop_name + ".myshopify.com", api_version, access_token)
    shopify.ShopifyResource.activate_session(session)

# Отримання колекцій та інформації про магазин
try:
    activate_shopify_session()
    collections = shopify.CustomCollection.find()
    result = [collection.title for collection in collections]
    shop = shopify.Shop.current()
    currency = shop.currency
    all_products = shopify.Product.find()
    print(result)
except Exception as e:
    result = ["Сталася помилка під час отримання колекцій"]
    print(f"Сталася помилка: {e}")

current_collection_index = 0
current_product_indices = {}
current_product_index = 0
collection_products_cache = {}

login_url = f"https://{shop_name}.myshopify.com/account/login"

admin_user_ids = [884461904, 987654321]


@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    catalog_button = types.KeyboardButton("Каталог")
    question_button = types.KeyboardButton("FAQ 📌")
    ask_button = types.KeyboardButton("Надіслати повідомлення 📩")
    myquestions_button = types.KeyboardButton("Мої повідомлення")

    markup.add(catalog_button)
    markup.add(question_button, ask_button)
    markup.add(myquestions_button)

    try:
        bot.send_message(
            message.chat.id,
            f'Шановний {message.from_user.first_name},\n'
            f'<b>Вітаємо в магазині "Майстерня домашнього затишку"!</b>\n'
            f'Оберіть одну з опцій нижче:',
            reply_markup=markup,
            parse_mode='html'
        )
        print("Відкрито головне меню")
    except Exception as e:
        print(f"Помилка при відправленні повідомлення: {e}")

@bot.message_handler(func=lambda message: message.text == "Каталог")
def catalog(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    collections_button = types.KeyboardButton("Колекції")
    categories_button = types.KeyboardButton("Категорії")
    view_all_button = types.KeyboardButton("Переглянути всі")
    search_button = types.KeyboardButton("Пошук 🔎")
    back_button = types.KeyboardButton("Назад 🔙")

    markup.add(collections_button, categories_button)
    markup.add(view_all_button, search_button)
    markup.add(back_button)

    try:
        bot.send_message(
            message.chat.id,
            f'Оберіть одну з опцій нижче:',
            reply_markup=markup,
            parse_mode='html'
        )
        print("Відкрито меню каталогу")
    except Exception as e:
        print(f"Помилка при відправленні повідомлення: {e}")

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id in admin_user_ids:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        view_questions_button = types.KeyboardButton("Переглянути повідомлення")
        back_button = types.KeyboardButton("Головне меню 🔙")

        markup.add(view_questions_button, back_button)

        try:
            bot.send_message(
                message.chat.id,
                f'Панель адміністратора',
                reply_markup=markup,
                parse_mode='html'
            )
            print("Відкрито панель адміністратора")
        except Exception as e:
            print(f"Помилка під час надсилання повідомлення: {e}")
    else:
        bot.send_message(message.chat.id, "Ви не можете використовувати цю команду")
def process_user_question(message):
    user_id = message.from_user.id
    username = message.from_user.username
    question_text = message.text

    cursor.execute('INSERT INTO questions (user_id, username, question) VALUES (?, ?, ?)', (user_id, username, question_text))
    conn.commit()

    bot.send_message(message.chat.id, "Дякуємо за ваше питання! Ми зв'яжемося з вами найближчим часом.")

    # Notify admin about the new question
    for admin_id in admin_user_ids:
        bot.send_message(admin_id, f'New question from {username}:\n{question_text}')


@bot.message_handler(func=lambda message: message.text == "Переглянути повідомлення")
def view_questions(message):
    if message.from_user.id in admin_user_ids:
        cursor.execute('SELECT id, username, question FROM questions WHERE answered = 0')
        questions = cursor.fetchall()
        if questions:
            for q in questions:
                reply_markup = types.InlineKeyboardMarkup()
                reply_markup.add(types.InlineKeyboardButton("Відповісти", callback_data=f"answer_{q[0]}"))
                bot.send_message(
                    message.chat.id,
                    f'Номер ID: {q[0]}\nКористувач: {q[1]}\nПовідомлення: {q[2]}',
                    reply_markup=reply_markup
                )
        else:
            bot.send_message(message.chat.id, "Нові повідомлення відсутні")
    else:
        bot.send_message(message.chat.id, "Ви не можете використовувати цю команду")

# Обробник для відповіді на питання
@bot.callback_query_handler(func=lambda call: call.data.startswith('answer_'))
def answer_question(call):
    question_id = int(call.data.split('_')[1])
    cursor.execute('SELECT username, question FROM questions WHERE id = ?', (question_id,))
    result = cursor.fetchone()
    if result:
        username, question_text = result
        bot.send_message(call.message.chat.id, f'Питання від {username}:\n\n{question_text}\n\nНапишіть вашу відповідь:')
        bot.register_next_step_handler(call.message, lambda msg: process_answer(msg, question_id))
    else:
        bot.send_message(call.message.chat.id, "Помилка: не вдалося знайти питання")

# Функція для збереження відповіді на питання
def process_answer(message, question_id):
    answer_text = message.text
    cursor.execute('UPDATE questions SET answered = 1, answer = ? WHERE id = ?', (answer_text, question_id))
    conn.commit()
    bot.send_message(message.chat.id, "Відповідь надіслана успішно!")

@bot.message_handler(func=lambda message: message.text == "Головне меню 🔙")
def back_button(message):
    try:
        start(message)
    except Exception as e:
        bot.send_message(message.chat.id, f"Сталася помилка: {str(e)}")
        print(f"Помилка під час виклику головного меню: {str(e)}")



@bot.message_handler(func=lambda message: message.text.lower() == "категорії")
def show_categories(message):
    try:
        activate_shopify_session()
        collections = shopify.SmartCollection.find()

        if collections:
            markup = types.InlineKeyboardMarkup()
            for collection in collections:
                collection_title = collection.title
                callback_data = f'show_smart_collection_{collection.id}'
                markup.add(types.InlineKeyboardButton(collection_title, callback_data=callback_data))
            bot.send_message(message.chat.id, "Оберіть категорію:", reply_markup=markup)
            print("Відображено категорії:", [collection.title for collection in collections])
        else:
            bot.send_message(message.chat.id, "Немає доступних категорій.")
            print("Немає доступних категорій")
    except Exception as e:
        bot.send_message(message.chat.id, f"Сталася помилка: {str(e)}")
        print(f"Сталася помилка: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('show_smart_collection_'))
def show_smart_collection_products(call):
    try:
        activate_shopify_session()
        collection_id = int(call.data.split('_')[3])
        collection = shopify.SmartCollection.find(collection_id)
        if collection:
            if collection_id not in collection_products_cache:
                collection_products_cache[collection_id] = shopify.Product.find(collection_id=collection_id)
            products = collection_products_cache[collection_id]
            if products:
                current_product_indices[call.message.chat.id] = (collection_id, 0)
                show_product(call.message.chat.id, products, 0)
                print(f"Відображено продукти колекції {collection.title}: {[product.title for product in products]}")
            else:
                bot.send_message(call.message.chat.id, "У цій колекції немає товарів.")
                print("У цій колекції немає товарів.")
        else:
            bot.send_message(call.message.chat.id, "Не вдалося знайти вказану колекцію.")
            print("Не вдалося знайти вказану колекцію.")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Сталася помилка: {str(e)}")
        print(f"Сталася помилка: {str(e)}")

@bot.message_handler(func=lambda message: message.text == "Колекції")
def show_collections(message):
    try:
        show_collection(message.chat.id, current_collection_index)
    except Exception as e:
        bot.send_message(message.chat.id, f"Сталася помилка під час відображення колекції: {str(e)}")
        print(f"Сталася помилка під час відображення колекції: {str(e)}")

def show_collection(chat_id, collection_index):
    global current_collection_index
    current_collection_index = collection_index

    collection_title = result[collection_index]
    print("Відображено колекції")
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton(" ⬅️ ", callback_data=f'prev_{collection_index}'),
        types.InlineKeyboardButton(f"{collection_index + 1} з {len(result)}", callback_data='dummy_data'),
        types.InlineKeyboardButton(" ➡️ ", callback_data=f'next_{collection_index}')
    )
    markup.add(types.InlineKeyboardButton("Переглянути", callback_data=f'view_{collection_index}'))

    description = "Опис відсутній"
    image_url = None
    for collection in collections:
        if collection.title == collection_title:
            if collection.body_html:
                # Використання BeautifulSoup для видалення HTML-тегів
                soup = BeautifulSoup(collection.body_html, 'html.parser')
                description = soup.get_text()[:500]  # Отримання лише тексту та обмеження його до 500 символів
                if hasattr(collection, 'image'):
                    image_url = collection.image.src
            break

    # Створення повідомлення з назвою, описом та зображенням колекції
    message_text = f'<b>Колекція:</b> {collection_title}\n\n<b>Опис:</b> {description}'
    if image_url:
        bot.send_photo(chat_id, image_url, caption=message_text, parse_mode='html', reply_markup=markup)
    else:
        bot.send_message(chat_id, message_text, parse_mode='html', reply_markup=markup)

    if not description:
        bot.send_message(chat_id, "Ця колекція порожня.")
        print("Колекція порожня.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('view_'))
def show_collection_products(call):
    try:
        activate_shopify_session()
        collection_index = int(call.data.split('_')[1])
        collection_title = result[collection_index]
        collection = next((c for c in collections if c.title == collection_title), None)
        if collection:
            if collection.id not in collection_products_cache:
                collection_products_cache[collection.id] = shopify.Product.find(collection_id=collection.id)
            products = collection_products_cache[collection.id]
            if products:
                current_product_indices[call.message.chat.id] = (collection.id, 0)
                show_product(call.message.chat.id, products, 0)
                print(call.message.chat.id, products, 0)
            else:
                bot.send_message(call.message.chat.id, "У цій колекції немає товарів.")
                print("У цій колекції немає товарів.")
        else:
            bot.send_message(call.message.chat.id, "Не вдалося знайти вказану колекцію.")
            print("Не вдалося знайти вказану колекцію.")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Сталася помилка: {str(e)}")
        print("Сталася помилка: {str(e)}")

@bot.message_handler(func=lambda message: message.text == "Переглянути всі")
def show_all_products(message):
    try:
        activate_shopify_session()
        global all_products
        all_products = shopify.Product.find()
        if all_products:
            current_product_indices[message.chat.id] = ("all", 0)
            show_product(message.chat.id, all_products, 0)
        else:
            bot.send_message(message.chat.id, "В магазині немає товарів.")
            print("В магазині немає товарів")
    except Exception as e:
        bot.send_message(message.chat.id, f"Сталася помилка під час завантаження товарів: {str(e)}")
        print(f"Сталася помилка під завантаження товарів: {str(e)}")

def show_product(chat_id, products, product_index):
    product = products[product_index]
    product_title = product.title
    product_price = product.variants[0].price
    product_image_url = product.image.src if hasattr(product, 'image') else None
    product_url = f"https://{shop_name}.myshopify.com/products/{product.handle}"

    # Статус наявності
    available = any(variant.inventory_quantity > 0 for variant in product.variants)
    availability_status = "В наявності" if available else "Немає в наявності"

    # Варіанти продукту
    variants = product.variants
    variant_info = "\n".join([f"{variant.title}: {variant.inventory_quantity} шт." for variant in variants])

    message_text = (
        f'<b>{product_title}</b>\n'
        f'Ціна: {product_price} {currency}\n'
        f'Статус: {availability_status}\n\n'
        f'<b>Варіанти:</b>\n{variant_info}'
    )

    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton(" ⬅️ ", callback_data=f'product_prev_{product_index}'),
        types.InlineKeyboardButton(f"{product_index + 1} з {len(products)}", callback_data='dummy_data'),
        types.InlineKeyboardButton(" ➡️ ", callback_data=f'product_next_{product_index}')
    )
    markup.row(types.InlineKeyboardButton("Відкрити на сайті 🌐", url=product_url))

    if product_image_url:
        bot.send_photo(chat_id, product_image_url, caption=message_text, parse_mode='html', reply_markup=markup)
    else:
        bot.send_message(chat_id, message_text, parse_mode='html', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith(('product_prev_', 'product_next_')))
def handle_product_pagination(call):
    try:
        chat_id = call.message.chat.id
        if chat_id not in current_product_indices:
            return

        _, product_index = current_product_indices[chat_id]
        products = None

        if current_product_indices[chat_id][0] == "all":
            products = all_products
        else:
            collection_id = current_product_indices[chat_id][0]
            products = collection_products_cache.get(collection_id, [])

        if len(products) == 0:
            return

        if call.data.startswith('product_prev_'):
            product_index = (product_index - 1) % len(products)
        else:
            product_index = (product_index + 1) % len(products)

        current_product_indices[chat_id] = (current_product_indices[chat_id][0], product_index)
        bot.delete_message(chat_id, call.message.message_id)
        show_product(chat_id, products, product_index)
    except Exception as e:
        bot.send_message(chat_id, f"Сталася помилка: {str(e)}")
        print(f"Сталася помилка: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith(('prev_', 'next_')))
def handle_pagination(call):
    global current_collection_index

    collection_index = int(call.data.split('_')[1])
    total_collections = len(result)

    try:
        if call.data.startswith('prev_'):
            collection_index -= 1
            if collection_index < 0:
                collection_index = total_collections - 1
        elif call.data.startswith('next_'):
            collection_index += 1
            if collection_index >= total_collections:
                collection_index = 0

        current_collection_index = collection_index
        bot.delete_message(call.message.chat.id, call.message.message_id)
        show_collection(call.message.chat.id, collection_index)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Сталася помилка під час обробки пагінації: {str(e)}")
        print(f"Сталася помилка під час обробки пагінації: {str(e)}")
@bot.message_handler(func=lambda message: message.text == "Пошук 🔎")
def search(message):
    msg = bot.reply_to(message, "Введіть пошуковий запит:")
    bot.register_next_step_handler(msg, process_search_query)

def process_search_query(message):
    global search_query
    search_query = message.text

    try:
        activate_shopify_session()
        search_results = search_products_in_shop(search_query)

        if search_results:
            current_product_indices[message.chat.id] = 0
            show_product(message.chat.id, search_results, 0)
        else:
            bot.send_message(message.chat.id, "Не знайдено товарів за вашим запитом.")
    except Exception as e:
        bot.send_message(message.chat.id, f"Сталася помилка під час пошуку: {str(e)}")

def search_products_in_shop(query):
    results = []
    for product in all_products:
        product_title = product.title
        ratio = fuzz.partial_ratio(query.lower(), product_title.lower())
        if ratio > 80:  # Мінімальний поріг схожості
            results.append(product)
    return results
@bot.message_handler(func=lambda message: message.text == "Назад 🔙")
def back_to_main_menu(message):
    try:
        start(message)
    except Exception as e:
        bot.send_message(message.chat.id, f"Сталася помилка: {str(e)}")
        print(f"Помилка під час виклику головного меню: {str(e)}")



@bot.message_handler(func=lambda message: message.text == "FAQ 📌")
def faq(message):
    faq_markup = types.InlineKeyboardMarkup()
    faq_markup.add(types.InlineKeyboardButton("Які способи оплати ви приймаєте?", callback_data="payment_methods"))
    faq_markup.add(types.InlineKeyboardButton("Які варіанти доставки доступні?", callback_data="delivery_options"))
    faq_markup.add(types.InlineKeyboardButton("Як я можу відстежити своє замовлення?", callback_data="track_order"))
    faq_markup.add(types.InlineKeyboardButton("Яка ваша політика повернення?", callback_data="return_policy"))
    faq_markup.add(types.InlineKeyboardButton("Як я можу зв'язатися з вами?", callback_data="contact_us"))

    try:
        bot.send_message(message.chat.id, "Оберіть запитання:", reply_markup=faq_markup)
        print("Відкрито FAQ меню")
    except Exception as e:
        print(f"Помилка при відправленні повідомлення: {e}")

@bot.callback_query_handler(func=lambda call: call.data in ["payment_methods", "delivery_options", "track_order", "return_policy", "contact_us"])
def answer_faq(call):
    faq_responses = {
        "payment_methods": "Ми приймаємо кредитні картки, дебетові картки, PayPal та Apple Pay.",
        "delivery_options": "Ми пропонуємо стандартну та експрес доставку. Стандартна доставка займає 3-5 робочих днів, а експрес доставка - 1-2 робочих дні.",
        "track_order": "Ви можете відстежувати своє замовлення за посиланням https://www.17track.net/en, або через трекер у кнопці *допомога* нашого сайту",
        "return_policy": "Ви можете повернути товар протягом 30 днів після отримання. Товар має бути в оригінальному стані.",
        "contact_us": "Ви можете зв'язатися з нами через телеграм-бот, натиснувши на *Надіслати повідомлення 📩*"
    }

    response = faq_responses.get(call.data, "Вибачте, інформація наразі недоступна.")
    bot.send_message(call.message.chat.id, response)


# Handling user questions
@bot.message_handler(func=lambda message: message.text == "Надіслати повідомлення 📩")
def ask_question(message):
    msg = bot.reply_to(message, "Введіть ваше питання:")
    bot.register_next_step_handler(msg, process_user_question)

def process_user_question(message):
    user_id = message.from_user.id
    username = message.from_user.username
    question_text = message.text

    cursor.execute('INSERT INTO questions (user_id, username, question) VALUES (?, ?, ?)', (user_id, username, question_text))
    conn.commit()

    bot.send_message(message.chat.id, "Дякуємо за ваше питання! Ми зв'яжемося з вами найближчим часом.")

    # Notify admin about the new question
    for admin_id in admin_user_ids:
        bot.send_message(admin_id, f'New question from {username}:\n{question_text}')

# Обробник для виведення питань користувача
@bot.message_handler(func=lambda message: message.text == "Мої повідомлення")
def my_questions_handler(message):
    user_id = message.from_user.id
    cursor.execute('SELECT question, answered, answer FROM questions WHERE user_id = ?', (user_id,))
    user_questions = cursor.fetchall()

    if user_questions:
        for question, answered, answer_text in user_questions:
            if answered:
                bot.send_message(message.chat.id, f"Ваше питання:\n\n{question}\n\nВідповідь:\n\n{answer_text}")
            else:
                bot.send_message(message.chat.id, f"Ваше питання:\n\n{question}\n\nМи відповімо найближчим часом.")
    else:
        bot.send_message(message.chat.id, "Ви ще не задавали питань")
# Обробник неспівпадаючих повідомлень
@bot.message_handler(func=lambda message: True)
def handle_all_message(message):
    bot.send_message(message.chat.id, "Я не розумію вашого повідомлення. Використовуйте кнопки для взаємодії з ботом.")


if __name__ == '__main__':
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"Помилка під час запуску бота: {e}")

