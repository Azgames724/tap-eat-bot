import os
import logging
import sqlite3
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

# ===================== CONFIGURATION =====================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8367062998:AAEr51KmoIKEIM5iHbfDU9W0jo_cPyivQCE")
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
        cursor.execute("INSERT INTO restaurants (name) VALUES ('🍔 Campus food')")
        cursor.execute("INSERT INTO restaurants (name) VALUES ('🍝 outside food')")
        cursor.execute("INSERT INTO restaurants (name) VALUES ('☕ Coming')")
        cursor.execute("INSERT INTO restaurants (name) VALUES ('🌯 Wrap Station')")
        
        # Get restaurant IDs
        cursor.execute("SELECT id FROM restaurants WHERE name = '🍔 Campus food'")
        pizza_id = cursor.fetchone()[0]
        cursor.execute("INSERT INTO menu_items (restaurant_id, name, price) VALUES (?, '🥙 Ertib', 70)", (pizza_id,))
        cursor.execute("INSERT INTO menu_items (restaurant_id, name, price) VALUES (?, '🥘 Shiro', 90)", (pizza_id,))
        cursor.execute("INSERT INTO menu_items (restaurant_id, name, price) VALUES (?, '🍲 firfir', 90)", (pizza_id,))
        
        cursor.execute("SELECT id FROM restaurants WHERE name = '🍝 outside food'")
        burger_id = cursor.fetchone()[0]
        cursor.execute("INSERT INTO menu_items (restaurant_id, name, price) VALUES (?, 'one', 1)", (burger_id,))
        cursor.execute("INSERT INTO menu_items (restaurant_id, name, price) VALUES (?, 'two', 2)", (burger_id,))
        cursor.execute("INSERT INTO menu_items (restaurant_id, name, price) VALUES (?, 'four ', 3)", (burger_id,))
        
        
    conn.commit()
    conn.close()
    logger.info("✅ Database initialized")

# ===================== HELPER FUNCTIONS =====================
def get_db_connection():
    return sqlite3.connect(DATABASE_FILE)

def generate_order_code():
    import random
    import string
    return f"TAP{random.randint(1000, 9999)}"

def save_user(user_id, username, full_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, full_name) 
        VALUES (?, ?, ?)
    ''', (user_id, username, full_name))
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
    order_id, code, user_id, rest_name, food_name, qty, total, customer, phone, dorm, block, room, status, created = order
    
    return f"""
🚨 <b>NEW ORDER #{order_id}</b>
📦 Code: {code}

🍽️ <b>{food_name}</b>
🏪 From: {rest_name}
🔢 Quantity: {qty}
💰 Total: birr{total:.2f}

👤 <b>{customer}</b>
📞 {phone}
📍 Dorm {dorm}, Block {block}{f', Room {room}' if room else ''}

⏰ {created}
📊 Status: <b>{status.upper()}</b>
"""

# ===================== KEYBOARDS =====================
def main_menu_keyboard(is_admin=False):
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
    keyboard = [
        [InlineKeyboardButton("➕ Add Restaurant", callback_data='add_restaurant')],
        [InlineKeyboardButton("➕ Add Food Item", callback_data='add_food')],
        [InlineKeyboardButton("📊 View Orders", callback_data='view_orders')],
        [InlineKeyboardButton("🏪 Restaurants", callback_data='manage_restaurants')],
        [InlineKeyboardButton("📈 Stats", callback_data='stats')],
        [InlineKeyboardButton("🏠 Main Menu", callback_data='back_to_main')]
    ]
    return InlineKeyboardMarkup(keyboard)

def restaurants_keyboard():
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

def quantity_keyboard(item_id):
    keyboard = []
    row = []
    for i in range(1, 6):
        row.append(InlineKeyboardButton(str(i), callback_data=f'qty_{item_id}_{i}'))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data=f'back_to_menu_{item_id}')])
    return InlineKeyboardMarkup(keyboard)

def order_actions_keyboard(order_id):
    keyboard = [
        [InlineKeyboardButton("✅ Accept", callback_data=f'accept_{order_id}'),
         InlineKeyboardButton("❌ Reject", callback_data=f'reject_{order_id}')],
        [InlineKeyboardButton("📞 Call Customer", callback_data=f'call_{order_id}'),
         InlineKeyboardButton("🚚 Deliver", callback_data=f'deliver_{order_id}')]
    ]
    return InlineKeyboardMarkup(keyboard)

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
• Update your info in '⚙️ About Me'
• Check '📋 My Orders' for status

<b>For Admin:</b>
• Use '👑 Admin Panel' for management
• Add restaurants and menu items
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
                "👑 <b>Admin Panel</b>\n\nManage restaurants, orders, and more:",
                reply_markup=admin_keyboard(),
                parse_mode='HTML'
            )
        else:
            await query.answer("❌ Admin access required!")
    
    elif data == 'add_restaurant':
        if is_admin:
            await query.edit_message_text(
                "🏪 <b>Add New Restaurant</b>\n\nSend me the restaurant name:",
                parse_mode='HTML'
            )
            context.user_data['awaiting_restaurant'] = True
    
    elif data == 'view_orders':
        if is_admin:
            await show_admin_orders(query, context)
    
    elif data.startswith('rest_'):
        restaurant_id = int(data.split('_')[1])
        await show_menu(query, context, restaurant_id)
    
    elif data.startswith('item_'):
        item_id = int(data.split('_')[1])
        await show_quantity(query, context, item_id)
    
    elif data.startswith('qty_'):
        _, item_id, quantity = data.split('_')
        item_id = int(item_id)
        quantity = int(quantity)
        
        # Store in user data
        context.user_data['order_item_id'] = item_id
        context.user_data['order_quantity'] = quantity
        
        await process_order(query, context)
    
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
            "😔 <b>No restaurants available yet.</b>\n\nCheck back soon or ask admin to add restaurants.",
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
        await query.answer("Restaurant not found!")
        return
    
    restaurant_name = restaurant[0]
    
    # Get menu items
    cursor.execute("SELECT id, name, price FROM menu_items WHERE restaurant_id = ? AND is_available = 1", (restaurant_id,))
    items = cursor.fetchall()
    conn.close()
    
    if not items:
        await query.edit_message_text(
            f"🏪 <b>{restaurant_name}</b>\n\nNo menu items available yet.",
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
    cursor.execute("SELECT name, price FROM menu_items WHERE id = ?", (item_id,))
    item = cursor.fetchone()
    conn.close()
    
    if not item:
        await query.answer("Item not found!")
        return
    
    item_name, price = item
    context.user_data['item_name'] = item_name
    context.user_data['price'] = price
    
    await query.edit_message_text(
        f"🍽️ <b>{item_name}</b>\n💰 Price: <b>${price:.2f}</b>\n\nSelect quantity:",
        reply_markup=quantity_keyboard(item_id),
        parse_mode='HTML'
    )

async def process_order(query, context):
    """Process order after quantity selection"""
    user_id = query.from_user.id
    
    # Check if user has saved info
    user_info = get_user_info(user_id)
    
    if not user_info or not user_info[3]:  # Check if phone exists
        # Ask for info
        await query.edit_message_text(
            "📝 <b>First, we need your information:</b>\n\nPlease send your phone number:",
            parse_mode='HTML'
        )
        context.user_data['step'] = 'ask_phone'
        return
    
    # Show order summary
    await show_order_summary(query, context, user_info)

async def show_order_summary(query, context, user_info):
    """Show order summary for confirmation"""
    user_id = query.from_user.id
    item_name = context.user_data.get('item_name', 'Unknown')
    price = context.user_data.get('price', 0)
    quantity = context.user_data.get('order_quantity', 1)
    total = price * quantity
    
    # Get restaurant info
    item_id = context.user_data.get('order_item_id')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT r.name FROM restaurants r
        JOIN menu_items m ON r.id = m.restaurant_id
        WHERE m.id = ?
    ''', (item_id,))
    restaurant = cursor.fetchone()
    conn.close()
    
    restaurant_name = restaurant[0] if restaurant else "Unknown"
    
    summary = f"""
✅ <b>ORDER SUMMARY</b>

🏪 Restaurant: {restaurant_name}
🍽️ Item: {item_name}
💰 Price: birr{price:.2f} each
🔢 Quantity: {quantity}
💵 Total: <b>birr{total:.2f}</b>

👤 Customer: {user_info[2]}
📞 Phone: {user_info[3]}
📍 Dorm: {user_info[4]}, Block: {user_info[5]}{f', Room: {user_info[6]}' if user_info[6] else ''}

<b>Type CONFIRM to place order or CANCEL to cancel.</b>
    """
    
    await query.edit_message_text(
        summary,
        parse_mode='HTML'
    )
    
    # Store for confirmation
    context.user_data['awaiting_confirmation'] = True
    context.user_data['restaurant_name'] = restaurant_name

# ===================== MESSAGE HANDLERS =====================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    # Admin adding restaurant
    if context.user_data.get('awaiting_restaurant') and user_id == ADMIN_ID:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO restaurants (name) VALUES (?)", (text,))
            conn.commit()
            await update.message.reply_text(
                f"✅ Restaurant '{text}' added successfully!",
                reply_markup=admin_keyboard(),
                parse_mode='HTML'
            )
        except sqlite3.IntegrityError:
            await update.message.reply_text(
                f"❌ Restaurant '{text}' already exists!",
                reply_markup=admin_keyboard(),
                parse_mode='HTML'
            )
        finally:
            conn.close()
            context.user_data.pop('awaiting_restaurant', None)
        return
    
    # User info collection
    if context.user_data.get('step') == 'ask_phone':
        if not text.isdigit() or len(text) < 10:
            await update.message.reply_text("Please enter a valid phone number (digits only, at least 10 digits):")
            return
        
        context.user_data['phone'] = text
        context.user_data['step'] = 'ask_name'
        await update.message.reply_text("👤 Please send your full name:")
    
    elif context.user_data.get('step') == 'ask_name':
        context.user_data['name'] = text
        context.user_data['step'] = 'ask_dorm'
        await update.message.reply_text("🏢 Please send your dorm name/number:")
    
    elif context.user_data.get('step') == 'ask_dorm':
        context.user_data['dorm'] = text
        context.user_data['step'] = 'ask_block'
        await update.message.reply_text("🏠 Please send your block:")
    
    elif context.user_data.get('step') == 'ask_block':
        context.user_data['block'] = text
        
        # Save user info
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users SET 
            phone = ?, full_name = ?, dorm = ?, block = ?
            WHERE user_id = ?
        ''', (
            context.user_data['phone'],
            context.user_data['name'],
            context.user_data['dorm'],
            context.user_data['block'],
            user_id
        ))
        conn.commit()
        conn.close()
        
        # Get updated user info
        user_info = get_user_info(user_id)
        
        # Show order summary
        await show_order_summary_message(update, context, user_info)
        context.user_data['step'] = None
    
    # Order confirmation
    elif context.user_data.get('awaiting_confirmation'):
        if text.upper() == 'CONFIRM':
            # Save order to database
            conn = get_db_connection()
            cursor = conn.cursor()
            
            order_code = generate_order_code()
            item_name = context.user_data.get('item_name', 'Unknown')
            price = context.user_data.get('price', 0)
            quantity = context.user_data.get('order_quantity', 1)
            total = price * quantity
            
            cursor.execute('''
                INSERT INTO orders (
                    order_code, user_id, restaurant_name, food_name,
                    quantity, total_price, customer_name, phone,
                    dorm, block, room, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                order_code, user_id,
                context.user_data.get('restaurant_name', 'Unknown'),
                item_name, quantity, total,
                context.user_data.get('name', ''),
                context.user_data.get('phone', ''),
                context.user_data.get('dorm', ''),
                context.user_data.get('block', ''),
                context.user_data.get('room', ''),
                'pending'
            ))
            
            order_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            # Notify admin
            await notify_admin(context, order_id)
            
            # Confirm to user
            await update.message.reply_text(
                f"""
✅ <b>Order #{order_id} placed successfully!</b>

📦 Order Code: {order_code}
💰 Total: birr{total:.2f}
⏰ Status: Pending approval

<i>Admin has been notified. You'll receive updates soon!</i>
                """,
                parse_mode='HTML'
            )
            
            # Clear user data
            for key in ['order_item_id', 'order_quantity', 'item_name', 'price', 
                       'awaiting_confirmation', 'restaurant_name', 'name', 
                       'phone', 'dorm', 'block', 'room']:
                context.user_data.pop(key, None)
            
        elif text.upper() == 'CANCEL':
            await update.message.reply_text(
                "❌ Order cancelled.",
                parse_mode='HTML'
            )
            context.user_data.clear()
    
    # Unknown message
    else:
        await update.message.reply_text(
            "🤔 I didn't understand that. Use the buttons below:",
            reply_markup=main_menu_keyboard(user_id == ADMIN_ID)
        )

async def show_order_summary_message(update, context, user_info):
    """Show order summary in message"""
    item_name = context.user_data.get('item_name', 'Unknown')
    price = context.user_data.get('price', 0)
    quantity = context.user_data.get('order_quantity', 1)
    total = price * quantity
    
    summary = f"""
✅ <b>ORDER SUMMARY</b>

🍽️ Item: {item_name}
💰 Price: birr{price:.2f} each
🔢 Quantity: {quantity}
💵 Total: <b>birr{total:.2f}</b>

👤 Customer: {user_info[2]}
📞 Phone: {user_info[3]}
📍 Dorm: {user_info[4]}, Block: {user_info[5]}

<b>Type CONFIRM to place order or CANCEL to cancel.</b>
    """
    
    await update.message.reply_text(summary, parse_mode='HTML')
    context.user_data['awaiting_confirmation'] = True

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
            "📭 <b>No pending orders!</b>",
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
    
    # Get order details
    cursor.execute("SELECT user_id, order_code FROM orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()
    
    conn.commit()
    conn.close()
    
    if order:
        user_id, order_code = order
        status_text = {
            'accepted': 'accepted ✅',
            'rejected': 'rejected ❌',
            'delivered': 'delivered 🚚'
        }.get(status, status)
        
        # Notify user
        try:
            await context.bot.send_message(
                user_id,
                f"📢 <b>Order Update!</b>\n\nOrder #{order_id} ({order_code}) has been {status_text}"
            )
        except:
            pass
    
    await query.answer(f"Order {status}!")
    
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
            "✅ Order status updated!\n\nView more orders:",
            reply_markup=admin_keyboard(),
            parse_mode='HTML'
        )

async def notify_admin(context, order_id):
    """Notify admin about new order"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()
    conn.close()
    
    if order:
        try:
            await context.bot.send_message(
                ADMIN_ID,
                format_order_for_admin(order),
                reply_markup=order_actions_keyboard(order_id),
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
        await query.answer(f"📞 {name}: {phone}", show_alert=True)
    else:
        await query.answer("Order not found!")

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
        LIMIT 5
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
            'pending': '⏳',
            'accepted': '✅',
            'delivered': '🚚',
            'rejected': '❌'
        }.get(status, '📦')
        
        orders_text += f"""
{status_emoji} <b>Order #{order_id}</b>
📦 {code}
🍽️ {food} (x{qty})
💰 birr{total:.2f}
📊 {status.upper()}
⏰ {time[:16]}
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
    
    if not user_info:
        info_text = "❌ <b>No information saved yet.</b>\n\nPlease update your info."
    else:
        info_text = f"""
👤 <b>Your Information:</b>

📛 <b>Name:</b> {user_info[2] or 'Not set'}
📞 <b>Phone:</b> {user_info[3] or 'Not set'}
🏢 <b>Dorm:</b> {user_info[4] or 'Not set'}
🏠 <b>Block:</b> {user_info[5] or 'Not set'}
🚪 <b>Room:</b> {user_info[6] or 'Not set'}

<i>To update, start a new order or contact admin.</i>
        """
    
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data='back_to_main')]])
    
    await query.edit_message_text(
        info_text,
        reply_markup=keyboard,
        parse_mode='HTML'
    )

# ===================== ADMIN COMMANDS =====================
async def addrest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add restaurant command"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Admin access required!")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /addrest Restaurant Name")
        return
    
    restaurant_name = ' '.join(context.args)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO restaurants (name) VALUES (?)", (restaurant_name,))
        conn.commit()
        await update.message.reply_text(f"✅ Restaurant '{restaurant_name}' added!")
    except sqlite3.IntegrityError:
        await update.message.reply_text(f"❌ Restaurant '{restaurant_name}' already exists!")
    finally:
        conn.close()

async def addfood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add food item command"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Admin access required!")
        return
    
    if len(context.args) < 3:
        await update.message.reply_text("Usage: /addfood restaurant_id food_name price")
        return
    
    try:
        restaurant_id = int(context.args[0])
        food_name = context.args[1]
        price = float(context.args[2])
    except ValueError:
        await update.message.reply_text("Invalid input. Use: /addfood 1 Pizza 12.99")
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO menu_items (restaurant_id, name, price) VALUES (?, ?, ?)",
            (restaurant_id, food_name, price)
        )
        conn.commit()
        await update.message.reply_text(f"✅ '{food_name}' added to menu!")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
    finally:
        conn.close()

async def vieworders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View orders command"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Admin access required!")
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, order_code, food_name, quantity, customer_name, phone, status, created_at
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
        order_id, code, food, qty, customer, phone, status, time = order
        orders_text += f"""
🆔 #{order_id} - {code}
🍽️ {food} (x{qty})
👤 {customer} - 📞 {phone}
📊 {status.upper()}
⏰ {time[:16]}
────────────
"""
    
    await update.message.reply_text(orders_text, parse_mode='HTML')

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show statistics"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Admin access required!")
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
    
    cursor.execute("SELECT SUM(total_price) FROM orders WHERE status = 'delivered'")
    revenue = cursor.fetchone()[0] or 0
    
    conn.close()
    
    stats_text = f"""
📈 <b>TAP&EAT Statistics</b>

👥 Users: {user_count}
🏪 Restaurants: {rest_count}
📦 Total Orders: {order_count}
⏳ Pending Orders: {pending_count}
💰 Total Revenue: birr{revenue:.2f}

<i>Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</i>
    """
    
    await update.message.reply_text(stats_text, parse_mode='HTML')

# ===================== MAIN FUNCTION =====================
def main():
    """Main function to start the bot"""
    # Initialize database
    init_database()
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("addrest", addrest))
    application.add_handler(CommandHandler("addfood", addfood))
    application.add_handler(CommandHandler("vieworders", vieworders))
    application.add_handler(CommandHandler("stats", stats))
    
    # Add callback query handler
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Add message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start bot
    logger.info("🤖 Starting TAP&EAT Bot...")
    logger.info(f"👑 Admin ID: {ADMIN_ID}")
    
    # Run bot
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
