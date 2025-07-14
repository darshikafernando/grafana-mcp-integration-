"""MCP client for communicating with the K8s Debugger server."""

import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class MCPRequest(BaseModel):
    """MCP request model."""
    method: str
    params: Dict[str, Any]


class MCPResponse(BaseModel):
    """MCP response model."""
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class MCPClient:
    """Client for communicating with the K8s Debugger MCP server."""
    
    def __init__(self, server_url: str, timeout: float = 30.0):
        self.server_url = server_url.rstrip('/')
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(timeout))
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    async def _call_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Call a tool on the MCP server."""
        try:
            response = await self.client.post(
                f"{self.server_url}/tools/{tool_name}",
                json=kwargs
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error calling {tool_name}: {e.response.status_code}")
            return {"error": f"HTTP {e.response.status_code}: {e.response.text}"}
        except Exception as e:
            logger.error(f"Error calling {tool_name}: {e}")
            return {"error": str(e)}
    
    async def get_pod_logs(
        self,
        namespace: str,
        pod_name: Optional[str] = None,
        label_selector: Optional[str] = None,
        time_range: str = "1h"
    ) -> Dict[str, Any]:
        """Get logs for pods."""
        return await self._call_tool(
            "get_pod_logs",
            namespace=namespace,
            pod_name=pod_name,
            label_selector=label_selector,
            time_range=time_range
        )
    
    async def get_pod_metrics(
        self,
        namespace: str,
        pod_name: Optional[str] = None,
        label_selector: Optional[str] = None,
        time_range: str = "1h"
    ) -> Dict[str, Any]:
        """Get metrics for pods."""
        return await self._call_tool(
            "get_pod_metrics",
            namespace=namespace,
            pod_name=pod_name,
            label_selector=label_selector,
            time_range=time_range
        )
    
    async def get_cluster_events(
        self,
        namespace: str = "default",
        time_range: str = "1h"
    ) -> Dict[str, Any]:
        """Get cluster events."""
        return await self._call_tool(
            "get_cluster_events",
            namespace=namespace,
            time_range=time_range
        )
    
    async def correlate_pod_data(
        self,
        namespace: str,
        pod_name: Optional[str] = None,
        label_selector: Optional[str] = None,
        time_range: str = "1h"
    ) -> Dict[str, Any]:
        """Get correlated pod debugging data."""
        return await self._call_tool(
            "correlate_pod_data",
            namespace=namespace,
            pod_name=pod_name,
            label_selector=label_selector,
            time_range=time_range
        )
    
    async def health_check(self) -> bool:
        """Check if the MCP server is healthy."""
        try:
            response = await self.client.get(f"{self.server_url}/health")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False