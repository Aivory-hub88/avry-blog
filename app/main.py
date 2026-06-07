"""
AVRY-Blog Service
Blog management with real-time interactions
Port: 8089
"""

import os
import sys
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.config import settings
from app.database.connection import create_pool, close_pool, check_health
from app.database.migrations import run_migrations
from app.seed import seed_welcome_post
from app.routes.posts import router as posts_router
from app.routes.admin import router as admin_router
from app.routes.reactions import router as reactions_router
from app.routes.comments import router as comments_router
from app.websocket.manager import blog_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup/shutdown events."""
    print(f"[{datetime.now().isoformat()}] [STARTUP] AVRY-Blog service starting on port {settings.port}...")
    # Initialize database connection pool and run migrations
    try:
        await create_pool()
        print(f"[{datetime.now().isoformat()}] [STARTUP] Database pool created")
        await run_migrations()
        print(f"[{datetime.now().isoformat()}] [STARTUP] Database migrations applied")
        await seed_welcome_post()
        print(f"[{datetime.now().isoformat()}] [STARTUP] Seed check complete")
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] [WARNING] Database initialization failed: {e}")
    yield
    # Cleanup WebSocket connections and database pool
    await blog_manager.shutdown()
    await close_pool()
    print(f"[{datetime.now().isoformat()}] [SHUTDOWN] AVRY-Blog service shutting down...")


app = FastAPI(
    title="AVRY Blog Service",
    version="1.0.0",
    description="Blog management with real-time interactions",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Register routers
app.include_router(posts_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(reactions_router, prefix="/api")
app.include_router(comments_router, prefix="/api")


@app.get("/health")
async def health():
    """Service health check — verifies database connectivity."""
    db_healthy = await check_health()

    if db_healthy:
        return JSONResponse(
            status_code=200,
            content={
                "status": "healthy",
                "service": "avry-blog",
                "database": "connected",
            },
        )
    else:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "service": "avry-blog",
                "database": "disconnected",
            },
        )


@app.get("/")
async def root():
    """Service info."""
    return {
        "service": "AVRY Blog Service",
        "version": "1.0.0",
    }


@app.websocket("/ws/blog")
async def websocket_blog(websocket: WebSocket):
    """
    WebSocket endpoint for blog real-time updates.

    Clients connect here to receive live notifications about:
    - New posts published
    - Posts hidden
    - Posts edited
    - New comments
    - Reaction count updates
    """
    await blog_manager.connect(websocket)
    try:
        while True:
            # Keep the connection alive by waiting for client messages
            # Clients can send "pong" in response to heartbeat pings
            data = await websocket.receive_text()
            # Client messages are acknowledged but not processed further
    except WebSocketDisconnect:
        blog_manager.disconnect(websocket)
    except Exception:
        blog_manager.disconnect(websocket)
