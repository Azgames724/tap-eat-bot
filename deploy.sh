 #!/bin/bash

echo "===================================="
echo "   TAP&EAT BOT - LINUX/MAC DEPLOY"
echo "===================================="
echo

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 is not installed!"
    echo "Please install Python 3.8+"
    exit 1
fi

echo "✅ Python3 is installed"

# Install dependencies
echo "📦 Installing dependencies..."
pip3 install -r requirements.txt

echo
echo "🤖 Starting TAP&EAT Bot..."
echo "👑 Admin ID: 6237524660"
echo

# Run bot
python3 bot.py