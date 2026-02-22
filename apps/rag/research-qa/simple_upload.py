#!/usr/bin/env python3
"""
Simple document uploader for AnythingLLM
Upload local files to technical-docs workspace
"""

import sys
import requests
from pathlib import Path
from typing import List

# Configuration
ANYTHINGLLM_URL = "http://192.168.5.10:3001"
API_KEY = "4Y06NPD-HWP4MN9-HVQKPC3-0XNTVY5"  # pragma: allowlist secret
WORKSPACE_SLUG = "technical-docs"


def upload_file(file_path: Path) -> bool:
    """Upload a single file to AnythingLLM"""
    url = f"{ANYTHINGLLM_URL}/api/v1/document/upload"
    headers = {"Authorization": f"Bearer {API_KEY}"}

    try:
        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f)}
            response = requests.post(url, headers=headers, files=files, timeout=30)

        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                print(f"✅ Uploaded: {file_path.name}")
                return True
            else:
                print(
                    f"❌ Failed: {file_path.name} - {data.get('error', 'Unknown error')}"
                )
                return False
        else:
            print(f"❌ HTTP {response.status_code}: {file_path.name}")
            return False

    except Exception as e:
        print(f"❌ Error uploading {file_path.name}: {e}")
        return False


def get_uploaded_files() -> List[str]:
    """Get list of files already in the system"""
    url = f"{ANYTHINGLLM_URL}/api/v1/documents"
    headers = {"Authorization": f"Bearer {API_KEY}"}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return [
                doc["docpath"] for doc in data.get("localFiles", {}).get("items", [])
            ]
        return []
    except Exception:
        return []


def add_to_workspace(filename: str) -> bool:
    """Add uploaded file to workspace"""
    url = f"{ANYTHINGLLM_URL}/api/v1/workspace/{WORKSPACE_SLUG}/update-embeddings"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

    payload = {"adds": [filename]}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                print(f"  ✅ Added to workspace: {filename}")
                return True
            else:
                print(f"  ❌ Failed to add: {data.get('message', 'Unknown error')}")
                return False
        else:
            print(f"  ❌ HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python simple_upload.py <file_or_directory>")
        print("\nExample:")
        print("  python simple_upload.py /tmp/orion-test-docs")
        print("  python simple_upload.py /path/to/document.pdf")
        sys.exit(1)

    path = Path(sys.argv[1])

    if not path.exists():
        print(f"Error: {path} does not exist")
        sys.exit(1)

    # Collect files to upload
    files_to_upload = []
    if path.is_file():
        files_to_upload = [path]
    else:
        # Get all markdown and PDF files
        for ext in ["*.md", "*.pdf", "*.txt"]:
            files_to_upload.extend(path.glob(ext))

    if not files_to_upload:
        print(f"No files found in {path}")
        sys.exit(1)

    print(f"\n📄 Found {len(files_to_upload)} files to upload")
    print(f"🎯 Target workspace: {WORKSPACE_SLUG}\n")

    # Get already uploaded files
    print("Checking existing files...")
    existing = get_uploaded_files()
    print(f"Found {len(existing)} files already uploaded\n")

    uploaded_count = 0
    added_count = 0

    for file_path in files_to_upload:
        # Step 1: Upload file
        if upload_file(file_path):
            uploaded_count += 1

            # Step 2: Add to workspace
            if add_to_workspace(file_path.name):
                added_count += 1

    print("\n✅ Summary:")
    print(f"  Uploaded: {uploaded_count}/{len(files_to_upload)}")
    print(f"  Added to workspace: {added_count}/{uploaded_count}")
    print(f"\n🌐 View at: {ANYTHINGLLM_URL}")


if __name__ == "__main__":
    main()
