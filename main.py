"""
avry-blog Microservice Entry Point
Description: Blog management with real-time interactions
Port: 8089
"""

import uvicorn
from app.main import app  # noqa: F401

if __name__ == "__main__":
    import os

    port = int(os.getenv("PORT", "8089"))
    print(f"\n[*] Starting AVRY-Blog on port {port}...")
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info",
    )
