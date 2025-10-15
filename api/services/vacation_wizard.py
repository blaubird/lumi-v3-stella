from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Optional, Tuple

from redis.asyncio import Redis
from sqlalchemy.orm import Session

from ai import generate_localized_phrase
from logging_utils import get_logger
from models import Unavailability
from services.cache_invalidate import invalidate_tenant_namespace
from services.owner_access import is_owner_contact, normalize_phone
from utils.localization import render_phrase

logger = get_logger(__name__)

REDIS_TTL_SECONDS = 300

TRIGGER_WORDS: Dict[str, str] = {
    "vacation": "en",
    "vacances": "fr",
    "vacaciones": "es",
    "vacanza": "it",
    "urlaub": "de",
    "каникулы": "ru",
    "отпуск": "ru",
    "ferias": "pt",
    "férias": "pt",
}

YES_TOKENS = {"✅", "✔", "✔️", "yes", "oui", "да"}
NO_TOKENS = {"❌", "✖", "✕", "no", "non", "нет"}


@dataclass(slots=True)
class WizardReply:
    text: str
    lang: str


async def handle_vacation_wizard(
    *,
    db: Session,
    tenant_id: str,
    admin_phone: str,
    text: str,
    message: Dict[str, Any],
    redis_client: Optional[Redis],
) -> Optional[WizardReply]:
    if redis_client is None:
        logger.debug("Redis unavailable; vacation wizard disabled")
        return None

    normalized_admin = normalize_phone(admin_phone)
    redis_key = f"vac_wizard:{tenant_id}:{normalized_admin}"

    stripped_text = text.strip()
    if not stripped_text:
        return None
    lowered = stripped_text.casefold()

    trigger_lang = _detect_trigger_language(message, stripped_text)

    if _is_trigger(lowered):
        if not is_owner_contact(db, tenant_id, admin_phone):
            lang = trigger_lang or _fallback_language_from_text(stripped_text)
            reply = await render_phrase(
                "vacation.denied",
                lang,
                generator=generate_localized_phrase,
            )
            return WizardReply(text=reply, lang=lang)

        lang = trigger_lang or _fallback_language_from_text(stripped_text)
        state = {
            "stage": "await_start",
            "lang": lang,
        }
        await redis_client.delete(redis_key)
        await redis_client.hset(redis_key, mapping=state)
        await redis_client.expire(redis_key, REDIS_TTL_SECONDS)
        reply = await render_phrase(
            "vacation.ask_start",
            lang,
            generator=generate_localized_phrase,
        )
        return WizardReply(text=reply, lang=lang)

    state = await _load_state(redis_client, redis_key)
    if not state:
        return None

    lang = (
        state.get("lang") or trigger_lang or _fallback_language_from_text(stripped_text)
    )
    stage = state.get("stage")

    if stage == "await_start":
        parsed = _parse_date(stripped_text)
        if parsed is None:
            await redis_client.delete(redis_key)
            reply = await render_phrase(
                "vacation.invalid_start", lang, generator=generate_localized_phrase
            )
            return WizardReply(text=reply, lang=lang)

        start_date, has_year = parsed
        if not has_year:
            today = datetime.utcnow().date()
            if start_date < today:
                start_date = date(start_date.year + 1, start_date.month, start_date.day)

        await redis_client.hset(
            redis_key,
            mapping={
                "stage": "await_end",
                "lang": lang,
                "start": start_date.isoformat(),
            },
        )
        await redis_client.expire(redis_key, REDIS_TTL_SECONDS)
        reply = await render_phrase(
            "vacation.ask_end", lang, generator=generate_localized_phrase
        )
        return WizardReply(text=reply, lang=lang)

    if stage == "await_end":
        start_raw = state.get("start")
        if not start_raw:
            await redis_client.delete(redis_key)
            reply = await render_phrase(
                "vacation.invalid_end", lang, generator=generate_localized_phrase
            )
            return WizardReply(text=reply, lang=lang)

        start_date = date.fromisoformat(start_raw)
        parsed = _parse_date(stripped_text, reference_year=start_date.year)
        if parsed is None:
            await redis_client.delete(redis_key)
            reply = await render_phrase(
                "vacation.invalid_end", lang, generator=generate_localized_phrase
            )
            return WizardReply(text=reply, lang=lang)

        end_date, has_year = parsed
        if not has_year and end_date < start_date:
            end_date = date(end_date.year + 1, end_date.month, end_date.day)

        if end_date < start_date:
            await redis_client.delete(redis_key)
            reply = await render_phrase(
                "vacation.invalid_end", lang, generator=generate_localized_phrase
            )
            return WizardReply(text=reply, lang=lang)

        await redis_client.hset(
            redis_key,
            mapping={
                "stage": "confirm",
                "lang": lang,
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
        )
        await redis_client.expire(redis_key, REDIS_TTL_SECONDS)
        reply = await render_phrase(
            "vacation.confirm",
            lang,
            generator=generate_localized_phrase,
            start=start_date.isoformat(),
            end=end_date.isoformat(),
        )
        return WizardReply(text=reply, lang=lang)

    if stage == "confirm":
        start_raw = state.get("start")
        end_raw = state.get("end")
        if not start_raw or not end_raw:
            await redis_client.delete(redis_key)
            reply = await render_phrase(
                "vacation.invalid_confirm",
                lang,
                generator=generate_localized_phrase,
            )
            return WizardReply(text=reply, lang=lang)

        lowered_clean = stripped_text.casefold()
        if lowered_clean in YES_TOKENS or "✅" in stripped_text:
            start_date = date.fromisoformat(start_raw)
            end_date = date.fromisoformat(end_raw)
            record = Unavailability(
                tenant_id=tenant_id,
                owner_phone=normalize_phone(admin_phone),
                starts_on=start_date,
                ends_on=end_date,
            )
            db.add(record)
            db.commit()
            await invalidate_tenant_namespace(tenant_id)
            await redis_client.delete(redis_key)
            reply = await render_phrase(
                "vacation.saved", lang, generator=generate_localized_phrase
            )
            return WizardReply(text=reply, lang=lang)

        if lowered_clean in NO_TOKENS or "❌" in stripped_text:
            await redis_client.delete(redis_key)
            reply = await render_phrase(
                "vacation.cancelled", lang, generator=generate_localized_phrase
            )
            return WizardReply(text=reply, lang=lang)

        await redis_client.delete(redis_key)
        reply = await render_phrase(
            "vacation.invalid_confirm", lang, generator=generate_localized_phrase
        )
        return WizardReply(text=reply, lang=lang)

    await redis_client.delete(redis_key)
    return None


async def _load_state(redis_client: Redis, key: str) -> Dict[str, str]:
    data = await redis_client.hgetall(key)
    return data or {}


def _is_trigger(word: str) -> bool:
    return word in TRIGGER_WORDS and " " not in word


def _detect_trigger_language(message: Dict[str, Any], text: str) -> str:
    language_info = message.get("language")
    if isinstance(language_info, dict):
        lang_code = language_info.get("code") or language_info.get("policy")
        if isinstance(lang_code, str) and lang_code:
            return lang_code.lower()

    context = message.get("context")
    if isinstance(context, dict):
        lang_code = context.get("language_code")
        if isinstance(lang_code, str) and lang_code:
            return lang_code.lower()
        metadata = context.get("metadata")
        if isinstance(metadata, dict):
            lang_code = metadata.get("lang")
            if isinstance(lang_code, str) and lang_code:
                return lang_code.lower()

    lowered = text.casefold()
    return TRIGGER_WORDS.get(lowered, "")


def _fallback_language_from_text(text: str) -> str:
    lowered = text.casefold()
    mapped = TRIGGER_WORDS.get(lowered)
    if mapped:
        return mapped
    if any("а" <= char <= "я" or "А" <= char <= "Я" for char in text):
        return "ru"
    if any("à" <= char <= "ÿ" for char in text):
        return "fr"
    return "en"


def _parse_date(
    raw: str, reference_year: Optional[int] = None
) -> Optional[Tuple[date, bool]]:
    raw = raw.strip()
    if not raw:
        return None

    raw_normalized = raw.replace(".", "/").replace("-", "/")
    formats_full_year = ["%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y"]
    for fmt in formats_full_year:
        try:
            parsed = datetime.strptime(raw_normalized, fmt).date()
            return parsed, True
        except ValueError:
            continue

    formats_partial = ["%d/%m", "%m/%d"]
    ref_year = reference_year or datetime.utcnow().year
    for fmt in formats_partial:
        try:
            parsed = datetime.strptime(raw_normalized, fmt).date()
            return date(ref_year, parsed.month, parsed.day), False
        except ValueError:
            continue

    return None


__all__ = ["handle_vacation_wizard", "WizardReply"]
