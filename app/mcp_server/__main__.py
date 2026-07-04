"""Main entry point for running the stdio MCP server."""

from app.mcp_server.server import mcp

if __name__ == "__main__":
    mcp.run()
