"""Client for communicating with the official Grafana MCP server."""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ..config import Settings
from .error_handling import (
    retry_with_exponential_backoff,
    with_timeout,
    handle_service_error,
    ErrorContext
)

logger = logging.getLogger(__name__)


class GrafanaMCPClient:
    """Client for communicating with the official Grafana MCP server."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.session: Optional[ClientSession] = None
        self._server_params = None
        self.is_connected = False
    
    async def __aenter__(self):
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()
    
    async def connect(self) -> None:
        """Connect to the Grafana MCP server."""
        try:
            # Configure the official Grafana MCP server parameters
            self._server_params = StdioServerParameters(
                command="mcp-grafana",
                args=["-t", "stdio"],
                env={
                    "GRAFANA_URL": self.settings.grafana_url,
                    "GRAFANA_API_KEY": self.settings.grafana_key
                }
            )
            
            # Start the server and create session
            stdio_server = stdio_client(self._server_params)
            self.session = await stdio_server.__aenter__()
            
            # Initialize the session
            await self.session.initialize()
            
            self.is_connected = True
            logger.info("Connected to Grafana MCP server")
            
        except Exception as e:
            logger.error(f"Failed to connect to Grafana MCP server: {e}")
            self.is_connected = False
            raise
    
    async def disconnect(self) -> None:
        """Disconnect from the Grafana MCP server."""
        if self.session:
            try:
                await self.session.close()
                self.is_connected = False
                logger.info("Disconnected from Grafana MCP server")
            except Exception as e:
                logger.error(f"Error disconnecting from Grafana MCP server: {e}")
    
    @retry_with_exponential_backoff(max_attempts=3)
    @with_timeout(30.0)
    @handle_service_error("grafana_mcp", "query")
    async def _call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool on the Grafana MCP server."""
        if not self.is_connected or not self.session:
            raise Exception("Not connected to Grafana MCP server")
        
        async with ErrorContext(f"grafana_mcp_tool_{tool_name}"):
            try:
                result = await self.session.call_tool(tool_name, arguments)
                return result.content[0].text if result.content else {}
            except Exception as e:
                logger.error(f"Error calling Grafana MCP tool {tool_name}: {e}")
                raise
    
    async def query_loki(
        self,
        query: str,
        start_time: str,
        end_time: str,
        limit: int = 1000
    ) -> Dict[str, Any]:
        """Query Loki logs via Grafana MCP server."""
        arguments = {
            "query": query,
            "start": start_time,
            "end": end_time,
            "limit": limit
        }
        
        try:
            result = await self._call_tool("loki_query", arguments)
            # Parse the result if it's a string
            if isinstance(result, str):
                return json.loads(result)
            return result
        except Exception as e:
            logger.error(f"Error querying Loki: {e}")
            return {"error": str(e)}
    
    async def query_prometheus(
        self,
        query: str,
        start_time: str,
        end_time: str,
        step: str = "30s"
    ) -> Dict[str, Any]:
        """Query Prometheus metrics via Grafana MCP server."""
        arguments = {
            "query": query,
            "start": start_time,
            "end": end_time,
            "step": step
        }
        
        try:
            result = await self._call_tool("prometheus_query", arguments)
            # Parse the result if it's a string
            if isinstance(result, str):
                return json.loads(result)
            return result
        except Exception as e:
            logger.error(f"Error querying Prometheus: {e}")
            return {"error": str(e)}
    
    async def get_datasources(self) -> List[Dict[str, Any]]:
        """Get list of configured data sources via Grafana MCP server."""
        try:
            result = await self._call_tool("list_datasources", {})
            # Parse the result if it's a string
            if isinstance(result, str):
                return json.loads(result)
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.error(f"Error getting datasources: {e}")
            return []
    
    async def get_dashboards(self) -> List[Dict[str, Any]]:
        """Get list of dashboards via Grafana MCP server."""
        try:
            result = await self._call_tool("list_dashboards", {})
            # Parse the result if it's a string
            if isinstance(result, str):
                return json.loads(result)
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.error(f"Error getting dashboards: {e}")
            return []
    
    async def search_dashboards(self, query: str) -> List[Dict[str, Any]]:
        """Search dashboards via Grafana MCP server."""
        arguments = {"query": query}
        
        try:
            result = await self._call_tool("search_dashboards", arguments)
            # Parse the result if it's a string
            if isinstance(result, str):
                return json.loads(result)
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.error(f"Error searching dashboards: {e}")
            return []
    
    async def get_alerts(self) -> List[Dict[str, Any]]:
        """Get alerts via Grafana MCP server."""
        try:
            result = await self._call_tool("get_alerts", {})
            # Parse the result if it's a string
            if isinstance(result, str):
                return json.loads(result)
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.error(f"Error getting alerts: {e}")
            return []
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check via Grafana MCP server."""
        health_status = {
            "grafana_mcp_connected": self.is_connected,
            "grafana_api": False,
            "datasources_available": False,
            "overall_healthy": False,
            "checks_performed": datetime.utcnow().isoformat(),
            "details": {}
        }
        
        if not self.is_connected:
            health_status["details"]["connection"] = "Not connected to Grafana MCP server"
            return health_status
        
        try:
            # Test basic connectivity by listing datasources
            datasources = await self.get_datasources()
            health_status["grafana_api"] = True
            health_status["datasources_available"] = len(datasources) > 0
            health_status["details"]["grafana_api"] = "Connected successfully"
            health_status["details"]["datasources"] = f"Found {len(datasources)} datasource(s)"
            
            # Check for specific datasource types
            loki_sources = [ds for ds in datasources if ds.get("type") == "loki"]
            prom_sources = [ds for ds in datasources if ds.get("type") == "prometheus"]
            
            health_status["details"]["loki_datasources"] = len(loki_sources)
            health_status["details"]["prometheus_datasources"] = len(prom_sources)
            
        except Exception as e:
            health_status["details"]["grafana_api"] = f"Failed: {str(e)}"
        
        # Overall health
        health_status["overall_healthy"] = (
            health_status["grafana_mcp_connected"] and 
            health_status["grafana_api"] and
            health_status["datasources_available"]
        )
        
        return health_status
    
    async def get_available_tools(self) -> List[Dict[str, Any]]:
        """Get list of available tools from Grafana MCP server."""
        if not self.is_connected or not self.session:
            return []
        
        try:
            tools = await self.session.list_tools()
            return [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema
                }
                for tool in tools.tools
            ]
        except Exception as e:
            logger.error(f"Error getting available tools: {e}")
            return []