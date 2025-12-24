import asyncio
import logging
import uuid

import uvicorn
from agentkit.trace import SpanContext, Tracer
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.websockets import WebSocket
from pydantic import ValidationError
from starlette.middleware.base import BaseHTTPMiddleware

from cortex.agents.types import AgentConfig
from cortex.orchestrator.orchestrator import Orchestrator, OrchMode
from cortex.orchestrator.types import AgentEvent, AgentEventType
from cortex.server.channel.ws_channel import WebSocketChannel
from cortex.server.log.log import setup_logging
from cortex.server.log.trace import set_trace_id

setup_logging()
logger = logging.getLogger(__name__)


def extract_and_set_trace_id(headers: dict) -> str:
    """
    Extract x-step-trace from headers, auto-generate UUID if not present,
    and set it to ContextVar

    Args:
        headers: HTTP headers dict

    Returns:
        trace_id string
    """
    trace_id = headers.get("Step-Trace-ID")
    if not trace_id:
        trace_id = str(uuid.uuid4())

    set_trace_id(trace_id)
    return trace_id


class TraceMiddleware(BaseHTTPMiddleware):
    """Extract x-step-trace from HTTP header and inject into log context, auto-generate if not present"""

    async def dispatch(self, request: Request, call_next):
        # Use unified function to extract and set trace_id
        extract_and_set_trace_id(request.headers)
        response = await call_next(request)
        return response


class HttpServer:
    orch: Orchestrator
    tracer: Tracer

    def __init__(self, orch: Orchestrator, tracer: Tracer):
        self.orch = orch
        self.tracer = tracer

    async def start(self, host: str = "0.0.0.0", port: int = 8001) -> None:
        app = self._build_app()
        logger.info("Starting HTTP server, listening on 0.0.0.0:8001")
        # Configure uvicorn to use Python logging
        server_config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_config=None,  # Disable uvicorn default log config
            access_log=True,  # Enable access log
        )
        await uvicorn.Server(server_config).serve()

    def _build_app(self) -> FastAPI:
        app = FastAPI(title="Agent Server")

        # Add CORS middleware, support cross-origin requests from any domain
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # Allow all domains
            allow_credentials=True,
            allow_methods=["*"],  # Allow all HTTP methods
            allow_headers=["*"],  # Allow all request headers
        )

        # Add Trace middleware to extract trace_id from x-step-trace header and inject into log
        app.add_middleware(TraceMiddleware)

        @app.get("/agents")
        async def list_agents() -> list[AgentConfig]:
            return self.orch.list_agents()

        @app.websocket("/multi/ws/{agent_name}/{context_id}")
        async def multi_call(websocket: WebSocket, agent_name: str, context_id: str):
            await websocket_handler(websocket, agent_name, context_id, OrchMode.MULTI)

        @app.websocket("/single/ws/{agent_name}/{context_id}")
        async def single_call(websocket: WebSocket, agent_name: str, context_id: str):
            await websocket_handler(websocket, agent_name, context_id, OrchMode.SINGLE)

        @app.post("/multi/sse/{agent_name}/{context_id}")
        async def multi_call_sse(agent_name: str, context_id: str, request: AgentEvent):
            return StreamingResponse(
                sse_handler(
                    agent_name, context_id, OrchMode.MULTI, request
                ),  # Async generator (core)
                media_type="text/event-stream",  # SSE response type
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    # Cross-origin support (needed if frontend and backend have different domains)
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Credentials": "true",
                },
            )

        @app.post("/single/sse/{agent_name}/{context_id}")
        async def single_call_sse(
            agent_name: str, context_id: str, request: AgentEvent
        ):
            return StreamingResponse(
                sse_handler(
                    agent_name, context_id, OrchMode.SINGLE, request
                ),  # Async generator (core)
                media_type="text/event-stream",  # SSE response type
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    # Cross-origin support (needed if frontend and backend have different domains)
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Credentials": "true",
                },
            )

        async def websocket_handler(
            websocket: WebSocket, agent_name: str, context_id: str, mode: OrchMode
        ):
            # Use unified function to extract and set trace_id from headers
            extract_and_set_trace_id(websocket.headers)

            await websocket.accept()

            channel = WebSocketChannel(websocket)
            task_id = str(uuid.uuid4())
            request = AgentEvent.model_validate(await channel.receive())
            if request.task_id is None:
                request.task_id = task_id
            if request.type != AgentEventType.REQUEST:
                raise ValueError("first event type must be request")

            async def send_to_agent_loop():
                while True:
                    try:
                        data = await channel.receive()
                        event = AgentEvent.model_validate(data)
                        await self.orch.send_event(event)
                    except ValidationError as e:
                        logger.error(f"Pydantic validation error: {e}")
                        continue

            async def send_to_client_loop():
                ctx = SpanContext(tracer=self.tracer, app_name=agent_name)
                with ctx.span(name=f"orchestrator_{agent_name}_{context_id}"):
                    async for event in self.orch.run(
                        agent_name, request, request.request.config, mode, context_id
                    ):
                        logger.warning(f'event: {event.model_dump()}')
                        await channel.send(event.model_dump())

            agent_task = asyncio.create_task(
                send_to_client_loop(), name="send_to_client_loop"
            )
            recv_task = asyncio.create_task(
                send_to_agent_loop(), name="send_to_agent_loop"
            )

            done, pending = await asyncio.wait(
                [recv_task, agent_task], return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                logger.info(f"Cancelling pending task: {task.get_name()}")
                task.cancel()

            for task in done:
                try:
                    task.result()
                    logger.info(f"Completed task: {task.get_name()}")
                except Exception as e:
                    logger.error(f"Task error in {task.get_name()}: {e}", exc_info=True)

            await channel.close()
            logger.info("WebSocket connection closed")

        async def sse_handler(
            agent_name: str, context_id: str, mode: OrchMode, request: AgentEvent
        ):
            ctx = SpanContext(tracer=self.tracer, app_name=agent_name)
            with ctx.span(name=f"http_sse_handler_{agent_name}_{context_id}"):
                config = None
                if request.request is not None:
                    config = request.request.config
                async for event in self.orch.run(
                    agent_name, request, config, mode, context_id
                ):
                    yield f"data: {event.model_dump_json()}\n\n"

        @app.get("/health")
        async def health_check() -> dict[str, str]:
            return {"status": "ok"}

        return app
