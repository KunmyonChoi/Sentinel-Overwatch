import os
import requests
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger("notifications")

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

def notify_critical_event(event_type: str, description: str):
    """Unified alert for any CRITICAL severity event."""
    send_slack_alert(
        title=f"🔴 CRITICAL: {event_type}",
        message=description,
        color="#ff0000",
    )

def send_slack_alert(title, message, color="#ff0000"):
    """
    Sends a formatted alert to Slack using a Webhook.
    """
    if not SLACK_WEBHOOK_URL:
        logger.warning("SLACK_WEBHOOK_URL not set. Skipping notification.")
        return

    payload = {
        "text": f"*{title}*\n{message}",
        "attachments": [
            {
                "color": color,
                "fields": [
                    {
                        "title": "Alert Details",
                        "value": message,
                        "short": False
                    }
                ]
            }
        ]
    }

    try:
        response = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=5)
        if response.status_code != 200:
            logger.error(f"Failed to send Slack alert. Status: {response.status_code}, Response: {response.text}")
        else:
            logger.info(f"Slack alert sent: {title}")
    except Exception as e:
        logger.error(f"Error sending Slack alert: {e}")
