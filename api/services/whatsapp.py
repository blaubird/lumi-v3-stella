from typing import Dict, Any, Optional
import requests
from logging_utils import get_logger

# Initialize logger
logger = get_logger(__name__)

class WhatsAppService:
    """
    Service for sending and receiving messages via WhatsApp Business API
    """
    def __init__(self, phone_id: str, token: str):
        self.phone_id = phone_id
        self.token = token
        self.base_url = "https://graph.facebook.com/v17.0"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        logger.info("WhatsApp service initialized", extra={"phone_id": phone_id})

    async def send_message(self, to: str, text: str) -> Dict[str, Any]:
        """
        Send a text message to a WhatsApp user
        
        Args:
            to: Recipient's phone number in international format
            text: Message text to send
            
        Returns:
            Response from WhatsApp API
        """
        url = f"{self.base_url}/{self.phone_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": text
            }
        }
        
        try:
            logger.info("Sending WhatsApp message", extra={
                "recipient": to,
                "message_length": len(text)
            })
            
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            
            response_data = response.json()
            logger.info("WhatsApp message sent successfully", extra={
                "message_id": response_data.get("messages", [{}])[0].get("id", "unknown"),
                "recipient": to
            })
            
            return response_data
        except Exception as e:
            logger.error("Error sending WhatsApp message", extra={
                "recipient": to,
                "error": str(e)
            }, exc_info=e)
            raise

    def verify_webhook_token(self, token: str) -> bool:
        """
        Verify that the webhook token matches the expected token
        
        Args:
            token: Token to verify
            
        Returns:
            True if token is valid, False otherwise
        """
        return token == self.token

    def parse_webhook_message(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parse a webhook message from WhatsApp
        
        Args:
            data: Webhook payload from WhatsApp
            
        Returns:
            Parsed message data or None if not a valid message
        """
        try:
            # Check if this is a valid WhatsApp message
            if data.get("object") != "whatsapp_business_account":
                logger.warning("Invalid webhook object type", extra={"object": data.get("object")})
                return None
                
            # Extract the first entry and change
            entries = data.get("entry", [])
            if not entries:
                logger.warning("No entries in webhook data")
                return None
                
            changes = entries[0].get("changes", [])
            if not changes:
                logger.warning("No changes in webhook entry")
                return None
                
            # Extract message data
            value = changes[0].get("value", {})
            messages = value.get("messages", [])
            if not messages:
                logger.info("No messages in webhook change")
                return None
                
            # Extract the first message
            message = messages[0]
            message_type = message.get("type")
            
            # Only process text messages for now
            if message_type != "text":
                logger.info("Ignoring non-text message", extra={"type": message_type})
                return None
                
            # Extract message details
            result = {
                "message_id": message.get("id"),
                "phone_number": message.get("from"),
                "timestamp": message.get("timestamp"),
                "text": message.get("text", {}).get("body", ""),
                "phone_id": value.get("metadata", {}).get("phone_number_id")
            }
            
            logger.info("Parsed webhook message", extra={
                "message_id": result["message_id"],
                "phone_number": result["phone_number"],
                "text_length": len(result["text"])
            })
            
            return result
        except Exception as e:
            logger.error("Error parsing webhook message", extra={
                "error": str(e)
            }, exc_info=e)
            return None
