import os
import logging
<<<<<<< HEAD
from urllib.parse import urlparse
=======
from urllib.parse import urlparse, urlunparse
>>>>>>> 7801ceee (    feat(sec): add secure, self-discovering agent.io integration skill)
from google.adk.models import Gemini
from google.adk.tools.mcp_tool import McpToolset
from agent_io_integration import get_io_mappings

logger = logging.getLogger("agent_io_patch")

# Determine active mappings by discovering the workspace config file
mappings = get_io_mappings()

if mappings:
    # Set placeholder keys to bypass local validation checks since agent.io will handle the actual keys
    if "GOOGLE_MAPS_API_KEY" not in os.environ:
        os.environ["GOOGLE_MAPS_API_KEY"] = "agent_io_secured_placeholder"
    if "GEMINI_API_KEY" not in os.environ:
        os.environ["GEMINI_API_KEY"] = "agent_io_secured_placeholder"

    # ----------------------------------------------------
    # 1. Patch McpToolset.__init__
    # ----------------------------------------------------
    original_mcp_init = McpToolset.__init__

    def patched_mcp_init(self, *args, **kwargs):
        connection_params = kwargs.get("connection_params") or (args[0] if args else None)
        # Use duck-typing to support both StreamableHTTPConnectionParams and SseConnectionParams
        if connection_params and hasattr(connection_params, "url") and hasattr(connection_params, "headers"):
            parsed_url = urlparse(connection_params.url)
            host = parsed_url.hostname
            
            if host in mappings:
                config = mappings[host]
                port = config["port"]
                logger.info(
<<<<<<< HEAD
                    f"[agent.io patch] Redirecting Maps MCP toolset from {connection_params.url} to http://localhost:{port}/mcp"
                )
                connection_params.url = f"http://localhost:{port}/mcp"
=======
                    f"[agent.io patch] Redirecting Maps MCP toolset from {connection_params.url} to local proxy port {port}"
                )
                
                # Dynamic redirect preserving path and query params
                connection_params.url = urlunparse(parsed_url._replace(scheme="http", netloc=f"localhost:{port}"))
>>>>>>> 7801ceee (    feat(sec): add secure, self-discovering agent.io integration skill)
                
                # Dynamically strip headers configured in HCL file
                if connection_params.headers:
                    for header in config.get("applied_headers", []):
                        for k in list(connection_params.headers.keys()):
                            if k.lower() == header.lower():
                                connection_params.headers.pop(k, None)

        original_mcp_init(self, *args, **kwargs)

    McpToolset.__init__ = patched_mcp_init

    # ----------------------------------------------------
    # 2. Patch Gemini.__init__
    # ----------------------------------------------------
    original_gemini_init = Gemini.__init__

    def patched_gemini_init(self, *args, **kwargs):
        base_url = kwargs.get("base_url")
        target = "generativelanguage.googleapis.com"
        
        # Automatically route if target matches maps or base_url is unset/points to live Google API
        if target in mappings and (not base_url or target in base_url):
            config = mappings[target]
            port = config["port"]
            logger.info(
                f"[agent.io patch] Redirecting Gemini model API requests to http://localhost:{port}"
            )
            kwargs["base_url"] = f"http://localhost:{port}"

        original_gemini_init(self, *args, **kwargs)

    Gemini.__init__ = patched_gemini_init
    logger.info(f"Successfully patched ADK. Active agent.io mappings detected: {list(mappings.keys())}")
else:
    logger.info("No active agent.io proxy definitions found in local configuration. Bypassing patch.")
