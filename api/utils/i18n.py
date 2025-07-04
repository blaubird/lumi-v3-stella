from langdetect import detect

TEMPLATES = {
    "booking.confirmed": {
        "fr": "✅ Réservé pour {dt}. Vous recevrez un rappel.",
        "en": "✅ Booked for {dt}. You'll get a reminder.",
    },
    "booking.reminder": {
        "fr": "Rappel : rendez-vous le {dt}.",
        "en": "Reminder: appointment on {dt}.",
    },
    "generic.received": {
        "fr": "Message reçu.",
        "en": "Message received.",
    },
}

DEFAULT_LANG = "fr"


def detect_lang(text: str) -> str:
    try:
        lang = detect(text)
        return "fr" if lang.startswith("fr") else "en"
    except Exception:
        return DEFAULT_LANG


def tr(key: str, lang: str | None = None, **kwargs) -> str:
    lang = lang or DEFAULT_LANG
    template = TEMPLATES.get(key, {}).get(lang)
    if template is None:
        template = TEMPLATES.get(key, {}).get(DEFAULT_LANG, "")
    return template.format(**kwargs)
