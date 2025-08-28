"""Base agent class for all CrewAI agents in the CSV converter."""

import os
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from crewai import LLM, Agent
from loguru import logger

from core.config import settings


class BaseCSVAgent(ABC):
    """Base class for all CSV conversion agents."""

    def __init__(self, name: str, role: str, goal: str, backstory: str):
        self.name = name
        self.role = role
        self.goal = goal
        self.backstory = backstory
        self._agent: Optional[Agent] = None
        self.logger = logger.bind(agent=name)

    @property
    def agent(self) -> Agent:
        """Get the CrewAI agent instance."""
        if self._agent is None:
            self._agent = self._create_agent()
        return self._agent

    def _create_agent(self) -> Agent:
        """Create the CrewAI agent instance."""
        return Agent(
            role=self.role,
            goal=self.goal,
            backstory=self.backstory,
            verbose=settings.debug,
            allow_delegation=False,
            llm=self._get_llm(),
        )

    def _get_llm(self) -> LLM:
        """Get the language model for the agent."""

        # Get API key from settings or environment
        api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise ValueError(
                "OpenAI API key is required for agent operation. "
                "Please set OPENAI_API_KEY in your .env file or environment variables."
            )

        # Set the environment variable for OpenAI
        os.environ["OPENAI_API_KEY"] = api_key
        temperature = settings.openai_temperature
        if "gpt-5" in settings.openai_model or "o4" in settings.openai_model:
            temperature = 1  # gpt-5 only supports temperature 1

        return LLM(model=f"openai/{settings.openai_model}", temperature=temperature, api_key=api_key)

    @abstractmethod
    async def execute_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the agent's task with the provided data."""
        pass

    def log_execution_start(self, task_description: str) -> None:
        """Log the start of task execution."""
        self.logger.info(f"Starting task: {task_description}")

    def log_execution_end(self, success: bool, details: Optional[str] = None) -> None:
        """Log the end of task execution."""
        status = "completed successfully" if success else "failed"
        message = f"Task {status}"
        if details:
            message += f": {details}"

        if success:
            self.logger.info(message)
        else:
            self.logger.error(message)
