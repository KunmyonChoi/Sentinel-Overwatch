"""
위협 인텔(공개 뉴스) 전용 번역/긴급도 평가.

호스트에서 수집한 로그는 이 모듈을 거치지 않는다. 오직 RSS 제목/요약만 외부 API 로 보낸다.
단일 워커 스레드가 큐를 처리해 요청당 스레드가 생기지 않는다.
"""
import json
import logging
import queue
import threading

import config
from database import SessionLocal, TranslationCache

logger = logging.getLogger("translate")

URGENCY_LEVELS = ("CRITICAL", "HIGH", "MEDIUM", "LOW")

_PROMPT = """\
You are a cybersecurity analyst. Given the title/description of a threat intelligence article, do two things:
1. Translate the text to Korean.
2. Rate the security urgency for a Linux server administrator as one of: CRITICAL, HIGH, MEDIUM, LOW.
   - CRITICAL: zero-day exploit, actively exploited vulnerability in the wild, major ransomware campaign
   - HIGH: new CVE (CVSS >= 8), confirmed data breach, active targeted attack campaign
   - MEDIUM: patch/update advisory, general threat report, new malware family (not yet widespread)
   - LOW: general security awareness, research, informational news

Respond ONLY with valid JSON (no markdown):
{"translation": "<Korean translation>", "urgency": "<CRITICAL|HIGH|MEDIUM|LOW>", "urgency_reason": "<one sentence in Korean>"}

Article text:
"""

_cache: dict[str, str | None] = {}     # None = 진행 중, "" = 실패, str = 완료
_urgency: dict[str, str] = {}
_queue: "queue.Queue[str]" = queue.Queue()
_lock = threading.Lock()
_started = False


def load_cache():
    db = SessionLocal()
    try:
        for row in db.query(TranslationCache).all():
            _cache[row.source_text] = row.translated_text
            if row.urgency in URGENCY_LEVELS:
                _urgency[row.source_text] = row.urgency
    except Exception as e:
        logger.error(f"load cache failed: {e}")
    finally:
        db.close()


def _persist(text: str, translated: str, urgency: str = ""):
    db = SessionLocal()
    try:
        row = db.query(TranslationCache).filter(TranslationCache.source_text == text).first()
        if row:
            row.translated_text = translated
            if urgency:
                row.urgency = urgency
        else:
            db.add(TranslationCache(source_text=text, translated_text=translated, urgency=urgency or None))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"persist failed: {e}")
    finally:
        db.close()


def _ensure_worker():
    global _started
    with _lock:
        if _started:
            return
        _started = True
        threading.Thread(target=_worker, daemon=True, name="IntelTranslator").start()


def _worker():
    while True:
        text = _queue.get()
        try:
            _translate(text)
        except Exception as e:
            logger.error(f"translate failed: {e}")
            _cache[text] = ""
        finally:
            _queue.task_done()


def _via_claude(text: str) -> tuple[str, str] | None:
    if not config.ANTHROPIC_API_KEY:
        return None
    import anthropic
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=512,
        messages=[{"role": "user", "content": _PROMPT + text[:600]}],
    )
    raw = msg.content[0].text.strip()
    raw = raw[raw.find("{"): raw.rfind("}") + 1]
    data = json.loads(raw)
    translation = str(data.get("translation") or "")[:1000]
    urgency = str(data.get("urgency", "")).upper()
    if urgency not in URGENCY_LEVELS:      # 프롬프트 인젝션/형식 오류 방어
        urgency = "MEDIUM"
    reason = str(data.get("urgency_reason") or "")[:300]
    display = f"{translation} [{reason}]" if reason else translation
    return display, urgency


def _via_google(text: str) -> str:
    from deep_translator import GoogleTranslator
    return GoogleTranslator(source="en", target="ko").translate(text[:500]) or ""


def _translate(text: str):
    try:
        res = _via_claude(text)
    except Exception as e:
        logger.warning(f"claude translation failed, falling back: {e}")
        res = None
    if res:
        display, urgency = res
        _cache[text], _urgency[text] = display, urgency
        if display:
            _persist(text, display, urgency)
        return
    try:
        translated = _via_google(text)
    except Exception as e:
        logger.warning(f"google translation failed: {e}")
        translated = ""
    _cache[text] = translated
    if translated:
        _persist(text, translated)


def translate_intel(text: str) -> tuple[str | None, str]:
    """(번역, 긴급도). 번역 None = 진행 중."""
    if not text:
        return "", ""
    key = text.strip()
    if key in _cache:
        return _cache[key], _urgency.get(key, "")
    if not config.INTEL_TRANSLATE:
        return "", ""
    _cache[key] = None
    _ensure_worker()
    _queue.put(key)
    return None, ""
