import json
import httpx
from pathlib import Path
from fastmcp import FastMCP

# Configuration
BACKEND_URL = "http://localhost:9000"
MCP_SERVER_HOST = "0.0.0.0"
MCP_SERVER_PORT = 8000

# Get the directory where this script is located
BASE_DIR = Path(__file__).parent


def load_openapi_spec(file_path: str = "openapi.json") -> dict:
    """Load the OpenAPI specification from file."""
    spec_path = BASE_DIR / file_path
    with open(spec_path, "r") as f:
        return json.load(f)


def create_mcp_server() -> FastMCP:
    """
    Create an MCP server from the OpenAPI specification.

    This function:
    1. Loads the OpenAPI spec (our API blueprint)
    2. Creates an HTTP client to communicate with the backend
    3. Uses FastMCP.from_openapi() to auto-generate MCP tools

    Returns:
        FastMCP: A configured MCP server ready to serve AI agents
    """
    # Load the OpenAPI specification
    openapi_spec = load_openapi_spec()

    # Create an async HTTP client that will make calls to the backend
    # This client is used by the generated MCP tools to call the actual API
    api_client = httpx.AsyncClient(
        base_url=BACKEND_URL,
        timeout=30.0,
        headers={"Content-Type": "application/json"}
    )

    # Create the MCP server from OpenAPI spec
    # FastMCP automatically converts each API endpoint into an MCP tool
    mcp = FastMCP.from_openapi(
        openapi_spec=openapi_spec,
        client=api_client,
        name="Legendary Margherita Pizza MCP Server"
    )

    return mcp


# Create the MCP server instance
mcp = create_mcp_server()


if __name__ == "__main__":
    print("=" * 60)
    print("Legendary Margherita MCP Server")
    print("=" * 60)
    print(f"Backend URL: {BACKEND_URL}")
    print(f"MCP Server: http://{MCP_SERVER_HOST}:{MCP_SERVER_PORT}")
    print("Transport: SSE (Server-Sent Events)")
    print("-" * 60)
    print("Available tools generated from OpenAPI:")
    print("  - get_menu: Get the full pizza menu")
    print("  - place_order: Place a new pizza order")
    print("  - track_order: Track an existing order")
    print("-" * 60)
    print("Waiting for AI agent connections...")
    print("=" * 60)

    # Run with SSE transport for network accessibility
    # AI agents will connect to http://localhost:8000/sse
    mcp.run(
        transport="sse",
        host=MCP_SERVER_HOST,
        port=MCP_SERVER_PORT
    )
