#!/bin/bash

cd "$(dirname "$0")"

echo "Starting Agrino bridge..."
python3 bridgenew.py &
BRIDGE_PID=$!

sleep 3

echo "Starting ngrok tunnel..."
ngrok http --url=shale-gladly-sip.ngrok-free.dev 8001 &
NGROK_PID=$!

echo ""
echo "Agrino is live at: https://shale-gladly-sip.ngrok-free.dev"
echo ""
echo "Press Ctrl+C to stop everything."

trap "kill $BRIDGE_PID $NGROK_PID 2>/dev/null; exit" INT
wait
