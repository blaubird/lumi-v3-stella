# Lumi-v3-Stella Project Documentation

This document provides a comprehensive overview of the `lumi-v3-stella` project, detailing its architecture, existing functionalities, and planned future integrations.

## Project Overview

`lumi-v3-stella` is a robust backend application designed to facilitate conversational AI interactions, primarily through messaging platforms. Its core goal is to provide a comprehensive and functional chat agent solution for small businesses, enabling automated customer support, lead generation, appointment booking, and other business-critical interactions. It leverages FastAPI for its API, SQLAlchemy for database interactions, and integrates with external services for AI processing and communication.

## Core Components

The project is structured into several key directories and modules:

- **`api/`**: Contains the core backend logic, including API endpoints, database models, services, and routers.
    - **`main.py`**: The main entry point for the FastAPI application, handling application startup, environment variable validation, and middleware configuration.
    - **`db.py`**: Manages database connections and sessions.
    - **`models.py`**: Defines the SQLAlchemy ORM models for various entities like `Tenant`, `Message`, `Usage`, `FAQ`, and `Appointment`.
    - **`routers/`**: Houses different API route modules, separating concerns for various functionalities (e.g., `webhook`, `admin`, `rag`).
    - **`services/`**: Contains modules for interacting with external services (e.g., `whatsapp.py`).
    - **`ai.py`**: Likely handles AI-related functionalities, such as generating responses using RAG (Retrieval Augmented Generation).
    - **`tasks.py`**: Defines background tasks, such as processing AI replies.
    - **`monitoring.py`**: Sets up application monitoring and metrics.
- **`alembic/`**: Contains database migration scripts managed by Alembic.
- **`site/`**: (Based on `ls -F` output) Likely contains frontend or static assets for a web interface.

## Existing Integrations

### WhatsApp Integration

The project currently features a well-defined integration with the WhatsApp Business API. This integration enables the system to receive and process messages from WhatsApp users and send automated responses. For a detailed breakdown, refer to the [WhatsApp Integration Documentation](./whatsapp_integration.md).

## Upcoming Features

`lumi-v3-stella` is designed with extensibility in mind, with plans to incorporate additional messaging platforms and functionalities. For a detailed discussion on the proposed architecture for Telegram and Instagram integrations, as well as calendar event creation, refer to the [Upcoming Features Documentation](./upcoming_features.md).

## Setup and Deployment

(Further details on setup and deployment would typically go here, including instructions for setting up environment variables, running migrations, and deploying the application.)

## Contributing

(Information on how to contribute to the project would typically go here.)

## License

This project is licensed under the MIT License. See the [LICENSE](../LICENSE) file for details.



### `api/` Directory Structure and Key Modules

The `api/` directory is the heart of the `lumi-v3-stella` application, containing all the backend logic. Below is a more detailed breakdown of its contents:

- **`main.py`**: This is the primary entry point for the FastAPI application. It handles:
    - Application startup and shutdown events (`lifespan`).
    - Configuration of logging using Python's `logging` module, directing output to `sys.stdout`.
    - Validation of essential environment variables (e.g., `OPENAI_API_KEY`, `VERIFY_TOKEN`, `DATABASE_URL`), ensuring the application has the necessary credentials to run. If any are missing, the application will exit.
    - Initialization of database connections and running Alembic migrations on startup to ensure the database schema is up-to-date.
    - Setting up CORS (Cross-Origin Resource Sharing) middleware to allow frontend applications from different origins to interact with the API.
    - Inclusion of various API routers (`webhook`, `admin`, `rag`) to organize endpoints.
    - Integration of Prometheus metrics for monitoring application performance and usage.

- **`db.py`**: This module is responsible for database connectivity and session management. It:
    - Retrieves the `DATABASE_URL` from environment variables.
    - Creates a SQLAlchemy `engine` to connect to the database.
    - Defines `SessionLocal` as a session factory for creating database sessions.
    - Provides the `get_db` dependency, a generator function used by FastAPI routes to obtain a database session, ensuring proper session lifecycle management (opening and closing).
    - Defines `Base` for declarative models.

- **`models.py`**: This module defines the SQLAlchemy ORM (Object-Relational Mapping) models, representing the database tables and their relationships. Key models include:
    - **`Tenant`**: Represents a client or organization using the system. It has a string `id` (to support custom identifiers), `phone_id` (unique identifier for WhatsApp Business Account), `wh_token` (WhatsApp token), and `system_prompt` (for AI customization).
    - **`Message`**: Stores incoming and outgoing messages. It includes `tenant_id` (foreign key to `Tenant`), `wa_msg_id` (WhatsApp message ID), `role` (inbound/assistant), `text`, `tokens`, and `ts` (timestamp).
    - **`FAQ`**: Stores frequently asked questions and their answers, associated with a `Tenant`. Includes `question`, `answer`, and `embedding` (for RAG purposes).
    - **`Usage`**: Tracks token usage for each tenant, including `direction` (inbound/outbound), `tokens`, and `msg_ts`.
    - **`Appointment`**: Manages appointments, including `tenant_id`, `customer_phone`, `customer_email`, `starts_at`, `status` (pending/confirmed/cancelled), `google_event_id` (for calendar integration), and `reminded` status.
    - **Relationships**: Models are interconnected using SQLAlchemy relationships (e.g., `Tenant` has relationships with `Message`, `FAQ`, `Usage`).

- **`routers/`**: This directory contains separate Python files, each defining a set of related API endpoints (routers). This modular approach helps in organizing the API and maintaining a clean codebase.
    - **`webhook.py`**: Handles incoming webhooks, primarily from the WhatsApp Business API. It includes endpoints for webhook verification (GET) and processing incoming messages (POST). This is where the core logic for receiving and initially processing WhatsApp messages resides.
    - **`admin.py`**: Provides administrative endpoints, likely for managing tenants, FAQs, and other system configurations. It might include endpoints for creating/updating tenants, managing FAQ entries, and viewing usage statistics.
    - **`rag.py`**: Likely contains endpoints related to Retrieval Augmented Generation (RAG), possibly for managing or querying the knowledge base used by the AI.

- **`services/`**: This directory holds modules that encapsulate logic for interacting with external services.
    - **`whatsapp.py`**: Contains functions specifically designed for sending messages via the WhatsApp Business API. This separation ensures that the logic for communicating with WhatsApp is centralized and reusable.

- **`ai.py`**: This module is dedicated to Artificial Intelligence functionalities. It imports `get_rag_response`, indicating its role in generating AI-powered responses, likely utilizing the RAG approach to fetch relevant information before generating a reply.

- **`tasks.py`**: Defines background tasks that can be executed asynchronously. The `process_ai_reply` task, for instance, suggests that AI response generation might be a long-running operation that is offloaded to a background task to avoid blocking the main API thread.

- **`monitoring.py`**: Responsible for setting up application monitoring, likely integrating with tools like Prometheus to expose metrics about API requests, errors, and other operational data.

- **`logging_utils.py`**: Provides utility functions for consistent logging across the application, ensuring that logs are formatted and handled uniformly.

- **`schemas/`**: (Not explicitly listed in `ls -F` but implied by common FastAPI patterns) This directory would typically contain Pydantic models used for request and response validation, ensuring data integrity and clear API contracts.

- **`utils/`**: Contains general utility functions that are reused across different parts of the application.

- **`alembic/`**: This directory contains the configuration and scripts for Alembic, a database migration tool. It allows for version controlling the database schema, making it easy to apply changes and roll back if necessary.

- **`requirements.txt`**: Lists all the Python dependencies required for the project, enabling easy environment setup and dependency management.



## Operational Aspects and Hosting

`lumi-v3-stella` is designed for cloud deployment, with a strong emphasis on leveraging Platform as a Service (PaaS) providers like Railway for simplified hosting and management.

### Railway Hosting

Railway is a modern PaaS that allows developers to deploy applications quickly without managing underlying infrastructure. For `lumi-v3-stella`, Railway provides:

-   **Automatic Deployment**: Integration with Git repositories (e.g., GitHub) enables automatic deployments whenever changes are pushed to the main branch.
-   **Environment Variable Management**: Railway offers a secure and convenient way to store and manage environment variables, which are crucial for the application's configuration.
-   **Database Provisioning**: Railway can provision and manage PostgreSQL databases, which is compatible with SQLAlchemy and `pgvector` used by `lumi-v3-stella`.
-   **Scalability**: Railway's infrastructure allows for easy scaling of the application based on demand.
-   **Monitoring**: Basic monitoring and logging capabilities are provided by the platform.

### Environment Variables

Environment variables are critical for configuring the `lumi-v3-stella` application without hardcoding sensitive information or deployment-specific settings. These variables are typically set in the hosting environment (e.g., Railway's dashboard) and are accessed by the application at runtime using `os.getenv()`.

Key environment variables required by `lumi-v3-stella` include:

-   **`OPENAI_API_KEY`**: Your API key for accessing OpenAI services (or other compatible AI models).
-   **`OPENAI_MODEL`**: Specifies the AI model to be used (e.g., `gpt-3.5-turbo`, `gpt-4`).
-   **`VERIFY_TOKEN`**: A token used for webhook verification with messaging platforms (e.g., WhatsApp).
-   **`WH_TOKEN`**: The WhatsApp Business API token for sending messages.
-   **`WH_PHONE_ID`**: The phone number ID associated with your WhatsApp Business Account.
-   **`DATABASE_URL`**: The connection string for the PostgreSQL database (e.g., `postgresql://user:password@host:port/database`). This is used by SQLAlchemy to connect to the database.
-   **`X_ADMIN_TOKEN`**: An administrative token used to secure sensitive API endpoints (e.g., those in `admin.py`).

These variables ensure that the application can connect to external services, authenticate securely, and adapt to different deployment environments without code changes.

### How Everything Operates

1.  **Deployment**: The `lumi-v3-stella` application is deployed to a PaaS like Railway. Upon deployment, the platform reads the `requirements.txt` to install dependencies and runs the `main.py` application.
2.  **Initialization**: On startup, `main.py` validates the presence of all necessary environment variables. It then connects to the PostgreSQL database specified by `DATABASE_URL` and applies any pending database migrations using Alembic.
3.  **Webhook Listener**: The FastAPI application exposes a `/webhook` endpoint (and will expose similar endpoints for Telegram and Instagram). Messaging platforms are configured to send incoming messages and events to this endpoint.
4.  **Message Processing**: When a message arrives at the webhook, the `webhook.py` router processes it. It identifies the `Tenant` based on the `phone_number_id` and then calls `process_message`.
5.  **AI and Business Logic**: Inside `process_message`, the system determines the intent of the user's message. It might trigger appointment booking logic or generate an AI response using the RAG approach. This involves fetching relevant FAQs and conversation history from the database and using the `ai.py` module to interact with the OpenAI API.
6.  **Response Generation**: Once a response is generated (either a booking confirmation or an AI-generated text), it is sent back to the user via the appropriate messaging service (e.g., `whatsapp.py`).
7.  **Data Persistence and Monitoring**: All messages, usage data, and appointments are stored in the PostgreSQL database. The `monitoring.py` module collects metrics, providing insights into the application's performance and usage patterns.

