# WhatsApp Integration

The `lumi-v3-stella` project integrates with WhatsApp Business API through a webhook mechanism. This integration allows the system to receive messages from WhatsApp users and respond to them.

## Webhook Verification

- **Endpoint:** `/webhook` (GET request)
- **Purpose:** To verify the webhook URL with Meta (Facebook) as part of the WhatsApp Business API setup.
- **Parameters:**
    - `hub.mode`: Must be `subscribe`.
    - `hub.challenge`: A unique string provided by Meta that needs to be echoed back.
    - `hub.verify_token`: A token configured in the system (loaded from `VERIFY_TOKEN` environment variable) that must match the token configured in Meta's developer console.
- **Process:** Upon receiving a `GET` request with the correct `mode` and `verify_token`, the system responds with the `hub.challenge` string, confirming the webhook's authenticity.

## Incoming Message Handling

- **Endpoint:** `/webhook` (POST request)
- **Purpose:** To receive incoming messages and other events from WhatsApp users.
- **Process:**
    1. **Request Parsing:** The incoming JSON payload from WhatsApp is parsed.
    2. **Entry and Change Iteration:** The system iterates through `entry` and `changes` arrays within the payload to extract relevant information.
    3. **Tenant Identification:** The `phone_number_id` from the webhook `metadata` is used to identify the corresponding `Tenant` in the system's database.
    4. **Message Type Filtering:** Currently, only `text` messages are processed.
    5. **Message Processing:** For each valid text message, the `process_message` function is called, which extracts details like `message_id`, `from_number`, `text` content, and `timestamp`.

## Key Components and Interactions

- **`webhook.py`:** Contains the FastAPI routes for webhook verification (`GET /webhook`) and message handling (`POST /webhook`). It also includes the `process_message` function, which is the entry point for processing individual WhatsApp messages.
- **Environment Variables:** Critical configuration details like `VERIFY_TOKEN`, `WH_TOKEN`, and `WH_PHONE_ID` are loaded from environment variables, ensuring secure and flexible deployment.
- **Database (`db.py`, `models.py`):** The system interacts with a database to retrieve `Tenant` information based on the `phone_number_id` and likely to store incoming messages and other related data (e.g., `Message`, `Usage`, `FAQ`, `Appointment` models are imported).
- **AI Integration (`ai.py`):** The `get_rag_response` function is imported, suggesting that AI-powered responses are generated based on the incoming message content.
- **WhatsApp Service (`services/whatsapp.py`):** The `send_whatsapp_message` function is imported, indicating that the system uses a dedicated service to send messages back to WhatsApp users.
- **Logging (`logging_utils.py`):** Extensive logging is implemented to track webhook requests, processing steps, and potential errors, aiding in debugging and monitoring.



## Detailed Flow of WhatsApp Message Processing

When a message is received from the WhatsApp Business API, the `webhook_handler` function in `webhook.py` orchestrates the following steps:

1.  **Request Reception and Initial Parsing**: The `webhook_handler` receives a `POST` request from WhatsApp. It attempts to parse the request body as JSON. If parsing fails, it logs an error but still returns a success status to WhatsApp to prevent repeated delivery attempts.

2.  **Iterating Through Entries and Changes**: The WhatsApp Business API sends updates in a structured format, typically containing an `entry` array, which in turn contains `changes`. The handler iterates through these to find relevant message data.

3.  **Tenant Identification**: For each `change` event, the `phone_number_id` is extracted from the `metadata` within the `value` object. This `phone_number_id` is crucial for identifying the `Tenant` (client) in the system's database. The system queries the `Tenant` model using `Tenant.phone_id` to retrieve the associated tenant object. If no tenant is found, a warning is logged, and the processing for that specific change is skipped.

4.  **Message Extraction and Filtering**: Within the `value` object, the `messages` array contains the actual user messages. The handler iterates through these messages. Currently, the system specifically processes messages where the `type` is `text`. Other message types (e.g., image, video, location) are ignored.

5.  **Calling `process_message`**: For each valid text message, the `process_message` asynchronous function is called. This function is responsible for the deeper processing of the individual message.

### `process_message` Function Details

The `process_message` function performs the following critical operations:

1.  **Message Data Extraction**: It extracts key details from the incoming WhatsApp message object:
    -   `message_id`: The unique ID assigned by WhatsApp to the message.
    -   `from_number`: The sender's WhatsApp number.
    -   `text`: The actual text content of the message.
    -   `raw_ts`: The timestamp when the message was sent from WhatsApp.

2.  **Saving Inbound Message**: The inbound message is saved to the database. A new `Message` record is created with `tenant_id`, `wa_msg_id`, `role` set to `inbound`, `text`, and `ts`.

3.  **Appointment Booking Logic**: The system attempts to detect if the incoming message is a request to book an appointment. It uses a regular expression (`BOOK_RE`) to match patterns like 



`book MM/DD HH:MM` or `book MM-DD HH:MM`. If a match is found:
    -   It extracts the requested date and time.
    -   It checks for existing appointments for the tenant at the requested time.
    -   If available, it creates a new `Appointment` record in the database with `pending` status.
    -   It then sends a confirmation message back to the user via `send_whatsapp_message`.

4.  **AI Response Generation (RAG)**: If the message is not an appointment booking request, the system proceeds to generate an AI response using the RAG (Retrieval Augmented Generation) approach.
    -   It retrieves the `system_prompt` associated with the `Tenant` to customize the AI's behavior.
    -   It fetches relevant `FAQ` entries for the tenant based on the user's query, using the `embedding` field for semantic search.
    -   It retrieves the conversation history (`Message` records) for the current user to provide context to the AI.
    -   The `get_rag_response` function (from `ai.py`) is called with the gathered context (system prompt, FAQs, conversation history) and the user's current message.
    -   The AI generates a response, which is then sent back to the user via `send_whatsapp_message`.

5.  **Saving Outbound Message**: The AI-generated response is also saved to the database as a `Message` record with `role` set to `assistant`.

6.  **Usage Tracking**: The system records the token usage for both inbound and outbound messages in the `Usage` table, allowing for monitoring and billing based on AI model consumption.

### Error Handling

The `webhook_handler` is designed to be resilient. While it logs errors encountered during processing (e.g., `json.JSONDecodeError`, `Exception` during message processing), it generally returns a success status (`{"status": "success"}`) to WhatsApp. This prevents WhatsApp from repeatedly retrying to send the same update, which could lead to message duplication or excessive load. Detailed error information is logged for debugging purposes.

