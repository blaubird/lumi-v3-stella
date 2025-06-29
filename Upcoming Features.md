# Upcoming Features

This section outlines the proposed architecture and integration patterns for upcoming features, drawing parallels from the existing WhatsApp integration.

## Telegram Integration

Similar to the WhatsApp integration, a Telegram integration would involve:

- **Webhook Endpoint:** A dedicated `/telegram_webhook` endpoint (GET and POST) to handle incoming updates from the Telegram Bot API.
    - **GET Request:** For webhook verification, echoing back a `challenge` parameter.
    - **POST Request:** To receive and process incoming messages and events from Telegram users.
- **Environment Variables:** New environment variables would be required for Telegram API credentials, such as `TELEGRAM_BOT_TOKEN`.
- **Service Module:** A new `telegram.py` module within `api/services/` would encapsulate functions for sending messages and interacting with the Telegram Bot API (e.g., `send_telegram_message`).
- **Message Processing:** A `process_telegram_message` function (similar to `process_message` for WhatsApp) would handle parsing incoming Telegram updates, identifying the sender, extracting message content, and routing it for AI processing or other actions.
- **Database Integration:** Storing Telegram-specific `Tenant` information and message history in the database.

## Instagram Integration

Integrating with Instagram (likely via the Messenger Platform API for Instagram) would follow a similar pattern:

- **Webhook Endpoint:** A dedicated `/instagram_webhook` endpoint (GET and POST) to receive updates from Instagram.
    - **GET Request:** For webhook verification.
    - **POST Request:** To receive and process incoming messages and events from Instagram users.
- **Environment Variables:** New environment variables for Instagram API credentials, such as `INSTAGRAM_APP_ID`, `INSTAGRAM_APP_SECRET`, and `INSTAGRAM_PAGE_ID`.
- **Service Module:** A new `instagram.py` module within `api/services/` would handle sending messages and interacting with the Instagram API (e.g., `send_instagram_message`).
- **Message Processing:** A `process_instagram_message` function would be responsible for parsing incoming Instagram messages, extracting relevant details, and initiating appropriate responses.
- **Database Integration:** Storing Instagram-specific `Tenant` information and message history in the database.

## Calendar Event Creation

Building upon the existing appointment booking functionality (as suggested by `BOOK_RE` in `webhook.py` and the `Appointment` model), calendar event creation would involve:

- **Natural Language Processing (NLP):** Enhancing the AI module (`ai.py`) to better understand user requests for scheduling events, extracting details like date, time, duration, and event title.
- **Calendar API Integration:** Integration with a calendar service (e.g., Google Calendar API, Outlook Calendar API) would be required.
    - **Service Module:** A new `calendar.py` module within `api/services/` would contain functions for authenticating with the calendar API, creating events, updating events, and querying availability.
    - **Environment Variables:** API keys or OAuth credentials for the chosen calendar service.
- **User Confirmation:** Implementing a confirmation flow where the system asks the user to confirm event details before creating the calendar entry.
- **Database Integration:** Storing calendar event details and linking them to `Tenant` and `Message` records for historical tracking and management.
- **Response Generation:** Providing clear confirmation messages to the user after successful event creation, including a link to the created event if possible.

