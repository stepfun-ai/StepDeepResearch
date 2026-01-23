import argparse
import asyncio
import logging

from agentkit.trace import LocalStorageTracer
from cortex.agents.agent_factory import AgentFactory
from cortex.orchestrator.orchestrator import Orchestrator
from cortex.server.http_server import HttpServer
from demo.dr_agent.dr_agent import get_dr_agent_config, make_dr_agent

logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="Deep Research Agent Server")
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="Server port (default: 8001)",
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    
    agent_factory = AgentFactory()
    agent_factory.register_agent(
        name="DeepResearchAgent",
        make_agent_func=make_dr_agent,
        default_config=get_dr_agent_config(),
    )
    orch = Orchestrator(agent_factory)
    tracer = LocalStorageTracer(storage_dir="./traces")
    http_server = HttpServer(orch, tracer=tracer)
    
    logger.info(f"Starting server on port={args.port}")
    print(
        f"Demo server started: http://localhost:{args.port} (press Ctrl+C to stop)",
        flush=True,
    )
    await http_server.start(port=args.port)


if __name__ == "__main__":
    asyncio.run(main())
