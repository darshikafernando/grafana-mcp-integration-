"""High-level pod debugging interface."""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.table import Table
from rich.text import Text

from .mcp_client import MCPClient

logger = logging.getLogger(__name__)


class PodDebugger:
    """High-level interface for pod debugging operations."""
    
    def __init__(self, mcp_client: MCPClient):
        self.client = mcp_client
        self.console = Console()
    
    async def debug_pod(
        self,
        namespace: str,
        pod_name: str,
        time_range: str = "1h",
        show_logs: bool = True,
        show_metrics: bool = True,
        show_events: bool = True
    ) -> Dict[str, Any]:
        """Debug a specific pod with comprehensive data collection."""
        self.console.print(f"[bold blue]Debugging pod {pod_name} in namespace {namespace}[/bold blue]")
        
        # Get correlated data
        result = await self.client.correlate_pod_data(
            namespace=namespace,
            pod_name=pod_name,
            time_range=time_range
        )
        
        if "error" in result:
            self.console.print(f"[bold red]Error: {result['error']}[/bold red]")
            return result
        
        # Display results
        await self._display_debug_results(result, show_logs, show_metrics, show_events)
        
        return result
    
    async def debug_by_labels(
        self,
        namespace: str,
        label_selector: str,
        time_range: str = "1h"
    ) -> Dict[str, Any]:
        """Debug pods matching a label selector."""
        self.console.print(f"[bold blue]Debugging pods with labels {label_selector} in namespace {namespace}[/bold blue]")
        
        result = await self.client.correlate_pod_data(
            namespace=namespace,
            label_selector=label_selector,
            time_range=time_range
        )
        
        if "error" in result:
            self.console.print(f"[bold red]Error: {result['error']}[/bold red]")
            return result
        
        await self._display_debug_results(result)
        
        return result
    
    async def analyze_namespace(
        self,
        namespace: str,
        time_range: str = "1h"
    ) -> Dict[str, Any]:
        """Analyze all activity in a namespace."""
        self.console.print(f"[bold blue]Analyzing namespace {namespace}[/bold blue]")
        
        # Get namespace-wide data
        tasks = [
            self.client.get_pod_logs(namespace=namespace, time_range=time_range),
            self.client.get_pod_metrics(namespace=namespace, time_range=time_range),
            self.client.get_cluster_events(namespace=namespace, time_range=time_range)
        ]
        
        logs_result, metrics_result, events_result = await asyncio.gather(*tasks)
        
        result = {
            "namespace": namespace,
            "time_range": time_range,
            "logs": logs_result,
            "metrics": metrics_result,
            "events": events_result
        }
        
        await self._display_namespace_analysis(result)
        
        return result
    
    async def _display_debug_results(
        self,
        result: Dict[str, Any],
        show_logs: bool = True,
        show_metrics: bool = True,
        show_events: bool = True
    ) -> None:
        """Display debugging results in a formatted way."""
        
        # Display summary
        if "summary" in result:
            self._display_summary(result["summary"])
        
        # Display events
        if show_events and "events" in result and "events" in result["events"]:
            self._display_events(result["events"]["events"])
        
        # Display metrics summary
        if show_metrics and "metrics" in result:
            self._display_metrics_summary(result["metrics"])
        
        # Display log summary
        if show_logs and "logs" in result:
            self._display_logs_summary(result["logs"])
    
    async def _display_namespace_analysis(self, result: Dict[str, Any]) -> None:
        """Display namespace analysis results."""
        self.console.print(f"\n[bold green]Namespace Analysis: {result['namespace']}[/bold green]")
        
        # Display events
        if "events" in result["events"]:
            self._display_events(result["events"]["events"])
        
        # Display metrics and logs summaries
        self._display_metrics_summary(result["metrics"])
        self._display_logs_summary(result["logs"])
    
    def _display_summary(self, summary: Dict[str, Any]) -> None:
        """Display debug summary."""
        table = Table(title="Debug Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="magenta")
        
        table.add_row("Log Entries", str(summary.get("log_entries", 0)))
        table.add_row("Error Logs", str(summary.get("error_logs", 0)))
        table.add_row("Warning Events", str(summary.get("warning_events", 0)))
        table.add_row("Error Events", str(summary.get("error_events", 0)))
        table.add_row("High CPU Usage", "Yes" if summary.get("high_cpu_usage") else "No")
        table.add_row("High Memory Usage", "Yes" if summary.get("high_memory_usage") else "No")
        
        self.console.print(table)
    
    def _display_events(self, events: List[Dict[str, Any]]) -> None:
        """Display Kubernetes events."""
        if not events:
            self.console.print("[yellow]No events found[/yellow]")
            return
        
        table = Table(title="Kubernetes Events")
        table.add_column("Time", style="cyan")
        table.add_column("Type", style="magenta")
        table.add_column("Reason", style="green")
        table.add_column("Object", style="blue")
        table.add_column("Message", style="white")
        
        for event in events[-10:]:  # Show last 10 events
            event_time = event.get("first_timestamp", "")
            if event_time:
                event_time = datetime.fromisoformat(event_time.replace('Z', '+00:00')).strftime("%H:%M:%S")
            
            event_type = event.get("type", "")
            color = "red" if event_type == "Warning" else "green"
            
            table.add_row(
                event_time,
                Text(event_type, style=color),
                event.get("reason", ""),
                f"{event.get('object', {}).get('kind', '')}/{event.get('object', {}).get('name', '')}",
                event.get("message", "")[:50] + "..." if len(event.get("message", "")) > 50 else event.get("message", "")
            )
        
        self.console.print(table)
    
    def _display_metrics_summary(self, metrics_result: Dict[str, Any]) -> None:
        """Display metrics summary."""
        if "error" in metrics_result:
            self.console.print(f"[red]Metrics Error: {metrics_result['error']}[/red]")
            return
        
        metrics = metrics_result.get("metrics", {})
        if not metrics:
            self.console.print("[yellow]No metrics data available[/yellow]")
            return
        
        self.console.print("\n[bold green]Metrics Summary[/bold green]")
        for metric_name, metric_data in metrics.items():
            if isinstance(metric_data, dict) and "error" in metric_data:
                self.console.print(f"  {metric_name}: [red]Error - {metric_data['error']}[/red]")
            elif isinstance(metric_data, list):
                self.console.print(f"  {metric_name}: {len(metric_data)} series")
            else:
                self.console.print(f"  {metric_name}: Available")
    
    def _display_logs_summary(self, logs_result: Dict[str, Any]) -> None:
        """Display logs summary."""
        if "error" in logs_result:
            self.console.print(f"[red]Logs Error: {logs_result['error']}[/red]")
            return
        
        logs = logs_result.get("logs", [])
        if not logs:
            self.console.print("[yellow]No log data available[/yellow]")
            return
        
        total_entries = sum(len(stream.get("values", [])) for stream in logs)
        self.console.print(f"\n[bold green]Logs Summary[/bold green]")
        self.console.print(f"  Total log streams: {len(logs)}")
        self.console.print(f"  Total log entries: {total_entries}")
        
        # Show recent log entries
        if logs and len(logs) > 0 and "values" in logs[0]:
            self.console.print("\n[bold cyan]Recent Log Entries:[/bold cyan]")
            for entry in logs[0]["values"][-5:]:  # Show last 5 entries
                if len(entry) >= 2:
                    timestamp = datetime.fromtimestamp(int(entry[0]) / 1e9).strftime("%H:%M:%S")
                    message = entry[1][:100] + "..." if len(entry[1]) > 100 else entry[1]
                    self.console.print(f"  {timestamp}: {message}")
    
    async def get_historical_data(
        self,
        namespace: str,
        pod_name: str,
        days_back: int = 7
    ) -> Dict[str, Any]:
        """Get historical data for terminated pods."""
        time_range = f"{days_back}d"
        
        self.console.print(f"[bold blue]Getting historical data for {pod_name} ({days_back} days)[/bold blue]")
        
        return await self.client.correlate_pod_data(
            namespace=namespace,
            pod_name=pod_name,
            time_range=time_range
        )