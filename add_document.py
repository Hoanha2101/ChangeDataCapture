"""
Helper script to add documents from files to the API
"""

import requests
import json
import sys
from pathlib import Path

BASE_URL = "http://localhost:8000"

def add_document_from_file(table_name: str, file_path: str):
    """Add document from file"""
    try:
        # Read file content
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Prepare request
        url = f"{BASE_URL}/api/v1/document/{table_name}/add"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        data = {
            "content": content
        }
        
        # Send request
        response = requests.post(url, json=data, headers=headers)
        
        # Print result
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        
        if response.status_code in [200, 201]:
            result = response.json()
            doc_id = result['result']['id']
            print(f"\n✅ Document added successfully with ID: {doc_id}")
            return doc_id
        else:
            print(f"\n❌ Failed to add document")
            return None
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def add_document_from_text(table_name: str, content: str):
    """Add document from text"""
    try:
        # Prepare request
        url = f"{BASE_URL}/api/v1/document/{table_name}/add"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        data = {
            "content": content
        }
        
        # Send request
        response = requests.post(url, json=data, headers=headers)
        
        # Print result
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        
        if response.status_code in [200, 201]:
            result = response.json()
            doc_id = result['result']['id']
            print(f"\n✅ Document added successfully with ID: {doc_id}")
            return doc_id
        else:
            print(f"\n❌ Failed to add document")
            return None
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage:")
        print("  python add_document.py <table_name> <file_path>")
        print("\nExample:")
        print("  python add_document.py rag data/CAR.txt")
        sys.exit(1)
    
    table_name = sys.argv[1]
    file_path = sys.argv[2]
    
    if not Path(file_path).exists():
        print(f"❌ File not found: {file_path}")
        sys.exit(1)
    
    add_document_from_file(table_name, file_path)
