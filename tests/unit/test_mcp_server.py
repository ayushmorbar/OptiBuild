"""Unit tests for the FastMCP server instance setup."""

from mcp.server.fastmcp import FastMCP

from app.mcp_server.server import mcp


def test_mcp_server_instance():
    assert isinstance(mcp, FastMCP)
    assert mcp.name == "gauss-solver"
