import os
from fastapi import APIRouter, Request
from api.logging_utils import get_logger
from api.services.instagram import send_instagram_message
from api.utils.i18n import detect_lang, tr

router = APIRouter(tags=["Instagram"])
logger = get_logger(__name__)


@router.post("/instagram_webhook")
async def instagram_webhook(request: Request):
    payload = await request.json()
    token = os.getenv("INSTAGRAM_TOKEN")
    messaging = payload.get("entry", [{}])[0].get("messaging", [{}])[0]
    sender = messaging.get("sender", {}).get("id")
    text = messaging.get("message", {}).get("text", "")
    if not sender:
        return {"status": "ok"}
    lang = detect_lang(text)
    await send_instagram_message(token, sender, tr("generic.received", lang))
    return {"status": "ok"}
