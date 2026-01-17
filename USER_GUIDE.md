# SharePoint RAG Importer - User Guide

Welcome to the **SharePoint RAG Importer**! This system allows you to ingest documents from SharePoint, process them into vectors, and query them using natural language (RAG).

## 🚀 Quick Start

### 1. Prerequisites
- Docker & Docker Compose
- OpenAI API Key
- Microsoft Graph API Credentials (Tenant ID, Client ID, Secret)

### 2. Setup Environment
1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```
2. Edit `.env` and fill in your credentials:
   - `OPENAI_API_KEY`
   - `MICROSOFT_TENANT_ID`, `CLIENT_ID`, `CLIENT_SECRET`

### 3. Launch System
Start all services (API, Database, Vector Store, Worker, Frontend):
```bash
docker-compose up --build -d
```

---

## 🖥️ Dashboard Usage

Access the dashboard at: **[http://localhost:8000/dashboard](http://localhost:8000/dashboard)**

### 🏠 Home Tab
- **Overview**: See system stats (Total Connections, Vectors, Documents).
- **Recent Connections**: Quick view of your active SharePoint connections.

### 🔗 Connections Tab
- **Add Connection**: Click "Add Connection" to link a new SharePoint Site/Tenant.
  - Enter a friendly name (e.g., "HR Dept Docs").
  - The system typically uses the global credentials from `.env`, or you can override them per connection.
- **Manage**: View sync status of existing connections.

### ⚙️ Jobs Tab (Importing)
- **Start Import**: Click "Start Import".
  - **Connection**: Select the connection to use.
  - **Folder URL**: Paste the full URL of the SharePoint folder you want to index.
    - Example: `https://company.sharepoint.com/sites/Marketing/Shared%20Documents/Campaigns`
- **Progress**: Watch files being crawled, chunked, and embedded in real-time.
- **Cancel**: Stop a running job if needed.

### 🔍 Query Tab (RAG)
- **Ask a Question**: Type natural language questions about your documents.
  - Example: *"What is the policy for remote work?"*
- **Filters**: Toggle specific file types (PDF, DOCX) to narrow down search.
- **Sources**: The AI will provide an answer and cite the specific documents used.

### 🔧 Settings Tab
- **Profile**: View current user info (if logged in).
- **Logout**: Sign out of the session.

---

## 🛠️ Advanced Usage & Testing

### API Documentation
Full Swagger/OpenAPI documentation is available for developers:
- **URL**: [http://localhost:8000/docs](http://localhost:8000/docs)

### Running System Tests
To validate that the entire pipeline is working correctly, use the included Ultimate Test Suite:

```bash
# Run the full end-to-end test suite
python3 tests/ultimate_test_suite.py
```

This will check:
1. API Health
2. Database Connectivity
3. Import Functionality (live test)
4. RAG Query Accuracy

---

## ❓ Troubleshooting

- **Missing Tabs?** ensure you have cleared your browser cache or run `docker-compose up -d --force-recreate` if you recently updated the code.
- **Import Errors?** Check the logs `docker-compose logs -f worker` to see specific file processing errors (e.g., encrypted PDFs).
- **Qdrant Errors?** Ensure your Qdrant version is 1.7+ (1.16.2 recommended).

---
*Generated for SharePoint RAG Importer v2.0*
