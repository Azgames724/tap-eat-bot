import os
import logging
import sqlite3
import random
import string
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    MenuButtonCommands,
    MenuButtonWebApp,
    WebAppInfo
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
from telegram.constants import ParseMode, ChatAction
import asyncio
from enum import Enum
import aiohttp
from flask import Flask, jsonify, request
import threading
import time

# ===================== CONFIGURATION =====================
class OrderStatus(Enum):
    PENDING = "⏳ Pending"
    PREPARING = "👨‍🍳 Preparing"
    ON_THE_WAY = "🚗 On the way"
    DELIVERED = "✅ Delivered"
    CANCELLED = "❌ Cancelled"

# Get environment variables
def get_config():
    config = {
        'BOT_TOKEN': os.environ.get('BOT_TOKEN', '8367062998:AAF0gmnN5VvLw4Vkosa89O9qK8ogrWmo7so').strip(),
        'ADMIN_ID': int(os.environ.get('ADMIN_ID', '6237524660')),
        'DATABASE_FILE': 'tap_eat.db',
        'PORT': int(os.environ.get('PORT', '8080')),
        'WEBHOOK_URL': os.environ.get('WEBHOOK_URL', ''),
    }
    print(f"🎯 Configuration loaded")
    print(f"🤖 Bot Token: {config['BOT_TOKEN'][:10]}...")
    print(f"👑 Admin ID: {config['ADMIN_ID']}")
    return config

config = get_config()
BOT_TOKEN = config['BOT_TOKEN']
ADMIN_ID = config['ADMIN_ID']
DATABASE_FILE = config['DATABASE_FILE']

# Setup advanced logging
logging.basicConfig(
    format='🏷️ %(asctime)s - %(name)s - %(levelname)s\n📝 %(message)s\n' + '─' * 50,
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ===================== ANIMATION & UI HELPERS =====================
class TypingAnimation:
    """Simulate typing animation"""
    @staticmethod
    async def send_with_typing(update: Update, text: str, **kwargs):
        """Send message with typing animation"""
        await update.effective_chat.send_chat_action(ChatAction.TYPING)
        await asyncio.sleep(min(len(text) * 0.01, 1.5))  # Dynamic typing time
        return await update.message.reply_text(text, **kwargs) if update.message else await update.callback_query.message.reply_text(text, **kwargs)

class ProgressIndicator:
    """Create progress bars and loading indicators"""
    @staticmethod
    def create_progress_bar(percentage: int, width: int = 10) -> str:
        """Create a visual progress bar"""
        filled = int(width * percentage / 100)
        empty = width - filled
        bar = '█' * filled + '░' * empty
        return f"[{bar}] {percentage}%"
    
    @staticmethod
    def create_loading_animation(step: int = 0) -> str:
        """Create loading animation with different frames"""
        animations = ['🔄', '⏳', '⌛', '⏰', '🕐', '🕑', '🕒', '🕓', '🕔']
        return animations[step % len(animations)]

class EmojiManager:
    """Manage emojis for different categories"""
    EMOJI_MAP = {
        'restaurants': {
            'pizza': '🍕', 'burger': '🍔', 'coffee': '☕', 'wrap': '🌯',
            'sushi': '🍣', 'taco': '🌮', 'salad': '🥗', 'noodles': '🍜'
        },
        'actions': {
            'order': '📝', 'view': '👁️', 'edit': '✏️', 'delete': '🗑️',
            'confirm': '✅', 'cancel': '❌', 'back': '🔙', 'home': '🏠'
        },
        'status': {
            'pending': '⏳', 'preparing': '👨‍🍳', 'delivering': '🚗',
            'delivered': '✅', 'cancelled': '❌'
        }
    }

# ===================== DATABASE MANAGER =====================
class DatabaseManager:
    """Advanced database management with connection pooling"""
    
    @staticmethod
    def get_connection():
        conn = sqlite3.connect(DATABASE_FILE, check_same_thread=False)
        conn.row_factory = sqlite3.Row  # Enable dict-like access
        return conn
    
    @staticmethod
    def init_database():
        """Initialize database with modern schema"""
        conn = DatabaseManager.get_connection()
        cursor = conn.cursor()
        
        # Users table with more fields
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                phone TEXT,
                dorm TEXT,
                block TEXT,
                room TEXT,
                preferences TEXT DEFAULT '{}',
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_orders INTEGER DEFAULT 0,
                total_spent REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Restaurants with categories and ratings
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS restaurants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                description TEXT,
                category TEXT,
                rating REAL DEFAULT 4.5,
                delivery_time INTEGER DEFAULT 30,
                min_order REAL DEFAULT 10.0,
                image_url TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Menu items with dietary info
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS menu_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                restaurant_id INTEGER,
                name TEXT,
                description TEXT,
                price REAL,
                category TEXT,
                is_spicy BOOLEAN DEFAULT 0,
                is_vegetarian BOOLEAN DEFAULT 0,
                is_available BOOLEAN DEFAULT 1,
                calories INTEGER,
                image_url TEXT,
                FOREIGN KEY (restaurant_id) REFERENCES restaurants(id)
            )
        ''')
        
        # Enhanced orders table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_code TEXT UNIQUE,
                user_id INTEGER,
                restaurant_id INTEGER,
                restaurant_name TEXT,
                items TEXT,  -- JSON string of items
                subtotal REAL,
                delivery_fee REAL DEFAULT 2.99,
                tax REAL,
                total_price REAL,
                customer_name TEXT,
                phone TEXT,
                delivery_address TEXT,
                special_instructions TEXT,
                status TEXT DEFAULT 'pending',
                payment_method TEXT DEFAULT 'cash',
                estimated_delivery TIMESTAMP,
                actual_delivery TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        
        # Cart table for active carts
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS carts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE,
                items TEXT DEFAULT '[]',  -- JSON string
                restaurant_id INTEGER,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        
        # Check if we need sample data
        cursor.execute("SELECT COUNT(*) FROM restaurants")
        if cursor.fetchone()[0] == 0:
            logger.info("Adding sample restaurants and menu items...")
            DatabaseManager._add_sample_data(cursor)
        
        conn.commit()
        conn.close()
        logger.info("✅ Database initialized with modern schema")
    
    @staticmethod
    def _add_sample_data(cursor):
        """Add modern sample data"""
        # Add trendy restaurants
        restaurants = [
            {
                'name': '🍕 Artisan Pizza Co.',
                'description': 'Hand-tossed artisanal pizzas with organic ingredients',
                'category': 'Italian',
                'rating': 4.8,
                'delivery_time': 25,
                'min_order': 15.99,
                'image_url': 'https://i.imgur.com/2QZQZwM.png'
            },
            {
                'name': '🍔 Gourmet Burger Hub',
                'description': 'Premium burgers with exotic toppings',
                'category': 'American',
                'rating': 4.7,
                'delivery_time': 20,
                'min_order': 12.99,
                'image_url': 'https://i.imgur.com/4J6XwQ9.png'
            },
            {
                'name': '☕ Urban Coffee Lab',
                'description': 'Specialty coffee & artisanal pastries',
                'category': 'Cafe',
                'rating': 4.9,
                'delivery_time': 15,
                'min_order': 8.99,
                'image_url': 'https://i.imgur.com/7K8QwZ2.png'
            },
            {
                'name': '🌯 Fresh Wrap Station',
                'description': 'Healthy wraps with fresh ingredients',
                'category': 'Healthy',
                'rating': 4.6,
                'delivery_time': 18,
                'min_order': 9.99,
                'image_url': 'https://i.imgur.com/9J8QwZ3.png'
            },
            {
                'name': '🍣 Sushi Masters',
                'description': 'Authentic Japanese sushi & rolls',
                'category': 'Japanese',
                'rating': 4.9,
                'delivery_time': 30,
                'min_order': 18.99,
                'image_url': 'https://i.imgur.com/1J8QwZ4.png'
            }
        ]
        
        for rest in restaurants:
            cursor.execute('''
                INSERT INTO restaurants (name, description, category, rating, delivery_time, min_order, image_url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (rest['name'], rest['description'], rest['category'], rest['rating'], 
                  rest['delivery_time'], rest['min_order'], rest['image_url']))
        
        # Get restaurant IDs and add modern menu items
        for i, rest in enumerate(restaurants, 1):
            if 'Pizza' in rest['name']:
                items = [
                    ('Truffle Mushroom Pizza', 'Wild mushrooms, truffle oil, mozzarella', 18.99, 'Signature', 0, 1, 850),
                    ('Spicy Pepperoni Deluxe', 'Double pepperoni, jalapeños, honey', 16.99, 'Spicy', 1, 0, 920),
                    ('Vegan Garden Pizza', 'Seasonal veggies, vegan cheese, pesto', 15.99, 'Vegan', 0, 1, 680)
                ]
            elif 'Burger' in rest['name']:
                items = [
                    ('Black Truffle Burger', 'Wagyu beef, black truffle, brioche bun', 22.99, 'Premium', 0, 0, 1100),
                    ('Spicy Chicken Supreme', 'Buttermilk chicken, ghost pepper mayo', 14.99, 'Spicy', 1, 0, 850),
                    ('Impossible Burger', 'Plant-based patty, vegan cheese', 16.99, 'Vegan', 0, 1, 720)
                ]
            elif 'Coffee' in rest['name']:
                items = [
                    ('Artisan Cold Brew', '24-hour cold brew with oat milk', 6.99, 'Coffee', 0, 1, 120),
                    ('Matcha Latte', 'Ceremonial grade matcha, almond milk', 7.99, 'Tea', 0, 1, 140),
                    ('Croissant Basket', 'Assorted artisanal croissants', 12.99, 'Pastries', 0, 1, 480)
                ]
            elif 'Wrap' in rest['name']:
                items = [
                    ('Mediterranean Wrap', 'Falafel, hummus, tahini, veggies', 10.99, 'Vegetarian', 0, 1, 420),
                    ('Spicy Chicken Caesar', 'Grilled chicken, romaine, parmesan', 11.99, 'Chicken', 1, 0, 580),
                    ('Protein Power Bowl', 'Quinoa, chickpeas, avocado, tofu', 13.99, 'Healthy', 0, 1, 520)
                ]
            else:  # Sushi
                items = [
                    ('Dragon Roll', 'Eel, avocado, cucumber, eel sauce', 18.99, 'Special Rolls', 0, 0, 420),
                    ('Vegetable Tempura', 'Assorted vegetables, tempura batter', 14.99, 'Vegetarian', 0, 1, 380),
                    ('Spicy Tuna Bowl', 'Tuna, spicy mayo, rice, seaweed', 16.99, 'Bowls', 1, 0, 450)
                ]
            
            for name, desc, price, category, spicy, veg, calories in items:
                cursor.execute('''
                    INSERT INTO menu_items (restaurant_id, name, description, price, category, is_spicy, is_vegetarian, calories)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (i, name, desc, price, category, spicy, veg, calories))

# ===================== UI COMPONENTS =====================
class ModernUI:
    """Create modern UI components"""
    
    @staticmethod
    def create_main_menu(user_id: int) -> InlineKeyboardMarkup:
        """Create modern main menu with grid layout"""
        is_admin = (user_id == ADMIN_ID)
        
        keyboard = [
            # Row 1: Primary actions
            [
                InlineKeyboardButton("🍽️ Browse Restaurants", callback_data="browse_restaurants"),
                InlineKeyboardButton("🛒 View Cart", callback_data="view_cart")
            ],
            # Row 2: Secondary actions
            [
                InlineKeyboardButton("📦 My Orders", callback_data="my_orders"),
                InlineKeyboardButton("⭐ Favorites", callback_data="favorites")
            ],
            # Row 3: Tertiary actions
            [
                InlineKeyboardButton("👤 Profile", callback_data="profile"),
                InlineKeyboardButton("⚙️ Settings", callback_data="settings")
            ]
        ]
        
        if is_admin:
            keyboard.append([
                InlineKeyboardButton("👑 Admin Dashboard", callback_data="admin_dashboard")
            ])
        
        # Add bottom row with help and refresh
        keyboard.append([
            InlineKeyboardButton("❓ Help", callback_data="help"),
            InlineKeyboardButton("🔄 Refresh", callback_data="refresh")
        ])
        
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def create_restaurant_card(restaurant: dict) -> str:
        """Create beautiful restaurant card"""
        rating_stars = '⭐' * int(restaurant['rating'])
        rating_decimal = restaurant['rating'] - int(restaurant['rating'])
        if rating_decimal >= 0.5:
            rating_stars += '½'
        
        card = f"""
🏪 *{restaurant['name']}* {rating_stars} ({restaurant['rating']})

📝 _{restaurant['description']}_

📊 **Category:** {restaurant['category']}
⏱️ **Delivery:** {restaurant['delivery_time']} min
💰 **Min Order:** ${restaurant['min_order']}

📍 _Tap below to view menu_
        """
        return card
    
    @staticmethod
    def create_restaurant_keyboard(restaurant_id: int) -> InlineKeyboardMarkup:
        """Create restaurant action keyboard"""
        keyboard = [
            [
                InlineKeyboardButton("📋 View Menu", callback_data=f"menu_{restaurant_id}"),
                InlineKeyboardButton("⭐ Add to Favorites", callback_data=f"fav_{restaurant_id}")
            ],
            [
                InlineKeyboardButton("📍 Directions", callback_data=f"directions_{restaurant_id}"),
                InlineKeyboardButton("📞 Contact", callback_data=f"contact_{restaurant_id}")
            ],
            [InlineKeyboardButton("🔙 Back to Restaurants", callback_data="browse_restaurants")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def create_menu_item_card(item: dict) -> str:
        """Create modern menu item card"""
        emoji = "🌶️ " if item['is_spicy'] else ""
        emoji += "🌱 " if item['is_vegetarian'] else ""
        emoji += "🔥 " if item.get('calories') else ""
        
        card = f"""
{emoji}*{item['name']}* - ${item['price']:.2f}

{item['description']}

📊 **Category:** {item['category']}
{"🌶️ **Spicy** • " if item['is_spicy'] else ""}{"🌱 **Vegetarian** • " if item['is_vegetarian'] else ""}{f"🔥 {item.get('calories', 0)} cal" if item.get('calories') else ""}

_Select quantity to add to cart_
        """
        return card
    
    @staticmethod
    def create_quantity_selector(item_id: int, max_qty: int = 10) -> InlineKeyboardMarkup:
        """Create quantity selector with modern layout"""
        keyboard = []
        row = []
        
        # Create number buttons
        for i in range(1, max_qty + 1):
            if i <= 6:
                row.append(InlineKeyboardButton(str(i), callback_data=f"add_{item_id}_{i}"))
                if len(row) == 3:
                    keyboard.append(row)
                    row = []
        
        if row:
            keyboard.append(row)
        
        # Add custom quantity button
        keyboard.append([
            InlineKeyboardButton("🔢 Custom Quantity", callback_data=f"custom_{item_id}")
        ])
        
        # Navigation buttons
        keyboard.append([
            InlineKeyboardButton("🔙 Back", callback_data=f"back_to_menu_{item_id}"),
            InlineKeyboardButton("🛒 View Cart", callback_data="view_cart")
        ])
        
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def create_cart_summary(cart_data: dict) -> str:
        """Create beautiful cart summary"""
        if not cart_data or not cart_data.get('items'):
            return "🛒 *Your cart is empty*\n\nBrowse restaurants to add items!"
        
        items_text = ""
        total = 0
        
        for item in cart_data['items']:
            item_total = item['price'] * item['quantity']
            total += item_total
            items_text += f"• {item['name']} x{item['quantity']} - ${item_total:.2f}\n"
        
        summary = f"""
🛒 *Your Shopping Cart*

{items_text}
────────────
💵 **Subtotal:** ${cart_data.get('subtotal', total):.2f}
🚚 **Delivery:** ${cart_data.get('delivery_fee', 2.99):.2f}
💰 **Tax:** ${cart_data.get('tax', total * 0.08):.2f}
🎯 **Total:** *${cart_data.get('total', total + 2.99 + total * 0.08):.2f}*

📍 **Delivery to:** {cart_data.get('delivery_address', 'Not set')}
        """
        return summary
    
    @staticmethod
    def create_cart_keyboard() -> InlineKeyboardMarkup:
        """Create cart action keyboard"""
        keyboard = [
            [
                InlineKeyboardButton("✅ Checkout", callback_data="checkout"),
                InlineKeyboardButton("🗑️ Clear Cart", callback_data="clear_cart")
            ],
            [
                InlineKeyboardButton("➕ Add More", callback_data="browse_restaurants"),
                InlineKeyboardButton("✏️ Edit Items", callback_data="edit_cart")
            ],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def create_order_status_card(order: dict) -> str:
        """Create order status tracking card"""
        status_emojis = {
            'pending': '⏳',
            'preparing': '👨‍🍳',
            'on_the_way': '🚗',
            'delivered': '✅',
            'cancelled': '❌'
        }
        
        emoji = status_emojis.get(order['status'], '📦')
        
        card = f"""
📦 *Order #{order['id']}* • {order['order_code']}
{emoji} **Status:** {order['status'].replace('_', ' ').title()}

🏪 **Restaurant:** {order['restaurant_name']}
💰 **Total:** ${order['total_price']:.2f}
⏰ **Ordered:** {order['created_at']}

📞 **Contact:** {order['phone']}
📍 **Delivery:** {order['delivery_address']}

{f"📝 **Instructions:** {order['special_instructions']}" if order.get('special_instructions') else ""}
        """
        return card
    
    @staticmethod
    def create_admin_dashboard(stats: dict) -> str:
        """Create modern admin dashboard"""
        return f"""
👑 *Admin Dashboard*

📊 **Today's Stats**
├─ 💰 Revenue: ${stats.get('today_revenue', 0):.2f}
├─ 📦 Orders: {stats.get('today_orders', 0)}
├─ 👥 New Users: {stats.get('today_users', 0)}
└─ ⭐ Avg Rating: {stats.get('avg_rating', 4.5)}

📈 **Overall Stats**
├─ 💰 Total Revenue: ${stats.get('total_revenue', 0):.2f}
├─ 📦 Total Orders: {stats.get('total_orders', 0)}
├─ 👥 Total Users: {stats.get('total_users', 0)}
└─ 🏪 Active Restaurants: {stats.get('active_restaurants', 0)}

⏰ **Pending Actions**
├─ ⏳ Pending Orders: {stats.get('pending_orders', 0)}
├─ ⚠️ Issues: {stats.get('issues', 0)}
└─ 📝 Reviews: {stats.get('pending_reviews', 0)}
        """
    
    @staticmethod
    def create_admin_keyboard() -> InlineKeyboardMarkup:
        """Create admin control panel"""
        keyboard = [
            [
                InlineKeyboardButton("📊 View Orders", callback_data="admin_orders"),
                InlineKeyboardButton("🏪 Manage Restaurants", callback_data="manage_restaurants")
            ],
            [
                InlineKeyboardButton("📈 Analytics", callback_data="analytics"),
                InlineKeyboardButton("👥 Users", callback_data="manage_users")
            ],
            [
                InlineKeyboardButton("⚙️ Settings", callback_data="admin_settings"),
                InlineKeyboardButton("📢 Broadcast", callback_data="broadcast")
            ],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        return InlineKeyboardMarkup(keyboard)

# ===================== BOT HANDLERS =====================
class TapEatBot:
    """Main bot class with modern handlers"""
    
    def __init__(self):
        self.db = DatabaseManager()
        self.ui = ModernUI()
        self.typing = TypingAnimation()
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced start command with animations"""
        user = update.effective_user
        user_id = user.id
        
        # Send typing animation
        await update.message.reply_chat_action(ChatAction.TYPING)
        await asyncio.sleep(0.5)
        
        # Create welcome message with animation
        welcome_text = f"""
🎉 *Welcome to TAP&EAT, {user.first_name}!* 

⚡ *Your Premium Campus Food Delivery Experience*

🌟 **Why Choose Us?**
• 🚀 Lightning-fast delivery (15-30 mins)
• 🎯 Real-time order tracking
• ⭐ Premium restaurant partners
• 💳 Multiple payment options
• 📱 Modern, intuitive interface

👇 *Get started by exploring our features below!*
        """
        
        # Send welcome message
        await update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=self.ui.create_main_menu(user_id)
        )
        
        # Send a follow-up message with features
        features_text = """
🔍 **Explore Features:**
• 🍽️ Browse premium restaurants
• 🛒 Smart shopping cart
• 📦 Track orders in real-time
• ⭐ Save favorites
• 👤 Personalized recommendations

_Ready to experience premium campus dining?_
        """
        
        await asyncio.sleep(1)
        await update.message.reply_text(
            features_text,
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Initialize user in database
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO users (user_id, username, full_name) 
            VALUES (?, ?, ?)
        ''', (user_id, user.username, f"{user.first_name} {user.last_name or ''}".strip()))
        conn.commit()
        conn.close()
    
    async def browse_restaurants(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Browse restaurants with beautiful cards"""
        query = update.callback_query
        await query.answer()
        
        # Show loading animation
        loading_msg = await query.edit_message_text(
            "🔍 *Loading premium restaurants...*\n" + ProgressIndicator.create_loading_animation(0),
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Simulate loading animation
        for i in range(1, 4):
            await asyncio.sleep(0.3)
            await loading_msg.edit_text(
                f"🔍 *Loading premium restaurants...*\n{ProgressIndicator.create_loading_animation(i)}",
                parse_mode=ParseMode.MARKDOWN
            )
        
        # Get restaurants from database
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, name, description, category, rating, delivery_time, min_order 
            FROM restaurants WHERE is_active = 1 ORDER BY rating DESC
        ''')
        restaurants = cursor.fetchall()
        conn.close()
        
        if not restaurants:
            await loading_msg.edit_text(
                "😔 *No restaurants available at the moment.*\n\nCheck back soon or contact support!",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Show first restaurant
        restaurant = dict(restaurants[0])
        await loading_msg.edit_text(
            self.ui.create_restaurant_card(restaurant),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=self.ui.create_restaurant_keyboard(restaurant['id'])
        )
        
        # Store remaining restaurants
        if len(restaurants) > 1:
            context.user_data['restaurants'] = restaurants[1:]
            context.user_data['current_restaurant'] = 0
    
    async def view_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """View restaurant menu with modern cards"""
        query = update.callback_query
        await query.answer()
        
        restaurant_id = int(query.data.split('_')[1])
        
        # Show loading animation
        loading_msg = await query.edit_message_text(
            "📋 *Loading menu...*\n" + ProgressIndicator.create_loading_animation(0),
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Get restaurant info
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT name FROM restaurants WHERE id = ?', (restaurant_id,))
        restaurant = cursor.fetchone()
        
        if not restaurant:
            await loading_msg.edit_text("❌ Restaurant not found!")
            return
        
        # Get menu items
        cursor.execute('''
            SELECT id, name, description, price, category, is_spicy, is_vegetarian, calories
            FROM menu_items 
            WHERE restaurant_id = ? AND is_available = 1
            ORDER BY category, price
        ''', (restaurant_id,))
        items = cursor.fetchall()
        conn.close()
        
        if not items:
            await loading_msg.edit_text(
                f"🏪 *{restaurant['name']}*\n\n📭 Menu is currently empty. Please check back later!",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="browse_restaurants")]])
            )
            return
        
        # Show first item
        item = dict(items[0])
        await loading_msg.edit_text(
            self.ui.create_menu_item_card(item),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=self.ui.create_quantity_selector(item['id'])
        )
        
        # Store remaining items
        if len(items) > 1:
            context.user_data['menu_items'] = items[1:]
            context.user_data['current_item'] = 0
            context.user_data['restaurant_id'] = restaurant_id
    
    async def add_to_cart(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add item to cart with quantity selection"""
        query = update.callback_query
        await query.answer()
        
        _, item_id, quantity = query.data.split('_')
        item_id = int(item_id)
        quantity = int(quantity)
        
        user_id = query.from_user.id
        
        # Get item details
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT mi.*, r.name as restaurant_name 
            FROM menu_items mi 
            JOIN restaurants r ON mi.restaurant_id = r.id 
            WHERE mi.id = ?
        ''', (item_id,))
        item = cursor.fetchone()
        
        if not item:
            await query.answer("❌ Item not found!", show_alert=True)
            return
        
        # Get or create user cart
        cursor.execute('SELECT * FROM carts WHERE user_id = ?', (user_id,))
        cart = cursor.fetchone()
        
        if cart:
            # Check if cart is from same restaurant
            if cart['restaurant_id'] and cart['restaurant_id'] != item['restaurant_id']:
                await query.answer(
                    "⚠️ Your cart contains items from another restaurant. Clear cart to add from here.",
                    show_alert=True
                )
                return
            
            # Update cart
            items = json.loads(cart['items'])
            items.append({
                'id': item['id'],
                'name': item['name'],
                'price': item['price'],
                'quantity': quantity,
                'restaurant_id': item['restaurant_id'],
                'restaurant_name': item['restaurant_name']
            })
            
            cursor.execute('''
                UPDATE carts SET items = ?, restaurant_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (json.dumps(items), item['restaurant_id'], user_id))
        else:
            # Create new cart
            items = [{
                'id': item['id'],
                'name': item['name'],
                'price': item['price'],
                'quantity': quantity,
                'restaurant_id': item['restaurant_id'],
                'restaurant_name': item['restaurant_name']
            }]
            
            cursor.execute('''
                INSERT INTO carts (user_id, items, restaurant_id)
                VALUES (?, ?, ?)
            ''', (user_id, json.dumps(items), item['restaurant_id']))
        
        conn.commit()
        conn.close()
        
        # Show success animation
        await query.answer(f"✅ Added {quantity}x {item['name']} to cart!", show_alert=True)
        
        # Show next item or go back
        if context.user_data.get('menu_items'):
            next_item = context.user_data['menu_items'].pop(0)
            await query.edit_message_text(
                self.ui.create_menu_item_card(dict(next_item)),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.ui.create_quantity_selector(next_item['id'])
            )
            context.user_data['current_item'] = context.user_data.get('current_item', 0) + 1
        else:
            # Ask if user wants to continue shopping or view cart
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("➕ Add More", callback_data=f"menu_{item['restaurant_id']}"),
                    InlineKeyboardButton("🛒 View Cart", callback_data="view_cart")
                ],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
            ])
            
            await query.edit_message_text(
                f"🎯 *Added to Cart Successfully!*\n\n• {quantity}x {item['name']}\n• ${item['price'] * quantity:.2f}\n\nWhat would you like to do next?",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
    
    async def view_cart(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """View cart with beautiful summary"""
        query = update.callback_query
        if query:
            await query.answer()
            message = query.message
        else:
            message = update.message
        
        user_id = query.from_user.id if query else update.effective_user.id
        
        # Get cart data
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM carts WHERE user_id = ?', (user_id,))
        cart = cursor.fetchone()
        conn.close()
        
        if not cart or not json.loads(cart['items']):
            empty_text = """
🛒 *Your cart is empty!*

🌟 **Discover amazing food:**
• Browse premium restaurants
• Try trending dishes
• Save your favorites

👇 Tap below to start exploring!
            """
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🍽️ Browse Restaurants", callback_data="browse_restaurants")],
                [InlineKeyboardButton("⭐ Trending Now", callback_data="trending")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
            ])
            
            if query:
                await query.edit_message_text(empty_text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
            else:
                await message.reply_text(empty_text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
            return
        
        # Calculate cart totals
        items = json.loads(cart['items'])
        subtotal = sum(item['price'] * item['quantity'] for item in items)
        delivery_fee = 2.99
        tax = subtotal * 0.08
        total = subtotal + delivery_fee + tax
        
        cart_data = {
            'items': items,
            'subtotal': subtotal,
            'delivery_fee': delivery_fee,
            'tax': tax,
            'total': total,
            'delivery_address': "Set your delivery address"
        }
        
        if query:
            await query.edit_message_text(
                self.ui.create_cart_summary(cart_data),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.ui.create_cart_keyboard()
            )
        else:
            await message.reply_text(
                self.ui.create_cart_summary(cart_data),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.ui.create_cart_keyboard()
            )
    
    async def checkout(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Modern checkout process"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        
        # Check if user has delivery info
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT phone, dorm, block, room FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        
        if not user or not user['phone']:
            # Ask for delivery info
            await query.edit_message_text(
                """
📋 *Delivery Information Required*

To complete your order, we need your delivery details.

Please send your information in this format:

**Phone Number** (10+ digits)
**Full Name**
**Dorm/Building**
**Block/Floor**
**Room Number** (optional)

Example:
0123456789
John Doe
Dorm 5
Block B
Room 101

Type 'cancel' to abort.
                """,
                parse_mode=ParseMode.MARKDOWN
            )
            context.user_data['awaiting_delivery_info'] = True
            return
        
        # Get cart data
        cursor.execute('SELECT * FROM carts WHERE user_id = ?', (user_id,))
        cart = cursor.fetchone()
        
        if not cart or not json.loads(cart['items']):
            await query.answer("❌ Your cart is empty!", show_alert=True)
            return
        
        # Create order
        items = json.loads(cart['items'])
        restaurant_id = cart['restaurant_id']
        
        # Get restaurant name
        cursor.execute('SELECT name FROM restaurants WHERE id = ?', (restaurant_id,))
        restaurant = cursor.fetchone()
        
        # Calculate totals
        subtotal = sum(item['price'] * item['quantity'] for item in items)
        delivery_fee = 2.99
        tax = subtotal * 0.08
        total = subtotal + delivery_fee + tax
        
        # Generate order code
        order_code = f"TAP{random.randint(1000, 9999)}{random.choice(string.ascii_uppercase)}"
        
        # Create order
        cursor.execute('''
            INSERT INTO orders (
                order_code, user_id, restaurant_id, restaurant_name, items,
                subtotal, delivery_fee, tax, total_price,
                customer_name, phone, delivery_address, status,
                estimated_delivery
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            order_code, user_id, restaurant_id, restaurant['name'], json.dumps(items),
            subtotal, delivery_fee, tax, total,
            f"{user['full_name']}", user['phone'],
            f"Dorm {user['dorm']}, Block {user['block']}{f', Room {user['room']}' if user['room'] else ''}",
            'pending',
            datetime.now() + timedelta(minutes=30)
        ))
        
        order_id = cursor.lastrowid
        
        # Clear cart
        cursor.execute('DELETE FROM carts WHERE user_id = ?', (user_id,))
        
        # Update user stats
        cursor.execute('''
            UPDATE users SET 
            total_orders = total_orders + 1,
            total_spent = total_spent + ?,
            last_active = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (total, user_id))
        
        conn.commit()
        
        # Get order for notification
        cursor.execute('SELECT * FROM orders WHERE id = ?', (order_id,))
        order = cursor.fetchone()
        conn.close()
        
        # Send order confirmation
        confirmation_text = f"""
🎉 *Order Confirmed!*

📦 **Order #{order_id}** • {order_code}
🏪 **Restaurant:** {restaurant['name']}
💰 **Total:** ${total:.2f}
⏰ **Estimated Delivery:** 30-45 minutes

📍 **Delivery to:** 
Dorm {user['dorm']}, Block {user['block']}{f', Room {user['room']}' if user['room'] else ''}

📞 **We'll contact you at:** {user['phone']}

🔄 **Track your order in real-time!**
        """
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📍 Track Order", callback_data=f"track_{order_id}"),
                InlineKeyboardButton("📞 Contact Support", callback_data="support")
            ],
            [InlineKeyboardButton("🛍️ Order Again", callback_data="browse_restaurants")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ])
        
        await query.edit_message_text(
            confirmation_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
        
        # Notify admin
        await self._notify_admin(context, order)
        
        # Send order tracking updates (simulated)
        await self._send_tracking_updates(context, order_id, user_id)
    
    async def _send_tracking_updates(self, context: ContextTypes.DEFAULT_TYPE, order_id: int, user_id: int):
        """Send simulated order tracking updates"""
        updates = [
            (5, "👨‍🍳 Restaurant has accepted your order"),
            (10, "👨‍🍳 Chef is preparing your food"),
            (15, "✅ Food is ready for pickup"),
            (20, "🚗 Delivery partner is on the way"),
            (25, "📍 Approaching your location"),
            (30, "✅ Order delivered! Enjoy your meal!")
        ]
        
        for delay, message in updates:
            await asyncio.sleep(delay)
            try:
                await context.bot.send_message(
                    user_id,
                    f"📦 *Order Update*\n\n{message}\n\n_Estimated completion: {30-delay} minutes_",
                    parse_mode=ParseMode.MARKDOWN
                )
            except:
                pass
    
    async def _notify_admin(self, context: ContextTypes.DEFAULT_TYPE, order: dict):
        """Notify admin about new order with rich formatting"""
        try:
            admin_text = f"""
🚨 *NEW ORDER ALERT!*

📦 **Order #{order['id']}** • {order['order_code']}
🏪 **Restaurant:** {order['restaurant_name']}
💰 **Total:** ${order['total_price']:.2f}

👤 **Customer:** {order['customer_name']}
📞 **Phone:** {order['phone']}
📍 **Delivery:** {order['delivery_address']}

⏰ **Order Time:** {order['created_at']}
🕐 **Estimated Delivery:** {order['estimated_delivery']}

📋 **Items Ordered:**
{self._format_order_items(json.loads(order['items']))}

⚠️ *Action Required: Update order status*
            """
            
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Accept", callback_data=f"admin_accept_{order['id']}"),
                    InlineKeyboardButton("👨‍🍳 Preparing", callback_data=f"admin_prepare_{order['id']}")
                ],
                [
                    InlineKeyboardButton("🚗 On the Way", callback_data=f"admin_delivering_{order['id']}"),
                    InlineKeyboardButton("✅ Delivered", callback_data=f"admin_delivered_{order['id']}")
                ],
                [
                    InlineKeyboardButton("📞 Call Customer", callback_data=f"admin_call_{order['id']}"),
                    InlineKeyboardButton("❌ Cancel", callback_data=f"admin_cancel_{order['id']}")
                ]
            ])
            
            await context.bot.send_message(
                ADMIN_ID,
                admin_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Failed to notify admin: {e}")
    
    def _format_order_items(self, items: list) -> str:
        """Format order items for display"""
        formatted = ""
        for item in items:
            formatted += f"• {item['name']} x{item['quantity']} - ${item['price'] * item['quantity']:.2f}\n"
        return formatted
    
    async def admin_dashboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Modern admin dashboard"""
        query = update.callback_query
        await query.answer()
        
        # Check if admin
        if query.from_user.id != ADMIN_ID:
            await query.answer("❌ Admin access required!", show_alert=True)
            return
        
        # Get stats
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        stats = {}
        
        # Today's stats
        cursor.execute('''
            SELECT 
                COUNT(*) as today_orders,
                SUM(total_price) as today_revenue
            FROM orders 
            WHERE DATE(created_at) = DATE('now')
        ''')
        today = cursor.fetchone()
        stats['today_orders'] = today['today_orders'] or 0
        stats['today_revenue'] = today['today_revenue'] or 0
        
        # User stats
        cursor.execute('SELECT COUNT(*) as total_users FROM users')
        stats['total_users'] = cursor.fetchone()['total_users']
        
        cursor.execute('SELECT COUNT(*) as today_users FROM users WHERE DATE(created_at) = DATE("now")')
        stats['today_users'] = cursor.fetchone()['today_users']
        
        # Overall stats
        cursor.execute('SELECT COUNT(*) as total_orders, SUM(total_price) as total_revenue FROM orders')
        overall = cursor.fetchone()
        stats['total_orders'] = overall['total_orders'] or 0
        stats['total_revenue'] = overall['total_revenue'] or 0
        
        # Restaurant stats
        cursor.execute('SELECT COUNT(*) as active_restaurants FROM restaurants WHERE is_active = 1')
        stats['active_restaurants'] = cursor.fetchone()['active_restaurants']
        
        # Pending orders
        cursor.execute('SELECT COUNT(*) as pending_orders FROM orders WHERE status = "pending"')
        stats['pending_orders'] = cursor.fetchone()['pending_orders']
        
        conn.close()
        
        await query.edit_message_text(
            self.ui.create_admin_dashboard(stats),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=self.ui.create_admin_keyboard()
        )
    
    async def handle_delivery_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle delivery information input"""
        if not context.user_data.get('awaiting_delivery_info'):
            return
        
        text = update.message.text.strip()
        
        if text.lower() == 'cancel':
            await update.message.reply_text(
                "❌ Order cancelled. Your cart has been saved.",
                reply_markup=self.ui.create_main_menu(update.effective_user.id)
            )
            context.user_data.pop('awaiting_delivery_info', None)
            return
        
        lines = text.split('\n')
        if len(lines) < 4:
            await update.message.reply_text(
                "❌ Please provide all required information:\n\nPhone Number\nFull Name\nDorm/Building\nBlock/Floor\n\nRoom Number is optional."
            )
            return
        
        # Parse info
        phone = lines[0].strip()
        name = lines[1].strip()
        dorm = lines[2].strip()
        block = lines[3].strip()
        room = lines[4].strip() if len(lines) > 4 else ''
        
        # Validate phone
        if not phone.isdigit() or len(phone) < 10:
            await update.message.reply_text("❌ Please enter a valid phone number (10+ digits)")
            return
        
        # Save to database
        user_id = update.effective_user.id
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE users SET 
            phone = ?, full_name = ?, dorm = ?, block = ?, room = ?,
            last_active = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (phone, name, dorm, block, room, user_id))
        
        conn.commit()
        conn.close()
        
        # Continue to checkout
        context.user_data.pop('awaiting_delivery_info', None)
        
        # Show success message
        await update.message.reply_text(
            f"""
✅ Delivery information saved!

📞 Phone: {phone}
👤 Name: {name}
📍 Address: Dorm {dorm}, Block {block}{f', Room {room}' if room else ''}

Proceeding to checkout...
            """,
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Simulate processing
        await asyncio.sleep(1)
        
        # Show checkout button
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Proceed to Checkout", callback_data="checkout")],
            [InlineKeyboardButton("🛒 View Cart", callback_data="view_cart")]
        ])
        
        await update.message.reply_text(
            "📋 Your delivery information has been saved. Ready to complete your order?",
            reply_markup=keyboard
        )
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle all callback queries"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user_id = query.from_user.id
        
        # Route callbacks
        if data == "main_menu":
            await query.edit_message_text(
                "🏠 *Main Menu*\n\nSelect an option below:",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.ui.create_main_menu(user_id)
            )
        
        elif data == "browse_restaurants":
            await self.browse_restaurants(update, context)
        
        elif data.startswith("menu_"):
            await self.view_menu(update, context)
        
        elif data.startswith("add_"):
            await self.add_to_cart(update, context)
        
        elif data == "view_cart":
            await self.view_cart(update, context)
        
        elif data == "checkout":
            await self.checkout(update, context)
        
        elif data == "admin_dashboard":
            await self.admin_dashboard(update, context)
        
        elif data.startswith("admin_"):
            await self.handle_admin_action(update, context)
        
        elif data == "my_orders":
            await self.show_my_orders(update, context)
        
        elif data == "profile":
            await self.show_profile(update, context)
        
        elif data == "help":
            await self.show_help(update, context)
        
        elif data == "refresh":
            await query.answer("🔄 Refreshed!")
            await query.edit_message_reply_markup(reply_markup=self.ui.create_main_menu(user_id))
    
    async def handle_admin_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle admin actions"""
        query = update.callback_query
        data = query.data
        
        if not data.startswith("admin_"):
            return
        
        # Check admin access
        if query.from_user.id != ADMIN_ID:
            await query.answer("❌ Admin access required!", show_alert=True)
            return
        
        if data.startswith("admin_accept_"):
            order_id = int(data.split('_')[2])
            await self.update_order_status(order_id, "preparing", context)
            await query.answer("✅ Order accepted!")
        
        elif data.startswith("admin_prepare_"):
            order_id = int(data.split('_')[2])
            await self.update_order_status(order_id, "preparing", context)
            await query.answer("👨‍🍳 Order marked as preparing!")
        
        elif data.startswith("admin_delivering_"):
            order_id = int(data.split('_')[2])
            await self.update_order_status(order_id, "on_the_way", context)
            await query.answer("🚗 Order marked as on the way!")
        
        elif data.startswith("admin_delivered_"):
            order_id = int(data.split('_')[2])
            await self.update_order_status(order_id, "delivered", context)
            await query.answer("✅ Order marked as delivered!")
        
        elif data.startswith("admin_cancel_"):
            order_id = int(data.split('_')[2])
            await self.update_order_status(order_id, "cancelled", context)
            await query.answer("❌ Order cancelled!")
        
        elif data.startswith("admin_call_"):
            order_id = int(data.split('_')[2])
            await self.show_customer_contact(update, context, order_id)
    
    async def update_order_status(self, order_id: int, status: str, context: ContextTypes.DEFAULT_TYPE):
        """Update order status and notify customer"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # Update order
        cursor.execute('UPDATE orders SET status = ? WHERE id = ?', (status, order_id))
        
        # Get order details
        cursor.execute('SELECT user_id, order_code FROM orders WHERE id = ?', (order_id,))
        order = cursor.fetchone()
        
        conn.commit()
        conn.close()
        
        if order:
            # Notify customer
            status_messages = {
                'preparing': "👨‍🍳 Your order is being prepared!",
                'on_the_way': "🚗 Your order is on the way!",
                'delivered': "✅ Your order has been delivered! Enjoy your meal!",
                'cancelled': "❌ Your order has been cancelled. Contact support for details."
            }
            
            message = status_messages.get(status, f"Order status updated to {status}")
            
            try:
                await context.bot.send_message(
                    order['user_id'],
                    f"📦 *Order Update*\n\nOrder #{order_id} ({order['order_code']})\n\n{message}",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error(f"Could not notify user: {e}")
    
    async def show_customer_contact(self, update: Update, context: ContextTypes.DEFAULT_TYPE, order_id: int):
        """Show customer contact info to admin"""
        query = update.callback_query
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT customer_name, phone FROM orders WHERE id = ?', (order_id,))
        order = cursor.fetchone()
        conn.close()
        
        if order:
            await query.answer(f"📞 {order['customer_name']}: {order['phone']}", show_alert=True)
        else:
            await query.answer("Order not found!", show_alert=True)
    
    async def show_my_orders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user's order history"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, order_code, restaurant_name, total_price, status, created_at
            FROM orders 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT 5
        ''', (user_id,))
        orders = cursor.fetchall()
        conn.close()
        
        if not orders:
            await query.edit_message_text(
                "📭 *No orders yet!*\n\nStart your first order and join our foodie community!",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🍽️ Browse Restaurants", callback_data="browse_restaurants")],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
                ])
            )
            return
        
        orders_text = "📋 *Your Recent Orders*\n\n"
        for order in orders:
            status_emoji = {
                'pending': '⏳',
                'preparing': '👨‍🍳',
                'on_the_way': '🚗',
                'delivered': '✅',
                'cancelled': '❌'
            }.get(order['status'], '📦')
            
            orders_text += f"""
{status_emoji} **Order #{order['id']}** • {order['order_code']}
🏪 {order['restaurant_name']}
💰 ${order['total_price']:.2f} • 📊 {order['status'].title()}
⏰ {order['created_at'][:16]}
────────────
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📍 Track Latest", callback_data=f"track_{orders[0]['id']}")],
            [InlineKeyboardButton("🔄 Order Again", callback_data="browse_restaurants")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ])
        
        await query.edit_message_text(
            orders_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
    
    async def show_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user profile with stats"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT username, full_name, phone, dorm, block, room, 
                   total_orders, total_spent, created_at
            FROM users WHERE user_id = ?
        ''', (user_id,))
        user = cursor.fetchone()
        conn.close()
        
        if not user:
            await query.edit_message_text("❌ User not found!")
            return
        
        # Calculate user level based on orders
        level = min(user['total_orders'] // 5 + 1, 10)
        level_stars = '⭐' * level
        
        profile_text = f"""
👤 *Your Profile* {level_stars}

📛 **Name:** {user['full_name'] or 'Not set'}
📞 **Phone:** {user['phone'] or 'Not set'}
📍 **Address:** {f"Dorm {user['dorm']}, Block {user['block']}{f', Room {user['room']}' if user['room'] else ''}" if user['dorm'] else 'Not set'}

📊 **Stats:**
├─ 📦 Total Orders: {user['total_orders']}
├─ 💰 Total Spent: ${user['total_spent']:.2f}
├─ 🎯 Member Since: {user['created_at'][:10]}
└─ 🏆 Level: {level}/10

⚡ **Quick Actions:**
        """
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✏️ Edit Profile", callback_data="edit_profile"),
                InlineKeyboardButton("📍 Update Address", callback_data="update_address")
            ],
            [
                InlineKeyboardButton("⭐ Loyalty Rewards", callback_data="rewards"),
                InlineKeyboardButton("⚙️ Preferences", callback_data="preferences")
            ],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ])
        
        await query.edit_message_text(
            profile_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
    
    async def show_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show modern help center"""
        query = update.callback_query
        await query.answer()
        
        help_text = """
❓ *Help Center*

🔍 **How to Order:**
1. Tap '🍽️ Browse Restaurants'
2. Select a restaurant
3. Choose items and quantity
4. Review your cart
5. Provide delivery info
6. Confirm payment

📦 **Order Tracking:**
• Real-time updates every 5 minutes
• Estimated delivery times
• Live delivery tracking (coming soon)

💰 **Payment Methods:**
• 💳 Cash on Delivery
• 📱 Mobile Money (coming soon)
• 💳 Card Payment (coming soon)

🔄 **Need Help?**
• 📞 Contact Support: Tap below
• 📧 Email: support@tapeatt.com
• 🕒 Hours: 24/7

👇 Select an option below:
        """
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📞 Contact Support", callback_data="contact_support"),
                InlineKeyboardButton("📚 FAQ", callback_data="faq")
            ],
            [
                InlineKeyboardButton("⚠️ Report Issue", callback_data="report_issue"),
                InlineKeyboardButton("💡 Suggestions", callback_data="suggestions")
            ],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ])
        
        await query.edit_message_text(
            help_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages"""
        text = update.message.text
        
        if text.startswith('/'):
            return
        
        # Check if we're waiting for delivery info
        if context.user_data.get('awaiting_delivery_info'):
            await self.handle_delivery_info(update, context)
            return
        
        # Default response
        await update.message.reply_text(
            "👋 Hi! Use the menu buttons below to navigate our food delivery service.",
            reply_markup=self.ui.create_main_menu(update.effective_user.id)
        )

# ===================== WEB SERVER & SETUP =====================
def create_flask_app():
    """Create Flask app for health checks"""
    app = Flask(__name__)
    
    @app.route('/')
    def home():
        return jsonify({
            'status': 'online',
            'service': 'tap-eat-bot',
            'version': '2.0.0',
            'features': ['modern-ui', 'real-time-tracking', 'admin-dashboard']
        })
    
    @app.route('/health')
    def health():
        try:
            conn = DatabaseManager.get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT 1')
            conn.close()
            return jsonify({'status': 'healthy'}), 200
        except:
            return jsonify({'status': 'unhealthy'}), 500
    
    return app

async def main():
    """Main application setup"""
    print("🚀 Starting TAP&EAT Premium Bot...")
    print(f"👑 Admin ID: {ADMIN_ID}")
    
    # Initialize database
    DatabaseManager.init_database()
    
    # Create bot application
    application = Application.builder().token(BOT_TOKEN).build()
    bot = TapEatBot()
    
    # Add command handlers
    application.add_handler(CommandHandler('start', bot.start))
    application.add_handler(CommandHandler('help', bot.show_help))
    application.add_handler(CommandHandler('menu', bot.browse_restaurants))
    application.add_handler(CommandHandler('cart', bot.view_cart))
    application.add_handler(CommandHandler('orders', bot.show_my_orders))
    application.add_handler(CommandHandler('profile', bot.show_profile))
    
    # Add callback query handler
    application.add_handler(CallbackQueryHandler(bot.handle_callback))
    
    # Add message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
    
    # Start Flask server in background
    flask_app = create_flask_app()
    port = config['PORT']
    
    def run_flask():
        flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    print(f"🌐 Flask server started on port {port}")
    print("🤖 Starting bot polling...")
    print("✨ TAP&EAT Premium is now running!")
    print("=" * 50)
    
    # Run bot
    await application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    asyncio.run(main())
