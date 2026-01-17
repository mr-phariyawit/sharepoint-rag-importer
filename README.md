# SharePoint RAG Importer

Enterprise-grade system for importing SharePoint/OneDrive files into a Vector Database for RAG (Retrieval-Augmented Generation) queries.

## ✨ Features

- 🔄 **Recursive Folder Import** - Import entire folder structures with subfolders
- 📄 **Multi-format Support** - PDF, DOCX, XLSX, PPTX, TXT, CSV, MD, HTML, JSON
- 🔍 **Hybrid Search** - Vector + Keyword search for best results
- 🤖 **AI-Powered Answers** - Claude/GPT generates answers with citations
- 🔗 **Source Links** - Click to open original file in SharePoint
- ⚡ **Real-time Sync** - Webhook support for automatic updates
- 🌏 **Thai Language** - Full support for Thai documents
- 📊 **Admin Dashboard** - Beautiful web UI for management

---

## 🚀 Quick Start

```bash
# 1. Setup
cd sharepoint-rag-importer
cp .env.example .env
# Edit .env with your credentials

# 2. Start
docker-compose up -d

# 3. Access
# API: http://localhost:8000
# Dashboard: http://localhost:8000/dashboard
# Docs: http://localhost:8000/docs
```

---

## 📖 API Usage

### Create Connection

```bash
curl -X POST http://localhost:8000/api/connections \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Company SharePoint",
    "tenant_id": "xxx",
    "client_id": "xxx",
    "client_secret": "xxx"
  }'
```

### Import Folder (Recursive)

```bash
curl -X POST http://localhost:8000/api/import \
  -H "Content-Type: application/json" \
  -d '{
    "connection_id": "xxx",
    "folder_url": "https://company.sharepoint.com/sites/docs/Shared Documents/Projects",
    "recursive": true
  }'
```

### Query Documents

```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "สรุปรายงาน Q3 ให้หน่อย"}'
```

---

## 🔔 Real-time Sync (Webhooks)

```bash
# Subscribe to folder changes
curl -X POST http://localhost:8000/api/webhooks/subscribe \
  -H "Content-Type: application/json" \
  -d '{
    "connection_id": "xxx",
    "drive_id": "xxx",
    "folder_path": "/Projects"
  }'
```

---

## 🧪 Testing

```bash
# Run test suite
python tests/test_import.py

# Specific tests
python tests/test_import.py --test health
python tests/test_import.py --test import --folder-url "..."
python tests/test_import.py --test query
```

---

## 📁 Project Structure

```
sharepoint-rag-importer/
├── docker-compose.yml      # All services
├── app/
│   ├── main.py             # FastAPI app
│   ├── api/                # API routes
│   ├── sharepoint/         # Graph API client
│   ├── processing/         # Text extraction & embedding
│   └── storage/            # Vector & metadata stores
├── frontend/
│   └── index.html          # Admin dashboard
└── tests/
    └── test_import.py      # Test suite
```

---

## 🔧 Requirements

- Docker & Docker Compose
- Azure AD App Registration (Files.Read.All, Sites.Read.All)
- OpenAI API key (embeddings)
- Anthropic API key (generation)

---

## 📝 License

MIT License
