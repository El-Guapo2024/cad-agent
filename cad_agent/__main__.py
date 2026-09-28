import sys

from .mcp_app import main

if __name__ == "__main__":
    if "--version" in sys.argv:
        import build123d
        from .mcp_app import mcp
        import asyncio
        n = len(asyncio.run(mcp.list_tools()))
        from .render import backend_status
        print(f"cad-agent 0.1.0  build123d {build123d.__version__}  tools {n}  render: {backend_status()}")
    else:
        main()
