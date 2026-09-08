#!/bin/bash

# Kill running ports if any (cleanup)
fuser -k 8000/tcp 2>/dev/null
fuser -k 5173/tcp 2>/dev/null

echo "Starting Security Monitor System..."

# Start Backend
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install sqlalchemy
python3 app.py &
BACKEND_PID=$!
echo "Backend started (PID: $BACKEND_PID)"

# Start Frontend
cd ../frontend
npm run dev -- --host 127.0.0.1 &
FRONTEND_PID=$!
echo "Frontend started (PID: $FRONTEND_PID)"

# Wait for process
wait $BACKEND_PID $FRONTEND_PID
