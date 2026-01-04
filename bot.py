import os
import logging
import sqlite3
import json
from datetime import datetime
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
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

# Conversation states
GETTING_RESTAURANT_NAME, GETTING_FOOD_NAME, GETTING_FOOD_PRICE, GETTING_FOOD_DESC = range(4)
GETTING_PHONE, GETTING_NAME, GETTING_DORM, GETTING_BLOCK, GETTING_INSTRUCTIONS = range(4, 9)

# ===================== DATABASE SETUP =====================
def init_database():
    """Initialize database with professional schema"""
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
        is_verified BOOLEAN DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_order TIMESTAMP
    )
    ''')
    
    # Restaurants table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS restaurants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        description TEXT,
        category TEXT DEFAULT 'Restaurant',
        emoji TEXT DEFAULT '🏪',
        is_active BOOLEAN DEFAULT 1,
        rating REAL DEFAULT 4.5,
        delivery_time INTEGER DEFAULT 30,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Menu items table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS menu_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        restaurant_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        description TEXT,
        price REAL NOT NULL,
        category TEXT DEFAULT 'Main',
        emoji TEXT DEFAULT '🍽️',
        is_available BOOLEAN DEFAULT 1,
        is_popular BOOLEAN DEFAULT 0,
        FOREIGN KEY (restaurant_id) REFERENCES restaurants(id) ON DELETE CASCADE
    )
    ''')
    
    # Orders table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_code TEXT UNIQUE NOT NULL,
        user_id INTEGER NOT NULL,
        restaurant_id INTEGER NOT NULL,
        items TEXT NOT NULL,
        total_price REAL NOT NULL,
        customer_name TEXT NOT NULL,
        phone TEXT NOT NULL,
        dorm TEXT NOT NULL,
        block TEXT NOT NULL,
        room TEXT,
        special_instructions TEXT,
        status TEXT DEFAULT 'pending',
        payment_method TEXT DEFAULT 'cash',
        estimated_delivery TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(user_id),
        FOREIGN KEY (restaurant_id) REFERENCES restaurants(id)
    )
    ''')
    
    conn.commit()
    conn.close()
    
    # Add sample data if empty
    add_sample_data()

def add_sample_data():
    """Add sample restaurants and menu items"""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    # Check if restaurants exist
    cursor.execute("SELECT COUNT(*) FROM restaurants")
    if cursor.fetchone()[0] == 0:
        # Add sample restaurants
        restaurants = [
            ('🍕 Pizza Palace', 'Authentic Italian pizza oven-baked to perfection', 'Italian', '🍕', 4.7, 25),
            ('🍔 Burger Hub', 'Juicy burgers with secret sauce', 'Fast Food', '🍔', 4.6, 20),
            ('☕ Campus Coffee', 'Premium coffee & pastries', 'Cafe', '☕', 4.8, 15),
            ('🌯 Wrap Station', 'Healthy wraps & bowls', 'Healthy', '🌯', 4.5, 30),
            ('🍜 Noodle House', 'Asian noodles & stir-fries', 'Asian', '🍜', 4.4, 35),
            ('🥗 Salad Bar', 'Fresh salads & smoothies', 'Healthy', '🥗', 4.3, 20)
        ]
        
        for name, desc, category, emoji, rating, time in restaurants:
            cursor.execute('''
                INSERT INTO restaurants (name, description, category, emoji, rating, delivery_time)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (name, desc, category, emoji, rating, time))
        
        # Get restaurant IDs and add menu items
        for i in range(1, 7):
            if i == 1:  # Pizza Palace
                items = [
                    (i, 'Margherita Pizza', 'Classic tomato & mozzarella', 12.99, 'Pizza', '🍕'),
                    (i, 'Pepperoni Pizza', 'Spicy pepperoni & cheese', 14.99, 'Pizza', '🍕', 1),
                    (i, 'Veggie Supreme', 'Loaded with fresh vegetables', 13.99, 'Pizza', '🍕'),
                    (i, 'Garlic Bread', 'Freshly baked with garlic butter', 4.99, 'Sides', '🍞')
                ]
            elif i == 2:  # Burger Hub
                items = [
                    (i, 'Classic Cheeseburger', 'Beef patty with cheese', 8.99, 'Burger', '🍔'),
                    (i, 'Chicken Burger', 'Crispy chicken fillet', 9.99, 'Burger', '🍔', 1),
                    (i, 'Bacon Double', 'Double patty with bacon', 11.99, 'Burger', '🍔'),
                    (i, 'French Fries', 'Golden crispy fries', 3.99, 'Sides', '🍟')
                ]
            elif i == 3:  # Campus Coffee
                items = [
                    (i, 'Cappuccino', 'Rich espresso with steamed milk', 3.99, 'Coffee', '☕', 1),
                    (i, 'Latte', 'Smooth coffee with milk', 4.49, 'Coffee', '☕'),
                    (i, 'Croissant', 'Buttery French pastry', 2.99, 'Pastry', '🥐'),
                    (i, 'Chocolate Muffin', 'Freshly baked muffin', 3.49, 'Pastry', '🧁')
                ]
            elif i == 4:  # Wrap Station
                items = [
                    (i, 'Chicken Caesar Wrap', 'Grilled chicken with caesar', 7.99, 'Wrap', '🌯'),
                    (i, 'Veggie Hummus Wrap', 'Fresh vegetables with hummus', 6.99, 'Wrap', '🌯', 1),
                    (i, 'Falafel Bowl', 'Falafel with rice & salad', 8.49, 'Bowl', '🥗')
                ]
            elif i == 5:  # Noodle House
                items = [
                    (i, 'Chicken Chow Mein', 'Stir-fried noodles with chicken', 9.99, 'Noodles', '🍜', 1),
                    (i, 'Vegetable Stir Fry', 'Fresh vegetables with sauce', 8.99, 'Noodles', '🍜'),
                    (i, 'Spring Rolls', 'Crispy vegetable rolls', 4.99, 'Appetizer', '🥟')
                ]
            else:  # Salad Bar
                items = [
                    (i, 'Greek Salad', 'Fresh vegetables with feta', 7.99, 'Salad', '🥗', 1),
                    (i, 'Chicken Salad', 'Grilled chicken with greens', 8.99, 'Salad', '🥗'),
                    (i, 'Berry Smoothie', 'Mixed berries with yogurt', 5.49, 'Smoothie', '🥤')
                ]
            
            for item in items:
                if len(item) == 6:
                    restaurant_id, name, desc, price, category, emoji = item
                    cursor.execute('''
                        INSERT INTO menu_items (restaurant_id, name, description, price, category, emoji)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (restaurant_id, name, desc, price, category, emoji))
                else:
                    restaurant_id, name, desc, price, category, emoji, popular = item
                    cursor.execute('''
                        INSERT INTO menu_items (restaurant_id, name, description, price, category, emoji, is_popular)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (restaurant_id, name, desc, price, category, emoji, popular))
    
    conn.commit()
    conn.close()

# ===================== HELPER FUNCTIONS =====================
def get_db_connection():
    """Get database connection"""
    return sqlite3.connect(DATABASE_FILE)

def generate_order_code():
    """Generate professional order code"""
    import random
    import string
    timestamp = datetime.now().strftime("%H%M")
    return f"TAP-{timestamp}-{random.randint(100, 999)}"

def save_user(user_id, username, full_name):
    """Save or update user"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, username, full_name, created_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    ''', (user_id, username, full_name))
    conn.commit()
    conn.close()

def get_user_info(user_id):
    """Get user information"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def update_user_info(user_id, phone, name, dorm, block, room=None):
    """Update user information"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE users SET phone = ?, full_name = ?, dorm = ?, block = ?, room = ?
        WHERE user_id = ?
    ''', (phone, name, dorm, block, room, user_id))
    conn.commit()
    conn.close()

# ===================== KEYBOARDS =====================
def get_main_menu_keyboard(is_admin=False):
    """Professional main menu keyboard"""
    keyboard = [
        [KeyboardButton("🍽️ Browse Restaurants"), KeyboardButton("⭐ Popular Items")],
        [KeyboardButton("📋 My Orders"), KeyboardButton("👤 My Profile")],
        [KeyboardButton("🛒 Cart (0)"), KeyboardButton("❓ Help")]
    ]
    if is_admin:
        keyboard.append([KeyboardButton("👑 Admin Dashboard")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, input_field_placeholder="Choose an option...")

def get_admin_dashboard_keyboard():
    """Admin dashboard keyboard"""
    keyboard = [
        [KeyboardButton("➕ Add Restaurant"), KeyboardButton("📝 Add Menu Item")],
        [KeyboardButton("📊 View Orders"), KeyboardButton("🏪 Manage Restaurants")],
        [KeyboardButton("📈 Analytics"), KeyboardButton("👥 Users")],
        [KeyboardButton("🏠 Student Menu")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_restaurants_keyboard():
    """Beautiful restaurants keyboard with categories"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get all active restaurants grouped by category
    cursor.execute('''
        SELECT category, GROUP_CONCAT(id || '|' || emoji || ' ' || name, '||') 
        FROM restaurants 
        WHERE is_active = 1 
        GROUP BY category
        ORDER BY category
    ''')
    categories = cursor.fetchall()
    conn.close()
    
    keyboard = []
    
    # Add category headers
    for category, restaurants in categories:
        # Add category as a separator (text only, no callback)
        keyboard.append([InlineKeyboardButton(
            f"━━━━━━ {category} ━━━━━━",
            callback_data="no_action"
        )])
        
        # Add restaurants in this category
        for restaurant in restaurants.split('||'):
            rest_id, display_name = restaurant.split('|', 1)
            keyboard.append([InlineKeyboardButton(
                display_name,
                callback_data=f"view_restaurant_{rest_id}"
            )])
    
    keyboard.append([
        InlineKeyboardButton("⭐ Popular Items", callback_data="popular_items"),
        InlineKeyboardButton("🔍 Search", callback_data="search_menu")
    ])
    keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")])
    
    return InlineKeyboardMarkup(keyboard)

def get_restaurant_menu_keyboard(restaurant_id):
    """Beautiful restaurant menu keyboard"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get restaurant info
    cursor.execute('''
        SELECT name, description, emoji, delivery_time, rating 
        FROM restaurants WHERE id = ?
    ''', (restaurant_id,))
    rest_info = cursor.fetchone()
    
    # Get menu items grouped by category
    cursor.execute('''
        SELECT category, GROUP_CONCAT(id || '|' || emoji || ' ' || name || ' - $' || price, '||')
        FROM menu_items 
        WHERE restaurant_id = ? AND is_available = 1
        GROUP BY category
        ORDER BY category
    ''', (restaurant_id,))
    categories = cursor.fetchall()
    conn.close()
    
    keyboard = []
    
    # Restaurant info header
    if rest_info:
        name, desc, emoji, delivery_time, rating = rest_info
        keyboard.append([InlineKeyboardButton(
            f"{emoji} {name} ⭐{rating} | 🚚 {delivery_time}min",
            callback_data="no_action"
        )])
    
    # Add category sections
    for category, items in categories:
        keyboard.append([InlineKeyboardButton(
            f"━━ {category} ━━",
            callback_data="no_action"
        )])
        
        for item in items.split('||'):
            item_id, display_text = item.split('|', 1)
            keyboard.append([InlineKeyboardButton(
                display_text,
                callback_data=f"view_item_{item_id}"
            )])
    
    keyboard.append([
        InlineKeyboardButton("🏪 All Restaurants", callback_data="browse_restaurants"),
        InlineKeyboardButton("🛒 View Cart", callback_data="view_cart")
    ])
    
    return InlineKeyboardMarkup(keyboard)

def get_item_detail_keyboard(item_id, restaurant_id):
    """Item detail keyboard with quantity selector"""
    keyboard = [
        [
            InlineKeyboardButton("➖", callback_data=f"decrease_{item_id}"),
            InlineKeyboardButton("1", callback_data=f"quantity_{item_id}_1"),
            InlineKeyboardButton("➕", callback_data=f"increase_{item_id}")
        ],
        [
            InlineKeyboardButton("2", callback_data=f"quantity_{item_id}_2"),
            InlineKeyboardButton("3", callback_data=f"quantity_{item_id}_3"),
            InlineKeyboardButton("4", callback_data=f"quantity_{item_id}_4")
        ],
        [
            InlineKeyboardButton("Add to Cart 🛒", callback_data=f"add_to_cart_{item_id}"),
            InlineKeyboardButton("Order Now ⚡", callback_data=f"order_now_{item_id}")
        ],
        [
            InlineKeyboardButton("📋 Back to Menu", callback_data=f"back_to_menu_{restaurant_id}"),
            InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_order_confirmation_keyboard(order_id):
    """Order confirmation keyboard"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm Order", callback_data=f"confirm_order_{order_id}"),
            InlineKeyboardButton("✏️ Edit Details", callback_data="edit_details")
        ],
        [
            InlineKeyboardButton("➕ Add More Items", callback_data="add_more_items"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_order")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_orders_keyboard():
    """Admin orders management keyboard"""
    keyboard = [
        [
            InlineKeyboardButton("📋 Pending Orders", callback_data="admin_pending_orders"),
            InlineKeyboardButton("🚚 Active Deliveries", callback_data="admin_active_orders")
        ],
        [
            InlineKeyboardButton("📊 Today's Stats", callback_data="admin_today_stats"),
            InlineKeyboardButton("📈 Monthly Report", callback_data="admin_monthly_report")
        ],
        [
            InlineKeyboardButton("🏪 Restaurant Stats", callback_data="admin_restaurant_stats"),
            InlineKeyboardButton("👤 Customer Orders", callback_data="admin_customer_orders")
        ],
        [InlineKeyboardButton("🔙 Admin Dashboard", callback_data="admin_dashboard")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ===================== COMMAND HANDLERS =====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name
    full_name = f"{user.first_name} {user.last_name or ''}".strip()
    
    # Save user
    save_user(user_id, username, full_name)
    
    # Check if admin
    is_admin = (user_id == ADMIN_ID)
    
    # Professional welcome message
    welcome_text = f"""
✨ *Welcome to TAP&EAT, {user.first_name}!* ✨

🎓 *Your Campus Food Delivery Partner*
🌟 *Premium Quality • Fast Delivery • Best Prices*

📱 *Quick Start:*
• Tap *'Browse Restaurants'* to explore menus
• Select items with *emoji buttons*
• Add to cart or order directly
• Track delivery in real-time

⚡ *Features:*
✅ 24/7 Ordering
✅ Dorm Room Delivery  
✅ Live Order Tracking
✅ Multiple Payment Options
✅ Order History

🎯 *Start by browsing restaurants below!*
"""
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=get_main_menu_keyboard(is_admin),
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = """
🆘 *TAP&EAT Help Center*

📞 *Contact Support:* @tap_eat_support

🔧 *How to Order:*
1. Tap *'Browse Restaurants'*
2. Choose a restaurant
3. Select food items
4. Add to cart or order now
5. Enter delivery details
6. Confirm & track order

💳 *Payment Methods:*
• Cash on Delivery
• University Card
• Mobile Payment

⏰ *Delivery Times:*
• Regular: 30-45 minutes
• Express: 20-30 minutes (+$2)
• Late Night: 24/7 available

❓ *Common Issues:*
• Wrong order? Contact us within 10 minutes
• Late delivery? Get 20% off your next order
• Missing items? Full refund available

⭐ *Pro Tip:* Save your delivery info for faster ordering!
"""
    
    await update.message.reply_text(
        help_text,
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )

# ===================== MESSAGE HANDLERS =====================
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages"""
    user_id = update.effective_user.id
    text = update.message.text
    is_admin = (user_id == ADMIN_ID)
    
    if text == "🍽️ Browse Restaurants":
        await browse_restaurants(update, context)
    
    elif text == "⭐ Popular Items":
        await show_popular_items(update, context)
    
    elif text == "📋 My Orders":
        await show_my_orders(update, context)
    
    elif text == "👤 My Profile":
        await show_my_profile(update, context)
    
    elif text == "🛒 Cart (0)":
        await show_cart(update, context)
    
    elif text == "❓ Help":
        await help_command(update, context)
    
    elif text == "👑 Admin Dashboard" and is_admin:
        await show_admin_dashboard(update, context)
    
    elif text == "➕ Add Restaurant" and is_admin:
        await update.message.reply_text(
            "🏪 *Add New Restaurant*\n\nPlease enter restaurant name:",
            parse_mode='Markdown'
        )
        return GETTING_RESTAURANT_NAME
    
    elif text == "📝 Add Menu Item" and is_admin:
        await show_restaurants_for_food_add(update, context)
    
    elif text == "📊 View Orders" and is_admin:
        await show_admin_orders_menu(update, context)
    
    elif text == "🏪 Manage Restaurants" and is_admin:
        await manage_restaurants(update, context)
    
    elif text == "📈 Analytics" and is_admin:
        await show_analytics(update, context)
    
    elif text == "👥 Users" and is_admin:
        await show_users(update, context)
    
    elif text == "🏠 Student Menu" and is_admin:
        await update.message.reply_text(
            "Switched to student menu:",
            reply_markup=get_main_menu_keyboard()
        )
    
    else:
        await update.message.reply_text(
            "I didn't understand that. Please use the menu buttons below:",
            reply_markup=get_main_menu_keyboard(is_admin)
        )

# ===================== RESTAURANT BROWSING =====================
async def browse_restaurants(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all restaurants"""
    await update.message.reply_text(
        "🏪 *Browse Restaurants*\n\nSelect a restaurant to view menu:",
        reply_markup=get_restaurants_keyboard(),
        parse_mode='Markdown'
    )

async def show_popular_items(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show popular menu items"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT m.id, m.emoji, m.name, m.price, r.name as restaurant_name, r.emoji as restaurant_emoji
        FROM menu_items m
        JOIN restaurants r ON m.restaurant_id = r.id
        WHERE m.is_popular = 1 AND m.is_available = 1 AND r.is_active = 1
        LIMIT 10
    ''')
    items = cursor.fetchall()
    conn.close()
    
    if not items:
        await update.message.reply_text(
            "⭐ *Popular Items*\n\nNo popular items available at the moment.",
            parse_mode='Markdown'
        )
        return
    
    text = "⭐ *Popular Items*\n\n"
    for i, item in enumerate(items, 1):
        item_id, emoji, name, price, rest_name, rest_emoji = item
        text += f"{i}. {emoji} *{name}* - ${price:.2f}\n"
        text += f"   {rest_emoji} {rest_name}\n\n"
    
    keyboard = []
    for item in items:
        item_id, emoji, name, price, rest_name, rest_emoji = item
        keyboard.append([InlineKeyboardButton(
            f"{emoji} {name} - ${price:.2f}",
            callback_data=f"view_item_{item_id}"
        )])
    
    keyboard.append([InlineKeyboardButton("🏪 Browse All Restaurants", callback_data="browse_restaurants")])
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ===================== ADMIN FUNCTIONS =====================
async def show_admin_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin dashboard"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get stats
    cursor.execute("SELECT COUNT(*) FROM orders WHERE DATE(created_at) = DATE('now')")
    today_orders = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'pending'")
    pending_orders = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(total_price) FROM orders WHERE DATE(created_at) = DATE('now')")
    today_revenue = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM orders WHERE DATE(created_at) = DATE('now')")
    today_customers = cursor.fetchone()[0]
    
    conn.close()
    
    dashboard_text = f"""
👑 *Admin Dashboard*

📊 *Today's Overview:*
• 📦 Orders: *{today_orders}*
• ⏳ Pending: *{pending_orders}*
• 💰 Revenue: *${today_revenue:.2f}*
• 👥 Customers: *{today_customers}*

📈 *Quick Actions:*
• Add new restaurant
• Manage menu items
• View all orders
• Analytics & reports

⚙️ *Use buttons below to manage:*
"""
    
    await update.message.reply_text(
        dashboard_text,
        reply_markup=get_admin_dashboard_keyboard(),
        parse_mode='Markdown'
    )

async def add_restaurant_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get restaurant name from admin"""
    context.user_data['restaurant_name'] = update.message.text
    await update.message.reply_text(
        "📝 Enter restaurant description (optional):\n\n*Example:* Authentic Italian cuisine with fresh ingredients",
        parse_mode='Markdown'
    )
    return GETTING_FOOD_DESC

async def add_restaurant_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get restaurant description"""
    context.user_data['restaurant_desc'] = update.message.text
    await update.message.reply_text(
        "🏷️ Select restaurant category:\n\n1. Italian\n2. Fast Food\n3. Cafe\n4. Asian\n5. Healthy\n6. Mexican\n\nReply with number or custom category:",
        parse_mode='Markdown'
    )
    return ConversationHandler.END  # Simplified for now

async def show_restaurants_for_food_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show restaurants for adding food items"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, emoji, name FROM restaurants WHERE is_active = 1")
    restaurants = cursor.fetchall()
    conn.close()
    
    keyboard = []
    for rest_id, emoji, name in restaurants:
        keyboard.append([InlineKeyboardButton(
            f"{emoji} {name}",
            callback_data=f"admin_add_food_{rest_id}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_dashboard")])
    
    await update.message.reply_text(
        "🏪 *Select Restaurant for New Menu Item:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def show_admin_orders_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin orders menu"""
    await update.message.reply_text(
        "📊 *Orders Management*\n\nSelect an option:",
        reply_markup=get_admin_orders_keyboard(),
        parse_mode='Markdown'
    )

async def manage_restaurants(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manage restaurants"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, emoji, name, is_active, rating, delivery_time 
        FROM restaurants 
        ORDER BY name
    ''')
    restaurants = cursor.fetchall()
    conn.close()
    
    text = "🏪 *Manage Restaurants*\n\n"
    keyboard = []
    
    for rest_id, emoji, name, is_active, rating, delivery_time in restaurants:
        status = "✅ Active" if is_active else "❌ Inactive"
        text += f"{emoji} *{name}*\n⭐ {rating} | 🚚 {delivery_time}min | {status}\n\n"
        
        keyboard.append([
            InlineKeyboardButton(f"Edit {emoji}", callback_data=f"admin_edit_rest_{rest_id}"),
            InlineKeyboardButton("Toggle Status" if is_active else "Activate", 
                               callback_data=f"admin_toggle_rest_{rest_id}")
        ])
    
    keyboard.append([InlineKeyboardButton("➕ Add New Restaurant", callback_data="admin_add_restaurant")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_dashboard")])
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def show_analytics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show analytics dashboard"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get various analytics
    cursor.execute('''
        SELECT 
            COUNT(*) as total_orders,
            SUM(total_price) as total_revenue,
            AVG(total_price) as avg_order_value,
            COUNT(DISTINCT user_id) as total_customers
        FROM orders
        WHERE DATE(created_at) >= DATE('now', '-7 days')
    ''')
    stats = cursor.fetchone()
    
    cursor.execute('''
        SELECT r.name, COUNT(o.id) as order_count, SUM(o.total_price) as revenue
        FROM orders o
        JOIN restaurants r ON o.restaurant_id = r.id
        WHERE DATE(o.created_at) >= DATE('now', '-7 days')
        GROUP BY r.name
        ORDER BY revenue DESC
        LIMIT 5
    ''')
    top_restaurants = cursor.fetchall()
    
    conn.close()
    
    analytics_text = f"""
📈 *Analytics Dashboard*

📅 *Last 7 Days:*
• 📦 Total Orders: *{stats[0] or 0}*
• 💰 Total Revenue: *${stats[1] or 0:.2f}*
• 💵 Avg Order Value: *${stats[2] or 0:.2f}*
• 👥 Unique Customers: *{stats[3] or 0}*

🏆 *Top Restaurants:*
"""
    
    for i, (name, count, revenue) in enumerate(top_restaurants, 1):
        analytics_text += f"{i}. {name}: {count} orders (${revenue:.2f})\n"
    
    await update.message.reply_text(
        analytics_text,
        parse_mode='Markdown',
        reply_markup=get_admin_dashboard_keyboard()
    )

async def show_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show users list"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT u.user_id, u.full_name, u.phone, u.dorm, u.block,
               COUNT(o.id) as order_count, MAX(o.created_at) as last_order
        FROM users u
        LEFT JOIN orders o ON u.user_id = o.user_id
        GROUP BY u.user_id
        ORDER BY order_count DESC
        LIMIT 20
    ''')
    users = cursor.fetchall()
    conn.close()
    
    text = "👥 *Top Customers*\n\n"
    for user in users:
        user_id, name, phone, dorm, block, order_count, last_order = user
        if name:
            text += f"👤 *{name}*\n"
            if phone:
                text += f"📞 {phone} | "
            if dorm and block:
                text += f"📍 {dorm}, {block}\n"
            text += f"📦 Orders: {order_count}\n\n"
    
    await update.message.reply_text(
        text,
        parse_mode='Markdown',
        reply_markup=get_admin_dashboard_keyboard()
    )

# ===================== CALLBACK HANDLERS =====================
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all callback queries"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    if data.startswith("view_restaurant_"):
        restaurant_id = int(data.split("_")[2])
        await show_restaurant_menu(query, context, restaurant_id)
    
    elif data == "popular_items":
        await show_popular_items_callback(query, context)
    
    elif data == "browse_restaurants":
        await browse_restaurants_callback(query, context)
    
    elif data == "main_menu":
        await show_main_menu_callback(query, context, user_id)
    
    elif data.startswith("view_item_"):
        item_id = int(data.split("_")[2])
        await show_item_details(query, context, item_id)
    
    elif data.startswith("add_to_cart_"):
        item_id = int(data.split("_")[3])
        # Simplified - just show message
        await query.edit_message_text(
            "✅ Added to cart!\n\nUse '🛒 Cart' button to view your cart.",
            reply_markup=get_main_menu_keyboard()
        )
    
    elif data == "admin_dashboard":
        await show_admin_dashboard_callback(query, context)
    
    elif data.startswith("admin_add_food_"):
        restaurant_id = int(data.split("_")[3])
        await start_add_food_conversation(query, context, restaurant_id)
    
    elif data.startswith("admin_edit_rest_"):
        restaurant_id = int(data.split("_")[3])
        await edit_restaurant(query, context, restaurant_id)
    
    elif data == "admin_pending_orders":
        await show_pending_orders_admin(query, context)

async def show_restaurant_menu(query, context, restaurant_id):
    """Show restaurant menu"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get restaurant info
    cursor.execute('''
        SELECT name, description, emoji, rating, delivery_time 
        FROM restaurants WHERE id = ?
    ''', (restaurant_id,))
    restaurant = cursor.fetchone()
    
    if not restaurant:
        await query.edit_message_text("Restaurant not found!")
        return
    
    name, desc, emoji, rating, delivery_time = restaurant
    
    # Build menu text
    menu_text = f"""
{emoji} *{name}*
⭐ {rating} | 🚚 {delivery_time} min

{desc if desc else ''}

*Menu:*
"""
    
    # Get categories and items
    cursor.execute('''
        SELECT category, name, price, emoji, description, id
        FROM menu_items 
        WHERE restaurant_id = ? AND is_available = 1
        ORDER BY category, name
    ''', (restaurant_id,))
    items = cursor.fetchall()
    conn.close()
    
    current_category = None
    keyboard = []
    
    for category, item_name, price, item_emoji, item_desc, item_id in items:
        if category != current_category:
            menu_text += f"\n━━━━ {category} ━━━━\n"
            current_category = category
        
        menu_text += f"{item_emoji} *{item_name}* - ${price:.2f}\n"
        if item_desc:
            menu_text += f"   _{item_desc}_\n"
        
        keyboard.append([InlineKeyboardButton(
            f"{item_emoji} {item_name} - ${price:.2f}",
            callback_data=f"view_item_{item_id}"
        )])
    
    keyboard.append([
        InlineKeyboardButton("🏪 All Restaurants", callback_data="browse_restaurants"),
        InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")
    ])
    
    await query.edit_message_text(
        menu_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def show_item_details(query, context, item_id):
    """Show item details with quantity selector"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT m.name, m.description, m.price, m.emoji, r.name, r.id
        FROM menu_items m
        JOIN restaurants r ON m.restaurant_id = r.id
        WHERE m.id = ?
    ''', (item_id,))
    item = cursor.fetchone()
    conn.close()
    
    if not item:
        await query.answer("Item not found!")
        return
    
    item_name, item_desc, price, emoji, restaurant_name, restaurant_id = item
    
    item_text = f"""
{emoji} *{item_name}*
🏪 From: {restaurant_name}

💰 Price: *${price:.2f}*

{item_desc if item_desc else '*No description*'}

👇 Select quantity:
"""
    
    await query.edit_message_text(
        item_text,
        reply_markup=get_item_detail_keyboard(item_id, restaurant_id),
        parse_mode='Markdown'
    )

async def show_popular_items_callback(query, context):
    """Show popular items via callback"""
    await show_popular_items(query, context)

async def browse_restaurants_callback(query, context):
    """Browse restaurants via callback"""
    await query.edit_message_text(
        "🏪 *Browse Restaurants*\n\nSelect a restaurant to view menu:",
        reply_markup=get_restaurants_keyboard(),
        parse_mode='Markdown'
    )

async def show_main_menu_callback(query, context, user_id):
    """Show main menu via callback"""
    is_admin = (user_id == ADMIN_ID)
    await query.edit_message_text(
        "🏠 *Main Menu*\n\nSelect an option:",
        reply_markup=get_main_menu_keyboard(is_admin),
        parse_mode='Markdown'
    )

async def show_admin_dashboard_callback(query, context):
    """Show admin dashboard via callback"""
    await query.edit_message_text(
        "👑 *Admin Dashboard*\n\nSelect an option:",
        reply_markup=get_admin_dashboard_keyboard(),
        parse_mode='Markdown'
    )

async def start_add_food_conversation(query, context, restaurant_id):
    """Start adding food item conversation"""
    context.user_data['add_food_restaurant'] = restaurant_id
    await query.edit_message_text(
        "🍽️ *Add New Menu Item*\n\nEnter food name:",
        parse_mode='Markdown'
    )
    # Note: This would continue to conversation handler

async def edit_restaurant(query, context, restaurant_id):
    """Edit restaurant details"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, description, delivery_time, is_active FROM restaurants WHERE id = ?", (restaurant_id,))
    restaurant = cursor.fetchone()
    conn.close()
    
    if restaurant:
        name, desc, delivery_time, is_active = restaurant
        status = "✅ Active" if is_active else "❌ Inactive"
        
        text = f"""
🏪 *Edit Restaurant: {name}*

📝 Description: {desc or 'None'}
⏰ Delivery Time: {delivery_time} minutes
📊 Status: {status}

*Options:*
1. Change name
2. Update description  
3. Adjust delivery time
4. Toggle active status
5. View menu items
"""
        
        keyboard = [
            [
                InlineKeyboardButton("✏️ Edit Name", callback_data=f"edit_rest_name_{restaurant_id}"),
                InlineKeyboardButton("📝 Edit Desc", callback_data=f"edit_rest_desc_{restaurant_id}")
            ],
            [
                InlineKeyboardButton("⏰ Delivery Time", callback_data=f"edit_rest_time_{restaurant_id}"),
                InlineKeyboardButton("🔄 Toggle Status", callback_data=f"toggle_rest_status_{restaurant_id}")
            ],
            [
                InlineKeyboardButton("📋 View Menu", callback_data=f"view_rest_menu_{restaurant_id}"),
                InlineKeyboardButton("➕ Add Item", callback_data=f"add_item_to_{restaurant_id}")
            ],
            [InlineKeyboardButton("🔙 Back", callback_data="manage_restaurants")]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

async def show_pending_orders_admin(query, context):
    """Show pending orders to admin"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT o.id, o.order_code, o.customer_name, o.phone, o.total_price, 
               o.dorm, o.block, o.created_at, r.name
        FROM orders o
        JOIN restaurants r ON o.restaurant_id = r.id
        WHERE o.status = 'pending'
        ORDER BY o.created_at ASC
        LIMIT 10
    ''')
    orders = cursor.fetchall()
    conn.close()
    
    if not orders:
        await query.edit_message_text(
            "✅ No pending orders at the moment!",
            reply_markup=get_admin_orders_keyboard()
        )
        return
    
    text = "⏳ *Pending Orders*\n\n"
    keyboard = []
    
    for order in orders:
        order_id, code, name, phone, total, dorm, block, time, restaurant = order
        time_str = datetime.strptime(time, '%Y-%m-%d %H:%M:%S').strftime('%H:%M')
        
        text += f"""
📦 *{code}*
👤 {name} | 📞 {phone}
🍽️ {restaurant}
💰 ${total:.2f} | 📍 {dorm}, {block}
⏰ {time_str}
────────────
"""
        
        keyboard.append([
            InlineKeyboardButton(f"✅ Accept {code}", callback_data=f"accept_order_{order_id}"),
            InlineKeyboardButton(f"📞 Call", callback_data=f"call_customer_{phone}")
        ])
    
    keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data="admin_pending_orders")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_dashboard")])
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ===================== USER PROFILE & ORDERS =====================
async def show_my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's orders"""
    user_id = update.effective_user.id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT o.id, o.order_code, o.total_price, o.status, o.created_at, r.name
        FROM orders o
        JOIN restaurants r ON o.restaurant_id = r.id
        WHERE o.user_id = ?
        ORDER BY o.created_at DESC
        LIMIT 5
    ''', (user_id,))
    orders = cursor.fetchall()
    conn.close()
    
    if not orders:
        await update.message.reply_text(
            "📭 *No Orders Yet*\n\n"
            "You haven't placed any orders yet. Browse restaurants to get started!",
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    text = "📋 *My Recent Orders*\n\n"
    
    for order_id, code, total, status, time, restaurant in orders:
        time_str = datetime.strptime(time, '%Y-%m-%d %H:%M:%S').strftime('%b %d, %H:%M')
        status_emoji = {
            'pending': '⏳',
            'accepted': '✅',
            'preparing': '👨‍🍳',
            'delivered': '🚚',
            'cancelled': '❌'
        }.get(status, '📦')
        
        text += f"""
{status_emoji} *{code}*
🏪 {restaurant}
💰 ${total:.2f}
📊 {status.title()}
⏰ {time_str}
────────────
"""
    
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_my_orders")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def show_my_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user profile"""
    user_id = update.effective_user.id
    user_info = get_user_info(user_id)
    
    if not user_info:
        profile_text = """
👤 *Profile Not Complete*

You haven't set up your profile yet. Complete it for faster ordering!

*Tap buttons below to update:*
"""
        keyboard = [
            [KeyboardButton("📱 Update Phone"), KeyboardButton("🏠 Update Address")],
            [KeyboardButton("🏠 Main Menu")]
        ]
        
        await update.message.reply_text(
            profile_text,
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
            parse_mode='Markdown'
        )
        return
    
    # user_info structure: (user_id, username, full_name, phone, dorm, block, room, is_verified, created_at, last_order)
    user_id, username, full_name, phone, dorm, block, room, is_verified, created_at, last_order = user_info
    
    profile_text = f"""
👤 *My Profile*

📛 Name: {full_name or 'Not set'}
📞 Phone: {phone or 'Not set'}
📍 Address: {f'Dorm {dorm}, Block {block}' + (f', Room {room}' if room else '') or 'Not set'}
✅ Verified: {'Yes ✅' if is_verified else 'No ❌'}
📅 Member since: {created_at[:10] if created_at else 'N/A'}
"""
    
    if last_order:
        profile_text += f"🛒 Last order: {last_order[:10]}\n"
    
    # Get order stats
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*), SUM(total_price) FROM orders WHERE user_id = ?", (user_id,))
    stats = cursor.fetchone()
    conn.close()
    
    order_count = stats[0] or 0
    total_spent = stats[1] or 0
    
    profile_text += f"""
📊 *Order Stats:*
📦 Total Orders: {order_count}
💰 Total Spent: ${total_spent:.2f}
"""
    
    keyboard = [
        [KeyboardButton("✏️ Edit Profile"), KeyboardButton("📱 Change Phone")],
        [KeyboardButton("📍 Update Address"), KeyboardButton("🔐 Privacy")],
        [KeyboardButton("🏠 Main Menu")]
    ]
    
    await update.message.reply_text(
        profile_text,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        parse_mode='Markdown'
    )

async def show_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show shopping cart"""
    await update.message.reply_text(
        "🛒 *Your Cart is Empty*\n\n"
        "Browse restaurants and add items to your cart for faster ordering!",
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )

# ===================== MAIN FUNCTION =====================
def main():
    """Start the bot"""
    # Initialize database
    init_database()
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("menu", start_command))
    
    # Add message handler for text messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    # Add callback query handler
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    
    # Add conversation handler for admin restaurant addition
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.TEXT & filters.Regex("^➕ Add Restaurant$"), 
                         lambda u, c: u.message.text == "➕ Add Restaurant" and u.effective_user.id == ADMIN_ID)
        ],
        states={
            GETTING_RESTAURANT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_restaurant_name)
            ],
            GETTING_FOOD_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_restaurant_desc)
            ],
        },
        fallbacks=[]
    )
    
    application.add_handler(conv_handler)
    
    # Start the bot
    logger.info("🤖 Starting TAP&EAT Professional Bot...")
    logger.info(f"👑 Admin ID: {ADMIN_ID}")
    logger.info("✅ Bot initialized with professional UI")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
