import telebot
from telebot import types
import sqlite3
import os
import time
from datetime import datetime
import hashlib
import random
import string

# Bot token
bot = telebot.TeleBot('7758722083:AAFUPC_XfMZ8R_njVQ8qtMeeK6AtG07s-ZY')

# Initialize database
def init_db():
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    
    # Enhanced movies table with title, size, and download count
    c.execute('''CREATE TABLE IF NOT EXISTS movies
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  title TEXT NOT NULL, 
                  description TEXT, 
                  file_id TEXT NOT NULL,
                  file_size INTEGER DEFAULT 0,
                  download_count INTEGER DEFAULT 0,
                  added_date TEXT DEFAULT CURRENT_TIMESTAMP)''')
    
    # Enhanced channels table with channel types
    c.execute('''CREATE TABLE IF NOT EXISTS channels
                 (username TEXT PRIMARY KEY, title TEXT, channel_type TEXT DEFAULT 'regular', 
                  invite_link TEXT, invite_hash TEXT)''')
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id TEXT PRIMARY KEY, username TEXT, first_name TEXT, 
                  last_name TEXT, joined_date TEXT)''')
    
    # Admins table
    c.execute('''CREATE TABLE IF NOT EXISTS admins
                 (user_id TEXT PRIMARY KEY, added_by TEXT, added_date TEXT)''')
    
    # Super users table
    c.execute('''CREATE TABLE IF NOT EXISTS super_users
                 (user_id TEXT PRIMARY KEY, added_by TEXT, added_date TEXT)''')
    
    # Pending join requests table for zayafka channels
    c.execute('''CREATE TABLE IF NOT EXISTS pending_requests
                 (user_id TEXT, channel_username TEXT, request_hash TEXT, 
                  request_date TEXT, PRIMARY KEY (user_id, channel_username))''')
    
    # Add initial admin
    c.execute("INSERT OR IGNORE INTO admins (user_id, added_by, added_date) VALUES (?, ?, ?)",
             ('7445142075', 'system', datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    
    conn.commit()
    conn.close()

# Generate random hash for invite links
def generate_hash():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=16))

# Format file size function
def format_file_size(size_bytes):
    if size_bytes == 0:
        return "0 B"
    size_names = ["B", "KB", "MB", "GB"]
    import math
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_names[i]}"

# User management functions
def register_user(user):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    try:
        c.execute("INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, joined_date) VALUES (?, ?, ?, ?, ?)",
                 (str(user.id), user.username, user.first_name, user.last_name, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    conn.close()

def get_all_users(page=1, per_page=20):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    offset = (page - 1) * per_page
    
    c.execute("SELECT user_id, username, first_name, last_name FROM users LIMIT ? OFFSET ?", (per_page, offset))
    users = c.fetchall()
    
    c.execute("SELECT COUNT(*) FROM users")
    total_count = c.fetchone()[0]
    
    conn.close()
    return users, total_count

def get_user_by_id(user_id):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    c.execute("SELECT user_id, username, first_name, last_name FROM users WHERE user_id = ?", (user_id,))
    user = c.fetchone()
    conn.close()
    return user

# Admin management functions
def is_admin(user_id):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM admins WHERE user_id = ?", (str(user_id),))
    result = c.fetchone() is not None
    conn.close()
    return result

def add_admin(user_id, added_by):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO admins (user_id, added_by, added_date) VALUES (?, ?, ?)",
                 (str(user_id), str(added_by), datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    return success

def remove_admin(user_id):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    c.execute("DELETE FROM admins WHERE user_id = ?", (str(user_id),))
    success = c.rowcount > 0
    conn.commit()
    conn.close()
    return success

def get_all_admins():
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    c.execute("SELECT a.user_id, u.username, u.first_name, u.last_name FROM admins a LEFT JOIN users u ON a.user_id = u.user_id")
    admins = c.fetchall()
    conn.close()
    return admins

# Super user management functions
def is_super_user(user_id):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM super_users WHERE user_id = ?", (str(user_id),))
    result = c.fetchone() is not None
    conn.close()
    return result

def add_super_user(user_id, added_by):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO super_users (user_id, added_by, added_date) VALUES (?, ?, ?)",
                 (str(user_id), str(added_by), datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    return success

def remove_super_user(user_id):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    c.execute("DELETE FROM super_users WHERE user_id = ?", (str(user_id),))
    success = c.rowcount > 0
    conn.commit()
    conn.close()
    return success

def get_all_super_users():
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    c.execute("SELECT s.user_id, u.username, u.first_name, u.last_name FROM super_users s LEFT JOIN users u ON s.user_id = u.user_id")
    super_users = c.fetchall()
    conn.close()
    return super_users

# Enhanced channel management functions
def add_channel(username, title, channel_type='regular'):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    try:
        invite_link = None
        invite_hash = None
        
        # For zayafka channels, create invite link
        if channel_type == 'zayafka':
            try:
                # Create invite link for the channel
                invite_link_obj = bot.create_chat_invite_link(f'@{username}', creates_join_request=True)
                invite_link = invite_link_obj.invite_link
                invite_hash = generate_hash()
            except Exception as e:
                print(f"Error creating invite link for {username}: {e}")
                return False
        
        c.execute("INSERT INTO channels (username, title, channel_type, invite_link, invite_hash) VALUES (?, ?, ?, ?, ?)", 
                 (username, title, channel_type, invite_link, invite_hash))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    return success

def remove_channel(username):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    c.execute("DELETE FROM channels WHERE username = ?", (username,))
    success = c.rowcount > 0
    conn.commit()
    conn.close()
    return success

def get_all_channels():
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    c.execute("SELECT username, title, channel_type, invite_link FROM channels")
    channels = c.fetchall()
    conn.close()
    return channels

def get_channel_by_username(username):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    c.execute("SELECT username, title, channel_type, invite_link, invite_hash FROM channels WHERE username = ?", (username,))
    channel = c.fetchone()
    conn.close()
    return channel

# Pending requests management for zayafka channels
def add_pending_request(user_id, channel_username, request_hash):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    try:
        c.execute("INSERT OR REPLACE INTO pending_requests (user_id, channel_username, request_hash, request_date) VALUES (?, ?, ?, ?)",
                 (str(user_id), channel_username, request_hash, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"Error adding pending request: {e}")
        return False
    finally:
        conn.close()

def check_pending_request(user_id, channel_username):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    c.execute("SELECT request_hash FROM pending_requests WHERE user_id = ? AND channel_username = ?", 
             (str(user_id), channel_username))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def remove_pending_request(user_id, channel_username):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    c.execute("DELETE FROM pending_requests WHERE user_id = ? AND channel_username = ?", 
             (str(user_id), channel_username))
    conn.commit()
    conn.close()

# Enhanced movie management functions
def add_movie(title, description, file_id, file_size=0):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO movies (title, description, file_id, file_size, download_count, added_date) VALUES (?, ?, ?, ?, ?, ?)",
                 (title, description, file_id, file_size, 0, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        success = True
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        success = False
    conn.close()
    return success

def delete_movie_by_id(movie_id):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    c.execute("DELETE FROM movies WHERE id = ?", (movie_id,))
    success = c.rowcount > 0
    conn.commit()
    conn.close()
    return success

def search_movies(query, page=1, per_page=5):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    offset = (page - 1) * per_page
    
    # Search by title (case insensitive)
    c.execute("""SELECT id, title, description, file_id, file_size, download_count 
                 FROM movies WHERE LOWER(title) LIKE LOWER(?) 
                 ORDER BY download_count DESC, id DESC 
                 LIMIT ? OFFSET ?""", 
             (f"%{query}%", per_page, offset))
    movies = c.fetchall()
    
    # Get total count for pagination
    c.execute("SELECT COUNT(*) FROM movies WHERE LOWER(title) LIKE LOWER(?)", (f"%{query}%",))
    total_count = c.fetchone()[0]
    
    conn.close()
    return movies, total_count

def search_movies_for_deletion(query, page=1, per_page=5):
    """Search movies specifically for deletion with pagination"""
    return search_movies(query, page, per_page)

def get_movie_by_id(movie_id):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    c.execute("SELECT id, title, description, file_id, file_size, download_count FROM movies WHERE id = ?", (movie_id,))
    movie = c.fetchone()
    conn.close()
    return movie

def increment_download_count(movie_id):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    c.execute("UPDATE movies SET download_count = download_count + 1 WHERE id = ?", (movie_id,))
    conn.commit()
    conn.close()

def get_top_movies(limit=10):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    c.execute("""SELECT id, title, description, file_id, file_size, download_count 
                 FROM movies ORDER BY download_count DESC LIMIT ?""", (limit,))
    movies = c.fetchall()
    conn.close()
    return movies

def get_random_movie():
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    c.execute("SELECT id, title, description, file_id, file_size, download_count FROM movies ORDER BY RANDOM() LIMIT 1")
    movie = c.fetchone()
    conn.close()
    return movie

def get_all_movies_for_admin(page=1, per_page=5):
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    offset = (page - 1) * per_page
    
    c.execute("""SELECT id, title, description, file_size, download_count, added_date 
                 FROM movies ORDER BY id DESC LIMIT ? OFFSET ?""", (per_page, offset))
    movies = c.fetchall()
    
    c.execute("SELECT COUNT(*) FROM movies")
    total_count = c.fetchone()[0]
    
    conn.close()
    return movies, total_count

# Message broadcasting function
def broadcast_message(message_obj):
    users, total_count = get_all_users(1, 10000)  # Get all users for broadcasting
    successful = 0
    failed = 0
    
    for user_id, _, _, _ in users:
        try:
            # Forward the original message
            if message_obj.forward_from or message_obj.forward_from_chat:
                bot.forward_message(user_id, message_obj.chat.id, message_obj.message_id)
            # Send photo with caption
            elif message_obj.photo:
                bot.send_photo(
                    user_id,
                    message_obj.photo[-1].file_id,
                    caption=message_obj.caption if message_obj.caption else None
                )
            # Send video with caption
            elif message_obj.video:
                bot.send_video(
                    user_id,
                    message_obj.video.file_id,
                    caption=message_obj.caption if message_obj.caption else None
                )
            # Send regular text message
            else:
                bot.send_message(user_id, message_obj.text)
            
            successful += 1
            time.sleep(0.1)  # Avoid hitting rate limits
        except Exception as e:
            failed += 1
            print(f"Failed to send message to {user_id}: {e}")
    
    return successful, failed

# Enhanced subscription check with different channel types
def check_subscription(chat_id):
    # If user is admin or super user, bypass subscription check
    if is_admin(chat_id) or is_super_user(chat_id):
        return True
        
    channels = get_all_channels()
    if not channels:  # If no channels are added, allow access
        return True
    
    unsubscribed_channels = []
    has_unsubscribed_regular = False
    
    for username, title, channel_type, invite_link in channels:
        if channel_type == 'zayafka':
            # Check if user has pending request or is member
            try:
                member = bot.get_chat_member(f'@{username}', chat_id)
                if member.status not in ['member', 'administrator', 'creator']:
                    # Check if there's a pending request
                    pending_hash = check_pending_request(chat_id, username)
                    if not pending_hash:
                        unsubscribed_channels.append((username, title, channel_type, invite_link))
            except Exception as e:
                print(f"Error checking membership for {chat_id} in {username}: {e}")
                unsubscribed_channels.append((username, title, channel_type, invite_link))
        elif channel_type == 'regular':  # regular channel
            try:
                member = bot.get_chat_member(f'@{username}', chat_id)
                if member.status not in ['member', 'administrator', 'creator']:
                    unsubscribed_channels.append((username, title, channel_type, invite_link))
                    has_unsubscribed_regular = True
            except Exception as e:
                print(f"Error checking membership for {chat_id} in {username}: {e}")
                unsubscribed_channels.append((username, title, channel_type, invite_link))
                has_unsubscribed_regular = True
    
    # Add web channels only if user is not subscribed to regular channels
    if has_unsubscribed_regular:
        for username, title, channel_type, invite_link in channels:
            if channel_type == 'web':
                unsubscribed_channels.append((username, title, channel_type, invite_link))
    
    # Store unsubscribed channels for later use
    if unsubscribed_channels:
        return False, unsubscribed_channels
    return True, []

# Get subscription markup with different channel types
def get_subscription_markup(unsubscribed_channels):
    markup = types.InlineKeyboardMarkup()
    
    for username, title, channel_type, invite_link in unsubscribed_channels:
        if channel_type == 'web':
            # Web channels show as external links
            channel_button = types.InlineKeyboardButton(
                f"🌐 {title}", 
                url=invite_link if invite_link else f"https://t.me/{username}"
            )
        elif channel_type == 'zayafka':
            # Zayafka channels use custom invite links
            channel_button = types.InlineKeyboardButton(
                f"🔐 {title} (So'rov yuborish)", 
                url=invite_link if invite_link else f"https://t.me/{username}"
            )
        else:  # regular channel
            channel_button = types.InlineKeyboardButton(
                f"📢 {title}", 
                url=f"https://t.me/{username}"
            )
        markup.add(channel_button)
    
    check_button = types.InlineKeyboardButton("Tekshirish ✅", callback_data="check_subscription")
    markup.add(check_button)
    return markup

# Get main menu for regular users
def get_main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("🔍 Kino qidirish"),
        types.KeyboardButton("🎭 Random kino")
    )
    markup.add(
        types.KeyboardButton("🔥 Top kinolar"),
        types.KeyboardButton("📋 Film buyurtma berish")
    )
    markup.add(
        types.KeyboardButton("📞 Aloqa")
    )
    return markup

# Create pagination markup for search results
def create_search_pagination(query, current_page, total_pages, movies):
    markup = types.InlineKeyboardMarkup()
    
    # Movie buttons
    for movie in movies:
        movie_id, title, description, file_id, file_size, download_count = movie
        size_text = format_file_size(file_size) if file_size > 0 else "N/A"
        button_text = f"🎬 {title[:30]}{'...' if len(title) > 30 else ''} | 📊 {download_count} | 📁 {size_text}"
        markup.add(types.InlineKeyboardButton(button_text, callback_data=f"movie_{movie_id}"))
    
    # Pagination buttons
    nav_buttons = []
    if current_page > 1:
        nav_buttons.append(types.InlineKeyboardButton("⬅️ Oldingi", callback_data=f"search_{query}_{current_page-1}"))
    
    nav_buttons.append(types.InlineKeyboardButton(f"{current_page}/{total_pages}", callback_data="page_info"))
    
    if current_page < total_pages:
        nav_buttons.append(types.InlineKeyboardButton("Keyingi ➡️", callback_data=f"search_{query}_{current_page+1}"))
    
    if nav_buttons:
        markup.row(*nav_buttons)
    
    return markup

# Create pagination for movies list (admin)
def create_movies_list_pagination(current_page, total_pages, movies):
    markup = types.InlineKeyboardMarkup()
    
    # Pagination buttons
    nav_buttons = []
    if current_page > 1:
        nav_buttons.append(types.InlineKeyboardButton("⬅️ Oldingi", callback_data=f"movies_list_{current_page-1}"))
    
    nav_buttons.append(types.InlineKeyboardButton(f"{current_page}/{total_pages}", callback_data="page_info"))
    
    if current_page < total_pages:
        nav_buttons.append(types.InlineKeyboardButton("Keyingi ➡️", callback_data=f"movies_list_{current_page+1}"))
    
    if nav_buttons:
        markup.row(*nav_buttons)
    
    return markup

# Create pagination for movie deletion search
def create_deletion_search_pagination(query, current_page, total_pages, movies):
    markup = types.InlineKeyboardMarkup()
    
    # Movie buttons for deletion
    for movie in movies:
        movie_id, title, description, file_id, file_size, download_count = movie
        size_text = format_file_size(file_size) if file_size > 0 else "N/A"
        button_text = f"❌ {title[:25]}{'...' if len(title) > 25 else ''} | 📊 {download_count} | 📁 {size_text}"
        markup.add(types.InlineKeyboardButton(button_text, callback_data=f"delete_movie_{movie_id}"))
    
    # Pagination buttons
    nav_buttons = []
    if current_page > 1:
        nav_buttons.append(types.InlineKeyboardButton("⬅️ Oldingi", callback_data=f"delete_search_{query}_{current_page-1}"))
    
    nav_buttons.append(types.InlineKeyboardButton(f"{current_page}/{total_pages}", callback_data="page_info"))
    
    if current_page < total_pages:
        nav_buttons.append(types.InlineKeyboardButton("Keyingi ➡️", callback_data=f"delete_search_{query}_{current_page+1}"))
    
    if nav_buttons:
        markup.row(*nav_buttons)
    
    return markup

# Create pagination for users list (admin)
def create_users_pagination(current_page, total_pages):
    markup = types.InlineKeyboardMarkup()
    
    # Pagination buttons
    nav_buttons = []
    if current_page > 1:
        nav_buttons.append(types.InlineKeyboardButton("⬅️ Oldingi", callback_data=f"users_list_{current_page-1}"))
    
    nav_buttons.append(types.InlineKeyboardButton(f"{current_page}/{total_pages}", callback_data="page_info"))
    
    if current_page < total_pages:
        nav_buttons.append(types.InlineKeyboardButton("Keyingi ➡️", callback_data=f"users_list_{current_page+1}"))
    
    if nav_buttons:
        markup.row(*nav_buttons)
    
    return markup

# Callback query handlers
@bot.callback_query_handler(func=lambda call: call.data == "check_subscription")
def check_subscription_callback(call):
    result = check_subscription(call.message.chat.id)
    if isinstance(result, tuple):
        is_subscribed, unsubscribed_channels = result
        if is_subscribed:
            bot.delete_message(call.message.chat.id, call.message.message_id)
            bot.send_message(call.message.chat.id, "🎬 Kinolar botiga xush kelibsiz!", reply_markup=get_main_menu())
        else:
            bot.answer_callback_query(
                call.id,
                "Siz hali barcha kanallarga obuna bo'lmagansiz! ⚠️",
                show_alert=True
            )
    else:
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, "🎬 Kinolar botiga xush kelibsiz!", reply_markup=get_main_menu())

@bot.callback_query_handler(func=lambda call: call.data.startswith("search_"))
def handle_search_pagination(call):
    try:
        parts = call.data.split("_")
        query = parts[1]
        page = int(parts[2])
        
        movies, total_count = search_movies(query, page, 5)
        total_pages = (total_count + 4) // 5  # Ceiling division
        
        if movies:
            text = f"🔍 Qidiruv natijalari: '{query}'\n📊 Jami: {total_count} ta kino\n\n"
            markup = create_search_pagination(query, page, total_pages, movies)
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
        else:
            bot.answer_callback_query(call.id, "Hech narsa topilmadi!")
    except Exception as e:
        bot.answer_callback_query(call.id, "Xatolik yuz berdi!")
        print(f"Search pagination error: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("movies_list_"))
def handle_movies_list_pagination(call):
    try:
        page = int(call.data.split("_")[2])
        movies, total_count = get_all_movies_for_admin(page, 5)
        total_pages = (total_count + 4) // 5
        
        if movies:
            text = f"🎬 <b>Kinolar ro'yxati</b> (Sahifa {page}/{total_pages})\nJami: {total_count} ta kino\n\n"
            
            for i, movie in enumerate(movies, 1):
                movie_id, title, description, file_size, download_count, added_date = movie
                size_text = format_file_size(file_size) if file_size > 0 else "N/A"
                
                text += f"{(page-1)*5 + i}. <b>{title}</b>\n"
                text += f"   📊 {download_count} yuklab olish | 📁 {size_text}\n"
                text += f"   📅 {added_date[:10]}\n\n"
            
            markup = create_movies_list_pagination(page, total_pages, movies)
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, 
                                parse_mode='HTML', reply_markup=markup)
        else:
            bot.answer_callback_query(call.id, "Kinolar topilmadi!")
    except Exception as e:
        bot.answer_callback_query(call.id, "Xatolik yuz berdi!")
        print(f"Movies list pagination error: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_search_"))
def handle_delete_search_pagination(call):
    try:
        parts = call.data.split("_")
        query = parts[2]
        page = int(parts[3])
        
        movies, total_count = search_movies_for_deletion(query, page, 5)
        total_pages = (total_count + 4) // 5
        
        if movies:
            text = f"🗑 O'chirish uchun qidiruv: '{query}'\n📊 Jami: {total_count} ta kino\nSahifa: {page}/{total_pages}\n\n"
            markup = create_deletion_search_pagination(query, page, total_pages, movies)
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
        else:
            bot.answer_callback_query(call.id, "Hech narsa topilmadi!")
    except Exception as e:
        bot.answer_callback_query(call.id, "Xatolik yuz berdi!")
        print(f"Delete search pagination error: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("users_list_"))
def handle_users_list_pagination(call):
    try:
        page = int(call.data.split("_")[2])
        users, total_count = get_all_users(page, 20)
        total_pages = (total_count + 19) // 20
        
        if users:
            text = f"👥 <b>Foydalanuvchilar ro'yxati</b> (Sahifa {page}/{total_pages})\nJami: {total_count} ta foydalanuvchi\n\n"
            
            for i, (user_id, username, first_name, last_name) in enumerate(users, 1):
                display_name = first_name or username or user_id
                text += f"{(page-1)*20 + i}. {display_name} ({user_id})\n"
            
            markup = create_users_pagination(page, total_pages)
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, 
                                parse_mode='HTML', reply_markup=markup)
        else:
            bot.answer_callback_query(call.id, "Foydalanuvchilar topilmadi!")
    except Exception as e:
        bot.answer_callback_query(call.id, "Xatolik yuz berdi!")
        print(f"Users list pagination error: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("movie_"))
def handle_movie_selection(call):
    try:
        movie_id = int(call.data.split("_")[1])
        movie = get_movie_by_id(movie_id)
        
        if movie:
            movie_id, title, description, file_id, file_size, download_count = movie
            
            # Increment download count
            increment_download_count(movie_id)
            
            # Format caption
            size_text = format_file_size(file_size) if file_size > 0 else "Noma'lum"
            caption = f"🎬 <b>{title}</b>\n\n"
            if description:
                caption += f"📝 {description}\n\n"
            caption += f"📁 Hajmi: {size_text}\n"
            caption += f"⬇️ Yuklab olishlar: {download_count + 1}"
            
            try:
                bot.send_video(call.message.chat.id, file_id, caption=caption, parse_mode='HTML')
                bot.answer_callback_query(call.id, f"✅ '{title}' yuborildi!")
            except Exception as e:
                bot.answer_callback_query(call.id, "Video yuborishda xatolik!")
                print(f"Error sending video: {e}")
        else:
            bot.answer_callback_query(call.id, "Kino topilmadi!")
    except Exception as e:
        bot.answer_callback_query(call.id, "Xatolik yuz berdi!")
        print(f"Movie selection error: {e}")

# Add callback handler for movie deletion
@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_movie_"))
def handle_movie_deletion(call):
    try:
        movie_id = int(call.data.split("_")[2])
        movie = get_movie_by_id(movie_id)
        
        if movie:
            movie_id, title, description, file_id, file_size, download_count = movie
            if delete_movie_by_id(movie_id):
                bot.answer_callback_query(call.id, f"✅ '{title}' o'chirildi!")
                bot.edit_message_text(f"✅ Kino '{title}' muvaffaqiyatli o'chirildi!", call.message.chat.id, call.message.message_id)
            else:
                bot.answer_callback_query(call.id, "❌ O'chirishda xatolik!")
        else:
            bot.answer_callback_query(call.id, "❌ Kino topilmadi!")
    except Exception as e:
        bot.answer_callback_query(call.id, "❌ Xatolik yuz berdi!")
        print(f"Movie deletion error: {e}")

# Handle chat join requests for zayafka channels
@bot.chat_join_request_handler()
def handle_join_request(join_request):
    user_id = join_request.from_user.id
    chat_id = join_request.chat.id
    
    try:
        # Get chat info to find channel username
        chat_info = bot.get_chat(chat_id)
        channel_username = chat_info.username
        
        if channel_username:
            # Check if this is a zayafka channel
            channel_info = get_channel_by_username(channel_username)
            if channel_info and channel_info[2] == 'zayafka':  # channel_type is zayafka
                # Check if user has pending request from our bot
                pending_hash = check_pending_request(user_id, channel_username)
                if pending_hash:
                    # Approve the request automatically
                    bot.approve_chat_join_request(chat_id, user_id)
                    # Remove from pending requests
                    remove_pending_request(user_id, channel_username)
                    print(f"Auto-approved join request for user {user_id} in channel {channel_username}")
                else:
                    # Decline the request (user didn't come through our bot)
                    bot.decline_chat_join_request(chat_id, user_id)
                    print(f"Declined join request for user {user_id} in channel {channel_username} - no pending request")
    except Exception as e:
        print(f"Error handling join request: {e}")

# Get cancel markup
def get_cancel_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(types.KeyboardButton("❌ Bekor qilish"))
    return markup

# Start command handler
@bot.message_handler(commands=['start'])
def start(message):
    # Register user in database
    register_user(message.from_user)
    
    result = check_subscription(message.chat.id)
    if isinstance(result, tuple):
        is_subscribed, unsubscribed_channels = result
        if not is_subscribed:
            markup = get_subscription_markup(unsubscribed_channels)
            bot.send_message(
                message.chat.id, 
                "Bot ishlashi uchun barcha kanallarga obuna bo'ling! 🔔", 
                reply_markup=markup
            )
            
            # For zayafka channels, add pending requests
            for username, title, channel_type, invite_link in unsubscribed_channels:
                if channel_type == 'zayafka':
                    request_hash = generate_hash()
                    add_pending_request(message.chat.id, username, request_hash)
            return

    if is_admin(message.chat.id):
        show_admin_menu(message.chat.id)
    else:
        welcome_text = "🎬 Kinolar botiga xush kelibsiz!\n\n"
        welcome_text += "🔍 Kino qidirish - Kino nomini yozing\n"
        welcome_text += "🎭 Random kino - Tasodifiy kino olish\n"  
        welcome_text += "🔥 Top kinolar - Eng ko'p yuklangan kinolar\n"
        welcome_text += "📋 Film buyurtma berish - Kerakli filmni so'rash"
        
        bot.send_message(message.chat.id, welcome_text, reply_markup=get_main_menu())

# Admin command handler
@bot.message_handler(commands=['admin'])
def admin_command(message):
    if is_admin(message.chat.id):
        show_admin_menu(message.chat.id)
    else:
        bot.send_message(message.chat.id, "Bu buyruq faqat adminlar uchun! ⛔")

# Admin menu
def show_admin_menu(chat_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    # Movie management buttons
    add_movie_btn = types.KeyboardButton("Kino qo'shish 📥")
    delete_movie_btn = types.KeyboardButton("Kino o'chirish 🗑")
    movies_list_btn = types.KeyboardButton("Kinolar ro'yxati 🎬")
    
    # Channel management buttons
    add_channel_btn = types.KeyboardButton("Kanal qo'shish ➕")
    remove_channel_btn = types.KeyboardButton("Kanal o'chirish ➖")
    
    # User management buttons
    admin_mgmt_btn = types.KeyboardButton("Admin boshqaruvi 👨‍💼")
    super_user_btn = types.KeyboardButton("Super user boshqaruvi 👑")
    
    # Messaging buttons
    broadcast_btn = types.KeyboardButton("Reklama yuborish 📢")
    direct_msg_btn = types.KeyboardButton("Xabar yuborish ✉️")
    
    # List buttons
    channels_btn = types.KeyboardButton("Kanallar 📋")
    users_btn = types.KeyboardButton("Userlar 👥")
    stats_btn = types.KeyboardButton("Statistika 📊")
    
    # Database button
    db_btn = types.KeyboardButton("Kinolar bazasi 💾")
    
    # Add all buttons to markup
    markup.add(
        add_movie_btn, delete_movie_btn,
        movies_list_btn, add_channel_btn,
        remove_channel_btn, admin_mgmt_btn,
        super_user_btn, broadcast_btn,
        direct_msg_btn, channels_btn,
        users_btn, stats_btn,
        db_btn
    )
    
    bot.send_message(chat_id, "Admin panel 👨‍💼", reply_markup=markup)

# Regular user message handler
@bot.message_handler(func=lambda message: not is_admin(message.chat.id))
def handle_user_messages(message):
    register_user(message.from_user)
    
    # Check subscription for non-admin users
    result = check_subscription(message.chat.id)
    if isinstance(result, tuple):
        is_subscribed, unsubscribed_channels = result
        if not is_subscribed:
            markup = get_subscription_markup(unsubscribed_channels)
            bot.send_message(
                message.chat.id, 
                "Bot ishlashi uchun barcha kanallarga obuna bo'ling! 🔔", 
                reply_markup=markup
            )
            
            # For zayafka channels, add pending requests
            for username, title, channel_type, invite_link in unsubscribed_channels:
                if channel_type == 'zayafka':
                    request_hash = generate_hash()
                    add_pending_request(message.chat.id, username, request_hash)
            return

    if message.text == "🔍 Kino qidirish":
        msg = bot.send_message(
            message.chat.id,
            "🔍 Qidirmoqchi bo'lgan kino nomini yozing:\n\n"
            "Masalan: 'Avengers', 'Titanic', 'Avatar' va h.k."
        )
        bot.register_next_step_handler(msg, process_search_query)
        
    elif message.text == "🎭 Random kino":
        movie = get_random_movie()
        if movie:
            movie_id, title, description, file_id, file_size, download_count = movie
            increment_download_count(movie_id)
            
            size_text = format_file_size(file_size) if file_size > 0 else "Noma'lum"
            caption = f"🎭 <b>Random kino: {title}</b>\n\n"
            if description:
                caption += f"📝 {description}\n\n"
            caption += f"📁 Hajmi: {size_text}\n"
            caption += f"⬇️ Yuklab olishlar: {download_count + 1}"
            
            try:
                bot.send_video(message.chat.id, file_id, caption=caption, parse_mode='HTML')
            except Exception as e:
                bot.send_message(message.chat.id, "Video yuborishda xatolik! ⚠️")
                print(f"Error sending random movie: {e}")
        else:
            bot.send_message(message.chat.id, "Hozircha kinolar bazasi bo'sh! 😔")
            
    elif message.text == "🔥 Top kinolar":
        top_movies = get_top_movies(10)
        if top_movies:
            text = "🔥 <b>Top kinolar (eng ko'p yuklangan)</b>\n\n"
            
            markup = types.InlineKeyboardMarkup()
            for i, movie in enumerate(top_movies, 1):
                movie_id, title, description, file_id, file_size, download_count = movie
                size_text = format_file_size(file_size) if file_size > 0 else "N/A"
                
                text += f"{i}. <b>{title}</b>\n"
                text += f"   📊 {download_count} ta yuklab olish | 📁 {size_text}\n\n"
                
                button_text = f"{i}. {title[:25]}{'...' if len(title) > 25 else ''}"
                markup.add(types.InlineKeyboardButton(button_text, callback_data=f"movie_{movie_id}"))
            
            bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=markup)
        else:
            bot.send_message(message.chat.id, "Hozircha kinolar bazasi bo'sh! 😔")

    elif message.text == "📋 Film buyurtma berish":
        # Get user's name
        user_name = message.from_user.first_name or message.from_user.username or "Foydalanuvchi"
        
        # Create message text
        order_text = f"Xurmatli {user_name}, agar film buyurtma berishni istasangiz pastdagi adminmizga filmdan lavha yoki nomini yuboring!"
        
        # Create admin button
        markup = types.InlineKeyboardMarkup()
        admin_button = types.InlineKeyboardButton("👨‍💼 Admin", url="https://t.me/jurayev_r07")
        markup.add(admin_button)
        
        bot.send_message(message.chat.id, order_text, reply_markup=markup)
            
    elif message.text == "📞 Aloqa":
        contact_text = "📞 <b>Bog'lanish uchun</b>\n\n"
        contact_text += "📱 Telegram: @jurayev_r07\n"
        
        bot.send_message(message.chat.id, contact_text, parse_mode='HTML')
        
    else:
        # Try to search for movies with the input text
        process_search_query(message)

def process_search_query(message):
    if not message.text:
        return
        
    query = message.text.strip()
    if len(query) < 2:
        bot.send_message(message.chat.id, "Kamida 2 ta harf yozing! 📝")
        return
    
    movies, total_count = search_movies(query, 1, 5)
    total_pages = (total_count + 4) // 5  # Ceiling division
    
    if movies:
        text = f"🔍 Qidiruv natijalari: '{query}'\n📊 Jami: {total_count} ta kino\n\n"
        markup = create_search_pagination(query, 1, total_pages, movies)
        bot.send_message(message.chat.id, text, reply_markup=markup)
    else:
        suggestion_text = f"🔍 '{query}' bo'yicha hech narsa topilmadi! 😔\n\n"
        suggestion_text += "💡 <b>Maslahatlar:</b>\n"
        suggestion_text += "• Kino nomini to'liq yozing\n"
        suggestion_text += "• Inglizcha nomini ham sinab ko'ring\n"
        suggestion_text += "• Imlo xatolarini tekshiring\n\n"
        suggestion_text += "📝 Agar kerakli kino yo'q bo'lsa, admin bilan bog'laning!"
        
        bot.send_message(message.chat.id, suggestion_text, parse_mode='HTML')

# Admin menu handler
@bot.message_handler(func=lambda message: is_admin(message.chat.id))
def handle_admin_commands(message):
    if message.text == "❌ Bekor qilish":
        show_admin_menu(message.chat.id)
        return
        
    if message.text == "Kino qo'shish 📥":
        msg = bot.send_message(
            message.chat.id,
            "Kino video faylini yuboring 🎥",
            reply_markup=get_cancel_markup()
        )
        bot.register_next_step_handler(msg, process_movie_file)
        
    elif message.text == "Kino o'chirish 🗑":
        msg = bot.send_message(
            message.chat.id,
            "O'chirmoqchi bo'lgan kino nomini yozing 📝\n(Kino nomining bir qismini yoza olasiz)",
            reply_markup=get_cancel_markup()
        )
        bot.register_next_step_handler(msg, process_movie_deletion_search)
            
    elif message.text == "Kinolar ro'yxati 🎬":
        movies, total_count = get_all_movies_for_admin(1, 5)
        if movies:
            total_pages = (total_count + 4) // 5
            text = f"🎬 <b>Kinolar ro'yxati</b> (Sahifa 1/{total_pages})\nJami: {total_count} ta kino\n\n"
            
            for i, movie in enumerate(movies, 1):
                movie_id, title, description, file_size, download_count, added_date = movie
                size_text = format_file_size(file_size) if file_size > 0 else "N/A"
                
                text += f"{i}. <b>{title}</b>\n"
                text += f"   📊 {download_count} yuklab olish | 📁 {size_text}\n"
                text += f"   📅 {added_date[:10]}\n\n"
            
            markup = create_movies_list_pagination(1, total_pages, movies)
            bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=markup)
        else:
            bot.send_message(message.chat.id, "Kinolar bazasi bo'sh! ⚠️")
            
    elif message.text == "Statistika 📊":
        conn = sqlite3.connect('movies.db')
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) FROM movies")
        movies_count = c.fetchone()[0]
        
        c.execute("SELECT SUM(download_count) FROM movies")
        total_downloads = c.fetchone()[0] or 0
        
        c.execute("SELECT SUM(file_size) FROM movies")
        total_size = c.fetchone()[0] or 0
        
        users, total_users_count = get_all_users(1, 10000)
        
        conn.close()
        
        stats_text = "📊 <b>Bot statistikasi</b>\n\n"
        stats_text += f"🎬 Jami kinolar: <b>{movies_count}</b>\n"
        stats_text += f"👥 Foydalanuvchilar: <b>{total_users_count}</b>\n"
        stats_text += f"⬇️ Jami yuklab olishlar: <b>{total_downloads}</b>\n"
        stats_text += f"💾 Jami hajm: <b>{format_file_size(total_size)}</b>\n"
        
        if movies_count > 0:
            stats_text += f"📊 O'rtacha yuklab olish: <b>{total_downloads // movies_count}</b>"
        
        bot.send_message(message.chat.id, stats_text, parse_mode='HTML')
    
    elif message.text == "Kanal qo'shish ➕":
        # Show channel type selection
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
        markup.add(
            types.KeyboardButton("📢 Oddiy kanal"),
            types.KeyboardButton("🌐 Web kanal"),
            types.KeyboardButton("🔐 Zayafka kanal"),
            types.KeyboardButton("❌ Bekor qilish")
        )
        msg = bot.send_message(
            message.chat.id,
            "Kanal turini tanlang:\n\n"
            "📢 Oddiy kanal - Telegram kanal (obuna tekshiriladi)\n"
            "🌐 Web kanal - Instagram/Sayt havolasi (tekshirilmaydi)\n"
            "🔐 Zayafka kanal - Qo'shilish so'rovi orqali kanal",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, process_channel_type_selection)
        
    elif message.text == "Kanal o'chirish ➖":
        channels = get_all_channels()
        if not channels:
            bot.send_message(message.chat.id, "Kanallar ro'yxati bo'sh! ⚠️")
            return
            
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
        for username, title, channel_type, invite_link in channels:
            type_emoji = "🌐" if channel_type == "web" else "🔐" if channel_type == "zayafka" else "📢"
            markup.add(types.KeyboardButton(f"❌ {type_emoji} {title} (@{username})"))
        markup.add(types.KeyboardButton("🔙 Orqaga"))
        
        bot.send_message(
            message.chat.id,
            "O'chirmoqchi bo'lgan kanalni tanlang:",
            reply_markup=markup
        )
        
    elif message.text.startswith("❌ ") and "(@" in message.text and ")" in message.text:
        # Extract username from the button text
        username = message.text.split("(@")[1].split(")")[0]
        if remove_channel(username):
            bot.send_message(message.chat.id, "Kanal muvaffaqiyatli o'chirildi ✅")
        else:
            bot.send_message(message.chat.id, "Xatolik yuz berdi ⚠️")
        show_admin_menu(message.chat.id)
        
    elif message.text == "Kanallar 📋":
        channels = get_all_channels()
        if not channels:
            text = "Kanallar ro'yxati bo'sh 📝"
        else:
            text = "Kanallar ro'yxati 📝:\n\n"
            for i, (username, title, channel_type, invite_link) in enumerate(channels, 1):
                type_emoji = "🌐" if channel_type == "web" else "🔐" if channel_type == "zayafka" else "📢"
                text += f"{i}. {type_emoji} {title} (@{username}) - {channel_type}\n"
        bot.send_message(message.chat.id, text)
        
    elif message.text == "Admin boshqaruvi 👨‍💼":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add(
            types.KeyboardButton("Admin qo'shish ➕"),
            types.KeyboardButton("Admin o'chirish ➖"),
            types.KeyboardButton("Adminlar ro'yxati 📋"),
            types.KeyboardButton("🔙 Orqaga")
        )
        bot.send_message(message.chat.id, "Admin boshqaruv paneli 👨‍💼", reply_markup=markup)
        
    elif message.text == "Admin qo'shish ➕":
        msg = bot.send_message(
            message.chat.id,
            "Yangi admin ID raqamini kiriting 🔢",
            reply_markup=get_cancel_markup()
        )
        bot.register_next_step_handler(msg, process_add_admin)
        
    elif message.text == "Admin o'chirish ➖":
        admins = get_all_admins()
        if not admins:
            bot.send_message(message.chat.id, "Adminlar ro'yxati bo'sh! ⚠️")
            return
            
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
        for admin_id, username, first_name, last_name in admins:
            display_name = first_name or username or admin_id
            markup.add(types.KeyboardButton(f"❌ {display_name} ({admin_id})"))
        markup.add(types.KeyboardButton("🔙 Orqaga"))
        
        bot.send_message(
            message.chat.id,
            "O'chirmoqchi bo'lgan adminni tanlang:",
            reply_markup=markup
        )
        
    elif message.text == "Adminlar ro'yxati 📋":
        admins = get_all_admins()
        if not admins:
            text = "Adminlar ro'yxati bo'sh 📝"
        else:
            text = "Adminlar ro'yxati 📝:\n\n"
            for i, (admin_id, username, first_name, last_name) in enumerate(admins, 1):
                display_name = first_name or username or admin_id
                text += f"{i}. {display_name} ({admin_id})\n"
        bot.send_message(message.chat.id, text)
        
    elif message.text == "Super user boshqaruvi 👑":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add(
            types.KeyboardButton("Super user qo'shish ➕"),
            types.KeyboardButton("Super user o'chirish ➖"),
            types.KeyboardButton("Super userlar ro'yxati 📋"),
            types.KeyboardButton("🔙 Orqaga")
        )
        bot.send_message(message.chat.id, "Super user boshqaruv paneli 👑", reply_markup=markup)
        
    elif message.text == "Super user qo'shish ➕":
        msg = bot.send_message(
            message.chat.id,
            "Yangi super user ID raqamini kiriting 🔢",
            reply_markup=get_cancel_markup()
        )
        bot.register_next_step_handler(msg, process_add_super_user)
        
    elif message.text == "Super user o'chirish ➖":
        super_users = get_all_super_users()
        if not super_users:
            bot.send_message(message.chat.id, "Super userlar ro'yxati bo'sh! ⚠️")
            return
            
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
        for user_id, username, first_name, last_name in super_users:
            display_name = first_name or username or user_id
            markup.add(types.KeyboardButton(f"❌ {display_name} ({user_id})"))
        markup.add(types.KeyboardButton("🔙 Orqaga"))
        
        bot.send_message(
            message.chat.id,
            "O'chirmoqchi bo'lgan super userni tanlang:",
            reply_markup=markup
        )
        
    elif message.text == "Super userlar ro'yxati 📋":
        super_users = get_all_super_users()
        if not super_users:
            text = "Super userlar ro'yxati bo'sh 📝"
        else:
            text = "Super userlar ro'yxati 📝:\n\n"
            for i, (user_id, username, first_name, last_name) in enumerate(super_users, 1):
                display_name = first_name or username or user_id
                text += f"{i}. {display_name} ({user_id})\n"
        bot.send_message(message.chat.id, text)
        
    elif message.text == "Reklama yuborish 📢":
        msg = bot.send_message(
            message.chat.id,
            "Yubormoqchi bo'lgan xabaringizni yuboring (rasm, video, forward xabar yoki matn) 📝",
            reply_markup=get_cancel_markup()
        )
        bot.register_next_step_handler(msg, process_broadcast)
        
    elif message.text == "Xabar yuborish ✉️":
        msg = bot.send_message(
            message.chat.id,
            "Xabar yubormoqchi bo'lgan foydalanuvchi ID raqamini kiriting 🔢",
            reply_markup=get_cancel_markup()
        )
        bot.register_next_step_handler(msg, process_direct_message_step1)
        
    elif message.text == "Userlar 👥":
        users, total_count = get_all_users(1, 20)
        if not users:
            text = "Foydalanuvchilar ro'yxati bo'sh 📝"
            bot.send_message(message.chat.id, text)
        else:
            total_pages = (total_count + 19) // 20
            text = f"👥 <b>Foydalanuvchilar ro'yxati</b> (Sahifa 1/{total_pages})\nJami: {total_count} ta foydalanuvchi\n\n"
            
            for i, (user_id, username, first_name, last_name) in enumerate(users, 1):
                display_name = first_name or username or user_id
                text += f"{i}. {display_name} ({user_id})\n"
            
            markup = create_users_pagination(1, total_pages)
            bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=markup)
        
    elif message.text == "Kinolar bazasi 💾":
        try:
            with open('movies.db', 'rb') as db_file:
                bot.send_document(
                    message.chat.id,
                    db_file,
                    caption="Kinolar bazasi 💾"
                )
        except Exception as e:
            bot.send_message(message.chat.id, "Bazani yuklashda xatolik yuz berdi ⚠️")
            
    elif message.text == "🔙 Orqaga":
        show_admin_menu(message.chat.id)
        
    # Handle admin and super user removal
    elif message.text.startswith("❌ ") and "(" in message.text and ")" in message.text:
        # Extract user ID from the button text
        user_id = message.text.split("(")[1].split(")")[0]
        
        # Try to remove admin
        if remove_admin(user_id):
            bot.send_message(message.chat.id, "Admin muvaffaqiyatli o'chirildi ✅")
            try:
                bot.send_message(user_id, "Sizning admin huquqingiz bekor qilindi ⚠️")
            except:
                pass
        # Try to remove super user
        elif remove_super_user(user_id):
            bot.send_message(message.chat.id, "Super foydalanuvchi muvaffaqiyatli o'chirildi ✅")
            try:
                bot.send_message(user_id, "Sizning super foydalanuvchi huquqingiz bekor qilindi ⚠️")
            except:
                pass
        else:
            bot.send_message(message.chat.id, "Xatolik yuz berdi ⚠️")
        
        show_admin_menu(message.chat.id)

# Movie deletion search handler
def process_movie_deletion_search(message):
    if message.text == "❌ Bekor qilish":
        bot.send_message(message.chat.id, "Amal bekor qilindi ❌")
        show_admin_menu(message.chat.id)
        return
        
    query = message.text.strip()
    if len(query) < 2:
        bot.send_message(message.chat.id, "Kamida 2 ta harf yozing! 📝")
        show_admin_menu(message.chat.id)
        return
    
    movies, total_count = search_movies_for_deletion(query, 1, 5)
    total_pages = (total_count + 4) // 5
    
    if movies:
        text = f"🗑 O'chirish uchun qidiruv: '{query}'\n📊 Jami: {total_count} ta kino\nSahifa: 1/{total_pages}\n\n"
        markup = create_deletion_search_pagination(query, 1, total_pages, movies)
        bot.send_message(message.chat.id, text, reply_markup=markup)
    else:
        suggestion_text = f"🔍 '{query}' bo'yicha hech narsa topilmadi! 😔\n\n"
        suggestion_text += "💡 Boshqa nom bilan qidirib ko'ring yoki to'liq nom kiriting."
        bot.send_message(message.chat.id, suggestion_text)
        show_admin_menu(message.chat.id)

# Movie management handlers
def process_movie_file(message):
    if message.text == "❌ Bekor qilish":
        bot.send_message(message.chat.id, "Amal bekor qilindi ❌")
        show_admin_menu(message.chat.id)
        return
        
    if message.content_type != 'video':
        bot.send_message(message.chat.id, "Iltimos, video fayl yuboring! ⚠️")
        show_admin_menu(message.chat.id)
        return

    file_id = message.video.file_id
    file_size = message.video.file_size if hasattr(message.video, 'file_size') else 0
    
    msg = bot.send_message(
        message.chat.id,
        f"Kino nomi kiriting 🎬\n\n📁 Fayl hajmi: {format_file_size(file_size)}",
        reply_markup=get_cancel_markup()
    )
    bot.register_next_step_handler(msg, process_movie_title, file_id, file_size)

def process_movie_title(message, file_id, file_size):
    if message.text == "❌ Bekor qilish":
        bot.send_message(message.chat.id, "Amal bekor qilindi ❌")
        show_admin_menu(message.chat.id)
        return
        
    title = message.text.strip()
    msg = bot.send_message(
        message.chat.id,
        f"Kino haqida tavsif kiriting 📝\n\n🎬 Nomi: {title}",
        reply_markup=get_cancel_markup()
    )
    bot.register_next_step_handler(msg, save_new_movie, title, file_id, file_size)

def save_new_movie(message, title, file_id, file_size):
    if message.text == "❌ Bekor qilish":
        bot.send_message(message.chat.id, "Amal bekor qilindi ❌")
        show_admin_menu(message.chat.id)
        return
        
    description = message.text.strip()
    if add_movie(title, description, file_id, file_size):
        success_text = f"✅ Kino muvaffaqiyatli qo'shildi!\n\n"
        success_text += f"🎬 <b>{title}</b>\n"
        success_text += f"📝 {description}\n"
        success_text += f"📁 Hajmi: {format_file_size(file_size)}"
        
        bot.send_message(message.chat.id, success_text, parse_mode='HTML')
    else:
        bot.send_message(message.chat.id, "Kinoni qo'shishda xatolik yuz berdi! ⚠️")
    show_admin_menu(message.chat.id)

def process_channel_type_selection(message):
    if message.text == "❌ Bekor qilish":
        bot.send_message(message.chat.id, "Amal bekor qilindi ❌")
        show_admin_menu(message.chat.id)
        return
    
    channel_type = None
    if message.text == "📢 Oddiy kanal":
        channel_type = "regular"
    elif message.text == "🌐 Web kanal":
        channel_type = "web"
    elif message.text == "🔐 Zayafka kanal":
        channel_type = "zayafka"
    else:
        bot.send_message(message.chat.id, "Noto'g'ri tanlov! ⚠️")
        show_admin_menu(message.chat.id)
        return
    
    if channel_type == "web":
        msg = bot.send_message(
            message.chat.id,
            "Web kanal havolasini kiriting (Instagram, sayt va h.k.) 🌐",
            reply_markup=get_cancel_markup()
        )
        bot.register_next_step_handler(msg, process_web_channel_link, channel_type)
    else:
        msg = bot.send_message(
            message.chat.id,
            f"{'Zayafka' if channel_type == 'zayafka' else 'Oddiy'} kanal usernameni kiriting (@ belgisisiz) 📝",
            reply_markup=get_cancel_markup()
        )
        bot.register_next_step_handler(msg, process_channel_username, channel_type)

def process_web_channel_link(message, channel_type):
    if message.text == "❌ Bekor qilish":
        bot.send_message(message.chat.id, "Amal bekor qilindi ❌")
        show_admin_menu(message.chat.id)
        return
        
    web_link = message.text.strip()
    msg = bot.send_message(
        message.chat.id,
        "Web kanal nomini kiriting 📝",
        reply_markup=get_cancel_markup()
    )
    bot.register_next_step_handler(msg, process_web_channel_title, channel_type, web_link)

def process_web_channel_title(message, channel_type, web_link):
    if message.text == "❌ Bekor qilish":
        bot.send_message(message.chat.id, "Amal bekor qilindi ❌")
        show_admin_menu(message.chat.id)
        return
        
    title = message.text.strip()
    # For web channels, use a unique identifier as username
    username = f"web_{int(time.time())}"
    
    conn = sqlite3.connect('movies.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO channels (username, title, channel_type, invite_link) VALUES (?, ?, ?, ?)", 
                 (username, title, channel_type, web_link))
        conn.commit()
        bot.send_message(message.chat.id, "Web kanal muvaffaqiyatli qo'shildi ✅")
    except sqlite3.IntegrityError:
        bot.send_message(message.chat.id, "Xatolik yuz berdi! ⚠️")
    finally:
        conn.close()
    
    show_admin_menu(message.chat.id)

def process_channel_username(message, channel_type):
    if message.text == "❌ Bekor qilish":
        bot.send_message(message.chat.id, "Amal bekor qilindi ❌")
        show_admin_menu(message.chat.id)
        return
        
    username = message.text.strip()
    msg = bot.send_message(
        message.chat.id,
        "Kanal nomini kiriting 📝",
        reply_markup=get_cancel_markup()
    )
    bot.register_next_step_handler(msg, process_channel_title, username, channel_type)

def process_channel_title(message, username, channel_type):
    if message.text == "❌ Bekor qilish":
        bot.send_message(message.chat.id, "Amal bekor qilindi ❌")
        show_admin_menu(message.chat.id)
        return
        
    title = message.text.strip()
    if add_channel(username, title, channel_type):
        type_name = "Zayafka" if channel_type == "zayafka" else "Oddiy"
        bot.send_message(message.chat.id, f"{type_name} kanal muvaffaqiyatli qo'shildi ✅")
    else: 
        bot.send_message(message.chat.id, "Bu kanal allaqachon mavjud yoki xatolik yuz berdi! ⚠️")
    show_admin_menu(message.chat.id)

# Admin management handlers
def process_add_admin(message):
    if message.text == "❌ Bekor qilish":
        bot.send_message(message.chat.id, "Amal bekor qilindi ❌")
        show_admin_menu(message.chat.id)
        return
        
    new_admin_id = message.text.strip()
    
    # Check if user exists
    if not get_user_by_id(new_admin_id):
        bot.send_message(message.chat.id, "Bu foydalanuvchi botdan foydalanmagan! Avval bot bilan muloqot qilishi kerak. ⚠️")
        show_admin_menu(message.chat.id)
        return
    
    # Check if already admin
    if is_admin(new_admin_id):
        bot.send_message(message.chat.id, "Bu foydalanuvchi allaqachon admin! ⚠️")
        show_admin_menu(message.chat.id)
        return
    
    if add_admin(new_admin_id, message.chat.id):
        bot.send_message(message.chat.id, f"Admin muvaffaqiyatli qo'shildi ✅ (ID: {new_admin_id})")
        try:
            bot.send_message(new_admin_id, "Siz admin etib tayinlandingiz! 🎉\nAdmin buyruqlarini ko'rish uchun /admin")
        except:
            pass
    else:
        bot.send_message(message.chat.id, "Adminni qo'shishda xatolik yuz berdi! ⚠️")
    
    show_admin_menu(message.chat.id)

# Super user management handlers
def process_add_super_user(message):
    if message.text == "❌ Bekor qilish":
        bot.send_message(message.chat.id, "Amal bekor qilindi ❌")
        show_admin_menu(message.chat.id)
        return
        
    new_user_id = message.text.strip()
    
    # Check if user exists
    if not get_user_by_id(new_user_id):
        bot.send_message(message.chat.id, "Bu foydalanuvchi botdan foydalanmagan! Avval bot bilan muloqot qilishi kerak. ⚠️")
        show_admin_menu(message.chat.id)
        return
    
    # Check if already super user
    if is_super_user(new_user_id):
        bot.send_message(message.chat.id, "Bu foydalanuvchi allaqachon super foydalanuvchi! ⚠️")
        show_admin_menu(message.chat.id)
        return
    
    if add_super_user(new_user_id, message.chat.id):
        bot.send_message(message.chat.id, f"Super foydalanuvchi muvaffaqiyatli qo'shildi ✅ (ID: {new_user_id})")
        try:
            bot.send_message(new_user_id, "Siz super foydalanuvchi etib tayinlandingiz! 🎉\nEndi siz kanallarga obuna bo'lmasdan kinolarni ko'rishingiz mumkin.")
        except:
            pass
    else:
        bot.send_message(message.chat.id, "Super foydalanuvchini qo'shishda xatolik yuz berdi! ⚠️")
    
    show_admin_menu(message.chat.id)

# Direct message handlers
def process_direct_message_step1(message):
    if message.text == "❌ Bekor qilish":
        bot.send_message(message.chat.id, "Amal bekor qilindi ❌")
        show_admin_menu(message.chat.id)
        return
        
    user_id = message.text.strip()
    
    # Check if user exists
    if not get_user_by_id(user_id):
        bot.send_message(message.chat.id, "Bu foydalanuvchi topilmadi! ⚠️")
        show_admin_menu(message.chat.id)
        return
    
    msg = bot.send_message(
        message.chat.id,
        f"Foydalanuvchi {user_id} ga yubormoqchi bo'lgan xabaringizni kiriting 📝",
        reply_markup=get_cancel_markup()
    )
    bot.register_next_step_handler(msg, process_direct_message_step2, user_id)

def process_direct_message_step2(message, user_id):
    if message.text == "❌ Bekor qilish":
        bot.send_message(message.chat.id, "Amal bekor qilindi ❌")
        show_admin_menu(message.chat.id)
        return
        
    direct_message = message.text
    
    try:
        bot.send_message(user_id, f"📩 Admindan xabar: {direct_message}")
        bot.send_message(message.chat.id, f"Xabar foydalanuvchi {user_id} ga muvaffaqiyatli yuborildi ✅")
    except Exception as e:
        bot.send_message(message.chat.id, f"Xabar yuborishda xatolik yuz berdi: {e} ⚠️")
    
    show_admin_menu(message.chat.id)

# Process broadcast message
def process_broadcast(message):
    if message.text == "❌ Bekor qilish":
        bot.send_message(message.chat.id, "Amal bekor qilindi ❌")
        show_admin_menu(message.chat.id)
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("Ha ✅"),
        types.KeyboardButton("Yo'q ❌")
    )
    
    preview_text = "Rasm bilan xabar" if message.photo else \
                  "Video bilan xabar" if message.video else \
                  "Forward xabar" if message.forward_from or message.forward_from_chat else \
                  f"Matn: {message.text}"
    
    msg = bot.send_message(
        message.chat.id,
        f"Quyidagi xabarni barcha foydalanuvchilarga yuborishni tasdiqlaysizmi?\n\n"
        f"Xabar turi: {preview_text}",
        reply_markup=markup
    )
    
    # Store the original message for broadcasting
    bot.register_next_step_handler(msg, confirm_broadcast, message)

def confirm_broadcast(message, original_message):
    if message.text == "Ha ✅":
        bot.send_message(message.chat.id, "Xabar yuborilmoqda... ⏳")
        successful, failed = broadcast_message(original_message)
        bot.send_message(
            message.chat.id,
            f"Xabar yuborildi ✅\n"
            f"Yuborildi: {successful}\n"
            f"Yuborilmadi: {failed}"
        )
    else:
        bot.send_message(message.chat.id, "Xabar yuborish bekor qilindi ❌")
    
    show_admin_menu(message.chat.id)

# Initialize database and start bot
if __name__ == "__main__":
    init_db()
    print("Bot ishga tushmoqda...")
    bot.polling(none_stop=True)
