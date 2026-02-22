"""
ORION Core - Main Application

The unified AI entity for homelab management.
Runs entirely on lab host, accessible via web UI.

Author: ORION Project
Date: November 17, 2025
"""

import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn
from pathlib import Path
import uuid

from .config import config
from .conversation import ConversationManager
from .router import IntelligenceRouter
from .request_queue import request_queue, Priority
from . import metrics
from . import dashboard_api
from fastapi.responses import Response

# AI Toolkit Tracing Integration
from .tracing import setup_tracing, instrument_fastapi

# Telegram Bot (optional)
try:
    from .integrations.telegram_bot import TelegramBot

    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    TelegramBot = None

# Setup logging
logging.basicConfig(
    level=getattr(logging, config.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# Application lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting ORION Core...")
    logger.info(config.get_summary())

    # Initialize AI Toolkit tracing
    app.state.tracer = setup_tracing(
        service_name="orion-core",
        service_version=config.version,
        otlp_endpoint=config.tracing_endpoint,
        enable=config.enable_tracing,
    )
    if app.state.tracer:
        logger.info("🔍 AI Toolkit tracing enabled")

    # Initialize components
    app.state.conversation_manager = ConversationManager()
    app.state.router = IntelligenceRouter()

    # Initialize metrics
    metrics.set_build_info(config.version, config.environment)
    logger.info("Metrics initialized")

    # Initialize Telegram Bot (if enabled)
    app.state.telegram_bot = None
    if config.telegram_enabled:
        if not TELEGRAM_AVAILABLE:
            logger.error("Telegram bot enabled but python-telegram-bot not installed!")
            logger.error("Install with: pip install python-telegram-bot>=20.0")
        elif not config.telegram_bot_token:
            logger.error("Telegram bot enabled but ORION_TELEGRAM_BOT_TOKEN not set!")
        elif not config.telegram_allowed_users:
            logger.warning("Telegram bot enabled but no allowed users configured!")
            logger.warning("Set ORION_TELEGRAM_ALLOWED_USERS=[user_id1,user_id2,...]")
        else:
            try:
                if TelegramBot is not None:
                    logger.info("Initializing Telegram bot...")
                    app.state.telegram_bot = TelegramBot(
                        token=config.telegram_bot_token,
                        allowed_user_ids=config.telegram_allowed_users,
                        router=app.state.router,
                        conversation_manager=app.state.conversation_manager,
                    )
                    await app.state.telegram_bot.start()
                    logger.info("✅ Telegram bot started successfully!")
            except Exception:
                logger.exception("Failed to start Telegram bot")
                app.state.telegram_bot = None

    logger.info("ORION Core started successfully!")

    yield

    # Cleanup
    logger.info("Shutting down ORION Core...")

    # Stop Telegram bot
    if app.state.telegram_bot:
        try:
            logger.info("Stopping Telegram bot...")
            await app.state.telegram_bot.stop()
            logger.info("Telegram bot stopped")
        except Exception:
            logger.exception("Error stopping Telegram bot")


# Create FastAPI app
app = FastAPI(
    title=config.app_name,
    version=config.version,
    description="Unified AI Entity for Homelab Management",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instrument FastAPI with AI Toolkit tracing
instrument_fastapi(app, service_name="orion-core")

# Mount static files (web UI)
web_dir = Path(__file__).parent.parent / "web"
if web_dir.exists():
    app.mount("/static", StaticFiles(directory=str(web_dir / "static")), name="static")


# ============================================================================
# WEB UI ROUTES
# ============================================================================


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve hybrid chat + monitoring UI."""
    hybrid_path = web_dir / "index-hybrid.html"
    if hybrid_path.exists():
        with open(hybrid_path) as f:
            return HTMLResponse(content=f.read())
    else:
        return HTMLResponse(
            content="<h1>ORION Core</h1><p>Hybrid UI not found. Please check installation.</p>"
        )


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Serve legacy dashboard UI."""
    dashboard_path = web_dir / "dashboard.html"
    if dashboard_path.exists():
        with open(dashboard_path) as f:
            return HTMLResponse(content=f.read())
    else:
        return HTMLResponse(
            content="<h1>ORION Dashboard</h1><p>Dashboard UI not found.</p>"
        )


@app.get("/chat/simple", response_class=HTMLResponse)
async def chat_ui():
    """Serve simple chat interface."""
    index_path = web_dir / "index.html"
    if index_path.exists():
        with open(index_path) as f:
            return HTMLResponse(content=f.read())
    else:
        return HTMLResponse(content="<h1>ORION Chat</h1><p>Chat UI not found.</p>")


# ============================================================================
# API ROUTES
# ============================================================================


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "app": config.app_name,
        "version": config.version,
        "environment": config.environment,
    }


@app.get("/metrics")
async def prometheus_metrics():
    """
    Prometheus metrics endpoint.

    Returns metrics in Prometheus text format for scraping.
    """
    metrics_data, content_type = metrics.get_metrics()
    return Response(content=metrics_data, media_type=content_type)


@app.get("/api/status")
async def get_status(request: Request):
    """Get comprehensive dashboard status (for dashboard UI)."""
    return await dashboard_api.get_dashboard_status(request)


@app.get("/api/hybrid/status")
async def get_hybrid_status(request: Request):
    """Get status in format for hybrid UI sidebar."""
    # Get base status from dashboard API
    base_status = await dashboard_api.get_dashboard_status(request)

    # Transform to hybrid UI format
    services = base_status.get("services", {})
    resources = base_status.get("resources", {})

    # Format services for hybrid UI
    hybrid_services = {}

    # vLLM service
    vllm = services.get("vllm", {})
    gpu_data = resources.get("gpu", {})
    gpu_percent = int(gpu_data.get("percent", 0))
    hybrid_services["vllm"] = {
        "state": vllm.get("status", "unknown"),
        "value": f"⚡ {gpu_percent}% GPU",
    }

    # Qdrant service
    qdrant = services.get("qdrant", {})
    vector_count = qdrant.get("vectors")
    qdrant_state = qdrant.get("status", "unknown")

    if isinstance(vector_count, (int, float)) and vector_count > 0:
        qdrant_value = f"⚡ {vector_count:,.0f} vectors"
    elif isinstance(vector_count, str) and vector_count.strip():
        qdrant_value = f"⚡ {vector_count}"
    else:
        qdrant_value = "⚠️ Rebuild required"
        if qdrant_state == "healthy":
            qdrant_state = "warning"

    hybrid_services["qdrant"] = {
        "state": qdrant_state,
        "value": qdrant_value,
    }

    # GPU temperature
    gpu_temp = gpu_data.get("temperature")
    hybrid_services["gpu"] = {
        "state": (
            "healthy"
            if gpu_temp and gpu_temp < 80
            else "warning" if gpu_temp else "unknown"
        ),
        "value": f"🌡️ {gpu_temp}°C" if gpu_temp else "🌡️ N/A",
    }

    # Disk usage
    disk_data = resources.get("disk", {})
    disk_percent = int(disk_data.get("percent", 0))
    hybrid_services["disk"] = {
        "state": "healthy" if disk_percent < 80 else "warning",
        "value": f"💾 {disk_percent}% used",
    }

    # Format metrics for hybrid UI
    def format_bytes(bytes_val):
        """Format bytes to human readable."""
        if bytes_val == 0:
            return "0 B"
        units = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        while bytes_val >= 1024 and i < len(units) - 1:
            bytes_val /= 1024
            i += 1
        return f"{bytes_val:.1f} {units[i]}"

    hybrid_metrics = {}

    # GPU metric
    if gpu_data:
        hybrid_metrics["gpu"] = {"percent": gpu_percent, "text": f"{gpu_percent}%"}

    # Disk metric
    if disk_data:
        disk_total = disk_data.get("total", 0)
        disk_used = disk_data.get("used", 0)
        hybrid_metrics["disk"] = {
            "percent": disk_percent,
            "text": f"{format_bytes(disk_used)} / {format_bytes(disk_total)}",
            "drives": disk_data.get("drives", []),  # Pass through drive details
        }

    # Memory metric
    memory_data = resources.get("memory", {})
    if memory_data:
        mem_percent = int(memory_data.get("percent", 0))
        mem_total = memory_data.get("total", 0)
        mem_used = memory_data.get("used", 0)
        hybrid_metrics["memory"] = {
            "percent": mem_percent,
            "text": f"{format_bytes(mem_used)} / {format_bytes(mem_total)}",
        }

    # Get alerts from watch subsystem
    router = request.app.state.router
    alerts_list = []
    try:
        watch_alerts = await router.watch.get_alerts(active_only=True, limit=5)
        for alert in watch_alerts:
            alerts_list.append(
                {
                    "level": alert.get("severity", "info"),
                    "icon": "⚠️" if alert.get("severity") == "warning" else "❌",
                    "message": alert.get("message", ""),
                    "time": alert.get("time", "Just now"),
                }
            )
    except Exception as e:
        logger.debug(f"Could not get alerts: {e}")

    # Recent activity
    recent_activity = [
        {"time": "Just now", "text": "Metrics updated"},
        {"time": "2m ago", "text": "System health check"},
    ]

    # Add conversation stats if available
    conv_manager = request.app.state.conversation_manager
    if conv_manager:
        stats = conv_manager.get_stats()
        if stats.get("active_sessions", 0) > 0:
            recent_activity.insert(
                1,
                {
                    "time": "Now",
                    "text": f"{stats['active_sessions']} active chat session(s)",
                },
            )

    return {
        "services": hybrid_services,
        "metrics": hybrid_metrics,
        "alerts": alerts_list,
        "recent_activity": recent_activity,
    }


@app.get("/api/user")
async def get_user(request: Request):
    """Get current user information from Authelia headers."""
    return await dashboard_api.get_user_info(request)


@app.get("/api/knowledge/stats")
async def get_knowledge_stats(request: Request):
    """Get knowledge base statistics."""
    router = request.app.state.router

    stats = await router.knowledge.get_knowledge_stats()

    return stats


@app.get("/api/tools")
async def list_tools(request: Request, category: str = None):
    """
    List available DevIA tools.

    Query Parameters:
        category: Optional category filter (e.g., "git", "docker", "system")

    Returns:
        {
            "available": bool,
            "total_tools": int,
            "tools": [
                {
                    "name": str,
                    "description": str,
                    "category": str
                }
            ]
        }
    """
    router = request.app.state.router
    action_subsystem = router.action

    if (
        not hasattr(action_subsystem, "tools_adapter")
        or not action_subsystem.tools_adapter
    ):
        return {
            "available": False,
            "total_tools": 0,
            "tools": [],
            "error": "DevIA tools adapter not initialized",
        }

    adapter = action_subsystem.tools_adapter
    tools_list = adapter.list_tools(category=category)

    return {
        "available": adapter.is_available(),
        "total_tools": len(tools_list),
        "tools": tools_list,
    }


@app.get("/api/tools/{tool_name}")
async def get_tool_info(request: Request, tool_name: str):
    """
    Get detailed information about a specific tool.

    Path Parameters:
        tool_name: Name of the tool

    Returns:
        {
            "name": str,
            "description": str,
            "category": str,
            "signature": str
        }
    """
    router = request.app.state.router
    action_subsystem = router.action

    if (
        not hasattr(action_subsystem, "tools_adapter")
        or not action_subsystem.tools_adapter
    ):
        return {"error": "DevIA tools adapter not initialized"}

    adapter = action_subsystem.tools_adapter
    tool_info = adapter.get_tool_info(tool_name)

    if not tool_info:
        return {"error": f"Tool '{tool_name}' not found"}

    return tool_info


@app.get("/api/tools/categories")
async def list_tool_categories(request: Request):
    """
    List all tool categories.

    Returns:
        {
            "categories": List[str]
        }
    """
    router = request.app.state.router
    action_subsystem = router.action

    if (
        not hasattr(action_subsystem, "tools_adapter")
        or not action_subsystem.tools_adapter
    ):
        return {"categories": [], "error": "DevIA tools adapter not initialized"}

    adapter = action_subsystem.tools_adapter
    return {"categories": adapter.get_categories()}


@app.get("/api/queue/stats")
async def get_queue_stats():
    """Get request queue statistics."""
    return request_queue.get_stats()


@app.get("/api/conversations/stats")
async def get_conversation_stats(request: Request):
    """Get conversation manager statistics."""
    manager = request.app.state.conversation_manager
    return manager.get_stats()


@app.get("/api/learning/status")
async def get_learning_status(request: Request):
    """Get learning queue status and statistics."""
    router = request.app.state.router
    status = await router.learning.get_learning_status()
    return status


@app.get("/api/learning/pending")
async def get_learning_pending(request: Request):
    """List all pending learning requests."""
    router = request.app.state.router
    pending = await router.learning.list_pending()
    return {"pending_requests": pending}


@app.post("/api/learning/complete")
async def mark_learning_complete(
    request: Request,
    topic: str,
    papers_found: int = 0,
    docs_found: int = 0,
):
    """
    Mark a learning request as completed.

    Used by automation (n8n workflows) to update status after harvesting.

    Args:
        topic: Topic that was learned
        papers_found: Number of papers harvested
        docs_found: Number of docs harvested

    Returns:
        Success status
    """
    router = request.app.state.router
    success = await router.learning.mark_completed(topic, papers_found, docs_found)

    if success:
        return {"status": "success", "topic": topic}
    else:
        return {"status": "error", "message": f"Learning request not found: {topic}"}


@app.post("/api/learning/fail")
async def mark_learning_failed(request: Request, topic: str, error: str):
    """
    Mark a learning request as failed.

    Used by automation (n8n workflows) when harvesting fails.

    Args:
        topic: Topic that failed
        error: Error message

    Returns:
        Success status
    """
    router = request.app.state.router
    success = await router.learning.mark_failed(topic, error)

    if success:
        return {"status": "success", "topic": topic}
    else:
        return {"status": "error", "message": f"Learning request not found: {topic}"}


@app.get("/api/watch/alerts")
async def get_watch_alerts(request: Request, active_only: bool = True, limit: int = 50):
    """
    Get system alerts.

    Args:
        active_only: Only return active alerts (default: True)
        limit: Maximum number of alerts (default: 50)

    Returns:
        List of alerts
    """
    router = request.app.state.router
    alerts = await router.watch.get_alerts(active_only=active_only, limit=limit)
    return {"alerts": alerts, "count": len(alerts)}


@app.post("/api/watch/alerts/{alert_id}/acknowledge")
async def acknowledge_watch_alert(request: Request, alert_id: str):
    """
    Acknowledge an alert.

    Args:
        alert_id: Alert ID to acknowledge

    Returns:
        Success status
    """
    router = request.app.state.router
    success = await router.watch.acknowledge_alert(alert_id)

    if success:
        return {"status": "success", "alert_id": alert_id}
    else:
        return {"status": "error", "message": f"Alert not found: {alert_id}"}


@app.post("/api/watch/thresholds")
async def set_watch_threshold(request: Request, metric: str, value: float):
    """
    Update an alert threshold.

    Args:
        metric: Metric name (e.g., "cpu_percent", "gpu_temperature")
        value: New threshold value

    Returns:
        Success status
    """
    router = request.app.state.router
    router.watch.set_threshold(metric, value)

    return {
        "status": "success",
        "metric": metric,
        "value": value,
        "thresholds": router.watch.thresholds,
    }


@app.get("/api/watch/gpu")
async def get_gpu_status(request: Request):
    """
    Get detailed GPU status.

    Returns:
        GPU metrics and status
    """
    router = request.app.state.router
    gpu_status = await router.watch._check_gpu()
    return gpu_status


# ============================================================================
# WEBSOCKET CHAT
# ============================================================================


@app.websocket("/chat")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket endpoint for real-time chat with ORION.

    Protocol:
    - Client sends: JSON {"message": "user message", "stream": true/false}
    - Server sends: JSON {"response": "orion response", "type": "message"} (non-streaming)
    - Server sends: JSON {"type": "progress", "message": "..."} (streaming)
    - Server sends: JSON {"type": "token", "content": "..."} (streaming)
    - Server sends: JSON {"type": "complete", ...} (streaming metadata)
    - Server sends: JSON {"type": "debug_breadcrumb", "data": {...}} (for debugging)
    - Server sends: JSON {"type": "debug_analysis", "data": {...}} (on errors)
    """
    await websocket.accept()

    # Create or resume session
    session_id = str(uuid.uuid4())
    conversation_manager = websocket.app.state.conversation_manager
    router = websocket.app.state.router

    session = conversation_manager.get_session(session_id)

    # Register WebSocket for debug tracking
    router.debug_tracker.add_ws_client(websocket)

    logger.info(f"WebSocket connected: session {session_id} (debug tracking enabled)")

    # Send welcome message
    welcome = """👋 Hello! I'm ORION, your AI homelab assistant.

I have access to:
- 📚 Technical knowledge base (RAG)
- 🛠️  Comprehensive system control tools
- 🧠 Self-learning capabilities
- 📊 Real-time monitoring

Ask me anything about your homelab, or request tasks in natural language!"""

    await websocket.send_json({"response": welcome, "type": "welcome"})

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            user_message = data.get("message", "")
            enable_streaming = data.get("stream", True)  # Default to streaming

            if not user_message:
                continue

            logger.info(
                f"User [{session_id}]: {user_message} (stream={enable_streaming})"
            )

            # Add to conversation history
            session.add_message("user", user_message)

            # Prepare context
            context = {
                "session_id": session_id,
                "history": session.get_history(limit=10),
            }

            # Route with or without streaming
            if enable_streaming:
                # Streaming mode - send progress and tokens in real-time
                response_buffer = []
                try:
                    async for chunk in router.route_streaming(user_message, context):
                        # Forward all chunks to client
                        await websocket.send_json(chunk)

                        # Buffer tokens for history
                        if chunk.get("type") == "token":
                            response_buffer.append(chunk["content"])

                    # Combine buffered response for history
                    full_response = "".join(response_buffer)
                    session.add_message("assistant", full_response)
                    logger.info(
                        f"ORION [{session_id}] streamed: {len(full_response)} chars"
                    )

                except Exception as e:
                    logger.exception("Streaming error")
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": f"❌ I encountered an error: {str(e)}",
                        }
                    )
                    session.add_message("assistant", f"Error: {str(e)}")

            else:
                # Non-streaming mode (backward compatible)
                try:
                    response = await request_queue.enqueue(
                        request_id=f"{session_id}-{uuid.uuid4().hex[:8]}",
                        handler=router.route,
                        args=(user_message, context),
                        priority=Priority.NORMAL,
                        session_id=session_id,
                    )
                except ValueError as e:
                    # Queue full (backpressure)
                    response = (
                        "⚠️ I'm currently handling a lot of requests. "
                        "Please try again in a moment.\n\n"
                        f"({str(e)})"
                    )
                except RuntimeError as e:
                    # Execution failed
                    response = f"❌ I encountered an error: {str(e)}"

                # Add response to history
                session.add_message("assistant", response)

                logger.info(f"ORION [{session_id}]: {response[:100]}")

                # Send response to client
                await websocket.send_json({"response": response, "type": "message"})

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: session {session_id}")
        conversation_manager.end_session(session_id)
        router.debug_tracker.remove_ws_client(websocket)

    except Exception as e:
        logger.exception("WebSocket error")
        router.debug_tracker.remove_ws_client(websocket)
        try:
            await websocket.send_json(
                {
                    "response": f"I encountered an error: {str(e)}",
                    "type": "error",
                }
            )
        except Exception:
            # WebSocket already closed, nothing we can do
            pass


# ============================================================================
# DEVELOPMENT ENDPOINTS
# ============================================================================


@app.get("/api/dev/routes")
async def list_routes():
    """List all API routes (development only)."""
    routes = []
    for route in app.routes:
        if hasattr(route, "path") and hasattr(route, "name"):
            route_info = {
                "path": getattr(route, "path", ""),
                "methods": (
                    list(getattr(route, "methods", []))
                    if hasattr(route, "methods")
                    else []
                ),
                "name": getattr(route, "name", ""),
            }
            routes.append(route_info)
    return {"routes": routes}


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=config.host,
        port=config.port,
        reload=config.environment == "development",
        log_level=config.log_level.lower(),
    )
