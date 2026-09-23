#!/usr/bin/env python3
import asyncio
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main(url: str) -> None:
    async with streamablehttp_client(url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            expected = {"search_plastics_knowledge", "get_plastic_material", "list_recycling_processes", "check_polymer_compatibility"}
            assert expected <= names, f"Missing tools: {expected - names}"
            result = await session.call_tool("get_plastic_material", {"code": "HDPE"})
            text = "\n".join(block.text for block in result.content if hasattr(block, "text"))
            assert "HDPE" in text and "Injection Molding" in text, text
            print(f"MCP initialize OK; tools={','.join(sorted(names))}; material lookup OK")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8001/mcp"))
