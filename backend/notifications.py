"""
알림 발송 (Slack Webhook).

모니터 스레드를 막지 않도록 큐 + 워커 스레드로 보내고,
분당 발송량을 제한해 폭주 시에는 집계 메시지 한 건으로 대체한다.
"""
import logging
import queue
import threading
import time
from collections import deque

import requests

import config

logger = logging.getLogger("notifications")

_queue: "queue.Queue[dict]" = queue.Queue()
_worker_started = False
_lock = threading.Lock()
_sent_times: deque = deque()
_suppressed: list[str] = []


def enqueue(title: str, message: str, color: str = "#ff0000"):
    """알림을 큐에 넣는다. 발송은 워커가 담당한다."""
    _ensure_worker()
    _queue.put({"title": title, "message": message, "color": color})


def send_slack_alert(title, message, color="#ff0000"):
    """이전 API 호환용. 즉시 보내지 않고 큐에 넣는다."""
    enqueue(title, message, color)


def notify_critical_event(event_type: str, description: str):
    enqueue(title=f"🔴 CRITICAL: {event_type}", message=description, color="#ff0000")


def _ensure_worker():
    global _worker_started
    with _lock:
        if _worker_started:
            return
        _worker_started = True
        threading.Thread(target=_worker, daemon=True, name="Notifier").start()


def _worker():
    while True:
        item = _queue.get()
        try:
            _dispatch(item)
        except Exception as e:
            logger.error(f"notification dispatch error: {e}")
        finally:
            _queue.task_done()


def _dispatch(item: dict):
    now = time.time()
    while _sent_times and now - _sent_times[0] > 60:
        _sent_times.popleft()

    if len(_sent_times) >= config.NOTIFY_MAX_PER_MINUTE:
        _suppressed.append(item["title"])
        return

    # 직전 분에 억제된 알림이 있으면 집계 한 줄을 먼저 붙인다
    message = item["message"]
    if _suppressed:
        message += f"\n\n(속도 제한으로 {len(_suppressed)}건 생략: " + ", ".join(_suppressed[:5])
        if len(_suppressed) > 5:
            message += " …"
        message += ")"
        _suppressed.clear()

    _post_slack(item["title"], message, item["color"])
    _sent_times.append(now)


def _post_slack(title: str, message: str, color: str):
    if not config.SLACK_WEBHOOK_URL:
        logger.debug("SLACK_WEBHOOK_URL not set; skipping notification")
        return
    title = f"[{config.HOSTNAME}] {title}"   # 여러 서버가 같은 웹훅을 쓸 때 출처 구분
    payload = {
        "text": f"*{title}*\n{message}",
        "attachments": [{"color": color, "fields": [{"title": "Alert Details", "value": message, "short": False}]}],
    }
    try:
        resp = requests.post(config.SLACK_WEBHOOK_URL, json=payload, timeout=5)
        if resp.status_code != 200:
            logger.error(f"Slack alert failed: {resp.status_code} {resp.text[:200]}")
        else:
            logger.info(f"Slack alert sent: {title}")
    except Exception as e:
        logger.error(f"Slack alert error: {e}")
