"""Agent factory for creating and managing CSV conversion agents."""

from typing import Dict, List

from .base_agent import BaseCSVAgent
from .coder_agent import CoderAgent
from .planner_agent import PlannerAgent
from .tester_agent import TesterAgent


class AgentFactory:
    """Factory class for creating and managing CSV conversion agents."""

    def __init__(self):
        self._agents: Dict[str, BaseCSVAgent] = {}

    def get_planner_agent(self) -> PlannerAgent:
        """Get or create the Planner Agent."""
        if "planner" not in self._agents:
            self._agents["planner"] = PlannerAgent()
        return self._agents["planner"]

    def get_coder_agent(self) -> CoderAgent:
        """Get or create the Coder Agent."""
        if "coder" not in self._agents:
            self._agents["coder"] = CoderAgent()
        return self._agents["coder"]

    def get_tester_agent(self) -> TesterAgent:
        """Get or create the Tester Agent."""
        if "tester" not in self._agents:
            self._agents["tester"] = TesterAgent()
        return self._agents["tester"]

    def get_all_agents(self) -> List[BaseCSVAgent]:
        """Get all agents."""
        return [self.get_planner_agent(), self.get_coder_agent(), self.get_tester_agent()]

    def reset_agents(self) -> None:
        """Reset all agents (create new instances)."""
        self._agents.clear()


# Global agent factory instance
agent_factory = AgentFactory()
