import os
import uuid
import sys
from typing import Any, Dict, List

sys.path.append("api")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_vacation.db")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("VERIFY_TOKEN", "verify")
os.environ.setdefault("WH_TOKEN", "wh-token")
os.environ.setdefault("WH_PHONE_ID", "phone-1")
os.environ.setdefault("X_ADMIN_TOKEN", "admin")

from database import Base, SessionLocal, engine  # noqa: E402
from models import OwnerContact, Tenant, Unavailability  # noqa: E402
from routers.webhook import router as webhook_router  # noqa: E402


class StubRedis:
    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, str]] = {}

    async def hset(self, key: str, mapping: Dict[str, Any]) -> None:
        bucket = self._store.setdefault(key, {})
        for field, value in mapping.items():
            bucket[str(field)] = str(value)

    async def hgetall(self, key: str) -> Dict[str, str]:
        return dict(self._store.get(key, {}))

    async def expire(self, key: str, ttl: int) -> None:
        return None

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)


@pytest.fixture(autouse=True)
def reset_database(tmp_path) -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def test_app(monkeypatch) -> Any:
    sent_messages: List[Dict[str, Any]] = []

    async def fake_send_whatsapp_message(
        *,
        phone_id: str,
        token: str,
        recipient: str,
        message: str,
        attachment: Any | None = None,
    ) -> None:
        sent_messages.append(
            {
                "phone_id": phone_id,
                "token": token,
                "recipient": recipient,
                "message": message,
                "attachment": attachment,
            }
        )

    async def fake_generate_localized_phrase(
        *, key: str, lang: str, template: str, variables: Dict[str, Any]
    ) -> str:
        phrases = {
            "vacation.ask_start": "Wann beginnt dein Urlaub?",
            "vacation.ask_end": "Und wann endet er?",
            "vacation.confirm": "Bitte bestätige: von {start} bis {end} (✅ speichern, ❌ abbrechen).",
            "vacation.saved": "Gespeichert!",
            "vacation.cancelled": "Abgebrochen.",
            "vacation.invalid_start": "Startdatum unklar. Assistent zurückgesetzt.",
            "vacation.invalid_end": "Enddatum unklar. Assistent zurückgesetzt.",
            "vacation.invalid_confirm": "Bestätigung unklar. Assistent zurückgesetzt.",
            "vacation.denied": "⛔ Nur Eigentümer können Urlaub setzen.",
        }
        template_used = phrases.get(key, template)
        try:
            return template_used.format(**variables)
        except Exception:
            return template_used

    monkeypatch.setattr(
        "routers.webhook.send_whatsapp_message",
        fake_send_whatsapp_message,
        raising=True,
    )
    monkeypatch.setattr(
        "services.whatsapp.send_whatsapp_message",
        fake_send_whatsapp_message,
        raising=True,
    )
    monkeypatch.setattr(
        "services.vacation_wizard.generate_localized_phrase",
        fake_generate_localized_phrase,
        raising=True,
    )
    monkeypatch.setattr(
        "ai.generate_localized_phrase", fake_generate_localized_phrase, raising=True
    )

    async def fake_invalidate_tenant_namespace(tenant_id: str) -> None:
        return None

    monkeypatch.setattr(
        "services.cache_invalidate.invalidate_tenant_namespace",
        fake_invalidate_tenant_namespace,
        raising=True,
    )

    app = FastAPI()
    app.include_router(webhook_router)
    app.state.redis = StubRedis()
    app.state.redis_wrapper = type(
        "RedisWrapperStub", (), {"ping": lambda self: True, "last_latency_ms": 0}
    )()

    client = TestClient(app)
    try:
        yield client, sent_messages
    finally:
        client.close()


def _create_tenant(owner_phone: str | None = None) -> Tenant:
    session = SessionLocal()
    tenant = Tenant(id="tenant-1", phone_id="phone-1", wh_token="secret-token")
    session.add(tenant)
    session.commit()
    if owner_phone:
        contact = OwnerContact(tenant_id=tenant.id, phone_number=owner_phone)
        session.add(contact)
        session.commit()
    session.close()
    return tenant


def _build_payload(
    text: str, lang: str, phone: str, message_id: str | None = None
) -> Dict[str, Any]:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "phone-1"},
                            "messages": [
                                {
                                    "id": message_id or str(uuid.uuid4()),
                                    "from": phone,
                                    "timestamp": "1717000000",
                                    "type": "text",
                                    "text": {"body": text},
                                    "language": {"code": lang},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }


def test_vacation_wizard_french_happy_path(test_app) -> None:
    client, sent_messages = test_app
    _create_tenant(owner_phone="+33123456789")

    for text in ["Vacances", "24/12/2024", "08/01/2025", "✅"]:
        payload = _build_payload(text, "fr", "+33123456789")
        response = client.post("/webhook", json=payload)
        assert response.status_code == 200

    assert [msg["message"] for msg in sent_messages] == [
        "Quelle est la date de début de vos congés ?",
        "Parfait. Et quand se termine-t-il ?",
        "Merci de confirmer : du 2024-12-24 au 2025-01-08 (✅ pour enregistrer, ❌ pour annuler).",
        "Enregistré ! Profitez de vos congés.",
    ]

    session = SessionLocal()
    records = session.query(Unavailability).all()
    session.close()
    assert len(records) == 1
    assert str(records[0].starts_on) == "2024-12-24"
    assert str(records[0].ends_on) == "2025-01-08"


def test_vacation_wizard_english_happy_path(test_app) -> None:
    client, sent_messages = test_app
    _create_tenant(owner_phone="+447900123456")

    for text in ["Vacation", "2024-07-01", "2024-07-10", "✅"]:
        payload = _build_payload(text, "en", "+447900123456")
        response = client.post("/webhook", json=payload)
        assert response.status_code == 200

    assert sent_messages[0]["message"] == "When does your vacation start?"
    assert sent_messages[-1]["message"] == "Saved! Enjoy your time off."


def test_vacation_wizard_mirrors_unknown_language(test_app) -> None:
    client, sent_messages = test_app
    _create_tenant(owner_phone="+4915200000001")

    steps = ["Urlaub", "01/02", "10/02", "✅"]
    for idx, text in enumerate(steps):
        payload = _build_payload(
            text, "de", "+4915200000001", message_id=str(uuid.uuid4()) + str(idx)
        )
        response = client.post("/webhook", json=payload)
        assert response.status_code == 200

    assert sent_messages[0]["message"] == "Wann beginnt dein Urlaub?"
    assert sent_messages[-1]["message"] == "Gespeichert!"


def test_non_owner_denied_in_same_language(test_app) -> None:
    client, sent_messages = test_app
    _create_tenant(owner_phone=None)

    payload = _build_payload("Vacaciones", "es", "+34123456789")
    response = client.post("/webhook", json=payload)
    assert response.status_code == 200

    assert sent_messages[0]["message"] in {
        "⛔ Only owners can set vacation.",
        "⛔ Nur Eigentümer können Urlaub setzen.",
        "⛔ Seuls les propriétaires peuvent définir des congés.",
        "⛔ Только владельцы могут задавать отпуск.",
    }

    session = SessionLocal()
    records = session.query(Unavailability).all()
    session.close()
    assert not records
