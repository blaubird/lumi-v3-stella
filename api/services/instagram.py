import aiohttp
from logging_utils import get_logger

logger = get_logger(__name__)


async def send_instagram_message(
    token: str | None, recipient: str, message: str
) -> None:
    if not token:
        logger.error("INSTAGRAM_TOKEN missing")
        return
    url = "https://graph.facebook.com/v17.0/me/messages"
    payload = {
        "recipient": {"id": recipient},
        "message": {"text": message},
        "messaging_type": "RESPONSE",
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as resp:
            if resp.status != 200:
                logger.error("Instagram send failed", extra={"status": resp.status})
