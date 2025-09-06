import os
from fastapi import APIRouter, Request
from api.logging_utils import get_logger
from api.services.telegram import send_telegram_message
from api.utils.i18n import detect_lang, tr

router = APIRouter(tags=["Telegram"])
logger = get_logger(__name__)


@router.post("/telegram_webhook")
async def telegram_webhook(request: Request):
    payload = await request.json()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    message = payload.get("message", {})
    chat = message.get("chat", {})
    chat_id = str(chat.get("id", ""))
    text = message.get("text", "")
    if not chat_id:
        return {"status": "ok"}
    lang = detect_lang(text)
    await send_telegram_message(token, chat_id, tr("generic.received", lang))
    return {"status": "ok"}
