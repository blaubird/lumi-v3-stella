import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

sys.path.append("api")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_booking.db")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("VERIFY_TOKEN", "verify")
os.environ.setdefault("WH_TOKEN", "wh-token")
os.environ.setdefault("WH_PHONE_ID", "phone-1")
os.environ.setdefault("X_ADMIN_TOKEN", "admin")

from database import Base, SessionLocal, engine  # noqa: E402
from models import Appointment, Message, Tenant  # noqa: E402
from routers.webhook import router as webhook_router  # noqa: E402
from tasks import process_ai_reply  # noqa: E402
from utils.i18n import tr  # noqa: E402


class StubRedis:
    async def setex(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover - helper
        return None


@pytest.fixture(autouse=True)
def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def webhook_app(monkeypatch: pytest.MonkeyPatch) -> Any:
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

    async def fake_handle_vacation_wizard(**_: Any) -> None:
        return None

    def fake_generate_ics(*_: Any, **__: Any) -> str:
        return "ICS"

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
        "routers.webhook.handle_vacation_wizard",
        fake_handle_vacation_wizard,
        raising=True,
    )
    monkeypatch.setattr(
        "services.vacation_wizard.handle_vacation_wizard",
        fake_handle_vacation_wizard,
        raising=True,
    )
    monkeypatch.setattr(
        "routers.webhook.generate_ics",
        fake_generate_ics,
        raising=True,
    )
    monkeypatch.setattr(
        "routers.webhook.detect_lang",
        lambda *_: "en",
        raising=True,
    )

    app = FastAPI()
    app.include_router(webhook_router)
    app.state.redis = StubRedis()
    client = TestClient(app)

    try:
        yield client, sent_messages
    finally:
        client.close()


def _create_tenant() -> Tenant:
    session = SessionLocal()
    tenant = Tenant(id="tenant-test", phone_id="phone-1", wh_token="tenant-token")
    session.add(tenant)
    session.commit()
    session.close()
    return tenant


def _build_message_payload(text: str, phone: str) -> Dict[str, Any]:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "phone-1"},
                            "messages": [
                                {
                                    "id": "wamid.ABC",
                                    "from": phone,
                                    "timestamp": str(int(datetime.now(timezone.utc).timestamp())),
                                    "type": "text",
                                    "text": {"body": text},
                                    "language": {"code": "en"},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }


def test_booking_confirmation_uses_translation(webhook_app: Any) -> None:
    client, sent_messages = webhook_app
    _create_tenant()

    future = datetime.now(timezone.utc) + timedelta(days=10)
    date_part = f"{future.month:02d}/{future.day:02d}"
    time_part = future.strftime("%H:%M")
    payload = _build_message_payload(f"book {date_part} {time_part}", "+33123456789")

    response = client.post("/webhook", json=payload)
    assert response.status_code == 200

    assert sent_messages, "Expected WhatsApp message to be queued"
    expected_dt = future.strftime("%d/%m %H:%M")
    expected_message = tr("booking.confirmed", "en", dt=expected_dt)
    assert sent_messages[0]["message"] == expected_message

    session = SessionLocal()
    assistant_message = (
        session.query(Message)
        .filter(Message.tenant_id == "tenant-test", Message.role == "assistant")
        .one()
    )
    session.close()
    assert assistant_message.text == expected_message

    session = SessionLocal()
    appointments = session.query(Appointment).all()
    session.close()
    assert appointments and appointments[0].starts_at.strftime("%d/%m %H:%M") == expected_dt


def test_process_ai_reply_routes_through_rag(monkeypatch: pytest.MonkeyPatch) -> None:
    session = SessionLocal()
    tenant = Tenant(id="tenant-ru", phone_id="phone-1", wh_token="tenant-token")
    session.add(tenant)
    session.commit()
    session.close()

    calls: Dict[str, Any] = {}
    sentinel_redis = object()

    async def fake_get_rag_response(
        *, tenant_id: str, user_text: str, lang: str, db: Any, redis: Any, trace_id: str
    ) -> Dict[str, Any]:
        calls.update(
            {
                "tenant_id": tenant_id,
                "user_text": user_text,
                "lang": lang,
                "redis": redis,
                "trace_id": trace_id,
                "session": db,
            }
        )
        return {"text": "Привет!", "total_tokens": 4}

    sent_messages: List[Dict[str, Any]] = []

    async def fake_send_whatsapp_message(
        *, phone_id: str, token: str, recipient: str, message: str
    ) -> None:
        sent_messages.append(
            {
                "phone_id": phone_id,
                "token": token,
                "recipient": recipient,
                "message": message,
            }
        )

    monkeypatch.setattr("tasks.get_rag_response", fake_get_rag_response, raising=True)
    monkeypatch.setattr("tasks.send_whatsapp_message", fake_send_whatsapp_message, raising=True)
    monkeypatch.setattr("tasks.detect_lang", lambda *_: "ru", raising=True)
    monkeypatch.setattr("tasks.redis_wrapper", type("StubWrapper", (), {"client": sentinel_redis})())

    asyncio.run(process_ai_reply("tenant-ru", "79990001122:wamid", "Привет"))

    assert calls["tenant_id"] == "tenant-ru"
    assert calls["lang"] == "ru"
    assert calls["redis"] is sentinel_redis
    assert sent_messages and sent_messages[0]["message"] == "Привет!"

    session = SessionLocal()
    stored = (
        session.query(Message)
        .filter(Message.tenant_id == "tenant-ru", Message.role == "assistant")
        .one()
    )
    session.close()
    assert stored.text == "Привет!"
