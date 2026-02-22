"""
DevIA Tools Adapter

Bridges ORION Core's ActionSubsystem with DevIA's 46 autonomous tools.
Handles tool discovery, execution, and result formatting.
"""

import logging
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class DevIAToolsAdapter:
    """
    Adapter for DevIA's tool system.

    Provides a clean interface between ORION Core and DevIA's tools
    without directly importing DevIA internals (to avoid import errors).
    """

    def __init__(self):
        """Initialize the DevIA tools adapter."""
        self.tools_registry = None
        self._setup_devops_agent_path()
        self._initialize_tools()

    def _setup_devops_agent_path(self) -> None:
        """Add devops-agent to Python path if not already present."""
        devops_agent_path = Path(__file__).parent.parent.parent.parent / "devops-agent"
        devops_agent_str = str(devops_agent_path)

        if devops_agent_str not in sys.path:
            sys.path.insert(0, devops_agent_str)
            logger.info(f"Added DevIA to path: {devops_agent_str}")

    def _initialize_tools(self) -> None:
        """Initialize DevIA's tools registry."""
        try:
            from devia.tools_registry import ToolRegistry

            self.tools_registry = ToolRegistry()
            logger.info(
                f"Initialized DevIA tools: {len(self.tools_registry.tools)} tools available"
            )
        except ImportError as e:
            logger.error(f"Failed to import DevIA tools registry: {e}")
            logger.warning("Tool execution will be unavailable")
            self.tools_registry = None
        except Exception as e:
            logger.error(f"Failed to initialize DevIA tools: {e}")
            self.tools_registry = None

    def list_tools(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List available tools, optionally filtered by category.

        Args:
            category: Optional category filter (e.g., "git", "docker", "system")

        Returns:
            List of tool metadata dictionaries
        """
        if not self.tools_registry:
            logger.warning("Tools registry not initialized")
            return []

        try:
            tools = []
            for tool_name, tool_func in self.tools_registry.tools.items():
                # Get tool metadata
                tool_meta = {
                    "name": tool_name,
                    "description": tool_func.__doc__ or "No description available",
                    "category": getattr(tool_func, "category", "unknown"),
                }

                # Filter by category if specified
                if category and tool_meta["category"] != category:
                    continue

                tools.append(tool_meta)

            return tools
        except Exception as e:
            logger.error(f"Failed to list tools: {e}")
            return []

    def get_tool_info(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific tool.

        Args:
            tool_name: Name of the tool

        Returns:
            Tool metadata dictionary or None if not found
        """
        if not self.tools_registry:
            return None

        try:
            tool_func = self.tools_registry.tools.get(tool_name)
            if not tool_func:
                return None

            return {
                "name": tool_name,
                "description": tool_func.__doc__ or "No description available",
                "category": getattr(tool_func, "category", "unknown"),
                "signature": (
                    str(tool_func.__annotations__)
                    if hasattr(tool_func, "__annotations__")
                    else "unknown"
                ),
            }
        except Exception as e:
            logger.error(f"Failed to get tool info for {tool_name}: {e}")
            return None

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a DevIA tool with the given arguments.

        Args:
            tool_name: Name of the tool to execute
            arguments: Dictionary of arguments for the tool
            context: Optional execution context (session info, etc.)

        Returns:
            Dictionary with execution results:
            {
                "success": bool,
                "result": str,
                "error": Optional[str],
                "metadata": Dict
            }
        """
        if not self.tools_registry:
            return {
                "success": False,
                "result": "",
                "error": "Tools registry not initialized",
                "metadata": {},
            }

        try:
            # Get the tool function
            tool_func = self.tools_registry.tools.get(tool_name)
            if not tool_func:
                return {
                    "success": False,
                    "result": "",
                    "error": f"Tool '{tool_name}' not found",
                    "metadata": {},
                }

            logger.info(f"Executing tool: {tool_name} with args: {arguments}")

            # Execute the tool
            # Note: DevIA tools are synchronous, so we call them directly
            result = tool_func(**arguments)

            return {
                "success": True,
                "result": str(result),
                "error": None,
                "metadata": {
                    "tool_name": tool_name,
                    "category": getattr(tool_func, "category", "unknown"),
                },
            }

        except TypeError as e:
            logger.error(f"Invalid arguments for tool {tool_name}: {e}")
            return {
                "success": False,
                "result": "",
                "error": f"Invalid arguments: {e}",
                "metadata": {"tool_name": tool_name},
            }

        except Exception as e:
            logger.error(f"Tool execution failed for {tool_name}: {e}")
            return {
                "success": False,
                "result": "",
                "error": str(e),
                "metadata": {"tool_name": tool_name},
            }

    def get_categories(self) -> List[str]:
        """
        Get list of all tool categories.

        Returns:
            List of category names
        """
        if not self.tools_registry:
            return []

        try:
            categories = set()
            for tool_func in self.tools_registry.tools.values():
                category = getattr(tool_func, "category", "unknown")
                categories.add(category)
            return sorted(list(categories))
        except Exception as e:
            logger.error(f"Failed to get categories: {e}")
            return []

    def is_available(self) -> bool:
        """
        Check if tools are available.

        Returns:
            True if tools registry is initialized
        """
        return self.tools_registry is not None

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about available tools.

        Returns:
            Dictionary with tool statistics
        """
        if not self.tools_registry:
            return {
                "available": False,
                "total_tools": 0,
                "categories": [],
                "tools_by_category": {},
            }

        try:
            tools_by_category = {}
            for tool_name, tool_func in self.tools_registry.tools.items():
                category = getattr(tool_func, "category", "unknown")
                if category not in tools_by_category:
                    tools_by_category[category] = []
                tools_by_category[category].append(tool_name)

            return {
                "available": True,
                "total_tools": len(self.tools_registry.tools),
                "categories": self.get_categories(),
                "tools_by_category": tools_by_category,
            }
        except Exception as e:
            logger.error(f"Failed to get tool stats: {e}")
            return {
                "available": False,
                "total_tools": 0,
                "categories": [],
                "tools_by_category": {},
            }
