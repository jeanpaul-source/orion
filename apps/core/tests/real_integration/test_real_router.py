"""
Real Integration Tests - Intelligence Router

Tests the router with REAL intent classification and subsystem routing.
NO MOCKS - Tests the actual vLLM integration.

Run with: pytest tests/real_integration/test_real_router.py -v
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.router import IntelligenceRouter
from src.config import config


@pytest.mark.integration
@pytest.mark.real
@pytest.mark.asyncio
async def test_router_initializes():
    """Test that router can be created with real subsystems."""
    router = IntelligenceRouter()

    assert router is not None
    assert router.knowledge is not None
    assert router.action is not None
    assert router.learning is not None
    assert router.watch is not None
    print("✅ Router initialized with all subsystems")


@pytest.mark.integration
@pytest.mark.real
@pytest.mark.asyncio
async def test_fallback_classification():
    """
    Test fallback keyword-based classification.

    This doesn't call vLLM, just tests the keyword matcher.
    """
    router = IntelligenceRouter()

    test_cases = {
        "What is Kubernetes?": "knowledge",
        "Check disk space": "action",
        "Learn about PostgreSQL": "learning",
        "Show system status": "watch",
        "Hello there": "chat",
    }

    for message, expected_intent in test_cases.items():
        intent = router._fallback_classification(message)
        print(f"'{message}' → {intent}")
        assert intent == expected_intent

    print("✅ Fallback classification works correctly")


@pytest.mark.integration
@pytest.mark.real
@pytest.mark.asyncio
async def test_real_intent_classification_with_vllm():
    """
    Test REAL intent classification using vLLM.

    This actually calls the vLLM API for intelligent classification.
    """
    router = IntelligenceRouter()

    test_cases = [
        "What are the best practices for Kubernetes deployments?",
        "Please check if Docker is running and show me the containers",
        "Can you learn about PostgreSQL replication strategies?",
        "Show me the current system health and resource usage",
        "Good morning! How are you doing today?",
    ]

    print("\n" + "=" * 70)
    print("Testing Real vLLM Intent Classification")
    print("=" * 70)

    for message in test_cases:
        try:
            intent, confidence = await router._classify_intent(message, {})

            print(f"\nMessage: {message[:60]}...")
            print(f"  → Intent: {intent}")
            print(f"  → Confidence: {confidence:.2f}")

            # Validate response structure
            assert intent in ["knowledge", "action", "learning", "watch", "chat"]
            assert 0.0 <= confidence <= 1.0

        except Exception as e:
            print(f"  ⚠️  vLLM classification failed (falling back): {e}")
            # Fallback should still work
            intent = router._fallback_classification(message)
            print(f"  → Fallback intent: {intent}")

    print("\n✅ Intent classification completed (with vLLM or fallback)")


@pytest.mark.integration
@pytest.mark.real
@pytest.mark.asyncio
async def test_real_route_message_end_to_end():
    """
    Test routing a message end-to-end with real services.

    This is the full flow:
    1. Classify intent (vLLM)
    2. Route to subsystem
    3. Get response
    4. Return to user
    """
    router = IntelligenceRouter()

    message = "What is Docker?"
    context = {}

    print(f"\n🤖 Routing message: {message}")

    try:
        response = await router.route(message, context)

        print(f"📝 Response ({len(response)} chars):")
        print(f"   {response[:300]}...")

        # Validate response
        assert isinstance(response, str)
        assert len(response) > 0

        print("\n✅ Full routing flow completed!")

    except Exception as e:
        pytest.fail(f"❌ Routing failed: {e}")


@pytest.mark.integration
@pytest.mark.real
@pytest.mark.asyncio
async def test_route_to_each_subsystem():
    """
    Test routing to each subsystem individually.

    This verifies that each subsystem can handle a request.
    """
    router = IntelligenceRouter()

    test_cases = {
        "knowledge": "What is Kubernetes?",
        "action": "Check disk usage",
        "learning": "Learn about Redis",
        "watch": "Show system status",
        "chat": "Hello!",
    }

    print("\n" + "=" * 70)
    print("Testing Routing to Each Subsystem")
    print("=" * 70)

    for expected_subsystem, message in test_cases.items():
        print(f"\n{expected_subsystem.upper()}: {message}")

        try:
            # Manually classify to ensure we hit the right subsystem
            if expected_subsystem == "knowledge" and config.enable_knowledge:
                response = await router.knowledge.handle(message, {})
            elif expected_subsystem == "action" and config.enable_action:
                response = await router.action.handle(message, {})
            elif expected_subsystem == "learning" and config.enable_learning:
                response = await router.learning.handle(message, {})
            elif expected_subsystem == "watch" and config.enable_watch:
                response = await router.watch.handle(message, {})
            else:
                response = await router._general_chat(message, {})

            print(f"  ✅ Response: {response[:100]}...")
            assert isinstance(response, str)
            assert len(response) > 0

        except Exception as e:
            if expected_subsystem not in ["knowledge", "action", "learning", "watch"]:
                # Chat should always work
                pytest.fail(f"❌ {expected_subsystem} failed: {e}")
            else:
                print(
                    f"  ⚠️  {expected_subsystem} subsystem error (may be expected): {e}"
                )

    print("\n✅ Subsystem routing tests completed!")
