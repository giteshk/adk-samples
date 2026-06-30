#!/usr/bin/env python3
import os
import pathlib
import subprocess
import time
import sys
from dotenv import load_dotenv

# Ensure we are in the script's directory
os.chdir(pathlib.Path(__file__).parent.absolute())

load_dotenv()

# We need GOOGLE_MAPS_API_KEY and GEMINI_API_KEY
google_maps_key = os.getenv("GOOGLE_MAPS_API_KEY")
gemini_key = os.getenv("GEMINI_API_KEY")

if not google_maps_key or not gemini_key:
    print("Error: GOOGLE_MAPS_API_KEY and GEMINI_API_KEY must be set in your .env file.")
    sys.exit(1)

# Ensure local config directory exists under home directory to avoid Unix socket path limits
local_io_dir = pathlib.Path.home() / ".local-io"
local_io_dir.mkdir(exist_ok=True)

# Write HCL config
hcl_content = f"""calling "google-maps-mcp" {{
  target = "mapstools.googleapis.com"
  port   = 8050
  apply_header "X-Goog-Api-Key" {{
    secret = "google-maps-api-key"
  }}
}}

calling "gemini-api" {{
  target = "generativelanguage.googleapis.com"
  port   = 8051
  apply_header "x-goog-api-key" {{
    secret = "gemini-api-key"
  }}
}}

secret "google-maps-api-key" {{
  value = "{google_maps_key}"
}}

secret "gemini-api-key" {{
  value = "{gemini_key}"
}}
"""

hcl_path = local_io_dir / "io.hcl"
hcl_path.write_text(hcl_content)

print("Starting agent.io proxy...")
# Run io process
io_log = open(local_io_dir / "io.log", "w")
# Locate agent.io license file 
license_path = pathlib.Path.home() / "license.hcl"
if not license_path.is_file():
    license_path = pathlib.Path("license.hcl")

try:
    io_proc = subprocess.Popen(
        ["io", "--home", str(local_io_dir.absolute()), "-c", str(license_path.absolute()), "-c", str(hcl_path.absolute())],
        stdout=io_log,
        stderr=io_log
    )
except FileNotFoundError:
    print("Error: 'io' binary not found on your system path. Please ensure agent.io is installed.")
    sys.exit(1)

# Wait for proxy to start
time.sleep(2.0)

# Check if proxy is running
if io_proc.poll() is not None:
    print("Error: agent.io proxy failed to start. Check ~/.local-io/io.log for details.")
    io_log.close()
    sys.exit(1)

print("agent.io proxy is running on ports 8050 (MCP) and 8051 (Gemini).")

try:
    # Build command to run
    cmd = [".venv/bin/adk"]
    if len(sys.argv) > 1 and sys.argv[1] == "web":
        print("Starting agent in Web UI mode...")
        cmd.extend(["web", "travel_planner_agent"])
        if len(sys.argv) > 2:
            cmd.extend(sys.argv[2:])
    else:
        print("Starting agent in interactive console mode...")
        cmd.extend(["run", "travel_planner_agent"])
        if len(sys.argv) > 1:
            cmd.extend(sys.argv[1:])
    
    # Clear the actual keys from the environment passed to the agent
    agent_env = os.environ.copy()
    agent_env.pop("GOOGLE_MAPS_API_KEY", None)
    agent_env.pop("GEMINI_API_KEY", None)
    
    # Direct agent connections to the agent.io proxy (without exposing keys)
    agent_env["GOOGLE_GEMINI_BASE_URL"] = "http://localhost:8051"
    agent_env["MAPS_MCP_URL"] = "http://localhost:8050/mcp"
    
    subprocess.run(cmd, env=agent_env)
finally:
    print("\nStopping agent.io proxy...")
    io_proc.terminate()
    io_proc.wait()
    io_log.close()
    print("Proxy stopped.")
