import aiohttp
import base64
from api.logging_utils import get_logger

logger = get_logger(__name__)


async def send_whatsapp_message(
    phone_id: str,
    token: str | None,
    recipient: str,
    message: str,
    attachment: bytes | None = None,
    filename: str = "invite.ics",
) -> None:
    """
    Send WhatsApp message

    Args:
        phone_id: WhatsApp phone ID
        token: WhatsApp token
        recipient: Recipient phone number
        message: Message text
    """
    if not token:
        logger.error("WhatsApp token missing")
        return
    try:
        url = f"https://graph.facebook.com/v17.0/{phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        if attachment:
            payload = {
                "messaging_product": "whatsapp",
                "to": recipient,
                "type": "document",
                "text": {"preview_url": False, "body": message},
                "document": {
                    "filename": filename,
                    "mime_type": "text/calendar",
                    "document": base64.b64encode(attachment).decode(),
                },
            }
        else:
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient,
                "type": "text",
                "text": {"preview_url": False, "body": message},
            }

        logger.info(
            "Sending WhatsApp message",
            extra={
                "phone_id": phone_id,
                "recipient": recipient,
                "message_length": len(message),
            },
        )

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                response_data = await response.json()

                if response.status == 200:
                    logger.info(
                        "WhatsApp message sent successfully",
                        extra={"recipient": recipient, "status_code": response.status},
                    )
                    return response_data
                else:
                    logger.error(
                        "Failed to send WhatsApp message",
                        extra={
                            "recipient": recipient,
                            "status_code": response.status,
                            "response": response_data,
                        },
                    )
                    return None
    except Exception as e:
        logger.error(
            "Error sending WhatsApp message",
            extra={"recipient": recipient, "error": str(e)},
            exc_info=e,
        )
        return None
