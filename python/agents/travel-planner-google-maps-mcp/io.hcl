# io.hcl (Checked into Repository / Topology Configuration)
#
# This file defines the outbound calling targets and local proxy ports for agent.io.
# It contains NO secret keys and is safe to be read by the agent process or checked into Git.
#
# Note: Keep the actual API keys in a separate, gitignored 'secrets.hcl' file.

calling "google-maps-mcp" {
  target = "mapstools.googleapis.com"
  port   = 8050
  apply_header "X-Goog-Api-Key" {
    secret = "google-maps-api-key"
  }
}

calling "gemini-api" {
  target = "generativelanguage.googleapis.com"
  port   = 8051
  apply_header "x-goog-api-key" {
    secret = "gemini-api-key"
  }
}
