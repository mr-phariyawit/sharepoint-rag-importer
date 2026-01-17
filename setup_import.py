import requests
import os
from dotenv import load_dotenv

load_dotenv()

API_URL = "http://localhost:8000/api"
TENANT_ID = os.getenv("MICROSOFT_TENANT_ID")
CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID")
CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET")
SITE_URL = "https://apollodemo118.sharepoint.com/sites/admin"
FOLDER_URL = "https://apollodemo118.sharepoint.com/:f:/s/admin/IgDTPFaHZG0JSaUHYOlktyFqASs6cl8JP_prOf9ZST8-4-c?e=YdDI45"

def create_connection():
    print("Creating connection...")
    payload = {
        "name": "Apollo Demo Admin",
        "tenant_id": TENANT_ID,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
    try:
        response = requests.post(f"{API_URL}/connections", json=payload)
        response.raise_for_status()
        data = response.json()
        print(f"✅ Connection created: {data['id']} ({data['name']})")
        return data['id']
    except requests.exceptions.HTTPError as e:
        print(f"❌ Failed to create connection: {e}")
        print(e.response.text)
        return None

def start_import(connection_id):
    print(f"Starting import for folder: {FOLDER_URL}")
    payload = {
        "connection_id": connection_id,
        "folder_url": FOLDER_URL,
        "recursive": True,
        "file_types": ["pdf", "docx", "xlsx"]
    }
    try:
        response = requests.post(f"{API_URL}/import", json=payload)
        response.raise_for_status()
        data = response.json()
        print(f"✅ Import job started: {data['id']}")
        return data['id']
    except requests.exceptions.HTTPError as e:
        print(f"❌ Failed to start import: {e}")
        print(e.response.text)
        return None

if __name__ == "__main__":
    if not all([TENANT_ID, CLIENT_ID, CLIENT_SECRET]):
        print("❌ Missing credentials in .env")
        exit(1)

    connection_id = create_connection()
    if connection_id:
        start_import(connection_id)
