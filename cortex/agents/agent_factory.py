"""
AgentFactory is the factory class for Agent, responsible for creating and managing Agents
"""

from typing import Awaitable, Callable

from cortex.agents.base_agent import BaseAgent
from cortex.agents.types import AgentConfig


class AgentFactory:
    """
    AgentFactory is the factory class for Agent, responsible for creating and managing Agents
    """

    agent_make_func: dict[str, Callable[[AgentConfig, str], Awaitable[BaseAgent]]] = {}
    default_agent_configs: dict[str, AgentConfig] = {}

    def list_agents(self) -> list[AgentConfig]:
        """
        Return all registered Agent configurations
        """
        return list(self.default_agent_configs.values())

    def get_default_agent_config(self, name: str) -> AgentConfig:
        """
        Get Agent configuration
        """
        config = self.default_agent_configs.get(name)
        if config is None:
            raise ValueError(
                f"AgentConfig not provided, and no default configuration set for '{name}' in factory"
            )
        return config

    def register_agent(
        self,
        name: str,
        make_agent_func: Callable[[AgentConfig, str], Awaitable[BaseAgent]],
        default_config: AgentConfig | None = None,
    ) -> None:
        """
        Register Agent
        """
        self.agent_make_func[name] = make_agent_func
        if default_config is not None:
            self.default_agent_configs[name] = default_config

    async def make_agent(
        self, name: str, context_id: str, agent_config: AgentConfig | None
    ) -> BaseAgent:
        """
        Create Agent
        """
        if name not in self.agent_make_func:
            raise ValueError(f"Agent {name} not found")
        config = agent_config or self.default_agent_configs.get(name)
        if config is None:
            raise ValueError(
                f"AgentConfig not provided, and no default configuration set for '{name}' in factory"
            )
        make_agent_func = self.agent_make_func[name]
        return await make_agent_func(config, context_id)
