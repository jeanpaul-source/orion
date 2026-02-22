"""
Knowledge Subsystem

Handles RAG-based question answering using the knowledge base.
All processing happens on lab host GPU via AnythingLLM and Qdrant.

Author: ORION Project
Date: November 17, 2025
"""

import logging
from datetime import datetime
import httpx
from typing import Any, Dict, List, Optional, AsyncGenerator

from ..config import config

STAGED_KNOWLEDGE_COUNTS = {
    "processed_chunks": 1403,
    "raw_documents": 2028,
    "research_papers": 493,
}

REBUILD_COMMANDS = [
    "orion process --max-files 50",
    "orion embed-index",
    "orion validate --quick",
]

FRESH_START_DATE = "2025-11-17"

logger = logging.getLogger(__name__)


class KnowledgeSubsystem:
    """
    Knowledge subsystem for RAG-based question answering.

    Uses:
    - AnythingLLM for RAG pipeline (embeddings + search + generation)
    - Qdrant for vector search (currently empty after Nov 17, 2025 fresh start)
    - vLLM for LLM inference (GPU)

    All running on lab host, internally networked.
    """

    def __init__(self):
        self.anythingllm_url = config.anythingllm_url
        self.api_key = config.anythingllm_api_key
        self.collection = config.qdrant_collection
        self.top_k = config.rag_top_k
        self._last_rebuild_notice: Optional[str] = None

        logger.info(f"Knowledge subsystem initialized (collection: {self.collection})")

    async def handle(self, query: str, context: Dict) -> str:
        """
        Process knowledge query using RAG.

        Args:
            query: User's question
            context: Conversation context

        Returns:
            Answer with citations

        Example:
            >>> knowledge = KnowledgeSubsystem()
            >>> answer = await knowledge.handle(
            ...     "What are Proxmox GPU passthrough best practices?",
            ...     context={}
            ... )
        """
        logger.info(f"Knowledge query: {query}")

        readiness_warning = await self._knowledge_base_gate()
        if readiness_warning:
            return readiness_warning

        try:
            # Query AnythingLLM (handles embedding, search, and generation)
            answer, sources = await self._query_anythingllm(query, context)

            # Format response with citations
            response = self._format_response(answer, sources)

            logger.info(
                f"Knowledge response: {len(answer)} chars, {len(sources)} sources"
            )
            return response

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning("AnythingLLM workspace %s missing", self.collection)
                return self._rebuild_message("Workspace not found in AnythingLLM")
            raise
        except Exception as e:
            logger.exception("Knowledge subsystem error")
            return f"I encountered an error accessing my knowledge base: {str(e)}"

    async def handle_streaming(
        self, query: str, context: Dict
    ) -> AsyncGenerator[Dict, None]:
        """
        Process knowledge query with streaming progress and response.

        Yields progress updates during RAG pipeline and streams the response.

        Args:
            query: User's question
            context: Conversation context

        Yields:
            Dict with "type" field:
            - {"type": "progress", "message": "..."} - Progress update
            - {"type": "token", "content": "..."} - Response token
            - {"type": "sources", "sources": [...]} - Source citations
            - {"type": "error", "message": "..."} - Error message
        """
        logger.info(f"Streaming knowledge query: {query}")

        # Check knowledge base readiness
        yield {"type": "progress", "message": "📊 Checking knowledge base..."}

        readiness_warning = await self._knowledge_base_gate()
        if readiness_warning:
            # Yield the rebuild message as tokens
            for chunk in self._chunk_text(readiness_warning):
                yield {"type": "token", "content": chunk}
            return

        try:
            # Indicate RAG pipeline stages
            yield {
                "type": "progress",
                "message": "🔍 Searching knowledge base...",
            }

            # Query AnythingLLM (handles embedding, search, and generation)
            answer, sources = await self._query_anythingllm(query, context)

            yield {
                "type": "progress",
                "message": f"✨ Found {len(sources)} sources, generating response...",
            }

            # Stream the answer
            for chunk in self._chunk_text(answer):
                yield {"type": "token", "content": chunk}

            # Send sources at the end
            if sources:
                yield {"type": "sources", "sources": sources, "count": len(sources)}

            logger.info(
                f"Streamed knowledge response: {len(answer)} chars, {len(sources)} sources"
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning("AnythingLLM workspace %s missing", self.collection)
                error_msg = self._rebuild_message("Workspace not found in AnythingLLM")
            else:
                error_msg = f"HTTP error {e.response.status_code}: {e}"

            for chunk in self._chunk_text(error_msg):
                yield {"type": "token", "content": chunk}

        except Exception as e:
            logger.exception("Streaming knowledge subsystem error")
            error_msg = f"I encountered an error accessing my knowledge base: {str(e)}"
            for chunk in self._chunk_text(error_msg):
                yield {"type": "token", "content": chunk}

    def _chunk_text(self, text: str, chunk_size: int = 10) -> List[str]:
        """
        Split text into word-based chunks for simulated streaming.

        Args:
            text: Full text
            chunk_size: Characters per chunk (approximate)

        Returns:
            List of text chunks
        """
        words = text.split()
        chunks = []
        current_chunk = []
        current_length = 0

        for word in words:
            current_chunk.append(word)
            current_length += len(word) + 1

            if current_length >= chunk_size:
                chunks.append(" ".join(current_chunk) + " ")
                current_chunk = []
                current_length = 0

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        return chunks

    async def _query_anythingllm(
        self, query: str, context: Dict
    ) -> tuple[str, List[Dict]]:
        """
        Query AnythingLLM API for RAG response.

        AnythingLLM handles:
        1. Embedding generation (BAAI/bge-base-en-v1.5)
        2. Vector search in Qdrant
        3. Context assembly
        4. LLM generation (vLLM)
        """
        url = f"{self.anythingllm_url}/api/v1/workspace/{self.collection}/chat"

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "message": query,
            "mode": "query",  # RAG mode
            "promptOverride": self._build_system_prompt(context),
        }

        async with httpx.AsyncClient(timeout=config.request_timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()

            result = response.json()

            answer = result.get("textResponse", "")
            sources = result.get("sources", [])

            return answer, sources

    async def _knowledge_base_gate(self) -> Optional[str]:
        """Check whether the knowledge base has any vectors before querying."""
        stats = await self._fetch_collection_stats()

        if stats and stats.get("vector_count", 0) > 0:
            self._last_rebuild_notice = None
            return None

        if stats is None:
            reason = "Unable to reach Qdrant service"
        elif not stats.get("exists", False):
            reason = "Qdrant collection missing"
        else:
            reason = f"Qdrant collection empty (vectors={stats.get('vector_count', 0)})"

        notice = self._rebuild_message(reason)
        self._last_rebuild_notice = notice
        return notice

    def _rebuild_message(self, reason: str) -> str:
        """Return a standardized rebuild advisory message."""
        return (
            "📦 Knowledge base rebuild required.\n\n"
            "Reason: " + reason + "\n\n"
            "Current state:\n"
            "• 1,403 processed chunks staged for embedding\n"
            "• 2,028 raw documents on host storage\n"
            "• 493 academic PDFs awaiting sync\n\n"
            "Next steps to restore RAG:\n"
            "1. orion process --max-files 50\n"
            "2. orion embed-index\n"
            "3. orion validate --quick\n\n"
            "Once embeddings are recreated, I'll resume providing cited answers."
        )

    async def _fetch_collection_stats(self) -> Optional[Dict[str, Any]]:
        """Query Qdrant for collection statistics."""
        url = f"{config.qdrant_url}/collections/{self.collection}"

        try:
            async with httpx.AsyncClient(timeout=config.request_timeout) as client:
                response = await client.get(url)
        except Exception as exc:
            logger.warning("Failed to contact Qdrant for stats: %s", exc)
            return None

        if response.status_code == 200:
            result = response.json().get("result", {})
            return {
                "exists": True,
                "status": result.get("status", "unknown"),
                "vector_count": result.get("points_count")
                or result.get("vectors_count", 0),
                "indexed_vectors": result.get("indexed_vectors_count", 0),
            }

        if response.status_code == 404:
            return {
                "exists": False,
                "status": "missing",
                "vector_count": 0,
                "indexed_vectors": 0,
            }

        logger.warning("Unexpected Qdrant response: %s", response.status_code)
        return None

    def _build_system_prompt(self, context: Dict) -> str:
        """
        Build system prompt for RAG queries.

        Instructs the LLM on how to use the retrieved context.
        """
        return """You are ORION, an AI homelab assistant preparing to restore the knowledge base after a fresh start.

Current reality:
- Qdrant collection `technical-docs` is empty until embeddings are regenerated
- 493 academic research papers, 2,028 technical documents, and 1,403 processed chunks are staged but not yet indexed
- Until the rebuild finishes, retrieved context may be unavailable

When answering:
1. If no context arrives, clearly state that the knowledge base is being rebuilt and cite the remediation commands
2. When context is available, provide accurate, cited answers with commands/configs when relevant
3. Cite sources with their titles when possible
4. If the context doesn't contain the answer, say so honestly and suggest next steps
5. For complex questions, break down the answer into clear steps

Be conversational but professional. You're helping manage a sophisticated homelab."""

    def _format_response(self, answer: str, sources: List[Dict]) -> str:
        """
        Format response with source citations.

        Args:
            answer: LLM-generated answer
            sources: List of source documents

        Returns:
            Formatted response with citations
        """
        response = answer

        # Add source citations if available
        if sources:
            response += "\n\n📚 **Sources:**\n"
            for i, source in enumerate(sources[:5], 1):
                title = source.get("title", "Unknown")
                score = source.get("score", 0)
                response += f"{i}. {title} (relevance: {score:.2f})\n"

        return response

    def get_last_rebuild_notice(self) -> Optional[str]:
        """Return the last rebuild advisory message, if any."""
        return self._last_rebuild_notice

    async def search_knowledge_base(
        self, query: str, top_k: Optional[int] = None
    ) -> List[Dict]:
        """
        Direct semantic search in Qdrant (without LLM generation).

        Useful for finding relevant documents without generating an answer.

        Args:
            query: Search query
            top_k: Number of results (default: config.rag_top_k)

        Returns:
            List of matching documents
        """
        # Use Qdrant directly for search
        # (AnythingLLM can also do this via /api/v1/workspace/{workspace}/search)

        url = f"{self.anythingllm_url}/api/v1/workspace/{self.collection}/search"

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {"query": query, "limit": top_k or self.top_k}

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()

            result = response.json()
            return result.get("results", [])

    async def get_knowledge_stats(self) -> Dict:
        """Get knowledge base statistics and rebuild directives."""
        stats = await self._fetch_collection_stats()

        payload: Dict[str, Any] = {
            "collection": self.collection,
            "fresh_start_date": FRESH_START_DATE,
            "staged_documents": STAGED_KNOWLEDGE_COUNTS,
            "recommended_commands": REBUILD_COMMANDS,
            "checked_at": datetime.utcnow().isoformat() + "Z",
        }

        if stats is None:
            payload.update(
                {
                    "status": "unknown",
                    "vectors_count": None,
                    "indexed_vectors": None,
                    "exists": None,
                    "rebuild_required": True,
                    "reason": "Unable to reach Qdrant",
                }
            )
        else:
            vector_count = stats.get("vector_count", 0)
            rebuild_required = (not stats.get("exists", False)) or vector_count <= 0

            payload.update(
                {
                    "status": stats.get("status", "unknown"),
                    "vectors_count": vector_count,
                    "indexed_vectors": stats.get("indexed_vectors", 0),
                    "exists": stats.get("exists", True),
                    "rebuild_required": rebuild_required,
                    "reason": (
                        "Qdrant collection missing"
                        if not stats.get("exists", False)
                        else "Qdrant collection empty" if vector_count <= 0 else None
                    ),
                }
            )

        if payload.get("rebuild_required"):
            reason = payload.get("reason") or "Knowledge base unavailable"
            payload["rebuild_message"] = (
                self._last_rebuild_notice or self._rebuild_message(reason)
            )
        else:
            payload["rebuild_message"] = None

        return payload
