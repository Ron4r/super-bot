

import logging
import re
import os
import json
import random
import asyncio
from datetime import datetime, date
from pyrogram import Client as PyroClient, errors as PyroErrors
from pyrogram.enums import ChatMemberStatus
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardRemove, File as TGFile
)
from telegram.ext import (
    ApplicationBuilder, CallbackQueryHandler,
    CommandHandler, MessageHandler, ContextTypes, filters
)

# Замените 'YOUR_BOT_TOKEN_HERE' на токен вашего бота, полученный от @BotFather
BOT_TOKEN = "7615626892:AAG0HtOU11GanFg48D2dyh5GNlebvjnRC20"

# Создаём необходимые папки, если они не существуют
for directory in ['accounts', 'sessions']:
    if not os.path.exists(directory):
        os.makedirs(directory)

# Создаём файл paid_users.json, если он не существует
if not os.path.exists('paid_users.json'):
    with open('paid_users.json', 'w') as f:
        json.dump([], f)

# Настройка логирования для отладки
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Список администраторов (замените на свой Telegram ID)
ADMINS = [1564745598]  # Замените на ваш Telegram ID

# Глобальные переменные для хранения состояний
USER_STATES = {}

# Функции для генерации клавиатур и кнопок
def generate_main_menu():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🕵️‍♂️ Парсер", callback_data="parser")],
            [InlineKeyboardButton("📩 Инвайтер", callback_data="inviter")],
            [InlineKeyboardButton("👥 Аккаунты", callback_data="accounts")],
            [InlineKeyboardButton("💎 Моя подписка", callback_data="subscription")],
            [InlineKeyboardButton("📜 Инструкция", callback_data="instructions")]
        ]
    )

def generate_next_button():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Далее", callback_data="next")]
        ]
    )

def generate_digit_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("1", callback_data="1"),
                InlineKeyboardButton("2", callback_data="2"),
                InlineKeyboardButton("3", callback_data="3")
            ],
            [
                InlineKeyboardButton("4", callback_data="4"),
                InlineKeyboardButton("5", callback_data="5"),
                InlineKeyboardButton("6", callback_data="6")
            ],
            [
                InlineKeyboardButton("7", callback_data="7"),
                InlineKeyboardButton("8", callback_data="8"),
                InlineKeyboardButton("9", callback_data="9")
            ],
            [
                InlineKeyboardButton("0", callback_data="0"),
                InlineKeyboardButton("Удалить", callback_data="delete"),
                InlineKeyboardButton("Отправить", callback_data="submit_code")
            ]
        ]
    )

def generate_back_button():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔙 Назад", callback_data="back")]
        ]
    )

def generate_return_button():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Вернуться в меню", callback_data="back_to_menu")]
        ]
    )

def generate_yes_no_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Да", callback_data="yes"),
                InlineKeyboardButton("Нет", callback_data="no")
            ]
        ]
    )

def generate_admin_menu():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Добавить платного пользователя", callback_data="admin_add_paid_user")],
            [InlineKeyboardButton("Убрать платного пользователя", callback_data="admin_remove_paid_user")],
            [InlineKeyboardButton("Показать список платных пользователей", callback_data="admin_list_paid_users")],
            [InlineKeyboardButton("Вернуться в меню", callback_data="back_to_menu")]
        ]
    )

def extract_chat_identifier(link: str):
    if link.startswith("@"):
        return link[1:]

    if link.lstrip("-").isdigit():
        return int(link)

    patterns = [
        r'^https?://t\.me/(?P<username>[\w\d_]+)$',
        r'^https?://telegram\.me/(?P<username>[\w\d_]+)$',
        r'^https?://t\.me/joinchat/(?P<invite>\w+)$',
        r'^https?://telegram\.me/joinchat/(?P<invite>\w+)$'
    ]

    for pattern in patterns:
        match = re.match(pattern, link)
        if match:
            if 'username' in match.groupdict():
                return match.group('username')
            elif 'invite' in match.groupdict():
                return match.group('invite')

    return None

# Глобальный список целевых чатов для удаления сообщений
TARGET_CHAT_IDS = set()

# Функции для управления платными пользователями
def load_paid_users():
    with open('paid_users.json', 'r') as f:
        return json.load(f)

def save_paid_users(paid_users):
    with open('paid_users.json', 'w') as f:
        json.dump(paid_users, f)

def is_paid_user(username):
    paid_users = load_paid_users()
    return username and username.lower() in (user.lower() for user in paid_users)

# Старт команды
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    context.user_data['session_created'] = False
    context.user_data['accounts'] = []
    context.user_data['current_account'] = None

    # Проверяем подписку пользователя по его никнейму
    username = update.effective_user.username
    if is_paid_user(username):
        context.user_data['is_paid'] = True
    else:
        context.user_data['is_paid'] = False

    # Загружаем список аккаунтов пользователя
    accounts = os.listdir('accounts')
    user_accounts = []
    for acc_file in accounts:
        if acc_file.startswith(f'{user_id}_'):
            user_accounts.append(acc_file)

    # Ограничение на количество аккаунтов для бесплатных пользователей
    if not context.user_data['is_paid'] and len(user_accounts) >= 1:
        # Если пользователь бесплатный и уже имеет 1 аккаунт
        message = await update.message.reply_text(
            "У вас уже есть один аккаунт. Для добавления более одного аккаунта необходимо приобрести платную версию.",
            reply_markup=generate_return_button()
        )
        context.user_data['last_message_id'] = message.message_id
        return

    if user_accounts:
        context.user_data['accounts'] = user_accounts
        # Если есть сохранённые аккаунты, предлагаем выбрать текущий
        message = await update.message.reply_text(
            "Выберите аккаунт для использования:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(acc.replace(f'{user_id}_', '').replace('.json', ''), callback_data=f"select_account_{acc}")]
                for acc in user_accounts
            ])
        )
        context.user_data['last_message_id'] = message.message_id
        return
    else:
        message = await update.message.reply_text(
            "Привет! 👋 \n \n Я помогу вам переводить участников из одной группы в другую ➡️👥\n\n ⚠️ Важно: пожалуйста, ознакомьтесь с инструкцией, чтобы избежать ограничений на ваш аккаунт.\n Готовы начать? 🚀",
            reply_markup=generate_next_button()
        )
        context.user_data['last_message_id'] = message.message_id
        return

# Обработка нажатия кнопки "Далее"
async def next_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        message = await query.edit_message_text(
            "Выберите, что хотите сделать:",
            reply_markup=generate_main_menu()
        )
        context.user_data['last_message_id'] = message.message_id
    else:
        message = await update.message.reply_text(
            "Выберите, что хотите сделать:",
            reply_markup=generate_main_menu()
        )
        context.user_data['last_message_id'] = message.message_id

# Обработка выбора функции "Инструкция"
async def show_instructions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    instruction_text = (
        "Дорогие друзья! 👋\n"
        "С помощью этого бота вы можете переводить участников из одной группы в другую ➡️👥\n\n"
        "⚠️ Обратите внимание: за такие действия ваш аккаунт может получить ограничение.\n\n"
        "🔹 Рекомендации:\n\n"
        "Переводите не более 30 человек в день 📊\n"
        "Убедитесь, что ваш аккаунт добавлен в администраторы группы 👤🔒\n\n"
        "Здесь вы можете управлять своими подключёнными аккаунтами Telegram для использования функций парсинга и инвайта.\n\n"
        "💬 Поддержка\n Если у вас возникли вопросы или идеи по улучшению бота, пишите мне в Telegram — @Rostislavas 📩\n"
    )
    message = await query.edit_message_text(
        instruction_text,
        parse_mode='Markdown',
        reply_markup=generate_return_button()
    )
    context.user_data['last_message_id'] = message.message_id

# Обработка выбора функции "Парсер"
async def select_parser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not context.user_data.get('session_created') or not context.user_data.get('current_account'):
        message = await query.edit_message_text(
            "У вас нет активного аккаунта. Пожалуйста, добавьте аккаунт через меню 'Аккаунты'.",
            reply_markup=generate_return_button()
        )
        context.user_data['last_message_id'] = message.message_id
        return

    message = await query.edit_message_text(
        "Пожалуйста, отправьте ссылку на группу или @username группы, из которой нужно собрать участников:",
        reply_markup=generate_back_button()
    )
    context.user_data['last_message_id'] = message.message_id

    # Устанавливаем состояние пользователя
    USER_STATES[update.effective_user.id] = 'PARSE_GROUP'

# Обработка функции парсера
async def parse_group_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if USER_STATES.get(update.effective_user.id) != 'PARSE_GROUP':
        return

    link = update.message.text.strip()
    context.user_data['parse_group_link'] = link
    try:
        await update.message.delete()
    except Exception as e:
        logger.error(f"Не удалось удалить сообщение: {e}")

    last_message_id = context.user_data.get('last_message_id')

    message = await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=last_message_id,
        text="Ссылка получена. Начинаю парсинг..."
    )
    context.user_data['last_message_id'] = message.message_id

    if not context.user_data.get('current_account'):
        message = await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=last_message_id,
            text="Ошибка: Аккаунт не выбран. Пожалуйста, выберите аккаунт.",
            reply_markup=generate_return_button()
        )
        context.user_data['last_message_id'] = message.message_id
        return

    account_data = context.user_data['current_account']

    try:
        app = PyroClient(
            account_data['session_name'],
            api_id=int(account_data['api_id']),
            api_hash=account_data['api_hash'],
            no_updates=True
        )

        await app.start()

        try:
            chat_identifier = extract_chat_identifier(link)
            if not chat_identifier:
                message = await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=last_message_id,
                    text="Ошибка: Неверный формат ссылки или имени пользователя.",
                    reply_markup=generate_return_button()
                )
                context.user_data['last_message_id'] = message.message_id
                return

            chat = await app.get_chat(chat_identifier)

            members = []
            async for member in app.get_chat_members(chat.id):
                if member.user.is_bot or not member.user.username:
                    continue  # Пропускаем ботов и пользователей без username
                link = f"https://t.me/{member.user.username}"
                members.append(link)

            if members:
                filename = f"userlinks_{update.effective_user.id}.txt"
                with open(filename, "w", encoding="utf-8") as file:
                    file.write("\n".join(members))

                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=open(filename, 'rb')
                )
                os.remove(filename)

                message = await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=last_message_id,
                    text="Парсинг завершён. Вот собранный файл пользователей.",
                    reply_markup=generate_return_button()
                )
                context.user_data['last_message_id'] = message.message_id
            else:
                message = await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=last_message_id,
                    text="В группе нет доступных никнеймов.",
                    reply_markup=generate_return_button()
                )
                context.user_data['last_message_id'] = message.message_id

        except PyroErrors.ChatAdminRequired:
            message = await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=last_message_id,
                text="Ошибка: Вы должны быть администратором этой группы.",
                reply_markup=generate_return_button()
            )
            context.user_data['last_message_id'] = message.message_id
        except PyroErrors.ChatInvalid:
            message = await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=last_message_id,
                text="Ошибка: Неверная ссылка на чат или группа недоступна.",
                reply_markup=generate_return_button()
            )
            context.user_data['last_message_id'] = message.message_id
        except Exception as e:
            logger.error(f"Ошибка при получении участников: {e}")
            message = await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=last_message_id,
                text=f"Произошла ошибка: {e}",
                reply_markup=generate_return_button()
            )
            context.user_data['last_message_id'] = message.message_id
        finally:
            await app.stop()

    except Exception as e:
        logger.error(f"Ошибка при инициализации клиента: {e}")
        message = await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=last_message_id,
            text="Произошла ошибка при подключении к Telegram API.",
            reply_markup=generate_return_button()
        )
        context.user_data['last_message_id'] = message.message_id

    # Сбрасываем состояние пользователя
    USER_STATES.pop(update.effective_user.id, None)

# Обработка выбора функции "Инвайтер"
async def select_inviter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not context.user_data.get('session_created') or not context.user_data.get('current_account'):
        message = await query.edit_message_text(
            "У вас нет активного аккаунта. Пожалуйста, добавьте аккаунт через меню 'Аккаунты'.",
            reply_markup=generate_return_button()
        )
        context.user_data['last_message_id'] = message.message_id
        return

    # Информируем пользователя о его подписке и ограничениях
    username = update.effective_user.username
    context.user_data['is_paid'] = is_paid_user(username)
    if context.user_data['is_paid']:
        subscription_info = "У вас активна платная подписка.\n Вы можете приглашать неограниченное число пользователей."
    else:
        subscription_info = "У вас бесплатная подписка ✨!\n Сейчас вы можете приглашать до 10 пользователей в день.\n\nВ платной версии лимит на количество приглашений исчезнет, и вы сможете добавлять бесконечное количество пользователей и аккаунты  🚀🌐.\n\n Пишите мне, если желаете приобрести платную версию  @Rostislavas 👍"

    message = await query.edit_message_text(
        f"{subscription_info}\n\nПожалуйста, введите ссылку на группу или @username группы, в которую нужно добавить участников:",
        reply_markup=generate_back_button()
    )
    context.user_data['last_message_id'] = message.message_id

    # Устанавливаем состояние пользователя
    USER_STATES[update.effective_user.id] = 'INVITE_GROUP'

# Получение ссылки на группу для инвайта и проверка прав администратора
async def get_invite_group_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if USER_STATES.get(update.effective_user.id) != 'INVITE_GROUP':
        return

    group_link = update.message.text.strip()
    context.user_data['invite_group_link'] = group_link
    try:
        await update.message.delete()
    except Exception as e:
        logger.error(f"Не удалось удалить сообщение: {e}")

    if not context.user_data.get('current_account'):
        message = await update.message.reply_text(
            "Ошибка: Аккаунт не выбран. Пожалуйста, выберите аккаунт.",
            reply_markup=generate_return_button()
        )
        context.user_data['last_message_id'] = message.message_id
        return

    last_message_id = context.user_data.get('last_message_id')

    account_data = context.user_data['current_account']

    app = PyroClient(
        account_data['session_name'],
        api_id=int(account_data['api_id']),
        api_hash=account_data['api_hash'],
        no_updates=True
    )

    try:
        await app.start()

        chat_identifier = extract_chat_identifier(group_link)
        if not chat_identifier:
            message = await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=last_message_id,
                text="Ошибка: Неверный формат ссылки или имени пользователя группы.",
                reply_markup=generate_return_button()
            )
            context.user_data['last_message_id'] = message.message_id
            return

        chat = await app.get_chat(chat_identifier)

        member_status = await app.get_chat_member(chat.id, (await app.get_me()).id)
        logger.info(f"Статус администратора: {member_status.status}")
        logger.info(f"Can invite users: {getattr(member_status, 'can_invite_users', 'N/A')}")

        has_invite_rights = False

        if member_status.status == ChatMemberStatus.OWNER:
            has_invite_rights = True
        elif member_status.status == ChatMemberStatus.ADMINISTRATOR:
            has_invite_rights = getattr(member_status, 'can_invite_users', False)
        else:
            has_invite_rights = False

        if not has_invite_rights:
            message = await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=last_message_id,
                text="Ошибка: У вас нет прав на приглашение пользователей в эту группу.",
                reply_markup=generate_return_button()
            )
            context.user_data['last_message_id'] = message.message_id
            return

        context.user_data['invite_chat_link'] = group_link  # Сохраняем ссылку на группу
        context.user_data['invite_chat_id'] = chat.id  # Сохраняем ID чата
        TARGET_CHAT_IDS.add(chat.id)  # Добавляем ID чата в список для удаления сообщений

        message = await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=last_message_id,
            text="Пожалуйста, отправьте файл со списком пользователей для приглашения (формат .txt):",
            reply_markup=generate_back_button()
        )
        context.user_data['last_message_id'] = message.message_id

        # Переходим к следующему состоянию
        USER_STATES[update.effective_user.id] = 'INVITE_FILE'

    except Exception as e:
        logger.error(f"Ошибка при проверке группы: {e}")
        message = await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=last_message_id,
            text=f"Произошла ошибка: {e}",
            reply_markup=generate_return_button()
        )
        context.user_data['last_message_id'] = message.message_id
    finally:
        await app.stop()

# Получение файла со списком пользователей
async def receive_invite_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if USER_STATES.get(update.effective_user.id) != 'INVITE_FILE':
        return

    document = None
    if update.message.document:
        document = update.message.document
        logger.info("Файл получен напрямую.")
    elif update.message.reply_to_message and update.message.reply_to_message.document:
        document = update.message.reply_to_message.document
        logger.info("Файл получен через ответ на сообщение.")
    else:
        logger.info("Файл не был найден в сообщении или ответе.")
        await update.message.reply_text(
            "Пожалуйста, отправьте файл в формате .txt или ответьте на сообщение с файлом."
        )
        return

    if not document:
        await update.message.reply_text("Не удалось найти файл. Пожалуйста, отправьте файл заново.")
        return

    if document.mime_type != 'text/plain':
        logger.info(f"Неверный тип файла: {document.mime_type}")
        await update.message.reply_text("Пожалуйста, отправьте файл в формате .txt.")
        return

    file_name = f"invitelist_{update.effective_user.id}.txt"

    try:
        tg_file: TGFile = await document.get_file()
        logger.info(f"Тип объекта tg_file: {type(tg_file)}")
        logger.info(f"Скачивание файла: {tg_file.file_id}")
        await tg_file.download_to_drive(custom_path=file_name)
        logger.info(f"Файл сохранён как {file_name}")
    except Exception as e:
        logger.error(f"Ошибка при скачивании файла: {e}")
        await update.message.reply_text(
            "Произошла ошибка при скачивании файла. Попробуйте снова."
        )
        return

    context.user_data['invite_file'] = file_name
    try:
        await update.message.delete()
    except Exception as e:
        logger.error(f"Не удалось удалить сообщение: {e}")

    # Спрашиваем, сколько пользователей добавить
    message = await update.message.reply_text(
        "Сколько пользователей добавить в группу?",
        reply_markup=generate_back_button()
    )
    context.user_data['last_message_id'] = message.message_id

    # Переходим к следующему состоянию
    USER_STATES[update.effective_user.id] = 'INVITE_COUNT'

# Получение количества пользователей для добавления
async def get_invite_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if USER_STATES.get(update.effective_user.id) != 'INVITE_COUNT':
        return

    try:
        invite_count = int(update.message.text.strip())
        if invite_count <= 0:
            raise ValueError

        user_id = update.effective_user.id
        username = update.effective_user.username
        context.user_data['is_paid'] = is_paid_user(username)

        # Ограничение для бесплатных пользователей
        if not context.user_data['is_paid']:
            # Проверяем, сколько пользователей пользователь уже пригласил сегодня
            today = date.today()
            user_invites = context.bot_data.get('user_invites', {})
            invites_today = user_invites.get(user_id, {}).get('date') == today and user_invites.get(user_id, {}).get('count', 0) or 0
            total_invites = invites_today + invite_count
            if total_invites > 10:
                remaining = 10 - invites_today
                remaining = max(remaining, 0)
                try:
                    await update.message.delete()
                except Exception as e:
                    logger.error(f"Не удалось удалить сообщение: {e}")
                message = await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=context.user_data.get('last_message_id'),
                    text=f"Вы можете пригласить ещё {remaining} пользователей сегодня. Приобретите платную версию для снятия ограничений \n @Rostislavas .",
                    reply_markup=generate_return_button()
                )
                context.user_data['last_message_id'] = message.message_id
                USER_STATES.pop(update.effective_user.id, None)
                return

        context.user_data['invite_count'] = invite_count
        try:
            await update.message.delete()
        except Exception as e:
            logger.error(f"Не удалось удалить сообщение: {e}")
    except ValueError:
        message = await update.message.reply_text(
            "Пожалуйста, введите корректное число больше нуля.",
            reply_markup=generate_back_button()
        )
        context.user_data['last_message_id'] = message.message_id
        return

    # Запускаем приглашение участников как фоновую задачу
    asyncio.create_task(invite_members_to_group(update, context))

    # Сбрасываем состояние пользователя
    USER_STATES.pop(update.effective_user.id, None)

# Функция для приглашения участников в группу с обновлениями
async def invite_members_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE, from_job=False):
    invite_file = context.user_data.get('invite_file')
    invite_chat_link = context.user_data.get('invite_group_link')
    invite_count = context.user_data.get('invite_count', 30)  # По умолчанию 30

    if not invite_file or not os.path.exists(invite_file):
        message = await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=context.user_data.get('last_message_id'),
            text="Ошибка: Файл со списком пользователей не найден. Пожалуйста, отправьте файл заново.",
            reply_markup=generate_return_button()
        )
        context.user_data['last_message_id'] = message.message_id
        return

    if not invite_chat_link:
        message = await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=context.user_data.get('last_message_id'),
            text="Ошибка: Ссылка на группу не найдена.",
            reply_markup=generate_return_button()
        )
        context.user_data['last_message_id'] = message.message_id
        return

    # Проверяем, сколько пользователей пользователь уже пригласил сегодня
    today = date.today()
    user_id = update.effective_user.id
    username = update.effective_user.username
    user_invites = context.bot_data.get('user_invites', {})

    context.user_data['is_paid'] = is_paid_user(username)

    if not context.user_data['is_paid']:
        invites_today = user_invites.get(user_id, {}).get('date') == today and user_invites.get(user_id, {}).get('count', 0) or 0
        total_invites = invites_today + invite_count
        if total_invites > 10:
            remaining = 10 - invites_today
            remaining = max(remaining, 0)
            message = await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=context.user_data.get('last_message_id'),
                text=f"Вы можете пригласить ещё {remaining} пользователей сегодня. Приобретите платную версию для снятия ограничений.\n @Rostislavas ",
                reply_markup=generate_return_button()
            )
            context.user_data['last_message_id'] = message.message_id
            return

    # Читаем файл и извлекаем usernames
    with open(invite_file, 'r', encoding='utf-8') as file:
        all_members = []
        for line in file:
            line = line.strip()
            if not line:
                continue
            if line.startswith('https://t.me/'):
                username = line.replace('https://t.me/', '').strip('/')
                username = username.lstrip('@')
                all_members.append(username)
            else:
                continue

    # Проверяем, остались ли ещё пользователи для приглашения
    invited_members = context.user_data.get('invited_members', [])
    remaining_members = [member for member in all_members if member not in invited_members]

    if not remaining_members:
        message = await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=context.user_data.get('last_message_id'),
            text="Все пользователи из списка уже приглашены.",
            reply_markup=generate_return_button()
        )
        context.user_data['last_message_id'] = message.message_id
        return

    members_to_invite = remaining_members[:invite_count]

    if not context.user_data.get('current_account'):
        message = await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=context.user_data.get('last_message_id'),
            text="Ошибка: Аккаунт не выбран. Пожалуйста, выберите аккаунт.",
            reply_markup=generate_return_button()
        )
        context.user_data['last_message_id'] = message.message_id
        return

    account_data = context.user_data['current_account']

    app = PyroClient(
        account_data['session_name'],
        api_id=int(account_data['api_id']),
        api_hash=account_data['api_hash'],
        no_updates=True
    )

    try:
        await app.start()

        # Получаем информацию о чате с использованием ссылки
        chat_identifier = extract_chat_identifier(invite_chat_link)
        chat = await app.get_chat(chat_identifier)

        status_message_id = context.user_data.get('last_message_id')
        status_text = "Начинаю приглашение пользователей:\n"

        # Отправляем первое сообщение
        message = await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=status_message_id,
            text=status_text
        )
        context.user_data['last_message_id'] = message.message_id

        # Хранение идентификаторов сообщений для удаления
        messages_to_delete = []

        for idx, username in enumerate(members_to_invite, start=1):
            try:
                username = username.lstrip('@')
                # Получаем информацию о пользователе
                user_entity = await app.get_users(username)
                await app.add_chat_members(chat.id, user_entity.id)
                logger.info(f"Пользователь {username} успешно добавлен.")
                status_text += f"{username} успешно добавлен\n"
                context.user_data.setdefault('invited_members', []).append(username)
                # Хранение ID сообщений о присоединении
                messages_to_delete.append(user_entity.id)

                # После успешного приглашения пользователя, увеличиваем счетчик
                if not context.user_data['is_paid']:
                    if user_id not in user_invites:
                        user_invites[user_id] = {'date': today, 'count': 1}
                    else:
                        if user_invites[user_id]['date'] == today:
                            user_invites[user_id]['count'] += 1
                        else:
                            user_invites[user_id] = {'date': today, 'count': 1}
                    context.bot_data['user_invites'] = user_invites

            except PyroErrors.UsernameInvalid:
                logger.error(f"Не удалось найти пользователя {username}: неверный username.")
                status_text += f"Не удалось найти пользователя {username}: неверный username.\n"
                continue  # Переходим к следующему пользователю
            except PyroErrors.PeerIdInvalid:
                logger.error(f"Не удалось добавить {username}: неверный идентификатор пользователя.")
                status_text += f"Не удалось добавить {username}: неверный идентификатор пользователя.\n"
            except PyroErrors.UserPrivacyRestricted:
                logger.error(f"Не удалось добавить {username}: пользователь ограничил приглашения в группы.")
                status_text += f"Не удалось добавить {username}: пользователь ограничил приглашения в группы.\n"
            except Exception as e:
                logger.error(f"Не удалось добавить {username}: {e}")
                status_text += f"Не удалось добавить {username}: {e}\n"

            # Обновляем сообщение после каждого пользователя
            try:
                message = await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=status_message_id,
                    text=status_text[-4096:]  # Ограничиваем длину сообщения
                )
                context.user_data['last_message_id'] = message.message_id
            except Exception as e:
                logger.error(f"Ошибка при обновлении сообщения: {e}")

            # Задержка между добавлениями, от 60 до 120 секунд
            await asyncio.sleep(random.randint(60, 120))

        # Удаляем системные сообщения о присоединении
        await delete_system_messages(app, chat.id, messages_to_delete)

        # Обновляем сообщение в конце
        try:
            message = await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=status_message_id,
                text=status_text[-4096:] + "\nПриглашение завершено.",
                reply_markup=generate_return_button()
            )
            context.user_data['last_message_id'] = message.message_id
        except Exception as e:
            logger.error(f"Ошибка при обновлении сообщения в конце: {e}")

        # Планируем отправку сообщения через 24 часа
        if not from_job:
            # Проверяем, что context.job_queue не None
            if context.job_queue:
                context.job_queue.run_once(
                    ask_continue_inviting,
                    when=86400,  # 24 часа
                    data={'chat_id': update.effective_chat.id, 'user_id': update.effective_user.id},
                    name=str(update.effective_chat.id)
                )
            else:
                logger.error("context.job_queue is None")

    except Exception as e:
        logger.error(f"Ошибка при приглашении участников: {e}")
        message = await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=context.user_data.get('last_message_id'),
            text=f"Произошла ошибка: {e}",
            reply_markup=generate_return_button()
        )
        context.user_data['last_message_id'] = message.message_id
    finally:
        await app.stop()

# Функция для удаления системных сообщений о присоединении
async def delete_system_messages(app, chat_id, user_ids):
    async for message in app.get_chat_history(chat_id):
        if message.service and message.new_chat_members:
            new_member_ids = [user.id for user in message.new_chat_members]
            if any(uid in user_ids for uid in new_member_ids):
                try:
                    await app.delete_messages(chat_id, message.id)
                    logger.info(f"Удалено системное сообщение с ID {message.id}")
                except Exception as e:
                    logger.error(f"Не удалось удалить сообщение {message.id}: {e}")

# Функция для отправки сообщения через 24 часа
async def ask_continue_inviting(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    chat_id = job_data['chat_id']
    user_id = job_data['user_id']

    message = await context.bot.send_message(
        chat_id=chat_id,
        text="Хотите продолжить добавлять пользователей?",
        reply_markup=generate_yes_no_keyboard()
    )
    context.user_data['last_message_id'] = message.message_id

    # Устанавливаем состояние пользователя
    USER_STATES[user_id] = 'WAITING_RESPONSE'

# Обработка ответа пользователя на вопрос о продолжении
async def handle_continue_inviting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if USER_STATES.get(update.effective_user.id) != 'WAITING_RESPONSE':
        return

    query = update.callback_query
    await query.answer()
    answer = query.data

    if answer == 'yes':
        message = await query.edit_message_text(
            "Продолжить добавлять пользователей из того же файла?",
            reply_markup=generate_yes_no_keyboard()
        )
        context.user_data['last_message_id'] = message.message_id

        # Переходим к следующему состоянию
        USER_STATES[update.effective_user.id] = 'CHOOSE_FILE'
    else:
        message = await query.edit_message_text(
            "Операция завершена.",
            reply_markup=generate_return_button()
        )
        context.user_data['last_message_id'] = message.message_id
        USER_STATES.pop(update.effective_user.id, None)

# Обработка выбора файла для продолжения
async def handle_choose_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if USER_STATES.get(update.effective_user.id) != 'CHOOSE_FILE':
        return

    query = update.callback_query
    await query.answer()
    answer = query.data

    if answer == 'yes':
        # Продолжаем с тем же файлом
        message = await query.edit_message_text(
            "Сколько пользователей добавить в этот раз?",
            reply_markup=generate_back_button()
        )
        context.user_data['last_message_id'] = message.message_id

        # Переходим к состоянию INVITE_COUNT
        USER_STATES[update.effective_user.id] = 'INVITE_COUNT'
    else:
        # Запрашиваем новый файл
        message = await query.edit_message_text(
            "Пожалуйста, отправьте новый файл со списком пользователей для приглашения (формат .txt):",
            reply_markup=generate_back_button()
        )
        context.user_data['last_message_id'] = message.message_id

        # Переходим к состоянию INVITE_FILE
        USER_STATES[update.effective_user.id] = 'INVITE_FILE'

# Функция для обработки кнопки "Назад"
async def go_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await next_step(update, context)
    USER_STATES.pop(update.effective_user.id, None)

# Функция для обработки кнопки "Вернуться в меню"
async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await next_step(update, context)
    USER_STATES.pop(update.effective_user.id, None)

# Обработка выбора функции "Аккаунты"
async def view_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    accounts = os.listdir('accounts')
    user_accounts = [acc for acc in accounts if acc.startswith(f'{user_id}_')]

    if user_accounts:
        buttons = [
            [InlineKeyboardButton(acc.replace(f'{user_id}_', '').replace('.json', ''), callback_data=f"select_account_{acc}")]
            for acc in user_accounts
        ]
        # Удаляем кнопку "Добавить аккаунт" из бесплатной версии, если достигнут лимит
        username = update.effective_user.username
        context.user_data['is_paid'] = is_paid_user(username)
        if context.user_data['is_paid'] or len(user_accounts) < 1:
            buttons.append([InlineKeyboardButton("Добавить аккаунт", callback_data="add_account")])
        buttons.append([InlineKeyboardButton("Вернуться в меню", callback_data="back_to_menu")])
        message = await query.edit_message_text(
            "Доступные аккаунты:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        context.user_data['last_message_id'] = message.message_id
    else:
        message = await query.edit_message_text(
            "Нет подключённых аккаунтов. Хотите добавить новый?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Да", callback_data="add_account")],
                [InlineKeyboardButton("Нет", callback_data="back_to_menu")]
            ])
        )
        context.user_data['last_message_id'] = message.message_id

# Обработка выбора функции "Добавить аккаунт"
async def add_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    username = update.effective_user.username
    context.user_data['is_paid'] = is_paid_user(username)
    if not context.user_data['is_paid']:
        accounts = os.listdir('accounts')
        user_accounts = [acc for acc in accounts if acc.startswith(f'{user_id}_')]
        if len(user_accounts) >= 1:
            message = await query.edit_message_text(
                "В бесплатной версии вы можете добавить только один аккаунт. Приобретите платную версию для снятия ограничений.\n @Rostislavas",
                reply_markup=generate_return_button()
            )
            context.user_data['last_message_id'] = message.message_id
            return

    message = await query.edit_message_text(
        "Введите ваш API ID:",
        reply_markup=generate_back_button()
    )
    context.user_data['last_message_id'] = message.message_id

    # Устанавливаем состояние пользователя
    USER_STATES[update.effective_user.id] = 'API_ID'

# Получение API ID
async def get_api_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if USER_STATES.get(update.effective_user.id) != 'API_ID':
        return

    context.user_data['api_id'] = update.message.text.strip()
    try:
        await update.message.delete()
    except Exception as e:
        logger.error(f"Не удалось удалить сообщение: {e}")

    last_message_id = context.user_data.get('last_message_id')
    message = await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=last_message_id,
        text="Введите ваш API Hash:",
        reply_markup=generate_back_button()
    )
    context.user_data['last_message_id'] = message.message_id

    # Переходим к следующему состоянию
    USER_STATES[update.effective_user.id] = 'API_HASH'

# Получение API Hash
async def get_api_hash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if USER_STATES.get(update.effective_user.id) != 'API_HASH':
        return

    context.user_data['api_hash'] = update.message.text.strip()
    try:
        await update.message.delete()
    except Exception as e:
        logger.error(f"Не удалось удалить сообщение: {e}")

    last_message_id = context.user_data.get('last_message_id')
    message = await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=last_message_id,
        text="Введите ваш номер телефона (в формате +79991234567):",
        reply_markup=generate_back_button()
    )
    context.user_data['last_message_id'] = message.message_id

    # Переходим к следующему состоянию
    USER_STATES[update.effective_user.id] = 'PHONE_NUMBER'

# Получение номера телефона и отправка кода через Pyrogram
async def get_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if USER_STATES.get(update.effective_user.id) != 'PHONE_NUMBER':
        return

    context.user_data['phone_number'] = update.message.text.strip()
    try:
        await update.message.delete()
    except Exception as e:
        logger.error(f"Не удалось удалить сообщение: {e}")

    last_message_id = context.user_data.get('last_message_id')

    try:
        logger.info(
            f"Попытка подключения к Telegram API с номером: {context.user_data['phone_number']}"
        )

        user_id = update.effective_user.id
        phone_number = context.user_data['phone_number']
        session_name = f'sessions/{user_id}_{phone_number}'

        context.user_data['app'] = PyroClient(
            session_name,
            api_id=int(context.user_data['api_id']),
            api_hash=context.user_data['api_hash']
        )

        await context.user_data['app'].connect()

        logger.info("Подключение успешно. Отправляем запрос на код...")
        phone_code_hash = await context.user_data['app'].send_code(
            context.user_data['phone_number']
        )
        context.user_data['phone_code_hash'] = phone_code_hash.phone_code_hash

        logger.info(
            f"Код подтверждения отправлен на номер: {context.user_data['phone_number']} в Telegram!"
        )

        message = await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=last_message_id,
            text="Введите код подтверждения (код придёт в ваше приложение Telegram):",
            reply_markup=generate_digit_keyboard()
        )
        context.user_data['last_message_id'] = message.message_id
        context.user_data['code'] = ""

        # Переходим к следующему состоянию
        USER_STATES[update.effective_user.id] = 'CODE'

    except Exception as e:
        logger.error(f"Ошибка при отправке кода подтверждения: {e}")
        message = await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=last_message_id,
            text=f"Ошибка при отправке кода подтверждения: {e}",
            reply_markup=generate_return_button()
        )
        context.user_data['last_message_id'] = message.message_id
        USER_STATES.pop(update.effective_user.id, None)

# Обработка кода подтверждения
async def get_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if USER_STATES.get(update.effective_user.id) != 'CODE':
        return

    query = update.callback_query
    await query.answer()
    data = query.data

    last_message_id = context.user_data.get('last_message_id')

    if data.isdigit():
        context.user_data['code'] += data
    elif data == "delete":
        context.user_data['code'] = context.user_data['code'][:-1]
    elif data == "submit_code":
        if context.user_data['code']:
            message = await query.edit_message_text("Проверяю код, подождите...")
            context.user_data['last_message_id'] = message.message_id
            try:
                await context.user_data['app'].sign_in(
                    phone_number=context.user_data['phone_number'],
                    phone_code=context.user_data['code'],
                    phone_code_hash=context.user_data['phone_code_hash']
                )
                # Сохраняем данные в файл
                user_id = update.effective_user.id
                phone_number = context.user_data['phone_number']
                account_file = f'accounts/{user_id}_{phone_number}.json'
                user_data = {
                    'phone_number': phone_number,
                    'api_id': context.user_data['api_id'],
                    'api_hash': context.user_data['api_hash'],
                    'session_name': f'sessions/{user_id}_{phone_number}'
                }
                with open(account_file, 'w') as f:
                    json.dump(user_data, f)

                await context.user_data['app'].send_message(
                    "me", "Сессия успешно создана и сохранена!"
                )
                await context.user_data['app'].disconnect()
                del context.user_data['app']  # Удаляем клиента из user_data

                context.user_data['current_account'] = user_data
                context.user_data['session_created'] = True

                message = await query.edit_message_text(
                    "Telegram сессия успешно создана и сохранена!",
                    reply_markup=generate_return_button()
                )
                context.user_data['last_message_id'] = message.message_id
                USER_STATES.pop(update.effective_user.id, None)
                return
            except PyroErrors.SessionPasswordNeeded:
                # Запросить пароль у пользователя
                message = await query.edit_message_text(
                    "Ваша учетная запись защищена двухфакторной аутентификацией. Пожалуйста, введите пароль:",
                    reply_markup=generate_back_button()
                )
                context.user_data['last_message_id'] = message.message_id

                # Переходим к следующему состоянию
                USER_STATES[update.effective_user.id] = 'PASSWORD'
                return
            except Exception as e:
                logger.error(f"Ошибка при авторизации: {e}")
                message = await query.edit_message_text(
                    f"Ошибка: {e}",
                    reply_markup=generate_return_button()
                )
                context.user_data['last_message_id'] = message.message_id
                USER_STATES.pop(update.effective_user.id, None)
                return
        else:
            message = await query.edit_message_text(
                "Вы не ввели код. Пожалуйста, введите код подтверждения:",
                reply_markup=generate_digit_keyboard()
            )
            context.user_data['last_message_id'] = message.message_id
            return
    else:
        pass  # Неизвестное действие

    # Обновляем сообщение с текущим кодом
    message = await query.edit_message_text(
        text=f"Текущий код: {context.user_data['code']}",
        reply_markup=generate_digit_keyboard()
    )
    context.user_data['last_message_id'] = message.message_id

# Получение пароля двухфакторной аутентификации
async def get_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if USER_STATES.get(update.effective_user.id) != 'PASSWORD':
        return

    password = update.message.text.strip()
    try:
        await update.message.delete()
    except Exception as e:
        logger.error(f"Не удалось удалить сообщение: {e}")

    last_message_id = context.user_data.get('last_message_id')

    try:
        await context.user_data['app'].check_password(password=password)
        # Сохраняем данные в файл
        user_id = update.effective_user.id
        phone_number = context.user_data['phone_number']
        account_file = f'accounts/{user_id}_{phone_number}.json'
        user_data = {
            'phone_number': phone_number,
            'api_id': context.user_data['api_id'],
            'api_hash': context.user_data['api_hash'],
            'session_name': f'sessions/{user_id}_{phone_number}'
        }
        with open(account_file, 'w') as f:
            json.dump(user_data, f)

        await context.user_data['app'].send_message(
            "me", "Сессия успешно создана и сохранена!"
        )
        await context.user_data['app'].disconnect()
        del context.user_data['app']  # Удаляем клиента из user_data

        context.user_data['current_account'] = user_data
        context.user_data['session_created'] = True

        message = await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=last_message_id,
            text="Telegram сессия успешно создана и сохранена!",
            reply_markup=generate_return_button()
        )
        context.user_data['last_message_id'] = message.message_id
        USER_STATES.pop(update.effective_user.id, None)
    except Exception as e:
        logger.error(f"Ошибка при вводе пароля: {e}")
        message = await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=last_message_id,
            text=f"Ошибка: {e}",
            reply_markup=generate_return_button()
        )
        context.user_data['last_message_id'] = message.message_id
        USER_STATES.pop(update.effective_user.id, None)

# Обработка выбора аккаунта
async def select_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if data.startswith("select_account_"):
        account_file = data.replace("select_account_", "")
        account_path = os.path.join('accounts', account_file)
        if os.path.exists(account_path):
            # Отключаем и удаляем старый клиент Pyrogram, если он существует
            if 'app' in context.user_data:
                try:
                    await context.user_data['app'].disconnect()
                except:
                    pass
                del context.user_data['app']

            with open(account_path, 'r') as f:
                account_data = json.load(f)
                context.user_data['current_account'] = account_data
                context.user_data['session_created'] = True
                context.user_data['invited_members'] = []  # Очищаем список приглашённых
                message = await query.edit_message_text(
                    f"Выбран аккаунт {account_data['phone_number']}.",
                    reply_markup=generate_return_button()
                )
                context.user_data['last_message_id'] = message.message_id
        else:
            message = await query.edit_message_text(
                "Ошибка: Аккаунт не найден.",
                reply_markup=generate_return_button()
            )
            context.user_data['last_message_id'] = message.message_id

# Обработка выбора функции "Моя подписка"
async def view_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    username = update.effective_user.username
    if is_paid_user(username):
        subscription_info = "У вас активна платная подписка. Вы можете добавлять неограниченное количество аккаунтов и приглашать неограниченное число пользователей."
    else:
        subscription_info = "У вас бесплатная подписка ✨!\n Сейчас вы можете приглашать до 10 пользователей в день.\n\nВ платной версии лимит на количество приглашений исчезнет, и вы сможете добавлять бесконечное количество пользователей и аккаунты  🚀🌐.\n\n Пишите мне, если желаете приобрести платную версию  @Rostislavas👍 \n"

    message = await query.edit_message_text(
        subscription_info,
        reply_markup=generate_return_button()
    )
    context.user_data['last_message_id'] = message.message_id

# Функция для удаления системных сообщений о присоединении в целевых чатах
async def delete_join_messages_in_target_chats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message.chat.id in TARGET_CHAT_IDS and (message.new_chat_members or message.left_chat_member):
        try:
            await message.delete()
        except Exception as e:
            logger.error(f"Не удалось удалить сообщение в чате {message.chat.id}: {e}")

# Добавление команды /admin
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMINS:
        await update.message.reply_text("У вас нет прав для использования этой команды.")
        return

    message = await update.message.reply_text(
        "Выберите действие:",
        reply_markup=generate_admin_menu()
    )
    context.user_data['last_message_id'] = message.message_id

# Обработка меню администратора
async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'admin_add_paid_user':
        message = await query.edit_message_text(
            "Введите @username пользователя, которого нужно добавить в платную версию:",
            reply_markup=generate_back_button()
        )
        context.user_data['last_message_id'] = message.message_id

        # Устанавливаем состояние пользователя
        USER_STATES[update.effective_user.id] = 'ADMIN_ADD_PAID_USER'

    elif data == 'admin_remove_paid_user':
        message = await query.edit_message_text(
            "Введите @username пользователя, которого нужно убрать из платной версии:",
            reply_markup=generate_back_button()
        )
        context.user_data['last_message_id'] = message.message_id

        # Устанавливаем состояние пользователя
        USER_STATES[update.effective_user.id] = 'ADMIN_REMOVE_PAID_USER'

    elif data == 'admin_list_paid_users':
        paid_users = load_paid_users()
        if paid_users:
            user_list = [f"@{user}" for user in paid_users]
            user_list_str = "\n".join(user_list)
            await query.edit_message_text(f"Список платных пользователей:\n{user_list_str}", reply_markup=generate_return_button())
        else:
            await query.edit_message_text("Список платных пользователей пуст.", reply_markup=generate_return_button())
    else:
        await query.edit_message_text("Неверный выбор.", reply_markup=generate_return_button())

# Добавление платного пользователя по никнейму
async def admin_add_paid_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if USER_STATES.get(update.effective_user.id) != 'ADMIN_ADD_PAID_USER':
        return

    username = update.message.text.strip().lstrip('@')
    try:
        await update.message.delete()
    except Exception as e:
        logger.error(f"Не удалось удалить сообщение: {e}")

    last_message_id = context.user_data.get('last_message_id')
    paid_users = load_paid_users()
    if username.lower() not in (user.lower() for user in paid_users):
        paid_users.append(username)
        save_paid_users(paid_users)
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=last_message_id,
            text=f"Пользователь @{username} добавлен в платную версию.",
            reply_markup=generate_return_button()
        )
    else:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=last_message_id,
            text=f"Пользователь @{username} уже имеет платную версию.",
            reply_markup=generate_return_button()
        )

    # Сбрасываем состояние пользователя
    USER_STATES.pop(update.effective_user.id, None)

# Удаление платного пользователя по никнейму
async def admin_remove_paid_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if USER_STATES.get(update.effective_user.id) != 'ADMIN_REMOVE_PAID_USER':
        return

    username = update.message.text.strip().lstrip('@')
    try:
        await update.message.delete()
    except Exception as e:
        logger.error(f"Не удалось удалить сообщение: {e}")

    last_message_id = context.user_data.get('last_message_id')
    paid_users = load_paid_users()
    if username.lower() in (user.lower() for user in paid_users):
        paid_users = [user for user in paid_users if user.lower() != username.lower()]
        save_paid_users(paid_users)
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=last_message_id,
            text=f"Пользователь @{username} удалён из платной версии.",
            reply_markup=generate_return_button()
        )
    else:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=last_message_id,
            text=f"Пользователь @{username} не найден в списке платных.",
            reply_markup=generate_return_button()
        )

    # Сбрасываем состояние пользователя
    USER_STATES.pop(update.effective_user.id, None)

# Обработка нажатий кнопок
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    if data == 'next':
        await next_step(update, context)
    elif data == 'parser':
        await select_parser(update, context)
    elif data == 'inviter':
        await select_inviter(update, context)
    elif data == 'accounts':
        await view_accounts(update, context)
    elif data == 'subscription':
        await view_subscription(update, context)
    elif data == 'instructions':
        await show_instructions(update, context)
    elif data == 'back_to_menu':
        await back_to_menu(update, context)
    elif data == 'back':
        await go_back(update, context)
    elif data.startswith('select_account_'):
        await select_account(update, context)
    elif data == 'add_account':
        await add_account(update, context)
    elif data in ('yes', 'no'):
        if USER_STATES.get(user_id) == 'WAITING_RESPONSE':
            await handle_continue_inviting(update, context)
        elif USER_STATES.get(user_id) == 'CHOOSE_FILE':
            await handle_choose_file(update, context)
    elif data.isdigit() or data in ('delete', 'submit_code'):
        if USER_STATES.get(user_id) == 'CODE':
            await get_code(update, context)
    elif data.startswith('admin_'):
        if user_id in ADMINS:
            await admin_menu_handler(update, context)
    else:
        logger.info(f"Неизвестная команда: {data}")

# Обработка текстовых сообщений
async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_state = USER_STATES.get(update.effective_user.id)

    if user_state == 'PARSE_GROUP':
        await parse_group_members(update, context)
    elif user_state == 'INVITE_GROUP':
        await get_invite_group_link(update, context)
    elif user_state == 'INVITE_FILE':
        await receive_invite_file(update, context)
    elif user_state == 'INVITE_COUNT':
        await get_invite_count(update, context)
    elif user_state == 'API_ID':
        await get_api_id(update, context)
    elif user_state == 'API_HASH':
        await get_api_hash(update, context)
    elif user_state == 'PHONE_NUMBER':
        await get_phone_number(update, context)
    elif user_state == 'PASSWORD':
        await get_password(update, context)
    elif user_state == 'ADMIN_ADD_PAID_USER':
        await admin_add_paid_user(update, context)
    elif user_state == 'ADMIN_REMOVE_PAID_USER':
        await admin_remove_paid_user(update, context)
    else:
        await update.message.reply_text("Пожалуйста, используйте доступные команды или кнопки.")

# Запуск бота
if __name__ == "__main__":
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Обработчики команд
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('admin', admin_command))

    # Обработчик нажатий кнопок
    application.add_handler(CallbackQueryHandler(button_handler))

    # Обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))

    # Обработчики для удаления системных сообщений о присоединении/выходе участников
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, delete_join_messages_in_target_chats))
    application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, delete_join_messages_in_target_chats))

    # Запускаем бота
    application.run_polling()
