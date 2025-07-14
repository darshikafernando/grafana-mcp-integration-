"""MCP server implementation for Kubernetes debugging."""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastmcp import FastMCP
from pydantic import BaseModel

from ..config import Settings
from .grafana_mcp_client import GrafanaMCPClient
from .tools import DebugTools

logger = logging.getLogger(__name__)


class PodQuery(BaseModel):
    """Query parameters for pod debugging."""
    
    namespace: str
    pod_name: Optional[str] = None
    label_selector: Optional[str] = None
    time_range: str = "1h"


class MCPServer:
    """MCP server for Kubernetes debugging with Grafana integration."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.grafana_mcp_client = GrafanaMCPClient(settings)
        self.debug_tools = DebugTools(self.grafana_mcp_client, settings)
        self.app = FastMCP("k8s-debugger")
        self._setup_tools()
    
    def _setup_tools(self) -> None:
        """Register MCP tools."""
        
        @self.app.tool()
        async def get_pod_logs(query: PodQuery) -> Dict[str, Any]:
            """Get logs for a specific pod or pods matching criteria."""
            try:
                return await self.debug_tools.get_pod_logs(
                    namespace=query.namespace,
                    pod_name=query.pod_name,
                    label_selector=query.label_selector,
                    time_range=query.time_range
                )
            except Exception as e:
                logger.error(f"Error getting pod logs: {e}")
                return {"error": str(e)}
        
        @self.app.tool()
        async def get_pod_metrics(query: PodQuery) -> Dict[str, Any]:
            """Get metrics for a specific pod or pods matching criteria."""
            try:
                return await self.debug_tools.get_pod_metrics(
                    namespace=query.namespace,
                    pod_name=query.pod_name,
                    label_selector=query.label_selector,
                    time_range=query.time_range
                )
            except Exception as e:
                logger.error(f"Error getting pod metrics: {e}")
                return {"error": str(e)}
        
        @self.app.tool()
        async def get_cluster_events(
            namespace: str = "default",
            time_range: str = "1h"
        ) -> Dict[str, Any]:
            """Get Kubernetes cluster events."""
            try:
                return await self.debug_tools.get_cluster_events(
                    namespace=namespace,
                    time_range=time_range
                )
            except Exception as e:
                logger.error(f"Error getting cluster events: {e}")
                return {"error": str(e)}
        
        @self.app.tool()
        async def correlate_pod_data(query: PodQuery) -> Dict[str, Any]:
            """Correlate logs, metrics, and events for pod debugging."""
            try:
                return await self.debug_tools.correlate_pod_data(
                    namespace=query.namespace,
                    pod_name=query.pod_name,
                    label_selector=query.label_selector,
                    time_range=query.time_range
                )
            except Exception as e:
                logger.error(f"Error correlating pod data: {e}")
                return {"error": str(e)}
        
        @self.app.tool()
        async def get_cloudwatch_events(
            cluster_name: str,
            time_range: str = "1h"
        ) -> Dict[str, Any]:
            """Get EKS events from CloudWatch logs."""
            try:
                return await self.debug_tools.get_cloudwatch_events(
                    cluster_name=cluster_name,
                    time_range=time_range
                )
            except Exception as e:
                logger.error(f"Error getting CloudWatch events: {e}")
                return {"error": str(e)}
        
        @self.app.tool()
        async def get_enhanced_correlation(query: PodQuery) -> Dict[str, Any]:
            """Enhanced correlation including CloudWatch data."""
            try:
                return await self.debug_tools.get_enhanced_correlation(
                    namespace=query.namespace,
                    pod_name=query.pod_name,
                    label_selector=query.label_selector,
                    time_range=query.time_range
                )
            except Exception as e:
                logger.error(f"Error getting enhanced correlation: {e}")
                return {"error": str(e)}
        
        @self.app.tool()
        async def analyze_time_correlation(
            namespace: str,
            pod_name: str,
            time_range: str = "2h",
            window_size: str = "15m"
        ) -> Dict[str, Any]:
            """Analyze data correlation across sliding time windows."""
            try:
                return await self.debug_tools.analyze_time_correlation(
                    namespace=namespace,
                    pod_name=pod_name,
                    time_range=time_range,
                    window_size=window_size
                )
            except Exception as e:
                logger.error(f"Error analyzing time correlation: {e}")
                return {"error": str(e)}
        
        @self.app.tool()
        async def comprehensive_health_check() -> Dict[str, Any]:
            """Perform comprehensive health check of all services."""
            try:
                health_results = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "overall_healthy": True,
                    "services": {}
                }
                
                # Check Grafana MCP
                grafana_health = await self.grafana_mcp_client.health_check()
                health_results["services"]["grafana_mcp"] = grafana_health
                if not grafana_health.get("overall_healthy", False):
                    health_results["overall_healthy"] = False
                
                # Check Kubernetes
                k8s_healthy = self.debug_tools.k8s_client is not None
                health_results["services"]["kubernetes"] = {
                    "connected": k8s_healthy,
                    "details": "Kubernetes API accessible" if k8s_healthy else "Kubernetes API not accessible"
                }
                if not k8s_healthy:
                    health_results["overall_healthy"] = False
                
                # Check CloudWatch
                cw_healthy = self.debug_tools.cloudwatch_client is not None
                health_results["services"]["cloudwatch"] = {
                    "connected": cw_healthy,
                    "details": "CloudWatch client initialized" if cw_healthy else "CloudWatch client not available"
                }
                
                # Add EKS cluster info if available
                if self.settings.eks_cluster_name:
                    health_results["services"]["eks_cluster"] = {
                        "cluster_name": self.settings.eks_cluster_name,
                        "configured": True
                    }
                
                return health_results
                
            except Exception as e:
                logger.error(f"Error performing health check: {e}")
                return {"error": str(e), "overall_healthy": False}
        
        @self.app.tool()
        async def get_system_diagnostics() -> Dict[str, Any]:
            """Get system diagnostics and error information."""
            try:
                from .error_handling import error_aggregator, service_health_checks
                
                diagnostics = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "error_summary": error_aggregator.get_error_summary(),
                    "service_health": {
                        name: {
                            "is_healthy": check.is_healthy,
                            "consecutive_failures": check.consecutive_failures,
                            "last_check": check.last_check.isoformat() if check.last_check else None
                        }
                        for name, check in service_health_checks.items()
                    },
                    "configuration": {
                        "grafana_url": self.settings.grafana_url,
                        "aws_region": self.settings.aws_region,
                        "aws_profile": self.settings.aws_profile,
                        "eks_cluster": self.settings.eks_cluster_name,
                        "query_timeout": self.settings.query_timeout,
                        "max_concurrent_queries": self.settings.max_concurrent_queries
                    }
                }
                
                return diagnostics
                
            except Exception as e:
                logger.error(f"Error getting system diagnostics: {e}")
                return {"error": str(e)}
    
    async def start(self) -> None:
        """Start the MCP server."""
        logger.info("Starting K8s Debugger MCP Server")
        
        # Connect to Grafana MCP server first
        try:
            await self.grafana_mcp_client.connect()
            logger.info("Connected to Grafana MCP server")
        except Exception as e:
            logger.error(f"Failed to connect to Grafana MCP server: {e}")
            # Continue anyway, some functionality may still work
        
        await self.app.run()
    
    async def stop(self) -> None:
        """Stop the MCP server."""
        logger.info("Stopping K8s Debugger MCP Server")
        
        # Disconnect from Grafana MCP server
        try:
            await self.grafana_mcp_client.disconnect()
            logger.info("Disconnected from Grafana MCP server")
        except Exception as e:
            logger.error(f"Error disconnecting from Grafana MCP server: {e}")
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()