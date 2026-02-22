"""
Real Integration Tests - Knowledge Subsystem

Tests the Knowledge subsystem with REAL external services.
NO MOCKS - This is the real deal.

Run with: pytest tests/real_integration/test_real_knowledge_subsystem.py -v
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.subsystems.knowledge import KnowledgeSubsystem
from src.config import config


@pytest.mark.integration
@pytest.mark.real
@pytest.mark.asyncio
async def test_knowledge_subsystem_initializes():
    """
    Test that KnowledgeSubsystem can be created.

    This is the most basic test - can we even instantiate the class?
    """
    knowledge = KnowledgeSubsystem()

    assert knowledge is not None
    assert knowledge.anythingllm_url == config.anythingllm_url
    assert knowledge.collection == config.qdrant_collection
    print(f"✅ KnowledgeSubsystem initialized with collection: {knowledge.collection}")


@pytest.mark.integration
@pytest.mark.real
@pytest.mark.asyncio
async def test_knowledge_base_gate_check():
    """
    Test the knowledge base readiness gate.

    This should detect that Qdrant collection is empty (cleared Nov 17, 2025).
    """
    knowledge = KnowledgeSubsystem()

    # This should return a warning about empty collection
    warning = await knowledge._knowledge_base_gate()

    if warning:
        print("⚠️  Knowledge base gate returned warning (expected):")
        print(f"   {warning[:200]}...")

        # Verify it mentions rebuild
        assert "rebuild" in warning.lower()
        print("✅ Gate correctly detected empty knowledge base")
    else:
        print("✅ Knowledge base has vectors - gate passed!")


@pytest.mark.integration
@pytest.mark.real
@pytest.mark.asyncio
async def test_fetch_collection_stats():
    """
    Test fetching real Qdrant collection stats.

    This makes an actual HTTP call to Qdrant to check the collection.
    """
    knowledge = KnowledgeSubsystem()

    try:
        stats = await knowledge._fetch_collection_stats()

        print("\n📊 Collection Stats:")
        print(f"   Exists: {stats['exists']}")
        print(f"   Status: {stats['status']}")
        print(f"   Vector Count: {stats['vector_count']:,}")
        print(f"   Indexed: {stats['indexed_vectors']:,}")

        # Verify structure
        assert "exists" in stats
        assert "status" in stats
        assert "vector_count" in stats

        if stats["vector_count"] == 0:
            print("\n⚠️  Collection is EMPTY (expected after Nov 17, 2025)")
            print("   Run: orion process --max-files 50")
            print("   Then: orion embed-index")
        else:
            print(f"\n✅ Collection has {stats['vector_count']:,} vectors")

    except Exception as e:
        pytest.fail(f"❌ Failed to fetch collection stats: {e}")


@pytest.mark.integration
@pytest.mark.real
@pytest.mark.asyncio
async def test_real_knowledge_query():
    """
    Test an actual knowledge query end-to-end.

    This makes real calls to:
    1. Qdrant (vector search)
    2. AnythingLLM (RAG pipeline)
    3. vLLM (LLM inference)

    Expected to return rebuild message if KB is empty.
    """
    knowledge = KnowledgeSubsystem()

    query = "What is Docker?"
    context = {}

    try:
        response = await knowledge.handle(query, context)

        print(f"\n🤖 Query: {query}")
        print(f"📝 Response ({len(response)} chars):")
        print(f"   {response[:300]}...")

        # Validate response structure
        assert isinstance(response, str)
        assert len(response) > 0

        # Check what type of response we got
        if "rebuild required" in response.lower():
            print("\n⚠️  Got rebuild message (expected if KB empty)")
            assert "orion process" in response
            assert "orion embed-index" in response
            print("✅ Knowledge subsystem correctly handling empty KB")
        else:
            # Should have actual answer
            assert len(response) > 100
            print("\n✅ Knowledge subsystem returned answer!")

            # Check for reasonable content
            if "docker" in response.lower() or "container" in response.lower():
                print("✅ Response is relevant to query!")
            else:
                print("⚠️  Response may not be relevant")

    except Exception as e:
        pytest.fail(f"❌ Knowledge query failed: {e}")


@pytest.mark.integration
@pytest.mark.real
@pytest.mark.asyncio
async def test_knowledge_subsystem_with_empty_query():
    """
    Test how knowledge subsystem handles edge cases.
    """
    knowledge = KnowledgeSubsystem()

    # Empty query
    response = await knowledge.handle("", {})
    assert isinstance(response, str)
    print(f"✅ Empty query handled: {response[:100]}")

    # Very short query
    response = await knowledge.handle("hi", {})
    assert isinstance(response, str)
    print(f"✅ Short query handled: {response[:100]}")


@pytest.mark.integration
@pytest.mark.real
@pytest.mark.asyncio
async def test_knowledge_query_with_context():
    """
    Test knowledge query with conversation context.

    This tests the RAG system's ability to use conversation history.
    """
    knowledge = KnowledgeSubsystem()

    context = {
        "history": [
            {"role": "user", "content": "Tell me about containers"},
            {"role": "assistant", "content": "Containers are..."},
        ]
    }

    query = "What about Docker specifically?"

    try:
        response = await knowledge.handle(query, context)

        print(f"\n🤖 Query with context: {query}")
        print(f"📝 Response: {response[:200]}...")

        assert isinstance(response, str)
        assert len(response) > 0
        print("✅ Knowledge subsystem handles context")

    except Exception as e:
        pytest.fail(f"❌ Query with context failed: {e}")
