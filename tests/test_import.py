#!/usr/bin/env python3
"""
SharePoint RAG Importer - Test Suite
=====================================

Comprehensive test script for the full import and query pipeline.

Usage:
    # Run all tests
    python tests/test_import.py
    
    # Run specific test
    python tests/test_import.py --test health
    python tests/test_import.py --test import --folder-url "https://..."

Environment Variables:
    MICROSOFT_TENANT_ID     - Azure AD Tenant ID
    MICROSOFT_CLIENT_ID     - App Registration Client ID
    MICROSOFT_CLIENT_SECRET - App Registration Client Secret
    TEST_FOLDER_URL         - SharePoint folder URL to test with
    API_BASE_URL            - API URL (default: http://localhost:8000)
"""

import asyncio
import httpx
import os
import sys
import time
import argparse
from datetime import datetime
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

# Load environment
load_dotenv()

# =============================================================================
# Configuration
# =============================================================================

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
TENANT_ID = os.getenv("MICROSOFT_TENANT_ID", "")
CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET", "")
TEST_FOLDER_URL = os.getenv("TEST_FOLDER_URL", "")

# =============================================================================
# Console Colors
# =============================================================================

class C:
    """Console colors"""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'

def print_header(text: str):
    print(f"\n{C.BOLD}{'='*60}{C.RESET}")
    print(f"{C.BOLD}{text}{C.RESET}")
    print(f"{C.BOLD}{'='*60}{C.RESET}")

def print_success(text: str):
    print(f"{C.GREEN}✅ {text}{C.RESET}")

def print_error(text: str):
    print(f"{C.RED}❌ {text}{C.RESET}")

def print_info(text: str):
    print(f"{C.BLUE}ℹ️  {text}{C.RESET}")

def print_warning(text: str):
    print(f"{C.YELLOW}⚠️  {text}{C.RESET}")

def print_progress(current: int, total: int, status: str = ""):
    pct = (current / total * 100) if total > 0 else 0
    bar_len = 30
    filled = int(bar_len * current / total) if total > 0 else 0
    bar = '█' * filled + '░' * (bar_len - filled)
    print(f"\r  [{bar}] {pct:5.1f}% {status[:40]:<40}", end='', flush=True)

# =============================================================================
# Test Client
# =============================================================================

class TestClient:
    """HTTP client for API testing"""
    
    def __init__(self, base_url: str = API_BASE_URL):
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=base_url, timeout=300.0)
    
    async def close(self):
        await self.client.aclose()
    
    async def get(self, path: str) -> httpx.Response:
        return await self.client.get(path)
    
    async def post(self, path: str, json: dict) -> httpx.Response:
        return await self.client.post(path, json=json)
    
    async def delete(self, path: str) -> httpx.Response:
        return await self.client.delete(path)

# =============================================================================
# Test Cases
# =============================================================================

async def test_health(client: TestClient) -> bool:
    """Test 1: API Health Check"""
    print_header("TEST 1: Health Check")
    
    try:
        response = await client.get("/health")
        data = response.json()
        
        if response.status_code == 200:
            print_success(f"API Status: {data.get('status', 'unknown')}")
            
            services = data.get('services', {})
            for name, status in services.items():
                icon = "✅" if status == "ok" else "❌"
                print(f"  {icon} {name}: {status}")
            
            return data.get('status') == 'healthy'
        else:
            print_error(f"Health check failed: {response.status_code}")
            return False
            
    except httpx.ConnectError:
        print_error(f"Cannot connect to API at {client.base_url}")
        print_info("Make sure the API is running: docker-compose up -d")
        return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False


async def test_create_connection(client: TestClient) -> Optional[str]:
    """Test 2: Create SharePoint Connection"""
    print_header("TEST 2: Create Connection")
    
    # Check credentials
    if not all([TENANT_ID, CLIENT_ID, CLIENT_SECRET]):
        print_warning("Microsoft credentials not set in environment")
        print_info("Set: MICROSOFT_TENANT_ID, MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET")
        return None
    
    print_info(f"Tenant ID: {TENANT_ID[:8]}...{TENANT_ID[-4:]}")
    print_info(f"Client ID: {CLIENT_ID[:8]}...{CLIENT_ID[-4:]}")
    
    try:
        response = await client.post("/api/connections", json={
            "name": f"Test Connection {datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "tenant_id": TENANT_ID,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET
        })
        
        if response.status_code == 200:
            data = response.json()
            print_success(f"Connection created!")
            print_info(f"ID: {data['id']}")
            print_info(f"Name: {data['name']}")
            print_info(f"Status: {data['status']}")
            return data['id']
        else:
            error = response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
            print_error(f"Failed: {error}")
            return None
            
    except Exception as e:
        print_error(f"Error: {e}")
        return None


async def test_list_connections(client: TestClient) -> List[Dict]:
    """Test 3: List Connections"""
    print_header("TEST 3: List Connections")
    
    try:
        response = await client.get("/api/connections")
        
        if response.status_code == 200:
            connections = response.json()
            print_success(f"Found {len(connections)} connection(s)")
            
            for conn in connections:
                status_color = C.GREEN if conn['status'] == 'connected' else C.YELLOW
                print(f"\n  {C.CYAN}{conn['name']}{C.RESET}")
                print(f"    ID: {conn['id'][:20]}...")
                print(f"    Status: {status_color}{conn['status']}{C.RESET}")
                print(f"    Documents: {conn.get('total_documents', 0)}")
                print(f"    Chunks: {conn.get('total_chunks', 0)}")
            
            return connections
        else:
            print_error(f"Failed: {response.text}")
            return []
            
    except Exception as e:
        print_error(f"Error: {e}")
        return []


async def test_import_folder(
    client: TestClient,
    connection_id: str,
    folder_url: str,
    recursive: bool = True,
    timeout: int = 600
) -> Optional[Dict]:
    """Test 4: Import SharePoint Folder"""
    print_header("TEST 4: Import Folder (Recursive)")
    
    if not folder_url:
        print_warning("No folder URL provided")
        print_info("Set TEST_FOLDER_URL or use --folder-url")
        return None
    
    print_info(f"Connection: {connection_id[:20]}...")
    print_info(f"Folder: {folder_url}")
    print_info(f"Recursive: {recursive}")
    
    try:
        # Start import
        response = await client.post("/api/import", json={
            "connection_id": connection_id,
            "folder_url": folder_url,
            "recursive": recursive
        })
        
        if response.status_code != 200:
            print_error(f"Failed to start import: {response.text}")
            return None
        
        job = response.json()
        job_id = job['id']
        print_success(f"Import job started: {job_id}")
        
        # Poll for progress
        print_info("Waiting for completion...")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            response = await client.get(f"/api/import/{job_id}")
            status = response.json()
            
            total = status.get('total_files_found', 0)
            processed = status.get('files_processed', 0)
            current = status.get('current_file', '')
            
            print_progress(processed, max(total, 1), f"{status['status']}: {current}")
            
            if status['status'] in ('completed', 'failed', 'cancelled'):
                print()  # New line after progress
                break
            
            await asyncio.sleep(2)
        
        # Final results
        if status['status'] == 'completed':
            print_success("Import completed!")
            print_info(f"Files found: {status['total_files_found']}")
            print_info(f"Files processed: {status['files_processed']}")
            print_info(f"Files failed: {status['files_failed']}")
            print_info(f"Chunks created: {status['total_chunks_created']}")
        elif status['status'] == 'failed':
            print_error("Import failed")
        else:
            print_warning(f"Import status: {status['status']}")
        
        return status
        
    except Exception as e:
        print_error(f"Error: {e}")
        return None


async def test_query(
    client: TestClient,
    query_text: str = "สรุปเนื้อหาเอกสารให้หน่อย",
    connection_id: Optional[str] = None
) -> Optional[Dict]:
    """Test 5: RAG Query"""
    print_header("TEST 5: RAG Query")
    
    print_info(f"Query: {query_text}")
    
    try:
        payload = {
            "query": query_text,
            "top_k": 5,
            "include_sources": True
        }
        if connection_id:
            payload["connection_id"] = connection_id
        
        start = time.time()
        response = await client.post("/api/query", json=payload)
        elapsed = time.time() - start
        
        if response.status_code == 200:
            result = response.json()
            print_success(f"Got response in {elapsed:.2f}s")
            
            # Answer
            print(f"\n{C.CYAN}Answer:{C.RESET}")
            answer = result['answer']
            # Wrap long lines
            for line in answer.split('\n'):
                if len(line) > 80:
                    words = line.split(' ')
                    current_line = ""
                    for word in words:
                        if len(current_line) + len(word) > 78:
                            print(f"  {current_line}")
                            current_line = word
                        else:
                            current_line += (" " if current_line else "") + word
                    if current_line:
                        print(f"  {current_line}")
                else:
                    print(f"  {line}")
            
            # Sources
            if result.get('sources'):
                print(f"\n{C.CYAN}Sources:{C.RESET}")
                for src in result['sources']:
                    print(f"  [{src['index']}] {src['document_name']}")
                    print(f"      Score: {src['score']:.3f}, Page: {src.get('page_number', 'N/A')}")
            
            # Timing
            timing = result.get('timing', {})
            print(f"\n{C.CYAN}Timing:{C.RESET}")
            print(f"  Embedding:  {timing.get('embedding_ms', 0):>6.0f} ms")
            print(f"  Retrieval:  {timing.get('retrieval_ms', 0):>6.0f} ms")
            print(f"  Generation: {timing.get('generation_ms', 0):>6.0f} ms")
            print(f"  Total:      {timing.get('total_ms', 0):>6.0f} ms")
            
            return result
        else:
            print_error(f"Query failed: {response.text}")
            return None
            
    except Exception as e:
        print_error(f"Error: {e}")
        return None


async def test_search(
    client: TestClient,
    query_text: str = "document summary",
    connection_id: Optional[str] = None
) -> List[Dict]:
    """Test 6: Semantic Search"""
    print_header("TEST 6: Semantic Search")
    
    print_info(f"Query: {query_text}")
    
    try:
        payload = {"query": query_text, "top_k": 5}
        if connection_id:
            payload["connection_id"] = connection_id
        
        response = await client.post("/api/query/search", json=payload)
        
        if response.status_code == 200:
            results = response.json()
            print_success(f"Found {len(results)} results")
            
            for i, r in enumerate(results, 1):
                print(f"\n  {C.CYAN}{i}. {r['document_name']}{C.RESET}")
                print(f"     Score: {r['score']:.4f}")
                content = r['content'][:150].replace('\n', ' ')
                print(f"     {content}...")
            
            return results
        else:
            print_error(f"Search failed: {response.text}")
            return []
            
    except Exception as e:
        print_error(f"Error: {e}")
        return []


async def test_stats(client: TestClient) -> Dict:
    """Test 7: Vector Store Statistics"""
    print_header("TEST 7: Vector Store Stats")
    
    try:
        response = await client.get("/api/query/stats")
        
        if response.status_code == 200:
            stats = response.json()
            print_success("Statistics retrieved")
            print_info(f"Total vectors:   {stats.get('vectors_count', 0):>10,}")
            print_info(f"Indexed vectors: {stats.get('indexed_vectors_count', 0):>10,}")
            print_info(f"Points:          {stats.get('points_count', 0):>10,}")
            print_info(f"Status:          {stats.get('status', 'unknown')}")
            return stats
        else:
            print_warning(f"Could not get stats: {response.text}")
            return {}
            
    except Exception as e:
        print_warning(f"Error: {e}")
        return {}


# =============================================================================
# Test Runner
# =============================================================================

async def run_all_tests(folder_url: Optional[str] = None):
    """Run complete test suite"""
    print(f"\n{C.BOLD}{C.MAGENTA}{'='*60}{C.RESET}")
    print(f"{C.BOLD}{C.MAGENTA}🧪 SharePoint RAG Importer - Test Suite{C.RESET}")
    print(f"{C.BOLD}{C.MAGENTA}{'='*60}{C.RESET}")
    print(f"API URL: {API_BASE_URL}")
    print(f"Time:    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    client = TestClient()
    results = {}
    
    try:
        # Test 1: Health
        results['health'] = await test_health(client)
        if not results['health']:
            print_error("\nAPI not healthy. Stopping tests.")
            return results
        
        # Test 2: Create connection
        connection_id = await test_create_connection(client)
        results['connection'] = connection_id is not None
        
        # Test 3: List connections
        connections = await test_list_connections(client)
        results['list'] = len(connections) > 0
        
        # Test 4: Import (if we have credentials and folder URL)
        test_url = folder_url or TEST_FOLDER_URL
        if connection_id and test_url:
            import_result = await test_import_folder(client, connection_id, test_url)
            results['import'] = import_result and import_result.get('status') == 'completed'
        else:
            results['import'] = None
            print_warning("\nSkipping import test (no folder URL)")
        
        # Test 5: Query
        query_result = await test_query(client, connection_id=connection_id)
        results['query'] = query_result is not None
        
        # Test 6: Search
        search_results = await test_search(client, connection_id=connection_id)
        results['search'] = len(search_results) > 0 if search_results else False
        
        # Test 7: Stats
        stats = await test_stats(client)
        results['stats'] = len(stats) > 0
        
    finally:
        await client.close()
    
    # Summary
    print_header("📊 Test Summary")
    
    passed = 0
    failed = 0
    skipped = 0
    
    for name, result in results.items():
        if result is None:
            print(f"  {C.YELLOW}⏭️  {name}: skipped{C.RESET}")
            skipped += 1
        elif result:
            print(f"  {C.GREEN}✅ {name}: passed{C.RESET}")
            passed += 1
        else:
            print(f"  {C.RED}❌ {name}: failed{C.RESET}")
            failed += 1
    
    print()
    print(f"  Total: {passed + failed + skipped}")
    print(f"  {C.GREEN}Passed: {passed}{C.RESET}")
    print(f"  {C.RED}Failed: {failed}{C.RESET}")
    print(f"  {C.YELLOW}Skipped: {skipped}{C.RESET}")
    
    return results


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="SharePoint RAG Importer Test Suite")
    parser.add_argument("--test", choices=['health', 'connection', 'list', 'import', 'query', 'search', 'stats', 'all'],
                       default='all', help="Specific test to run")
    parser.add_argument("--folder-url", help="SharePoint folder URL for import test")
    parser.add_argument("--connection-id", help="Existing connection ID to use")
    parser.add_argument("--query", help="Custom query text")
    
    args = parser.parse_args()
    
    # Run tests
    if args.test == 'all':
        asyncio.run(run_all_tests(args.folder_url))
    else:
        # Run specific test
        asyncio.run(run_single_test(args))


async def run_single_test(args):
    """Run a single test"""
    client = TestClient()
    
    try:
        if args.test == 'health':
            await test_health(client)
        elif args.test == 'connection':
            await test_create_connection(client)
        elif args.test == 'list':
            await test_list_connections(client)
        elif args.test == 'import':
            if not args.connection_id:
                print_error("--connection-id required for import test")
                return
            folder_url = args.folder_url or TEST_FOLDER_URL
            if not folder_url:
                print_error("--folder-url or TEST_FOLDER_URL required")
                return
            await test_import_folder(client, args.connection_id, folder_url)
        elif args.test == 'query':
            query = args.query or "สรุปเอกสารให้หน่อย"
            await test_query(client, query, args.connection_id)
        elif args.test == 'search':
            query = args.query or "document summary"
            await test_search(client, query, args.connection_id)
        elif args.test == 'stats':
            await test_stats(client)
    finally:
        await client.close()


if __name__ == "__main__":
    main()
