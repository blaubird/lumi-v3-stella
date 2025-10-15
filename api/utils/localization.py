from __future__ import annotations

from typing import Any, Dict

from logging_utils import get_logger

logger = get_logger(__name__)

PHRASES: Dict[str, Dict[str, str]] = {
    "vacation.ask_start": {
        "en": "When does your vacation start?",
        "fr": "Quelle est la date de début de vos congés ?",
        "ru": "С какой даты начинается отпуск?",
    },
    "vacation.ask_end": {
        "en": "Great. And when does it end?",
        "fr": "Parfait. Et quand se termine-t-il ?",
        "ru": "Отлично. А когда он заканчивается?",
    },
    "vacation.confirm": {
        "en": "Please confirm: from {start} to {end} (✅ to save, ❌ to cancel).",
        "fr": "Merci de confirmer : du {start} au {end} (✅ pour enregistrer, ❌ pour annuler).",
        "ru": "Подтвердите: с {start} по {end} (✅ чтобы сохранить, ❌ чтобы отменить).",
    },
    "vacation.saved": {
        "en": "Saved! Enjoy your time off.",
        "fr": "Enregistré ! Profitez de vos congés.",
        "ru": "Сохранено! Приятного отдыха.",
    },
    "vacation.cancelled": {
        "en": "Cancelled. No vacation saved.",
        "fr": "Annulé. Aucun congé enregistré.",
        "ru": "Отменено. Отпуск не сохранён.",
    },
    "vacation.invalid_start": {
        "en": "I couldn't read that start date. Wizard reset—please start again.",
        "fr": "Je n'ai pas compris cette date de début. Assistant réinitialisé — recommencez.",
        "ru": "Не удалось распознать дату начала. Мастер перезапущен — начните заново.",
    },
    "vacation.invalid_end": {
        "en": "That end date doesn't work. Wizard reset—please start again.",
        "fr": "Cette date de fin ne convient pas. Assistant réinitialisé — recommencez.",
        "ru": "Дата окончания некорректна. Мастер перезапущен — начните заново.",
    },
    "vacation.invalid_confirm": {
        "en": "Confirmation not recognised. Wizard reset—please start again.",
        "fr": "Confirmation non reconnue. Assistant réinitialisé — recommencez.",
        "ru": "Подтверждение не распознано. Мастер перезапущен — начните заново.",
    },
    "vacation.denied": {
        "en": "⛔ Only owners can set vacation.",
        "fr": "⛔ Seuls les propriétaires peuvent définir des congés.",
        "ru": "⛔ Только владельцы могут задавать отпуск.",
    },
}


async def render_phrase(key: str, lang: str, generator: Any, **kwargs: Any) -> str:
    lang = (lang or "").lower()
    catalogue = PHRASES.get(key, {})

    template = _select_template(catalogue, lang)
    if template is not None:
        return template.format(**kwargs)

    fallback_template = _select_template(catalogue, "en") or key
    logger.debug(
        "Falling back to AI-generated phrase",
        extra={"key": key, "lang": lang, "kwargs": kwargs},
    )
    return await generator(
        key=key, lang=lang, template=fallback_template, variables=kwargs
    )


def _select_template(catalogue: Dict[str, str], lang: str) -> str | None:
    if not catalogue:
        return None
    if not lang:
        return catalogue.get("en")

    direct = catalogue.get(lang)
    if direct is not None:
        return direct

    short = lang.split("-")[0]
    for stored_lang, template in catalogue.items():
        if stored_lang.split("-")[0] == short:
            return template
    return None


__all__ = ["render_phrase", "PHRASES"]
