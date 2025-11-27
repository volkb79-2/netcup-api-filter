#!/usr/bin/env python3
"""
Startup script for Playwright Standalone Service

Runs both the WebSocket server (port 3000) and MCP server (port 8765)
concurrently in the same container.

Environment Variables:
    WS_PORT: WebSocket server port (default: 3000)
    MCP_ENABLED: Enable MCP server (default: true)
    MCP_PORT: MCP server port (default: 8765)
    
Author: netcup-api-filter project
Date: 2025-11-26
"""

import asyncio
import logging
import os
import signal
import sys
from typing import List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
MCP_ENABLED = os.getenv('MCP_ENABLED', 'true').lower() == 'true'
MCP_PORT = int(os.getenv('MCP_PORT', '8765'))
WS_PORT = int(os.getenv('WS_PORT', '3000'))


async def run_ws_server():
    """Run WebSocket server."""
    logger.info(f"Starting WebSocket server on port {WS_PORT}...")
    
    # Import here to avoid circular imports
    from ws_server import PlaywrightWebSocketServer
    
    server = PlaywrightWebSocketServer()
    await server.start()


async def run_mcp_server():
    """Run MCP server using uvicorn."""
    logger.info(f"Starting MCP server on port {MCP_PORT}...")
    
    import uvicorn
    from mcp_server import mcp
    
    # Get the Starlette app from FastMCP
    app = mcp.streamable_http_app()
    
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=MCP_PORT,
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    """Main entry point - runs both servers."""
    logger.info("=" * 60)
    logger.info("Playwright Standalone Service Starting")
    logger.info("=" * 60)
    logger.info(f"WebSocket server: ws://0.0.0.0:{WS_PORT}")
    if MCP_ENABLED:
        logger.info(f"MCP server: http://0.0.0.0:{MCP_PORT}")
    else:
        logger.info("MCP server: disabled")
    logger.info("=" * 60)
    
    # Create tasks for each server
    tasks: List[asyncio.Task] = []
    
    # Always run WebSocket server
    tasks.append(asyncio.create_task(run_ws_server()))
    
    # Optionally run MCP server
    if MCP_ENABLED:
        tasks.append(asyncio.create_task(run_mcp_server()))
    
    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_event_loop()
    
    def signal_handler():
        logger.info("Received shutdown signal, stopping services...")
        for task in tasks:
            task.cancel()
    
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)
    
    try:
        # Wait for all tasks
        await asyncio.gather(*tasks, return_exceptions=True)
    except asyncio.CancelledError:
        logger.info("Services cancelled")
    except Exception as e:
        logger.error(f"Error running services: {e}")
        sys.exit(1)
    finally:
        logger.info("Playwright Standalone Service stopped")


if __name__ == "__main__":
    asyncio.run(main())
