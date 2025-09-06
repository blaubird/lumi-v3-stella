import aiohttp
from api.logging_utils import get_logger

logger = get_logger(__name__)


async def send_telegram_message(token: str | None, chat_id: str, message: str) -> None:
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN missing")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            if resp.status != 200:
                logger.error("Telegram send failed", extra={"status": resp.status})
