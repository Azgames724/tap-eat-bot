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
from flask import Flask, Response
from threading import Thread
import time

# ===================== CONFIGURATION =====================
# Get environment variables
def get_bot_token():
    """Get and clean bot token from environment"""
    token = os.environ.get("8633260754:AAE_TBIA8IwKwYYrEMztqmsoqJpzx7UB3ys", "").strip()
    
    # Clean the token - remove any quotes, spaces, or equals signs
    token = token.strip()
    token = token.strip('"\'')  # Remove quotes
    token = token.strip('=')    # Remove equals signs
    token = token.strip()       # Strip again
    
    # Debug log (show first and last 5 chars only for security)
    if token:
        masked_token = f"{token[:10]}...{token[-5:]}"
        print(f"🔑 Bot token loaded: {masked_token}")
    
    return token

def get_admin_id():
    """Get admin ID from environment"""
    admin_id = os.environ.get("ADMIN_ID", "").strip()
    if admin_id:
        try:
            return int(admin_id)
        except ValueError:
            print(f"⚠️ Invalid ADMIN_ID: {admin_id}, using default")
    return 6237524660  # Default admin ID

BOT_TOKEN = get_bot_token()
ADMIN_ID = get_admin_id()
DATABASE_FILE = "tap_eat.db"
PORT = int(os.environ.get("PORT", 8080))

print(f"🚀 Starting TAP&EAT Bot...")
print(f"👑 Admin ID: {ADMIN_ID}")
print(f"🌐 Port: {PORT}")

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===================== DATABASE SETUP =====================
def init_database():
    """Initialize database with tables"""
    try:
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
            print("📝 Adding sample restaurants and menu items...")
            
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
        print("✅ Database initialized successfully")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")

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
    for i in [1, 2, 3, 4, 5]:
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

# ===================== COMMAND HANDLERS =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    try:
        user = update.effective_user
        user_id = user.id
        username = user.username
        full_name = f"{user.first_name} {user.last_name or ''}".strip()
        
        print(f"👤 User {user_id} ({full_name}) started the bot")
        
        # Save user to database
        save_user(user_id, username, full_name)
        
        # Check if admin
        is_admin = (user_id == ADMIN_ID)
        print(f"🔐 Is admin: {is_admin}")
        
        # SIMPLIFIED WELCOME MESSAGE - NO HTML FORMATTING
        welcome_text = f"""🎓 Welcome to TAP&EAT, {user.first_name}!

🍔 Your Campus Food Delivery Bot

📍 How it works:
1. Tap '🍽️ Order Food'
2. Choose restaurant
3. Select food & quantity
4. Confirm details
5. We deliver to your dorm!

🚚 Delivery to your room
⏰ 24/7 Ordering Available

Start by tapping '🍽️ Order Food' below!"""
        
        if is_admin:
            welcome_text += "\n\n👑 Admin privileges activated!"
        
        # Send message without HTML parsing first
        await update.message.reply_text(
            welcome_text,
            reply_markup=main_menu_keyboard(is_admin)
        )
        print(f"✅ Sent welcome message to user {user_id}")
        
    except Exception as e:
        print(f"❌ Error in start command: {e}")
        # Try sending a simple error message
        try:
            await update.message.reply_text("Welcome to TAP&EAT! Please use the menu buttons below:")
        except:
            pass

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = """🤖 TAP&EAT - Help Guide

For Students:
• Use '🍽️ Order Food' to place orders
• Update your info in '⚙️ My Info'
• Check '📋 My Orders' for status

For Admin:
• Use '👑 Admin Panel' for management
• View and manage orders

Need help?
Contact the administrator."""
    await update.message.reply_text(help_text)

# ===================== CALLBACK HANDLERS =====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all button callbacks"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    is_admin = (user_id == ADMIN_ID)
    
    try:
        print(f"🔄 Button pressed by {user_id}: {data}")
        
        # Main menu actions
        if data == 'order_food':
            await show_restaurants(query, context)
        
        elif data == 'back_to_main':
            await query.edit_message_text(
                "🏠 Main Menu",
                reply_markup=main_menu_keyboard(is_admin)
            )
        
        elif data == 'my_orders':
            await show_my_orders(query, context)
        
        elif data == 'my_info':
            await show_my_info(query, context)
        
        elif data == 'help':
            await query.edit_message_text(
                "🤖 TAP&EAT Help\n\nNeed assistance? Contact admin.",
                reply_markup=main_menu_keyboard(is_admin)
            )
        
        elif data == 'admin_panel':
            if is_admin:
                await query.edit_message_text(
                    "👑 Admin Panel\n\nManage orders and view stats:",
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
    
    except Exception as e:
        print(f"❌ Error in button handler: {e}")
        await query.answer("❌ An error occurred. Please try again.", show_alert=True)

async def show_restaurants(query, context):
    """Show list of restaurants"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM restaurants WHERE is_active = 1")
        restaurants = cursor.fetchall()
        conn.close()
        
        if not restaurants:
            await query.edit_message_text(
                "😔 No restaurants available yet.\n\nCheck back soon!"
            )
            return
        
        restaurants_text = "🏪 Choose a restaurant:\n\n"
        for rest_id, name in restaurants:
            restaurants_text += f"• {name}\n"
        
        await query.edit_message_text(
            restaurants_text,
            reply_markup=restaurants_keyboard()
        )
    except Exception as e:
        print(f"❌ Error in show_restaurants: {e}")
        await query.edit_message_text("❌ Error loading restaurants. Please try again.")

async def show_menu(query, context, restaurant_id):
    """Show menu for a restaurant"""
    try:
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
                f"🏪 {restaurant_name}\n\nNo menu items available yet.",
                reply_markup=restaurants_keyboard()
            )
            return
        
        menu_text = f"🏪 {restaurant_name}\n\n📋 Menu:\n\n"
        for item_id, name, price in items:
            menu_text += f"• {name} - ${price:.2f}\n"
        
        await query.edit_message_text(
            menu_text,
            reply_markup=menu_keyboard(restaurant_id)
        )
    except Exception as e:
        print(f"❌ Error in show_menu: {e}")
        await query.answer("Error loading menu!", show_alert=True)

async def show_quantity(query, context, item_id):
    """Show quantity selection for an item"""
    try:
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
            f"🍽️ {item_name}\n💰 Price: ${price:.2f}\n\nSelect quantity:",
            reply_markup=quantity_keyboard(item_id, restaurant_id)
        )
    except Exception as e:
        print(f"❌ Error in show_quantity: {e}")
        await query.answer("Error loading item!", show_alert=True)

async def process_order(query, context):
    """Process order after quantity selection"""
    try:
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
    except Exception as e:
        print(f"❌ Error in process_order: {e}")
        await query.answer("Error processing order!", show_alert=True)

async def ask_user_info_start(query, context):
    """Start asking user for information"""
    try:
        await query.edit_message_text(
            "📝 We need your information for delivery:\n\nPlease send your phone number:"
        )
        context.user_data['awaiting_info'] = True
        context.user_data['info_step'] = 'phone'
    except Exception as e:
        print(f"❌ Error in ask_user_info_start: {e}")

async def show_order_summary(query, context, user_info):
    """Show order summary for confirmation - SIMPLE VERSION WITHOUT BUTTONS"""
    try:
        item_name = context.user_data.get('item_name', 'Unknown')
        price = context.user_data.get('price', 0)
        quantity = context.user_data.get('order_quantity', 1)
        total = context.user_data.get('total', 0)
        restaurant_name = context.user_data.get('restaurant_name', 'Unknown')
        
        summary = f"""✅ ORDER SUMMARY

🏪 Restaurant: {restaurant_name}
🍽️ Item: {item_name}
💰 Price: ${price:.2f} each
🔢 Quantity: {quantity}
💵 Total: ${total:.2f}

👤 Customer: {user_info[2]}
📞 Phone: {user_info[3]}
📍 Dorm: {user_info[4]}, Block: {user_info[5]}{f', Room: {user_info[6]}' if user_info[6] else ''}

📝 To confirm your order, type:
1 - ✅ Confirm Order
2 - ❌ Cancel Order

Please type 1 or 2:"""
        
        await query.edit_message_text(summary)
        
        # Set state for confirmation
        context.user_data['awaiting_confirmation'] = True
    except Exception as e:
        print(f"❌ Error in show_order_summary: {e}")

# ===================== MESSAGE HANDLERS =====================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages"""
    try:
        user_id = update.effective_user.id
        text = update.message.text.strip()
        is_admin = (user_id == ADMIN_ID)
        
        print(f"📨 Message from {user_id}: {text}")
        
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
        
        # Check if we're waiting for order confirmation
        if context.user_data.get('awaiting_confirmation'):
            if text == '1':  # Confirm order
                await confirm_order(update, context)
            elif text == '2':  # Cancel order
                await update.message.reply_text("❌ Order cancelled.")
                context.user_data.clear()
                await update.message.reply_text(
                    "🏠 Main Menu",
                    reply_markup=main_menu_keyboard(is_admin)
                )
            else:
                await update.message.reply_text(
                    "❌ Invalid option. Please type:\n1 - ✅ Confirm Order\n2 - ❌ Cancel Order"
                )
            return
        
        # Unknown message - show main menu
        await update.message.reply_text(
            "Please use the menu buttons to navigate:",
            reply_markup=main_menu_keyboard(is_admin)
        )
        
    except Exception as e:
        print(f"❌ Error in handle_message: {e}")
        await update.message.reply_text("❌ An error occurred. Please try /start again.")

async def show_order_summary_message(update, context, user_info):
    """Show order summary in message - SIMPLE VERSION WITHOUT BUTTONS"""
    try:
        item_name = context.user_data.get('item_name', 'Unknown')
        price = context.user_data.get('price', 0)
        quantity = context.user_data.get('order_quantity', 1)
        total = context.user_data.get('total', 0)
        restaurant_name = context.user_data.get('restaurant_name', 'Unknown')
        
        summary = f"""✅ ORDER SUMMARY

🏪 Restaurant: {restaurant_name}
🍽️ Item: {item_name}
💰 Price: ${price:.2f} each
🔢 Quantity: {quantity}
💵 Total: ${total:.2f}

👤 Customer: {user_info[2]}
📞 Phone: {user_info[3]}
📍 Dorm: {user_info[4]}, Block: {user_info[5]}{f', Room: {user_info[6]}' if user_info[6] else ''}

📝 To confirm your order, type:
1 - ✅ Confirm Order
2 - ❌ Cancel Order

Please type 1 or 2:"""
        
        await update.message.reply_text(summary)
        
        # Set state for confirmation
        context.user_data['awaiting_confirmation'] = True
    except Exception as e:
        print(f"❌ Error in show_order_summary_message: {e}")
        await update.message.reply_text("❌ Error showing order summary. Please try again.")

async def confirm_order(update, context):
    """Handle order confirmation"""
    try:
        user_id = update.effective_user.id
        is_admin = (user_id == ADMIN_ID)
        
        # Get order details from context
        item_id = context.user_data.get('order_item_id')
        quantity = context.user_data.get('order_quantity', 1)
        item_name = context.user_data.get('item_name', 'Unknown')
        price = context.user_data.get('price', 0)
        total = context.user_data.get('total', 0)
        restaurant_name = context.user_data.get('restaurant_name', 'Unknown')
        
        if not all([item_id, item_name, restaurant_name]):
            await update.message.reply_text("❌ Order details missing! Please start over.")
            context.user_data.clear()
            return
        
        # Get user info
        user_info = get_user_info(user_id)
        if not user_info or not user_info[3]:
            await update.message.reply_text("❌ Please complete your info first! Start a new order.")
            context.user_data.clear()
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
        await update.message.reply_text(
            f"""✅ Order #{order_id} placed successfully!

📦 Order Code: {order_code}
🏪 Restaurant: {restaurant_name}
🍽️ Item: {item_name} (x{quantity})
💰 Total: ${total:.2f}
⏰ Status: Pending approval

Admin has been notified. You'll receive updates soon!"""
        )
        
        # Show main menu
        await update.message.reply_text(
            "🏠 Main Menu",
            reply_markup=main_menu_keyboard(is_admin)
        )
        
        # Clear user data
        context.user_data.clear()
        print(f"✅ Order #{order_id} placed by user {user_id}")
        
    except Exception as e:
        print(f"❌ Error in confirm_order: {e}")
        await update.message.reply_text("❌ Error placing order. Please try again.")

# ===================== ADMIN FUNCTIONS =====================
async def show_admin_orders(query, context):
    """Show pending orders to admin"""
    try:
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
                "📭 No pending orders!\n\nAll orders are processed.",
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
    except Exception as e:
        print(f"❌ Error in show_admin_orders: {e}")
        await query.edit_message_text("❌ Error loading orders.")

async def update_order_status(query, context, order_id, status):
    """Update order status"""
    try:
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
                    f"📢 Order Update!\n\nOrder #{order_id} ({order_code}) has been {status_msg}\n\nThank you for using TAP&EAT!"
                )
            except Exception as e:
                print(f"⚠️ Could not notify user {user_id}: {e}")
        
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
    except Exception as e:
        print(f"❌ Error in update_order_status: {e}")
        await query.answer("❌ Error updating order!", show_alert=True)

async def notify_admin(context, order):
    """Notify admin about new order"""
    try:
        await context.bot.send_message(
            ADMIN_ID,
            format_order_for_admin(order),
            reply_markup=order_actions_keyboard(order[0]),
            parse_mode='HTML'
        )
        print(f"📢 Admin notified about order #{order[0]}")
    except Exception as e:
        print(f"❌ Failed to notify admin: {e}")

async def show_customer_phone(query, context, order_id):
    """Show customer phone to admin"""
    try:
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
    except Exception as e:
        print(f"❌ Error in show_customer_phone: {e}")
        await query.answer("Error loading order!", show_alert=True)

async def show_my_orders(query, context):
    """Show user's orders"""
    try:
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
                "📭 No orders yet!\n\nPlace your first order!",
                reply_markup=main_menu_keyboard(user_id == ADMIN_ID)
            )
            return
        
        orders_text = "📋 Your Recent Orders:\n\n"
        for order in orders:
            order_id, code, food, qty, total, status, time = order
            status_emoji = {
                'pending': '⏳ Pending',
                'accepted': '✅ Accepted',
                'delivered': '🚚 Delivered',
                'rejected': '❌ Rejected'
            }.get(status, '📦 ' + status)
            
            orders_text += f"""Order #{order_id} ({code})
{food} (x{qty})
Total: ${total:.2f}
Status: {status_emoji}
Time: {time[:16]}
────────────
"""
        
        await query.edit_message_text(
            orders_text,
            reply_markup=main_menu_keyboard(user_id == ADMIN_ID)
        )
    except Exception as e:
        print(f"❌ Error in show_my_orders: {e}")
        await query.edit_message_text("❌ Error loading your orders.")

async def show_my_info(query, context):
    """Show user's info"""
    try:
        user_id = query.from_user.id
        user_info = get_user_info(user_id)
        
        if not user_info or not user_info[3]:  # No phone means incomplete info
            info_text = """❌ No complete information saved yet.

To place an order, you'll need to provide:
1. Phone number
2. Full name  
3. Dorm
4. Block
5. Room (optional)

Start a new order to update your info!"""
        else:
            info_text = f"""👤 Your Information:

📛 Name: {user_info[2] or 'Not set'}
📞 Phone: {user_info[3] or 'Not set'}
🏢 Dorm: {user_info[4] or 'Not set'}
🏠 Block: {user_info[5] or 'Not set'}
🚪 Room: {user_info[6] or 'Not set'}

To update, start a new order."""
        
        await query.edit_message_text(
            info_text,
            reply_markup=main_menu_keyboard(user_id == ADMIN_ID)
        )
    except Exception as e:
        print(f"❌ Error in show_my_info: {e}")
        await query.edit_message_text("❌ Error loading your info.")

async def show_stats(query, context):
    """Show statistics to admin"""
    try:
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
        
        stats_text = f"""📈 TAP&EAT Statistics

👥 Total Users: {user_count}
🏪 Restaurants: {rest_count}
📦 Total Orders: {order_count}
⏳ Pending Orders: {pending_count}
✅ Delivered Orders: {delivered_count}
💰 Total Revenue: ${revenue:.2f}

Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"""
        
        await query.edit_message_text(
            stats_text,
            reply_markup=admin_keyboard()
        )
    except Exception as e:
        print(f"❌ Error in show_stats: {e}")
        await query.edit_message_text("❌ Error loading statistics.")

# ===================== WEB SERVER FOR RAILWAY =====================
app = Flask(__name__)

@app.route('/')
def home():
    """Health check endpoint - root"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM orders")
        order_count = cursor.fetchone()[0]
        conn.close()
        return Response(
            f"🤖 TAP&EAT Bot is running!\n\n👥 Users: {user_count}\n📦 Orders: {order_count}\n✅ Status: Online",
            status=200,
            mimetype='text/plain'
        )
    except Exception as e:
        print(f"Health check error: {e}")
        return Response(
            "🤖 TAP&EAT Bot is running!\n⚠️ Database connection issue",
            status=200,
            mimetype='text/plain'
        )

@app.route('/health')
def health():
    """Health check endpoint for Railway"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        conn.close()
        return {"status": "healthy", "service": "tap-eat-bot", "timestamp": datetime.now().isoformat()}, 200
    except Exception as e:
        print(f"Health check error: {e}")
        return {"status": "unhealthy", "error": str(e)}, 500

def run_flask():
    """Run Flask server in a separate thread"""
    print(f"🌐 Starting Flask server on port {PORT}...")
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)

# ===================== MAIN FUNCTION =====================
def main():
    """Main function to start the bot"""
    # Initialize database
    print("📊 Initializing database...")
    init_database()
    
    # Create application
    print("🤖 Creating bot application...")
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    
    # Add callback query handler
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Add message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start Flask server in background thread
    print("🚀 Starting Flask server...")
    from threading import Thread
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Give Flask time to start
    time.sleep(2)
    
    # Start bot
    print("✅ Starting bot polling...")
    print("🎉 Bot is now running! Press Ctrl+C to stop.")
    
    # Run bot with error handling
    try:
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
            close_loop=False
        )
    except Exception as e:
        print(f"❌ Bot error: {e}")
        print("🔄 Restarting in 10 seconds...")
        time.sleep(10)
        main()

if __name__ == "__main__":
    main()
