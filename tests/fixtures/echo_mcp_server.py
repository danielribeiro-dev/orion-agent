from mcp.server.mcpserver import MCPServer

mcp = MCPServer("echo")


@mcp.tool()
def echo(text: str) -> str:
    """Echo text back."""
    return f"echo:{text}"


@mcp.tool()
def delete_record(id: int) -> str:
    """Delete a record (mutating)."""
    return f"deleted:{id}"


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 2 and sys.argv[1] == "sse":
        mcp.run("sse", host="127.0.0.1", port=int(sys.argv[2]))
    else:
        mcp.run("stdio")
