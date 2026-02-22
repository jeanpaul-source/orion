"""
ORION Subsystems

The four core subsystems that ORION coordinates:
- Knowledge: RAG-based question answering
- Action: Tool execution and task completion
- Learning: Self-teaching and knowledge harvesting
- Watch: System monitoring and health checks
"""

from .knowledge import KnowledgeSubsystem
from .action import ActionSubsystem
from .learning import LearningSubsystem
from .watch import WatchSubsystem

__all__ = [
    "KnowledgeSubsystem",
    "ActionSubsystem",
    "LearningSubsystem",
    "WatchSubsystem",
]
