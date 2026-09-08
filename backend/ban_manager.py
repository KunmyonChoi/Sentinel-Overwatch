import os
import datetime
from sqlalchemy.orm import Session
from database import BlockedIP, Event

from notifications import send_slack_alert

class BanManager:
    def __init__(self, db: Session):
        self.db = db

    def ban_ip(self, ip_address: str, reason: str):
        # Check if already banned
        existing = self.db.query(BlockedIP).filter(
            BlockedIP.ip_address == ip_address, 
            BlockedIP.status == "ACTIVE"
        ).first()
        
        if existing:
            return # Already banned

        print(f"!!! BANNING IP: {ip_address} reason: {reason} !!!")
        
        # Simulate iptables command
        # In a real scenario: os.system(f"iptables -A INPUT -s {ip_address} -j DROP")
        
        # Log to DB
        new_ban = BlockedIP(ip_address=ip_address, reason=reason)
        self.db.add(new_ban)
        
        # Log event
        event = Event(
            event_type="SYSTEM",
            severity="INFO",
            source="BanManager",
            description=f"IP {ip_address} has been blocked. Reason: {reason}"
        )
        self.db.add(event)
        self.db.commit()

        # Send Slack Alert
        send_slack_alert(
            title="🚫 IP BANNED",
            message=f"IP Check: `{ip_address}` has been banned.\nReason: {reason}",
            color="#ff0000"
        )

    def unblock_ip(self, ip_address: str):
        # Find active ban
        existing = self.db.query(BlockedIP).filter(
            BlockedIP.ip_address == ip_address, 
            BlockedIP.status == "ACTIVE"
        ).first()

        if existing:
            print(f"!!! UNBLOCKING IP: {ip_address} !!!")
            # Simulate iptables command
            # In a real scenario: os.system(f"iptables -D INPUT -s {ip_address} -j DROP")
            
            existing.status = "UNBLOCKED"
            
            # Log event
            event = Event(
                event_type="SYSTEM",
                severity="INFO",
                source="BanManager",
                description=f"IP {ip_address} has been unblocked manually."
            )
            self.db.add(event)
            self.db.commit()
            return True
        return False
