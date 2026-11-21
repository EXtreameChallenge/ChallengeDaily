"""Compatibility entrypoint for the MCP server.

The implementation lives in ``integrations/mcp_server.py`` after B34.
"""
from legacy_aliases import install

install()

from integrations.mcp_server import main  # noqa: E402


if __name__ == "__main__":
    main()
