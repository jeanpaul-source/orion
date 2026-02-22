"""
Action Subsystem - Powered by DevOps Agent

Handles task execution, tool calls, and system operations.
Integrates with DevIA's 46 tools, agentic planning, and 5 memory systems.

This subsystem delegates all action execution to the DevOps Agent,
providing access to:
- 46 autonomous tools (Git, Docker, K8s, databases, testing, logs, system)
- Agentic loop (planning, execution, reflection)
- 5 memory systems (episodic, semantic, procedural, short-term, learning)
- vLLM integration (GPU-accelerated inference)
- ORION RAG integration (knowledge base queries)

Author: ORION Project
Date: November 17, 2025
"""

import logging
import asyncio
from typing import Dict
from pathlib import Path
import sys

# Add DevOps Agent to path
devops_agent_path = Path(__file__).parent.parent.parent.parent / "devops-agent"
if str(devops_agent_path) not in sys.path:
    sys.path.insert(0, str(devops_agent_path))

try:
    from devia.agent import DevOpsAgent
    from devia.agentic_loop import AgenticLoop
    from devia.task_planner import TaskPlanner
    from devia.reflection_engine import ReflectionEngine
    from devia.config import DeviaConfig
    from devia.grounded_memory import AntiDriftMemory

    DEVOPS_AVAILABLE = True
except ImportError as e:
    DEVOPS_AVAILABLE = False
    IMPORT_ERROR = str(e)

logger = logging.getLogger(__name__)

# Import DevIA tools adapter
try:
    from src.adapters.devia_tools import DevIAToolsAdapter

    TOOLS_ADAPTER_AVAILABLE = True
except ImportError as e:
    TOOLS_ADAPTER_AVAILABLE = False
    logger.warning(f"DevIA tools adapter not available: {e}")


class ActionSubsystem:
    """
    Action subsystem powered by DevOps Agent.

    Provides access to 46 tools through agentic autonomous execution:
    - Git operations (clone, commit, push, diff, log, etc.)
    - Docker management (ps, logs, restart, compose)
    - Kubernetes operations (get, describe, logs, exec)
    - Database queries (PostgreSQL, MySQL, MongoDB, Redis)
    - System monitoring (disk, memory, CPU, network, processes)
    - Testing (pytest, unit tests, integration tests)
    - Log analysis (grep, tail, parsing, correlation)

    Example tasks:
    - "Check disk usage on all NVMe drives and recommend cleanup"
    - "Find all Docker containers using more than 2GB RAM"
    - "Show me the last 100 lines of nginx error logs and analyze issues"
    - "Run pytest on the API module and summarize failures"
    - "Check if PostgreSQL is running and show connection count"
    """

    def __init__(self):
        """Initialize Action subsystem with DevOps Agent integration."""
        self.devops_available = DEVOPS_AVAILABLE
        self.agent = None
        self.agentic_loop = None
        self.tools_adapter = None

        # Initialize DevIA tools adapter
        if TOOLS_ADAPTER_AVAILABLE:
            try:
                self.tools_adapter = DevIAToolsAdapter()
                logger.info(
                    f"Initialized DevIA tools adapter: {self.tools_adapter.get_stats()}"
                )
            except Exception as e:
                logger.error(f"Failed to initialize tools adapter: {e}")
                self.tools_adapter = None

        if not DEVOPS_AVAILABLE:
            logger.error(
                f"DevOps Agent not available: {IMPORT_ERROR}. "
                "Action subsystem will have limited functionality."
            )
            return

        try:
            # Initialize DevOps Agent with host profile (GPU available)
            # CRITICAL: Configure DevIA to use vLLM instead of Ollama
            # We don't have Ollama running - we use vLLM at vllm:8000
            import os

            os.environ["DEVIA_PROFILE"] = "host"
            os.environ["DEVIA_VLLM_URL"] = "http://vllm:8000/v1"
            os.environ["DEVIA_OLLAMA_HOST"] = (
                "http://vllm:8000"  # Fallback if tool caller tries Ollama
            )
            # PHASE 1: Enable tool calling through DevIA
            os.environ["DEVIA_ENABLE_TOOL_CALLING"] = "true"

            self.config = DeviaConfig(
                profile="host",
                enable_tool_calling=True,  # Enable tools!
            )

            # Force vLLM preference in case env vars didn't apply
            self.config.prefer_vllm = True
            self.config.vllm_url = "http://vllm:8000/v1"
            self.config.ollama_host = (
                "http://vllm:8000"  # Point Ollama references to vLLM
            )

            # Initialize agent
            self.agent = DevOpsAgent(self.config)

            # Initialize agentic components (DevOpsAgent uses .llm, not .llm_client)
            task_planner = TaskPlanner(self.agent.llm)
            reflection_engine = ReflectionEngine(self.agent.llm)

            # Initialize anti-drift memory for agentic loop
            memory = AntiDriftMemory()

            # Create agentic loop (using correct parameter names)
            self.agentic_loop = AgenticLoop(
                agent=self.agent,
                task_planner=task_planner,
                reflection_engine=reflection_engine,
                memory=memory,
            )

            # Mark as successfully initialized
            self.devops_available = True

            logger.info(
                "Action subsystem initialized with DevOps Agent "
                "(46 tools, agentic loop, 5 memory systems)"
            )

        except Exception:
            logger.exception("Failed to initialize DevOps Agent")
            self.devops_available = False

    async def handle(self, task: str, context: Dict) -> str:
        """
        Execute user task using DevOps Agent's agentic capabilities.

        Delegates to agentic loop for:
        - Task planning (multi-step decomposition)
        - Tool selection (46 tools available)
        - Execution with retries
        - Memory storage (episodic + procedural + semantic)
        - Self-reflection and learning
        - Comprehensive reporting

        Args:
            task: Natural language task description
            context: Conversation context

        Returns:
            Task execution result (formatted for user)

        Examples:
            >>> action = ActionSubsystem()
            >>> result = await action.handle(
            ...     "Check disk usage on nvme2 and recommend cleanup",
            ...     context={}
            ... )
            >>> print(result)
            ✅ EXECUTION COMPLETE
            Step 1: Check disk usage on /mnt/nvme2 [✅ COMPLETED]
            Step 2: Analyze usage patterns [✅ COMPLETED]
            Step 3: Query ORION for cleanup best practices [✅ COMPLETED]
            Step 4: Generate recommendations [✅ COMPLETED]

            Recommendations:
            - Delete Docker build cache (saves 12GB)
            - Archive old log files (saves 8GB)
            ...
        """
        logger.info(f"Action task: {task}")

        # Fallback if DevOps Agent not available
        if not self.devops_available:
            return self._fallback_handler(task, context)

        try:
            # Execute task using agentic loop
            # Run in executor to avoid blocking async event loop
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self.agentic_loop.execute_autonomous_task,
                task,
                False,  # dry_run=False
            )

            # Format result for ORION UI
            formatted = self._format_result(result)

            logger.info(
                f"Action completed: {result.steps_completed}/{len(result.plan.steps)} "
                f"steps in {result.total_time:.1f}s"
            )

            return formatted

        except Exception as e:
            logger.exception("Action subsystem error")
            return f"❌ I encountered an error executing that task: {str(e)}\n\nPlease try rephrasing your request or breaking it into smaller steps."

    def _format_result(self, result) -> str:
        """
        Format AgenticResult for ORION UI display.

        Converts DevOps Agent's detailed execution report into
        user-friendly format suitable for web chat.

        Args:
            result: AgenticResult from agentic loop

        Returns:
            Formatted string for display
        """
        lines = []

        # Status header
        if result.success:
            lines.append("✅ **Task Completed Successfully**\n")
        else:
            lines.append("⚠️ **Task Completed with Errors**\n")

        # Execution summary
        lines.append(f"**Duration:** {result.total_time:.1f}s")
        lines.append(
            f"**Steps:** {result.steps_completed}/{len(result.plan.steps)} completed\n"
        )

        # Step-by-step results
        lines.append("### Execution Steps\n")
        for i, step_result in enumerate(result.results, 1):
            status = "✅" if step_result.success else "❌"
            lines.append(f"{status} **Step {i}:** {step_result.step.name}")

            # Show output (truncate if too long)
            if step_result.output:
                output = step_result.output.strip()
                if len(output) > 500:
                    output = output[:500] + "...\n*(output truncated)*"
                lines.append(f"```\n{output}\n```")

            # Show errors
            if not step_result.success and step_result.step.error:
                lines.append(f"*Error:* {step_result.step.error}")

            lines.append("")

        # Lessons learned (from reflection engine)
        if result.lessons_learned:
            lines.append("### 💡 Lessons Learned\n")
            for lesson in result.lessons_learned:
                lines.append(f"- {lesson}")
            lines.append("")

        # Recommendations
        if result.recommendations:
            lines.append("### 📋 Recommendations\n")
            for rec in result.recommendations:
                lines.append(f"- {rec}")
            lines.append("")

        return "\n".join(lines)

    def _fallback_handler(self, task: str, context: Dict) -> str:
        """
        Fallback handler when DevOps Agent is not available.

        Provides basic guidance to user.

        Args:
            task: User's task
            context: Conversation context

        Returns:
            Fallback message
        """
        return f"""⚠️ **DevOps Agent Not Available**

I understand you want me to: *{task}*

However, the DevOps Agent (which powers my action capabilities) is not currently available.

**To fix this:**
1. Ensure DevOps Agent is installed: `cd applications/devops-agent && pip install -e .`
2. Verify dependencies are available
3. Check logs for initialization errors

**Alternative:**
You can use the DevOps Agent directly via CLI:
```bash
devia query "{task}"
```

Would you like me to help with something else, or provide information from my knowledge base instead?
"""

    async def get_capabilities(self) -> Dict:
        """
        Get available capabilities and tools.

        Returns:
            Dict with tool counts, categories, and availability status
        """
        if not self.devops_available or not self.agent:
            return {
                "available": False,
                "reason": "DevOps Agent not initialized",
                "tools": 0,
                "categories": [],
            }

        try:
            # Get tool registry from agent
            tools = self.agent.tools_registry.get_all_tools()

            return {
                "available": True,
                "tools": len(tools),
                "categories": [
                    "git",
                    "docker",
                    "kubernetes",
                    "database",
                    "system",
                    "testing",
                    "logs",
                ],
                "features": [
                    "Agentic planning",
                    "Multi-step execution",
                    "Reflection and learning",
                    "5 memory systems",
                    "vLLM integration",
                    "ORION RAG queries",
                ],
            }

        except Exception as e:
            logger.error(f"Failed to get capabilities: {e}")
            return {
                "available": False,
                "reason": str(e),
                "tools": 0,
                "categories": [],
            }

    async def cleanup(self):
        """Clean up resources (agent, memory systems)."""
        if self.agent:
            # DevOps Agent cleanup (if needed)
            logger.info("Action subsystem cleanup complete")
