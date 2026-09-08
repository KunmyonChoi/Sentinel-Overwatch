#!/bin/bash
echo ">>> Cleaning up simulation data..."

# 1. Clear the test authentication log
if [ -f "backend/test_auth.log" ]; then
    echo "" > backend/test_auth.log
    echo "✓ Cleared backend/test_auth.log"
else
    echo "⚠ backend/test_auth.log not found, skipping."
fi

# 2. Remove the database (resets all events and blocked IPs)
if [ -f "backend/security_monitor.db" ]; then
    rm backend/security_monitor.db
    echo "✓ Removed backend/security_monitor.db"
else
    echo "⚠ backend/security_monitor.db not found, skipping."
fi

# 3. Kill any lingering dummy processes (just in case)
pkill -f "./nmap" 2>/dev/null
pkill -f "./wireshark" 2>/dev/null
echo "✓ Killed lurking dummy processes"

echo ">>> Cleanup Complete."
echo "Please run './start.sh' to restart the system with a fresh database."
