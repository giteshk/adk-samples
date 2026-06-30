package agentio

import (
	"fmt"
	"io/ioutil"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
)

// ProxyConfig represents the port and list of headers configured to be injected by agent.io
type ProxyConfig struct {
	Port           int
	AppliedHeaders []string
}

// FindWorkspaceRoot walks up the directory tree to find the folder containing '.agents'
func FindWorkspaceRoot() (string, error) {
	dir, err := os.Getwd()
	if err != nil {
		return "", err
	}
	for {
		if _, err := os.Stat(filepath.Join(dir, ".agents")); err == nil {
			return dir, nil
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			break
		}
		dir = parent
	}
	return "", fmt.Errorf("workspace root containing '.agents' folder not found")
}

// ParseIoHcl parses a public HCL topology file and maps target hostnames to ProxyConfig
func ParseIoHcl(hclPath string) (map[string]ProxyConfig, error) {
	mappings := make(map[string]ProxyConfig)

	data, err := ioutil.ReadFile(hclPath)
	if err != nil {
		return mappings, err
	}

	// Regular expression to match calling blocks: calling "name" { ... }
	reBlock := regexp.MustCompile(`calling\s+"([^"]+)"\s*\{([^}]+)\}`)
	matches := reBlock.FindAllStringSubmatch(string(data), -1)

	reTarget := regexp.MustCompile(`target\s*=\s*"([^"]+)"`)
	rePort := regexp.MustCompile(`port\s*=\s*(\d+)`)
	reHeader := regexp.MustCompile(`apply_header\s+"([^"]+)"`)

	for _, match := range matches {
		blockContent := match[2]
		targetMatch := reTarget.FindStringSubmatch(blockContent)
		portMatch := rePort.FindStringSubmatch(blockContent)

		if len(targetMatch) > 1 && len(portMatch) > 1 {
			target := strings.TrimSpace(targetMatch[1])
			port, err := strconv.Atoi(strings.TrimSpace(portMatch[1]))
			if err != nil {
				continue
			}

			// Extract all apply_header names inside the block
			headerMatches := reHeader.FindAllStringSubmatch(blockContent, -1)
			headers := []string{}
			for _, hm := range headerMatches {
				headers = append(headers, strings.TrimSpace(hm[1]))
			}

			mappings[target] = ProxyConfig{
				Port:           port,
				AppliedHeaders: headers,
			}
		}
	}

	return mappings, nil
}

var cachedMappings map[string]ProxyConfig

// GetIOMappings resolves proxy mappings by parsing the discovered workspace io.hcl config file
func GetIOMappings() (map[string]ProxyConfig, error) {
	if cachedMappings != nil {
		return cachedMappings, nil
	}

	root, err := FindWorkspaceRoot()
	if err != nil {
		return nil, err
	}

	hclPath := filepath.Join(root, "io.hcl")
	mappings, err := ParseIoHcl(hclPath)
	if err != nil {
		return nil, err
	}

	cachedMappings = mappings
	return mappings, nil
}

// RedirectRequest intercepts and redirects an http.Request to the agent.io proxy if configured in HCL
func RedirectRequest(req *http.Request) {
	mappings, err := GetIOMappings()
	if err != nil || mappings == nil {
		return
	}

	host := req.URL.Hostname()
	if config, exists := mappings[host]; exists {
		// Update URL scheme and host to point to local proxy port, preserving the original path
		req.URL.Scheme = "http"
		req.URL.Host = fmt.Sprintf("localhost:%d", config.Port)

		// Dynamically strip headers that the proxy will inject automatically
		for _, header := range config.AppliedHeaders {
			for k := range req.Header {
				if strings.ToLower(k) == strings.ToLower(header) {
					req.Header.Del(k)
				}
			}
		}
	}
}

// UpdateEnviron updates environment variables (like GOOGLE_GEMINI_BASE_URL, MAPS_MCP_URL)
// based on the discovered HCL config, and sets placeholder API keys.
func UpdateEnviron() {
	mappings, err := GetIOMappings()
	if err != nil || mappings == nil {
		return
	}

	for target, config := range mappings {
		if target == "generativelanguage.googleapis.com" {
			if os.Getenv("GOOGLE_GEMINI_BASE_URL") == "" {
				os.Setenv("GOOGLE_GEMINI_BASE_URL", fmt.Sprintf("http://localhost:%d", config.Port))
			}
			if os.Getenv("GEMINI_API_KEY") == "" {
				os.Setenv("GEMINI_API_KEY", "agent_io_secured_placeholder")
			}
		} else if target == "mapstools.googleapis.com" {
			if os.Getenv("MAPS_MCP_URL") == "" {
				os.Setenv("MAPS_MCP_URL", fmt.Sprintf("http://localhost:%d/mcp", config.Port))
			}
			if os.Getenv("GOOGLE_MAPS_API_KEY") == "" {
				os.Setenv("GOOGLE_MAPS_API_KEY", "agent_io_secured_placeholder")
			}
		}
	}
}

