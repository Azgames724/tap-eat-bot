import os
import telebot
from datetime import datetime

# Your bot token from @BotFather
BOT_TOKEN = os.getenv("BOT_TOKEN", "8367062998:AAEr51KmoIKEIM5iHbfDU9W0jo_cPyivQCE")
# Your Telegram ID from @userinfobot
ADMIN_ID = 6237524660

bot = telebot.TeleBot(BOT_TOKEN)

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
        for i, order in enumerate(orders[-10:], 1):  # Show last 10 orders
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
            
            # Create order string
            order_time = datetime.now().strftime("%H:%M")
            order_text = f"""
🚨 *NEW ORDER*
⏰ {order_time}
🍽️ {food}
🔢 {quantity}
👤 {name}
📞 {phone}
📍 Dorm {dorm}, Block {block}
            """
            
            # Save order
            orders.append(order_text)
            
            # Send to student
            bot.reply_to(message, 
                f"✅ *Order Received!*\n\n"
                f"We'll contact you at *{phone}*\n"
                f"Delivery to: Dorm *{dorm}*, Block *{block}*\n\n"
                f"Order will be ready in 30-45 minutes.",
                parse_mode='Markdown'
            )
            
            # Send to ADMIN (you)
            try:
                bot.send_message(
                    ADMIN_ID,
                    order_text,
                    parse_mode='Markdown'
                )
                bot.send_message(
                    ADMIN_ID,
                    f"📞 Call: {phone}\n👤 Name: {name}",
                    parse_mode='Markdown'
                )
            except:
                pass
                
        except Exception as e:
            bot.reply_to(message, "❌ Error. Please check format!")
    else:
        bot.reply_to(message,
            "Please send in correct format:\n\n"
            "Food name\n"
            "Quantity\n"
            "Phone number\n"
            "Your name\n"
            "Dorm number\n"
            "Block number\n\n"
            "Example:\n"
            "Pizza\n"
            "2\n"
            "0123456789\n"
            "John\n"
            "Dorm 5\n"
            "Block B"
        )

# Add web server for Railway health checks
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "🤖 TAP&EAT Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# Start the bot
print("🚀 Starting TAP&EAT Bot...")
print(f"👑 Admin ID: {ADMIN_ID}")
print("✅ Bot is now running!")

keep_alive()
bot.polling(non_stop=True, interval=0)
