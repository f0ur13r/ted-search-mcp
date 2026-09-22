"""MCP entry point for ChatGPT and local clients."""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from ted_api import search_ted

mcp = FastMCP(
    "TED Search",
    instructions=(
        "Use search_ted_notices to find public procurement notices. "
        "For network-security screening, search broadly, then assess the returned "
        "titles and descriptions semantically. This server is read-only."
    ),
    stateless_http=True,
    json_response=True,
)


@mcp.tool()
def search_ted_notices(
    date_from: str,
    date_to: str,
    country: str | None = None,
    cpv_codes: list[str] | None = None,
    free_text_query: str | None = None,
    max_results: int = 50,
) -> dict:
    """Search published TED notices and return normalized tender data.

    Args:
        date_from: Inclusive publication start date in YYYY-MM-DD format.
        date_to: Inclusive publication end date in YYYY-MM-DD format.
        country: Optional three-letter place-of-performance code, e.g. DEU.
        cpv_codes: Optional CPV codes or prefixes, e.g. ["32420000", "72*"].
        free_text_query: Optional literal full-text search phrase, e.g. "firewall".
        max_results: Maximum notices to return, from 1 to 250.
    """
    return search_ted(
        date_from=date_from,
        date_to=date_to,
        country=country,
        cpv_codes=cpv_codes,
        free_text_query=free_text_query,
        max_results=max_results,
    )


app = mcp.streamable_http_app()


if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)
