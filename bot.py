import os
import telebot
from datetime import datetime
import logging
import time
from flask import Flask
from threading import Thread

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Your bot token from @BotFather
BOT_TOKEN = os.getenv("BOT_TOKEN", "8367062998:AAEr51KmoIKEIM5iHbfDU9W0jo_cPyivQCE")
# Your Telegram ID from @userinfobot
ADMIN_ID = os.getenv("ADMIN_ID", "6237524660")

# Convert ADMIN_ID to integer
try:
    ADMIN_ID = int(ADMIN_ID)
except ValueError:
    logger.error(f"Invalid ADMIN_ID: {ADMIN_ID}. Using default.")
    ADMIN_ID = 6237524660

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# Store orders in memory (for Railway, use database if needed)
orders = []

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    if message.from_user.id == ADMIN_ID:
        bot.reply_to(message, 
            "👑 *ADMIN MODE*\n\n"
            "Commands:\n"
            "/orders - View all orders\n"
            "/clear - Clear all orders\n\n"
            "Students will send orders to you automatically!",
            parse_mode='Markdown')
    else:
        bot.reply_to(message,
            "🎓 *Welcome to TAP&EAT!*\n\n"
            "To order food, send:\n\n"
            "1. Food name\n"
            "2. Quantity\n"
            "3. Your phone\n"
            "4. Your name\n"
            "5. Dorm number\n"
            "6. Block number\n\n"
            "*Example:*\n"
            "Pizza\n"
            "2\n"
            "0123456789\n"
            "John\n"
            "Dorm 5\n"
            "Block B",
            parse_mode='Markdown')

@bot.message_handler(commands=['orders'])
def show_orders(message):
    if message.from_user.id == ADMIN_ID:
        if not orders:
            bot.reply_to(message, "📭 No orders yet!")
            return
        
        text = "📦 *Recent Orders:*\n\n"
        # Show last 10 orders in reverse order (newest first)
        recent_orders = orders[-10:][::-1]
        for i, order in enumerate(recent_orders, 1):
            text += f"{i}. {order}\n"
        
        bot.reply_to(message, text, parse_mode='Markdown')
    else:
        bot.reply_to(message, "❌ Admin only command!")

@bot.message_handler(commands=['clear'])
def clear_orders(message):
    if message.from_user.id == ADMIN_ID:
        orders.clear()
        bot.reply_to(message, "✅ All orders cleared!")
    else:
        bot.reply_to(message, "❌ Admin only command!")

@bot.message_handler(func=lambda message: True)
def handle_order(message):
    user_id = message.from_user.id
    
    # Ignore admin commands
    if user_id == ADMIN_ID and message.text.startswith('/'):
        return
    
    # Parse student order
    lines = message.text.strip().split('\n')
    
    if len(lines) >= 6:
        try:
            food = lines[0].strip()
            quantity = lines[1].strip()
            phone = lines[2].strip()
            name = lines[3].strip()
            dorm = lines[4].strip()
            block = lines[5].strip()
            
            # Validate inputs
            if not all([food, quantity, phone, name, dorm, block]):
                bot.reply_to(message, "❌ All fields are required!")
                return
            
            # Create order string
            order_time = datetime.now().strftime("%H:%M")
            order_date = datetime.now().strftime("%Y-%m-%d")
            
            order_text = f"""
🚨 *NEW ORDER*
📅 {order_date} ⏰ {order_time}
🍽️ {food}
🔢 {quantity}
👤 {name}
📞 {phone}
📍 Dorm {dorm}, Block {block}
            """
            
            # Save order
            orders.append(order_text)
            logger.info(f"New order from {name}: {food} x{quantity}")
            
            # Send confirmation to student
            bot.reply_to(message, 
                f"✅ *Order Received!*\n\n"
                f"Food: *{food}*\n"
                f"Quantity: *{quantity}*\n"
                f"We'll contact you at *{phone}*\n"
                f"Delivery to: Dorm *{dorm}*, Block *{block}*\n\n"
                f"Order will be ready in 30-45 minutes.",
                parse_mode='Markdown'
            )
            
            # Send to ADMIN
            try:
                bot.send_message(
                    ADMIN_ID,
                    order_text,
                    parse_mode='Markdown'
                )
                # Send contact info separately
                contact_info = f"📞 *Contact Info:*\nPhone: {phone}\nName: {name}"
                bot.send_message(ADMIN_ID, contact_info, parse_mode='Markdown')
                
                logger.info(f"Order sent to admin {ADMIN_ID}")
            except Exception as e:
                logger.error(f"Failed to send to admin: {e}")
                
        except Exception as e:
            logger.error(f"Order parsing error: {e}")
            bot.reply_to(message, "❌ Error processing order. Please check the format!")
    else:
        # Show format help
        bot.reply_to(message,
            "📋 *Please use this format:*\n\n"
            "Food name\n"
            "Quantity\n"
            "Phone number\n"
            "Your name\n"
            "Dorm number\n"
            "Block number\n\n"
            "*Example:*\n"
            "Pizza\n"
            "2\n"
            "0123456789\n"
            "John\n"
            "Dorm 5\n"
            "Block B",
            parse_mode='Markdown'
        )

# Add web server for Railway health checks
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 TAP&EAT Bot is running! Orders: " + str(len(orders))

@app.route('/health')
def health():
    return {"status": "healthy", "orders": len(orders)}, 200

def run_flask():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_flask, daemon=True)
    t.start()

# Start the bot with error handling
def main():
    keep_alive()
    logger.info("🚀 Starting TAP&EAT Bot...")
    logger.info(f"👑 Admin ID: {ADMIN_ID}")
    logger.info(f"🤖 Bot username: @{bot.get_me().username}")
    logger.info("✅ Bot is now running!")
    
    while True:
        try:
            bot.polling(non_stop=True, timeout=60)
        except Exception as e:
            logger.error(f"Bot polling error: {e}")
            logger.info("🔄 Restarting bot in 10 seconds...")
            time.sleep(10)

if __name__ == "__main__":
    try:
        # Test bot connection
        bot_info = bot.get_me()
        if bot_info:
            logger.info(f"Bot connected successfully: @{bot_info.username}")
        else:
            logger.error("Failed to connect to Telegram API")
    except Exception as e:
        logger.error(f"Initial connection failed: {e}")
        logger.error("Check your BOT_TOKEN and internet connection")
    
    main()
