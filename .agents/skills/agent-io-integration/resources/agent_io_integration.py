import os
import re
import pathlib
import logging
from urllib.parse import urlparse, urlunparse
from google.adk.models import Gemini
from google.adk.tools.mcp_tool import McpToolset

logger = logging.getLogger("agent_io_integration")

def find_workspace_io_hcl() -> pathlib.Path | None:
    """Walks up from the current working directory to find a checked-in io.hcl config file."""
    current = pathlib.Path.cwd().resolve()
    for parent in [current] + list(current.parents):
        hcl_path = parent / "io.hcl"
        if hcl_path.is_file():
            return hcl_path
    return None

def parse_io_hcl_file(hcl_path: pathlib.Path) -> dict[str, dict]:
    """Parses agent.io HCL config to map target domains to local proxy ports and injected headers."""
    mappings = {}
    try:
        content = hcl_path.read_text()
        # Split on "calling " declarations to separate blocks
        blocks = content.split("calling ")
        for block in blocks[1:]:
            target_match = re.search(r'target\s*=\s*"([^"]+)"', block)
            port_match = re.search(r'port\s*=\s*(\d+)', block)
            if target_match and port_match:
                target = target_match.group(1).strip()
                port = int(port_match.group(1).strip())
                
                # Dynamic extraction of apply_header names from the block
                applied_headers = re.findall(r'apply_header\s+"([^"]+)"', block)
                
                mappings[target] = {
                    "port": port,
                    "applied_headers": [h.strip() for h in applied_headers]
                }
    except Exception as e:
        logger.warning(f"Failed to parse agent.io config at {hcl_path}: {e}")
    return mappings

_cached_mappings = None

def get_io_mappings() -> dict[str, dict]:
    """Resolves proxy mappings solely by parsing the discovered workspace io.hcl config file."""
    global _cached_mappings
    if _cached_mappings is not None:
        return _cached_mappings
        
    mappings = {}
    hcl_path = find_workspace_io_hcl()
    if hcl_path:
        logger.info(f"[agent.io] Discovered configuration file: {hcl_path}")
        mappings = parse_io_hcl_file(hcl_path)
                
    _cached_mappings = mappings
    return mappings

# Custom dynamic subclasses:

class AgentIoMcpToolset(McpToolset):
    """McpToolset wrapper that automatically checks and routes through agent.io if configured."""
    def __init__(self, *args, **kwargs):
        connection_params = kwargs.get("connection_params") or (args[0] if args else None)
        # Use duck-typing to support both StreamableHTTPConnectionParams and SseConnectionParams
        if connection_params and hasattr(connection_params, "url") and hasattr(connection_params, "headers"):
            mappings = get_io_mappings()
            parsed_url = urlparse(connection_params.url)
            host = parsed_url.hostname
            
            if host in mappings:
                config = mappings[host]
                port = config["port"]
                logger.info(f"[agent.io] Automatically routing {connection_params.url} through proxy port {port}")
                
                # Dynamic redirect preserving path and query params
                connection_params.url = urlunparse(parsed_url._replace(scheme="http", netloc=f"localhost:{port}"))
                
                # Dynamically strip headers that the proxy is configured to inject
                if connection_params.headers:
                    for header in config.get("applied_headers", []):
                        for k in list(connection_params.headers.keys()):
                            if k.lower() == header.lower():
                                connection_params.headers.pop(k, None)
                                logger.debug(f"[agent.io] Stripped header: {k} (will be injected by proxy)")
                    
        super().__init__(*args, **kwargs)

class AgentIoGemini(Gemini):
    """Gemini client wrapper that automatically checks and routes through agent.io if configured."""
    def __init__(self, *args, **kwargs):
        mappings = get_io_mappings()
        target = "generativelanguage.googleapis.com"
        if target in mappings:
            config = mappings[target]
            port = config["port"]
            logger.info(f"[agent.io] Automatically routing Gemini model requests through proxy port {port}")
            kwargs["base_url"] = f"http://localhost:{port}"
            
        super().__init__(*args, **kwargs)
