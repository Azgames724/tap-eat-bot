import os
import logging
import sqlite3
import random
import string
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
from flask import Flask
from threading import Thread
import asyncio

# ===================== CONFIGURATION =====================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8367062998:AAF0gmnN5VvLw4Vkosa89O9qK8ogrWmo7so")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "6237524660"))
DATABASE_FILE = "tap_eat.db"

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===================== DATABASE SETUP =====================
def init_database():
    """Initialize database with tables"""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        phone TEXT,
        dorm TEXT,
        block TEXT,
        room TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Restaurants table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS restaurants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        is_active BOOLEAN DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Menu items table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS menu_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        restaurant_id INTEGER,
        name TEXT,
        price REAL,
        is_available BOOLEAN DEFAULT 1,
        FOREIGN KEY (restaurant_id) REFERENCES restaurants(id)
    )
    ''')
    
    # Orders table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_code TEXT UNIQUE,
        user_id INTEGER,
        restaurant_name TEXT,
        food_name TEXT,
        quantity INTEGER,
        total_price REAL,
        customer_name TEXT,
        phone TEXT,
        dorm TEXT,
        block TEXT,
        room TEXT,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Check if we need sample data
    cursor.execute("SELECT COUNT(*) FROM restaurants")
    if cursor.fetchone()[0] == 0:
        # Add sample restaurants
        sample_restaurants = [
            '🍕 Pizza Palace',
            '🍔 Burger Joint', 
            '☕ Coffee Corner',
            '🌯 Wrap Station'
        ]
        
        for rest in sample_restaurants:
            cursor.execute("INSERT OR IGNORE INTO restaurants (name) VALUES (?)", (rest,))
        
        # Get restaurant IDs and add sample items
        for rest_name in sample_restaurants:
            cursor.execute("SELECT id FROM restaurants WHERE name = ?", (rest_name,))
            rest_id = cursor.fetchone()[0]
            
            if rest_name == '🍕 Pizza Palace':
                items = [
                    ('Margherita Pizza', 12.99),
                    ('Pepperoni Pizza', 14.99),
                    ('Veggie Pizza', 13.99)
                ]
            elif rest_name == '🍔 Burger Joint':
                items = [
                    ('Cheeseburger', 8.99),
                    ('Chicken Burger', 9.99),
                    ('Double Burger', 11.99)
                ]
            elif rest_name == '☕ Coffee Corner':
                items = [
                    ('Cappuccino', 3.99),
                    ('Latte', 4.49),
                    ('Mocha', 4.99)
                ]
            else:
                items = [
                    ('Chicken Wrap', 7.99),
                    ('Veggie Wrap', 6.99)
                ]
            
            for item_name, price in items:
                cursor.execute(
                    "INSERT OR IGNORE INTO menu_items (restaurant_id, name, price) VALUES (?, ?, ?)",
                    (rest_id, item_name, price)
                )
    
    conn.commit()
    conn.close()
    logger.info("✅ Database initialized")

# ===================== HELPER FUNCTIONS =====================
def get_db_connection():
    return sqlite3.connect(DATABASE_FILE)

def generate_order_code():
    """Generate unique order code"""
    return f"TAP{random.randint(1000, 9999)}{random.choice(string.ascii_uppercase)}"

def save_user(user_id, username, full_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, full_name) 
        VALUES (?, ?, ?)
    ''', (user_id, username or "", full_name))
    conn.commit()
    conn.close()

def get_user_info(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def format_order_for_admin(order):
    """Format order details for admin notification"""
    return f"""
🚨 <b>NEW ORDER #{order[0]}</b>
📦 Code: {order[1]}

🍽️ <b>{order[4]}</b>
🏪 From: {order[3]}
🔢 Quantity: {order[5]}
💰 Total: ${order[6]:.2f}

👤 <b>{order[7]}</b>
📞 {order[8]}
📍 Dorm {order[9]}, Block {order[10]}{f', Room {order[11]}' if order[11] else ''}

⏰ {order[13]}
📊 Status: <b>{order[12].upper()}</b>
"""

# ===================== KEYBOARDS =====================
def main_menu_keyboard(is_admin=False):
    """Create main menu keyboard"""
    keyboard = [
        [InlineKeyboardButton("🍽️ Order Food", callback_data='order_food')],
        [InlineKeyboardButton("📋 My Orders", callback_data='my_orders')],
        [InlineKeyboardButton("⚙️ My Info", callback_data='my_info')],
        [InlineKeyboardButton("ℹ️ Help", callback_data='help')]
    ]
    if is_admin:
        keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data='admin_panel')])
    return InlineKeyboardMarkup(keyboard)

def admin_keyboard():
    """Create admin panel keyboard"""
    keyboard = [
        [InlineKeyboardButton("📊 View Orders", callback_data='view_orders')],
        [InlineKeyboardButton("🏪 Manage Restaurants", callback_data='manage_restaurants')],
        [InlineKeyboardButton("📈 Stats", callback_data='stats')],
        [InlineKeyboardButton("🏠 Main Menu", callback_data='back_to_main')]
    ]
    return InlineKeyboardMarkup(keyboard)

def restaurants_keyboard():
    """Create restaurants selection keyboard"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM restaurants WHERE is_active = 1")
    restaurants = cursor.fetchall()
    conn.close()
    
    keyboard = []
    for rest_id, name in restaurants:
        keyboard.append([InlineKeyboardButton(name, callback_data=f'rest_{rest_id}')])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='back_to_main')])
    return InlineKeyboardMarkup(keyboard)

def menu_keyboard(restaurant_id):
    """Create menu items keyboard for a restaurant"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price FROM menu_items WHERE restaurant_id = ? AND is_available = 1", (restaurant_id,))
    items = cursor.fetchall()
    conn.close()
    
    keyboard = []
    for item_id, name, price in items:
        keyboard.append([InlineKeyboardButton(f"{name} - ${price:.2f}", callback_data=f'item_{item_id}')])
    keyboard.append([InlineKeyboardButton("🔙 Back to Restaurants", callback_data='order_food')])
    return InlineKeyboardMarkup(keyboard)

def quantity_keyboard(item_id, restaurant_id):
    """Create quantity selection keyboard"""
    keyboard = []
    row = []
    for i in range(1, 10):
        if i <= 5 or i in [8, 10]:
            row.append(InlineKeyboardButton(str(i), callback_data=f'qty_{item_id}_{i}'))
            if len(row) == 3:
                keyboard.append(row)
                row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data=f'rest_{restaurant_id}')])
    return InlineKeyboardMarkup(keyboard)

def order_actions_keyboard(order_id):
    """Create order action buttons for admin"""
    keyboard = [
        [InlineKeyboardButton("✅ Accept", callback_data=f'accept_{order_id}'),
         InlineKeyboardButton("❌ Reject", callback_data=f'reject_{order_id}')],
        [InlineKeyboardButton("📞 Call Customer", callback_data=f'call_{order_id}'),
         InlineKeyboardButton("🚚 Deliver", callback_data=f'deliver_{order_id}')],
        [InlineKeyboardButton("🔙 Back to Orders", callback_data='view_orders')]
    ]
    return InlineKeyboardMarkup(keyboard)

def confirm_cancel_keyboard():
    """Create confirm/cancel keyboard"""
    keyboard = [
        [InlineKeyboardButton("✅ Confirm Order", callback_data='confirm_order')],
        [InlineKeyboardButton("❌ Cancel", callback_data='cancel_order')]
    ]
    return InlineKeyboardMarkup(keyboard)

def back_to_main_keyboard(is_admin=False):
    """Create back to main keyboard"""
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data='back_to_main')]])

# ===================== COMMAND HANDLERS =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    user_id = user.id
    username = user.username
    full_name = f"{user.first_name} {user.last_name or ''}".strip()
    
    # Save user to database
    save_user(user_id, username, full_name)
    
    # Check if admin
    is_admin = (user_id == ADMIN_ID)
    
    welcome_text = f"""
🎓 <b>Welcome to TAP&EAT, {user.first_name}!</b>

🍔 <b>Your Campus Food Delivery Bot</b>

📍 <b>How it works:</b>
1. Tap '🍽️ Order Food'
2. Choose restaurant
3. Select food & quantity
4. Confirm details
5. We deliver to your dorm!

🚚 <b>Delivery to your room</b>
⏰ <b>24/7 Ordering Available</b>

<i>Start by tapping '🍽️ Order Food' below!</i>
    """
    
    if is_admin:
        welcome_text += "\n\n👑 <b>Admin privileges activated!</b>"
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=main_menu_keyboard(is_admin),
        parse_mode='HTML'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = """
<b>🤖 TAP&EAT - Help Guide</b>

<b>For Students:</b>
• Use '🍽️ Order Food' to place orders
• Update your info in '⚙️ My Info'
• Check '📋 My Orders' for status

<b>For Admin:</b>
• Use '👑 Admin Panel' for management
• View and manage orders

<b>Need help?</b>
Contact the administrator.
    """
    await update.message.reply_text(help_text, parse_mode='HTML')

# ===================== CALLBACK HANDLERS =====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all button callbacks"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    is_admin = (user_id == ADMIN_ID)
    
    # Main menu actions
    if data == 'order_food':
        await show_restaurants(query, context)
    
    elif data == 'back_to_main':
        await query.edit_message_text(
            "🏠 <b>Main Menu</b>",
            reply_markup=main_menu_keyboard(is_admin),
            parse_mode='HTML'
        )
    
    elif data == 'my_orders':
        await show_my_orders(query, context)
    
    elif data == 'my_info':
        await show_my_info(query, context)
    
    elif data == 'help':
        await query.edit_message_text(
            "🤖 <b>TAP&EAT Help</b>\n\nNeed assistance? Contact admin.",
            reply_markup=main_menu_keyboard(is_admin),
            parse_mode='HTML'
        )
    
    elif data == 'admin_panel':
        if is_admin:
            await query.edit_message_text(
                "👑 <b>Admin Panel</b>\n\nManage orders and view stats:",
                reply_markup=admin_keyboard(),
                parse_mode='HTML'
            )
        else:
            await query.answer("❌ Admin access required!", show_alert=True)
    
    elif data == 'view_orders':
        if is_admin:
            await show_admin_orders(query, context)
        else:
            await query.answer("❌ Admin access required!", show_alert=True)
    
    elif data == 'stats':
        if is_admin:
            await show_stats(query, context)
        else:
            await query.answer("❌ Admin access required!", show_alert=True)
    
    elif data == 'manage_restaurants':
        if is_admin:
            await query.edit_message_text(
                "🏪 <b>Restaurant Management</b>\n\nCurrently restaurants are pre-configured. Contact developer for changes.",
                reply_markup=admin_keyboard(),
                parse_mode='HTML'
            )
        else:
            await query.answer("❌ Admin access required!", show_alert=True)
    
    elif data.startswith('rest_'):
        restaurant_id = int(data.split('_')[1])
        await show_menu(query, context, restaurant_id)
    
    elif data.startswith('item_'):
        item_id = int(data.split('_')[1])
        await show_quantity(query, context, item_id)
    
    elif data.startswith('qty_'):
        parts = data.split('_')
        if len(parts) >= 3:
            item_id = int(parts[1])
            quantity = int(parts[2])
            
            # Store in user data
            context.user_data['order_item_id'] = item_id
            context.user_data['order_quantity'] = quantity
            
            await process_order(query, context)
    
    elif data == 'confirm_order':
        await confirm_order_handler(query, context)
    
    elif data == 'cancel_order':
        await query.edit_message_text(
            "❌ Order cancelled.",
            reply_markup=main_menu_keyboard(is_admin),
            parse_mode='HTML'
        )
        context.user_data.clear()
    
    elif data.startswith('accept_'):
        if is_admin:
            order_id = int(data.split('_')[1])
            await update_order_status(query, context, order_id, 'accepted')
    
    elif data.startswith('reject_'):
        if is_admin:
            order_id = int(data.split('_')[1])
            await update_order_status(query, context, order_id, 'rejected')
    
    elif data.startswith('deliver_'):
        if is_admin:
            order_id = int(data.split('_')[1])
            await update_order_status(query, context, order_id, 'delivered')
    
    elif data.startswith('call_'):
        if is_admin:
            order_id = int(data.split('_')[1])
            await show_customer_phone(query, context, order_id)

async def show_restaurants(query, context):
    """Show list of restaurants"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM restaurants WHERE is_active = 1")
    restaurants = cursor.fetchall()
    conn.close()
    
    if not restaurants:
        await query.edit_message_text(
            "😔 <b>No restaurants available yet.</b>\n\nCheck back soon!",
            reply_markup=back_to_main_keyboard(),
            parse_mode='HTML'
        )
        return
    
    restaurants_text = "🏪 <b>Choose a restaurant:</b>\n\n"
    for rest_id, name in restaurants:
        restaurants_text += f"• {name}\n"
    
    await query.edit_message_text(
        restaurants_text,
        reply_markup=restaurants_keyboard(),
        parse_mode='HTML'
    )

async def show_menu(query, context, restaurant_id):
    """Show menu for a restaurant"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get restaurant name
    cursor.execute("SELECT name FROM restaurants WHERE id = ?", (restaurant_id,))
    restaurant = cursor.fetchone()
    
    if not restaurant:
        await query.answer("Restaurant not found!", show_alert=True)
        return
    
    restaurant_name = restaurant[0]
    
    # Get menu items
    cursor.execute("SELECT id, name, price FROM menu_items WHERE restaurant_id = ? AND is_available = 1", (restaurant_id,))
    items = cursor.fetchall()
    conn.close()
    
    if not items:
        await query.edit_message_text(
            f"🏪 <b>{restaurant_name}</b>\n\nNo menu items available yet.",
            reply_markup=restaurants_keyboard(),
            parse_mode='HTML'
        )
        return
    
    menu_text = f"🏪 <b>{restaurant_name}</b>\n\n📋 <b>Menu:</b>\n\n"
    for item_id, name, price in items:
        menu_text += f"• {name} - <b>${price:.2f}</b>\n"
    
    await query.edit_message_text(
        menu_text,
        reply_markup=menu_keyboard(restaurant_id),
        parse_mode='HTML'
    )

async def show_quantity(query, context, item_id):
    """Show quantity selection for an item"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, price, restaurant_id FROM menu_items WHERE id = ?", (item_id,))
    item = cursor.fetchone()
    conn.close()
    
    if not item:
        await query.answer("Item not found!", show_alert=True)
        return
    
    item_name, price, restaurant_id = item
    context.user_data['item_name'] = item_name
    context.user_data['price'] = price
    context.user_data['item_id'] = item_id
    context.user_data['restaurant_id'] = restaurant_id
    
    await query.edit_message_text(
        f"🍽️ <b>{item_name}</b>\n💰 Price: <b>${price:.2f}</b>\n\nSelect quantity:",
        reply_markup=quantity_keyboard(item_id, restaurant_id),
        parse_mode='HTML'
    )

async def process_order(query, context):
    """Process order after quantity selection"""
    user_id = query.from_user.id
    
    # Get item details
    item_id = context.user_data.get('order_item_id')
    quantity = context.user_data.get('order_quantity', 1)
    
    if not item_id:
        await query.answer("Item not selected!", show_alert=True)
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, price, restaurant_id FROM menu_items WHERE id = ?", (item_id,))
    item = cursor.fetchone()
    conn.close()
    
    if not item:
        await query.answer("Item not found!", show_alert=True)
        return
    
    item_name, price, restaurant_id = item
    total = price * quantity
    
    # Store order details
    context.user_data['item_name'] = item_name
    context.user_data['price'] = price
    context.user_data['total'] = total
    context.user_data['restaurant_id'] = restaurant_id
    
    # Get restaurant name
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM restaurants WHERE id = ?", (restaurant_id,))
    restaurant = cursor.fetchone()
    conn.close()
    
    if restaurant:
        context.user_data['restaurant_name'] = restaurant[0]
    
    # Check if user has saved info
    user_info = get_user_info(user_id)
    
    if not user_info or not user_info[3]:  # Check if phone exists
        # Ask for info via conversation
        await ask_user_info_start(query, context)
    else:
        # Show order summary with saved info
        await show_order_summary(query, context, user_info)

async def ask_user_info_start(query, context):
    """Start asking user for information"""
    await query.edit_message_text(
        "📝 <b>We need your information for delivery:</b>\n\nPlease send your phone number:",
        parse_mode='HTML'
    )
    context.user_data['awaiting_info'] = True
    context.user_data['info_step'] = 'phone'

async def show_order_summary(query, context, user_info):
    """Show order summary for confirmation"""
    item_name = context.user_data.get('item_name', 'Unknown')
    price = context.user_data.get('price', 0)
    quantity = context.user_data.get('order_quantity', 1)
    total = context.user_data.get('total', 0)
    restaurant_name = context.user_data.get('restaurant_name', 'Unknown')
    
    summary = f"""
✅ <b>ORDER SUMMARY</b>

🏪 Restaurant: {restaurant_name}
🍽️ Item: {item_name}
💰 Price: ${price:.2f} each
🔢 Quantity: {quantity}
💵 Total: <b>${total:.2f}</b>

👤 Customer: {user_info[2]}
📞 Phone: {user_info[3]}
📍 Dorm: {user_info[4]}, Block: {user_info[5]}{f', Room: {user_info[6]}' if user_info[6] else ''}

<b>Please confirm your order:</b>
    """
    
    await query.edit_message_text(
        summary,
        reply_markup=confirm_cancel_keyboard(),
        parse_mode='HTML'
    )

async def confirm_order_handler(query, context):
    """Handle order confirmation"""
    user_id = query.from_user.id
    
    # Get order details from context
    item_id = context.user_data.get('order_item_id')
    quantity = context.user_data.get('order_quantity', 1)
    item_name = context.user_data.get('item_name', 'Unknown')
    price = context.user_data.get('price', 0)
    total = context.user_data.get('total', 0)
    restaurant_name = context.user_data.get('restaurant_name', 'Unknown')
    
    if not all([item_id, item_name, restaurant_name]):
        await query.answer("Order details missing!", show_alert=True)
        return
    
    # Get user info
    user_info = get_user_info(user_id)
    if not user_info or not user_info[3]:
        await query.answer("Please complete your info first!", show_alert=True)
        return
    
    # Save order to database
    conn = get_db_connection()
    cursor = conn.cursor()
    
    order_code = generate_order_code()
    
    cursor.execute('''
        INSERT INTO orders (
            order_code, user_id, restaurant_name, food_name,
            quantity, total_price, customer_name, phone,
            dorm, block, room, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        order_code, user_id,
        restaurant_name,
        item_name, quantity, total,
        user_info[2],  # customer_name
        user_info[3],  # phone
        user_info[4],  # dorm
        user_info[5],  # block
        user_info[6] if len(user_info) > 6 else '',  # room
        'pending'
    ))
    
    order_id = cursor.lastrowid
    conn.commit()
    
    # Get the complete order for admin notification
    cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()
    conn.close()
    
    # Notify admin
    if order:
        await notify_admin(context, order)
    
    # Confirm to user
    await query.edit_message_text(
        f"""
✅ <b>Order #{order_id} placed successfully!</b>

📦 Order Code: {order_code}
🏪 Restaurant: {restaurant_name}
🍽️ Item: {item_name} (x{quantity})
💰 Total: ${total:.2f}
⏰ Status: Pending approval

<i>Admin has been notified. You'll receive updates soon!</i>
        """,
        parse_mode='HTML',
        reply_markup=main_menu_keyboard(user_id == ADMIN_ID)
    )
    
    # Clear user data
    context.user_data.clear()

# ===================== MESSAGE HANDLERS =====================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    is_admin = (user_id == ADMIN_ID)
    
    # Check if we're collecting user info
    if context.user_data.get('awaiting_info'):
        step = context.user_data.get('info_step')
        
        if step == 'phone':
            # Basic phone validation
            if not text.replace('+', '').replace(' ', '').isdigit() or len(text.replace('+', '').replace(' ', '')) < 10:
                await update.message.reply_text("Please enter a valid phone number (at least 10 digits):")
                return
            
            context.user_data['phone'] = text
            context.user_data['info_step'] = 'name'
            await update.message.reply_text("👤 Please send your full name:")
        
        elif step == 'name':
            if len(text) < 2:
                await update.message.reply_text("Please enter a valid name (at least 2 characters):")
                return
            
            context.user_data['name'] = text
            context.user_data['info_step'] = 'dorm'
            await update.message.reply_text("🏢 Please send your dorm name/number:")
        
        elif step == 'dorm':
            context.user_data['dorm'] = text
            context.user_data['info_step'] = 'block'
            await update.message.reply_text("🏠 Please send your block:")
        
        elif step == 'block':
            context.user_data['block'] = text
            context.user_data['info_step'] = 'room'
            await update.message.reply_text("🚪 Please send your room number (or type 'skip' if none):")
        
        elif step == 'room':
            if text.lower() != 'skip':
                context.user_data['room'] = text
            else:
                context.user_data['room'] = ''
            
            # Save user info to database
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Check if user exists
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            user = cursor.fetchone()
            
            if user:
                # Update existing user
                cursor.execute('''
                    UPDATE users SET 
                    phone = ?, full_name = ?, dorm = ?, block = ?, room = ?
                    WHERE user_id = ?
                ''', (
                    context.user_data['phone'],
                    context.user_data['name'],
                    context.user_data['dorm'],
                    context.user_data['block'],
                    context.user_data.get('room', ''),
                    user_id
                ))
            else:
                # Insert new user
                user_obj = update.effective_user
                cursor.execute('''
                    INSERT INTO users (user_id, username, full_name, phone, dorm, block, room)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    user_id,
                    user_obj.username or "",
                    context.user_data['name'],
                    context.user_data['phone'],
                    context.user_data['dorm'],
                    context.user_data['block'],
                    context.user_data.get('room', '')
                ))
            
            conn.commit()
            conn.close()
            
            # Get updated user info
            user_info = get_user_info(user_id)
            
            # Show order summary
            await show_order_summary_message(update, context, user_info)
            
            # Clear collection state
            context.user_data.pop('awaiting_info', None)
            context.user_data.pop('info_step', None)
        
        return
    
    # Unknown message - show main menu
    await update.message.reply_text(
        "Please use the menu buttons to navigate:",
        reply_markup=main_menu_keyboard(is_admin)
    )

async def show_order_summary_message(update, context, user_info):
    """Show order summary in message"""
    item_name = context.user_data.get('item_name', 'Unknown')
    price = context.user_data.get('price', 0)
    quantity = context.user_data.get('order_quantity', 1)
    total = context.user_data.get('total', 0)
    restaurant_name = context.user_data.get('restaurant_name', 'Unknown')
    
    summary = f"""
✅ <b>ORDER SUMMARY</b>

🏪 Restaurant: {restaurant_name}
🍽️ Item: {item_name}
💰 Price: ${price:.2f} each
🔢 Quantity: {quantity}
💵 Total: <b>${total:.2f}</b>

👤 Customer: {user_info[2]}
📞 Phone: {user_info[3]}
📍 Dorm: {user_info[4]}, Block: {user_info[5]}{f', Room: {user_info[6]}' if user_info[6] else ''}

<b>Please confirm your order using the buttons in your previous message.</b>
<i>(Go back to the conversation with the order summary)</i>
    """
    
    await update.message.reply_text(
        summary,
        parse_mode='HTML'
    )

# ===================== ADMIN FUNCTIONS =====================
async def show_admin_orders(query, context):
    """Show pending orders to admin"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM orders 
        WHERE status = 'pending' 
        ORDER BY created_at DESC
        LIMIT 10
    ''')
    orders = cursor.fetchall()
    conn.close()
    
    if not orders:
        await query.edit_message_text(
            "📭 <b>No pending orders!</b>\n\nAll orders are processed.",
            reply_markup=admin_keyboard(),
            parse_mode='HTML'
        )
        return
    
    # Show first order with actions
    order = orders[0]
    await query.edit_message_text(
        format_order_for_admin(order),
        reply_markup=order_actions_keyboard(order[0]),
        parse_mode='HTML'
    )
    
    # Store remaining orders
    if len(orders) > 1:
        context.user_data['pending_orders'] = orders[1:]

async def update_order_status(query, context, order_id, status):
    """Update order status"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Update status
    cursor.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
    
    # Get order details for notification
    cursor.execute("SELECT user_id, order_code, customer_name FROM orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()
    
    conn.commit()
    conn.close()
    
    if order:
        user_id, order_code, customer_name = order
        
        # Prepare status message for user
        status_messages = {
            'accepted': 'accepted ✅\n\nYour order is being prepared!',
            'rejected': 'rejected ❌\n\nPlease contact admin for details.',
            'delivered': 'delivered 🚚\n\nEnjoy your meal!'
        }
        
        status_msg = status_messages.get(status, f'{status}')
        
        # Notify user
        try:
            await context.bot.send_message(
                user_id,
                f"📢 <b>Order Update!</b>\n\n"
                f"Order #{order_id} ({order_code}) has been {status_msg}\n\n"
                f"Thank you for using TAP&EAT!",
                parse_mode='HTML'
            )
        except Exception as e:
            logger.warning(f"Could not notify user {user_id}: {e}")
    
    await query.answer(f"✅ Order {status}!")
    
    # Show next order or go back
    if context.user_data.get('pending_orders'):
        next_order = context.user_data['pending_orders'].pop(0)
        await query.edit_message_text(
            format_order_for_admin(next_order),
            reply_markup=order_actions_keyboard(next_order[0]),
            parse_mode='HTML'
        )
    else:
        await query.edit_message_text(
            f"✅ Order #{order_id} has been {status}!\n\nView more orders:",
            reply_markup=admin_keyboard(),
            parse_mode='HTML'
        )

async def notify_admin(context, order):
    """Notify admin about new order"""
    try:
        await context.bot.send_message(
            ADMIN_ID,
            format_order_for_admin(order),
            reply_markup=order_actions_keyboard(order[0]),
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")

async def show_customer_phone(query, context, order_id):
    """Show customer phone to admin"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT phone, customer_name FROM orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()
    conn.close()
    
    if order:
        phone, name = order
        await query.answer(f"📞 Customer: {name}\nPhone: {phone}", show_alert=True)
    else:
        await query.answer("Order not found!", show_alert=True)

async def show_my_orders(query, context):
    """Show user's orders"""
    user_id = query.from_user.id
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, order_code, food_name, quantity, total_price, status, created_at
        FROM orders 
        WHERE user_id = ? 
        ORDER BY created_at DESC 
        LIMIT 10
    ''', (user_id,))
    orders = cursor.fetchall()
    conn.close()
    
    if not orders:
        await query.edit_message_text(
            "📭 <b>No orders yet!</b>\n\nPlace your first order!",
            reply_markup=main_menu_keyboard(user_id == ADMIN_ID),
            parse_mode='HTML'
        )
        return
    
    orders_text = "📋 <b>Your Recent Orders:</b>\n\n"
    for order in orders:
        order_id, code, food, qty, total, status, time = order
        status_emoji = {
            'pending': '⏳ Pending',
            'accepted': '✅ Accepted',
            'delivered': '🚚 Delivered',
            'rejected': '❌ Rejected'
        }.get(status, '📦 ' + status)
        
        orders_text += f"""
<b>Order #{order_id}</b> ({code})
{food} (x{qty})
Total: ${total:.2f}
Status: {status_emoji}
Time: {time[:16]}
────────────
"""
    
    await query.edit_message_text(
        orders_text,
        reply_markup=main_menu_keyboard(user_id == ADMIN_ID),
        parse_mode='HTML'
    )

async def show_my_info(query, context):
    """Show user's info"""
    user_id = query.from_user.id
    user_info = get_user_info(user_id)
    
    if not user_info or not user_info[3]:  # No phone means incomplete info
        info_text = """
❌ <b>No complete information saved yet.</b>

To place an order, you'll need to provide:
1. Phone number
2. Full name  
3. Dorm
4. Block
5. Room (optional)

<i>Start a new order to update your info!</i>
        """
    else:
        info_text = f"""
👤 <b>Your Information:</b>

📛 <b>Name:</b> {user_info[2] or 'Not set'}
📞 <b>Phone:</b> {user_info[3] or 'Not set'}
🏢 <b>Dorm:</b> {user_info[4] or 'Not set'}
🏠 <b>Block:</b> {user_info[5] or 'Not set'}
🚪 <b>Room:</b> {user_info[6] or 'Not set'}

<i>To update, start a new order.</i>
        """
    
    await query.edit_message_text(
        info_text,
        reply_markup=back_to_main_keyboard(user_id == ADMIN_ID),
        parse_mode='HTML'
    )

async def show_stats(query, context):
    """Show statistics to admin"""
    if query.from_user.id != ADMIN_ID:
        await query.answer("❌ Admin access required!", show_alert=True)
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get counts
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM restaurants")
    rest_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM orders")
    order_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'pending'")
    pending_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'delivered'")
    delivered_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(total_price) FROM orders WHERE status = 'delivered'")
    revenue = cursor.fetchone()[0] or 0
    
    conn.close()
    
    stats_text = f"""
📈 <b>TAP&EAT Statistics</b>

👥 <b>Total Users:</b> {user_count}
🏪 <b>Restaurants:</b> {rest_count}
📦 <b>Total Orders:</b> {order_count}
⏳ <b>Pending Orders:</b> {pending_count}
✅ <b>Delivered Orders:</b> {delivered_count}
💰 <b>Total Revenue:</b> ${revenue:.2f}

<i>Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</i>
    """
    
    await query.edit_message_text(
        stats_text,
        reply_markup=admin_keyboard(),
        parse_mode='HTML'
    )

# ===================== ADMIN COMMANDS =====================
async def orders_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to view orders"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin access required!")
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, order_code, food_name, quantity, customer_name, status, created_at
        FROM orders 
        ORDER BY created_at DESC 
        LIMIT 10
    ''')
    orders = cursor.fetchall()
    conn.close()
    
    if not orders:
        await update.message.reply_text("📭 No orders yet!")
        return
    
    orders_text = "📊 <b>Recent Orders:</b>\n\n"
    for order in orders:
        order_id, code, food, qty, customer, status, time = order
        orders_text += f"""
🆔 #{order_id} - {code}
🍽️ {food} (x{qty})
👤 {customer}
📊 {status.upper()}
⏰ {time[:16]}
────────────
"""
    
    await update.message.reply_text(orders_text, parse_mode='HTML')

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to clear all orders"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin access required!")
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM orders")
    conn.commit()
    conn.close()
    
    await update.message.reply_text("✅ All orders cleared!")

# ===================== WEB SERVER FOR RAILWAY =====================
app = Flask(__name__)

@app.route('/')
def home():
    """Health check endpoint"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        conn.close()
        return f"🤖 TAP&EAT Bot is running! Users: {user_count}"
    except:
        return "🤖 TAP&EAT Bot is running!"

@app.route('/health')
def health():
    """Health check endpoint"""
    return {"status": "healthy", "service": "tap-eat-bot"}, 200

def run_flask():
    """Run Flask server in a separate thread"""
    app.run(host='0.0.0.0', port=8080)

# ===================== MAIN FUNCTION =====================
def main():
    """Main function to start the bot"""
    # Initialize database
    init_database()
    logger.info("✅ Database initialized")
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("orders", orders_command))
    application.add_handler(CommandHandler("clear", clear_command))
    
    # Add callback query handler
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Add message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start Flask server in background
    import threading
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("✅ Flask server started on port 8080")
    
    # Start bot
    logger.info("🤖 Starting TAP&EAT Bot...")
    logger.info(f"👑 Admin ID: {ADMIN_ID}")
    
    # Run bot
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
