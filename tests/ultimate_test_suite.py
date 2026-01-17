#!/usr/bin/env python3
"""
Ultimate Test Suite - SharePoint RAG Importer
=============================================
Runs a comprehensive end-to-end validation of the entire system.
1. Health Check
2. Authentication & Connection Creation
3. Live Import from SharePoint
4. RAG Query & Semantic Search Verification
5. Dashboard Stats Validation
6. Cleanup
"""

import sys
import os
import asyncio
from dotenv import load_dotenv

# Add parent directory to path to import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.test_import import run_all_tests, C, print_header

def main():
    load_dotenv()
    
    # Validation logic
    required_vars = [
        "MICROSOFT_TENANT_ID",
        "MICROSOFT_CLIENT_ID", 
        "MICROSOFT_CLIENT_SECRET",
        "TEST_FOLDER_URL"
    ]
    
    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        print(f"{C.RED}Error: Missing environment variables for test:{C.RESET}")
        for v in missing:
            print(f"  - {v}")
        print("\nPlease update your .env file.")
        sys.exit(1)
        
    print_header("🚀 LAUNCHING ULTIMATE TEST SUITE 🚀")
    
    try:
        results = asyncio.run(run_all_tests())
        
        # Check overall success
        critical_tests = ['health', 'connection', 'import', 'query', 'search']
        failures = [t for t in critical_tests if not results.get(t)]
        
        if failures:
            print(f"\n{C.RED}❌ SUITE FAILED{C.RESET}")
            print(f"Failed critical tests: {', '.join(failures)}")
            sys.exit(1)
        else:
            print(f"\n{C.GREEN}✨ ALL SYSTEMS GO - SUITE PASSED ✨{C.RESET}")
            sys.exit(0)
            
    except KeyboardInterrupt:
        print("\n⚠️ Test aborted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n{C.RED}❌ FATAL ERROR: {e}{C.RESET}")
        sys.exit(1)

if __name__ == "__main__":
    main()
