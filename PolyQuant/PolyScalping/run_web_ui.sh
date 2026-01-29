#!/bin/bash

echo "🚀 Starting BTC Scalping Web UI..."
echo ""
echo "1. Stopping any existing server..."
pkill -f btc_web_server 2>/dev/null
sleep 1

echo "2. Starting new server..."
python3 btc_web_server.py &
sleep 3

echo ""
echo "✅ Server started!"
echo ""
echo "📱 Access the dashboard:"
echo "   Local:    http://localhost:8000"
echo "   Network:  http://$(ipconfig getifaddr en0 2>/dev/null || hostname -I | awk '{print $1}'):8000"
echo ""
echo "🎯 Features:"
echo "   - ➕ Add Market button (top right)"
echo "   - Real-time trading monitoring"
echo "   - WebSocket live updates"
echo ""
echo "📖 Guide: HOW_TO_ADD_MARKETS.md"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Keep script running
tail -f /dev/null
