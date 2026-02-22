"""
AnythingLLM API Client
Handles document upload, workspace management, and embedding via AnythingLLM API

API Documentation: http://192.168.5.10:3001/api/docs/

Created: 2025-11-09 (Phase 8 - API Integration)
"""

import os
import logging
import requests
from pathlib import Path
from typing import List, Dict, Optional, Union, Callable
from dataclasses import dataclass
import time

# Set up logging
logger = logging.getLogger(__name__)


@dataclass
class UploadResult:
    """Result of document upload"""

    success: bool
    document_id: Optional[str] = None
    workspace_slug: Optional[str] = None
    error: Optional[str] = None
    chunks_created: int = 0


class AnythingLLMClient:
    """Client for interacting with AnythingLLM API"""

    def __init__(
        self,
        base_url: str = "http://localhost:3001",
        api_key: Optional[str] = None,
        upload_timeout: int = 120,
        embed_timeout: int = 180,  # Increased from 120s for large academic papers
        embed_retries: int = 5,    # Increased from 3 for better resilience
        embed_retry_backoff: float = 5.0,
    ) -> None:
        """
        Initialize AnythingLLM API client

        Args:
            base_url: AnythingLLM instance URL
            api_key: API key (if None, reads from ANYTHINGLLM_API_KEY env var)
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.getenv("ANYTHINGLLM_API_KEY")

        if not self.api_key:
            raise ValueError(
                "API key required. Set ANYTHINGLLM_API_KEY env var or pass api_key parameter"
            )

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }

        self.upload_timeout = upload_timeout
        self.embed_timeout = embed_timeout
        self.embed_retries = max(1, embed_retries)
        self.embed_retry_backoff = max(0.0, embed_retry_backoff)

        # Create session with retry logic
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create requests session with retry logic for reliability"""
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        session = requests.Session()

        # Retry on connection errors, timeouts, and 5xx server errors
        retry = Retry(
            total=3,
            backoff_factor=1,  # 1s, 2s, 4s delays
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],  # Retry safe methods
        )

        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def test_connection(self) -> bool:
        """Test API connection and authentication"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/v1/system", headers=self.headers, timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Connection test failed for {self.base_url}: {e}")
            return False

    def list_workspaces(self) -> List[Dict]:
        """Get list of all workspaces"""
        response = self.session.get(
            f"{self.base_url}/api/v1/workspaces", headers=self.headers, timeout=30
        )
        response.raise_for_status()
        return response.json().get("workspaces", [])

    def get_workspace(self, workspace_slug: str) -> Optional[Dict]:
        """Get workspace details by slug"""
        response = self.session.get(
            f"{self.base_url}/api/v1/workspace/{workspace_slug}",
            headers=self.headers,
            timeout=30,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json().get("workspace")

    def create_workspace(
        self, name: str, collection_name: Optional[str] = None, **kwargs
    ) -> Dict:
        """
        Create a new workspace

        Args:
            name: Workspace display name
            collection_name: Qdrant collection name (optional, auto-generated if None)
            **kwargs: Additional workspace settings (openAiTemp, openAiHistory, etc.)

        Returns:
            Created workspace details
        """
        payload = {"name": name, **kwargs}

        if collection_name:
            payload["vectorDb"] = collection_name

        response = self.session.post(
            f"{self.base_url}/api/v1/workspace/new",
            headers=self.headers,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def update_workspace(self, workspace_slug: str, **settings) -> Dict:
        """
        Update workspace settings

        Args:
            workspace_slug: Workspace slug identifier
            **settings: Settings to update (openAiTemp, similarityThreshold, topK, etc.)
        """
        response = self.session.post(
            f"{self.base_url}/api/v1/workspace/{workspace_slug}/update",
            headers=self.headers,
            json=settings,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def upload_document(
        self,
        file_path: Union[str, Path],
        workspace_slug: str,
        metadata: Optional[Dict] = None,
    ) -> UploadResult:
        """
        Upload a document to a workspace

        Args:
            file_path: Path to document file (PDF, TXT, MD, HTML, etc.)
            workspace_slug: Target workspace slug
            metadata: Optional metadata dict

        Returns:
            UploadResult with success status and details
        """
        file_path = Path(file_path)

        if not file_path.exists():
            return UploadResult(success=False, error=f"File not found: {file_path}")

        try:
            # Step 1: Upload file to AnythingLLM's document processor
            with open(file_path, "rb") as f:
                files = {"file": (file_path.name, f, self._get_content_type(file_path))}

                # Upload to document processor
                upload_response = self.session.post(
                    f"{self.base_url}/api/v1/document/upload",
                    headers={
                        "Authorization": f"Bearer {self.api_key}"
                    },  # No content-type header for multipart
                    files=files,
                    timeout=self.upload_timeout,
                )
                upload_response.raise_for_status()
                upload_data = upload_response.json()

                if not upload_data.get("success"):
                    return UploadResult(
                        success=False, error=upload_data.get("error", "Upload failed")
                    )

                document_location = upload_data.get("documents", [{}])[0].get(
                    "location"
                )

                if not document_location:
                    return UploadResult(
                        success=False, error="No document location returned"
                    )

            # Step 2: Add document to workspace (triggers embedding)
            last_error: Optional[str] = None
            for attempt in range(1, self.embed_retries + 1):
                try:
                    embed_response = self.session.post(
                        f"{self.base_url}/api/v1/workspace/{workspace_slug}/update-embeddings",
                        headers=self.headers,
                        json={"adds": [document_location], "deletes": []},
                        timeout=self.embed_timeout,
                    )
                    embed_response.raise_for_status()
                    embed_data = embed_response.json()

                    return UploadResult(
                        success=True,
                        workspace_slug=workspace_slug,
                        document_id=document_location,
                        chunks_created=embed_data.get("vectorized", 0),
                    )
                except Exception as embed_error:  # pragma: no cover - network errors
                    last_error = str(embed_error)
                    if attempt == self.embed_retries:
                        break
                    time.sleep(self.embed_retry_backoff * attempt)

            return UploadResult(success=False, error=last_error or "embedding failed")

        except Exception as e:  # pragma: no cover - network errors
            return UploadResult(success=False, error=str(e))

    def upload_documents_bulk(
        self,
        file_paths: List[Union[str, Path]],
        workspace_slug: str,
        progress_callback: Optional[Callable[[int, int, UploadResult], None]] = None,
    ) -> List[UploadResult]:
        """
        Upload multiple documents to a workspace

        Args:
            file_paths: List of file paths to upload
            workspace_slug: Target workspace slug
            progress_callback: Optional callback function(current, total, result)

        Returns:
            List of UploadResult for each file
        """
        results = []
        total = len(file_paths)

        for idx, file_path in enumerate(file_paths, 1):
            result = self.upload_document(file_path, workspace_slug)
            results.append(result)

            if progress_callback:
                progress_callback(idx, total, result)

            # Small delay to avoid overwhelming the API
            time.sleep(0.5)

        return results

    def get_workspace_documents(self, workspace_slug: str) -> List[Dict]:
        """Get all documents in a workspace"""
        response = self.session.get(
            f"{self.base_url}/api/v1/workspace/{workspace_slug}/documents",
            headers=self.headers,
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get("documents", [])

    def generate_embeddings(
        self, texts: List[str], batch_size: int = 32
    ) -> List[List[float]]:
        """
        Generate embeddings for text chunks using AnythingLLM's embedding model

        Args:
            texts: List of text strings to embed
            batch_size: Number of texts to embed per API call

        Returns:
            List of embedding vectors (each is a list of floats)

        Note:
            AnythingLLM uses Xenova/nomic-embed-text-v1 (768-dim, max 8192 tokens).
            This endpoint may vary by AnythingLLM version.
        """
        all_embeddings = []

        # Process in batches to avoid overwhelming API
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]

            try:
                response = self.session.post(
                    f"{self.base_url}/api/v1/embed",
                    headers=self.headers,
                    json={"texts": batch},
                    timeout=60,  # Longer timeout for batch embedding
                )
                response.raise_for_status()

                result = response.json()
                # API might return different structures, handle common patterns
                if isinstance(result, dict) and "embeddings" in result:
                    embeddings = result["embeddings"]
                elif isinstance(result, list):
                    embeddings = result
                else:
                    raise ValueError(
                        f"Unexpected embedding response format: {type(result)}"
                    )

                all_embeddings.extend(embeddings)

            except requests.exceptions.HTTPError as e:
                # If embed endpoint doesn't exist, try alternative method
                if e.response.status_code == 404:
                    raise NotImplementedError(
                        "AnythingLLM embedding API not available. "
                        "Consider using sentence-transformers locally instead."
                    )
                raise

        return all_embeddings

    def chat(
        self,
        workspace_slug: str,
        message: str,
        mode: str = "query",  # "chat" or "query"
    ) -> Dict:
        """
        Send a chat message to a workspace

        Args:
            workspace_slug: Target workspace
            message: Query or message
            mode: "chat" (with history) or "query" (stateless)

        Returns:
            Response dict with textResponse, sources, etc.
        """
        response = self.session.post(
            f"{self.base_url}/api/v1/workspace/{workspace_slug}/chat",
            headers=self.headers,
            json={"message": message, "mode": mode},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _get_content_type(file_path: Path) -> str:
        """Get MIME type for file"""
        ext = file_path.suffix.lower()
        mime_types = {
            ".pdf": "application/pdf",
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".html": "text/html",
            ".htm": "text/html",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc": "application/msword",
        }
        return mime_types.get(ext, "application/octet-stream")


# Example usage
if __name__ == "__main__":
    # Initialize client (uses environment variables)
    client = AnythingLLMClient(
        base_url=os.getenv("ANYTHINGLLM_URL", "http://192.168.5.10:3001"),
        api_key=os.getenv("ANYTHINGLLM_API_KEY") or os.getenv("ANYTHINGLLM_AUTH_TOKEN"),
    )

    # Configure logging for example
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Test connection
    if client.test_connection():
        logger.info("✓ Connected to AnythingLLM")

        # List workspaces
        workspaces = client.list_workspaces()
        logger.info(f"\nFound {len(workspaces)} workspace(s):")
        for ws in workspaces:
            logger.info(f"  - {ws['name']} (slug: {ws['slug']})")
    else:
        logger.error("✗ Connection failed")
