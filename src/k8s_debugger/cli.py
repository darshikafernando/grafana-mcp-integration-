"""Command-line interface for K8s Debugger."""

import asyncio
import logging
from pathlib import Path
from typing import Optional, Coroutine, Any

import typer
from rich.console import Console
from rich.logging import RichHandler

from .config import Settings, load_settings, validate_configuration
from .server.mcp_server import MCPServer
from .client.mcp_client import MCPClient
from .client.debugger import PodDebugger
from .utils.logging import setup_logging

app = typer.Typer(help="Kubernetes Debugger with Grafana MCP integration")
console = Console()


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run async coroutine, handling existing event loops gracefully."""
    try:
        # Check if there's already a running loop
        loop = asyncio.get_running_loop()
        # If we get here, there's already a loop running
        console.print("[yellow]Warning: Running in an existing event loop context.[/yellow]")
        console.print("[yellow]This command cannot be run from within an async environment.[/yellow]")
        console.print("[yellow]Please run from a regular Python environment or terminal.[/yellow]")
        raise typer.Exit(1)
    except RuntimeError:
        # No loop is running, safe to use asyncio.run
        return asyncio.run(coro)


@app.command("server")
def start_server(
    config_file: Optional[Path] = typer.Option(None, "--config", "-c", help="Configuration file path"),
    host: Optional[str] = typer.Option(None, "--host", help="Server host"),
    port: Optional[int] = typer.Option(None, "--port", help="Server port"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug mode")
):
    """Start the MCP server."""
    settings = load_settings(config_file)
    
    if host:
        settings.server_host = host
    if port:
        settings.server_port = port
    if debug:
        settings.debug = debug
    
    # Validate configuration
    issues = validate_configuration(settings)
    if issues:
        console.print("[red]Configuration issues found:[/red]")
        for issue in issues:
            console.print(f"  - {issue}")
        raise typer.Exit(1)
    
    setup_logging(settings)
    
    # Create and run the server directly (FastMCP handles its own event loop)
    # Note: No console output when running as MCP server (STDIO protocol)
    server = MCPServer(settings)
    server.run_sync()


@app.command("debug")
def debug_pod(
    namespace: str = typer.Argument(..., help="Kubernetes namespace"),
    pod_name: str = typer.Argument(..., help="Pod name to debug"),
    server_url: str = typer.Option("http://localhost:8000", "--server", help="MCP server URL"),
    time_range: str = typer.Option("1h", "--time", help="Time range (e.g., 1h, 30m, 2d)"),
    logs: bool = typer.Option(True, "--logs/--no-logs", help="Show logs"),
    metrics: bool = typer.Option(True, "--metrics/--no-metrics", help="Show metrics"),
    events: bool = typer.Option(True, "--events/--no-events", help="Show events")
):
    """Debug a specific pod."""
    
    async def run_debug():
        async with MCPClient(server_url) as client:
            debugger = PodDebugger(client)
            await debugger.debug_pod(
                namespace=namespace,
                pod_name=pod_name,
                time_range=time_range,
                show_logs=logs,
                show_metrics=metrics,
                show_events=events
            )
    
    run_async(run_debug())


@app.command("analyze")
def analyze_namespace(
    namespace: str = typer.Argument(..., help="Kubernetes namespace"),
    server_url: str = typer.Option("http://localhost:8000", "--server", help="MCP server URL"),
    time_range: str = typer.Option("1h", "--time", help="Time range (e.g., 1h, 30m, 2d)")
):
    """Analyze all activity in a namespace."""
    
    async def run_analysis():
        async with MCPClient(server_url) as client:
            debugger = PodDebugger(client)
            await debugger.analyze_namespace(
                namespace=namespace,
                time_range=time_range
            )
    
    run_async(run_analysis())


@app.command("labels")
def debug_by_labels(
    namespace: str = typer.Argument(..., help="Kubernetes namespace"),
    labels: str = typer.Argument(..., help="Label selector (e.g., app=myapp,version=v1)"),
    server_url: str = typer.Option("http://localhost:8000", "--server", help="MCP server URL"),
    time_range: str = typer.Option("1h", "--time", help="Time range (e.g., 1h, 30m, 2d)")
):
    """Debug pods matching label selector."""
    
    async def run_debug():
        async with MCPClient(server_url) as client:
            debugger = PodDebugger(client)
            await debugger.debug_by_labels(
                namespace=namespace,
                label_selector=labels,
                time_range=time_range
            )
    
    run_async(run_debug())


@app.command("history")
def get_historical_data(
    namespace: str = typer.Argument(..., help="Kubernetes namespace"),
    pod_name: str = typer.Argument(..., help="Pod name"),
    server_url: str = typer.Option("http://localhost:8000", "--server", help="MCP server URL"),
    days: int = typer.Option(7, "--days", help="Number of days back to search")
):
    """Get historical data for terminated pods."""
    
    async def run_history():
        async with MCPClient(server_url) as client:
            debugger = PodDebugger(client)
            result = await debugger.get_historical_data(
                namespace=namespace,
                pod_name=pod_name,
                days_back=days
            )
            
            if "error" in result:
                console.print(f"[red]Error: {result['error']}[/red]")
            else:
                console.print("[green]Historical data retrieved successfully[/green]")
    
    run_async(run_history())


@app.command("health")
def check_health(
    server_url: str = typer.Option("http://localhost:8000", "--server", help="MCP server URL")
):
    """Check MCP server health."""
    
    async def run_health_check():
        async with MCPClient(server_url) as client:
            is_healthy = await client.health_check()
            if is_healthy:
                console.print("[green]✓ MCP server is healthy[/green]")
            else:
                console.print("[red]✗ MCP server is not responding[/red]")
                raise typer.Exit(1)
    
    run_async(run_health_check())


@app.command("config")
def show_config(
    config_file: Optional[Path] = typer.Option(None, "--config", "-c", help="Configuration file path")
):
    """Show current configuration."""
    settings = load_settings(config_file)
    
    console.print("[bold blue]K8s Debugger Configuration[/bold blue]")
    console.print(f"Grafana URL: {settings.grafana_url}")
    console.print(f"Server: {settings.server_host}:{settings.server_port}")
    console.print(f"Debug mode: {settings.debug}")
    console.print(f"Log level: {settings.log_level}")
    console.print(f"AWS region: {settings.aws_region}")
    console.print(f"K8s namespace: {settings.k8s_namespace}")
    
    # Validate configuration
    issues = validate_configuration(settings)
    if issues:
        console.print("\n[red]Configuration issues:[/red]")
        for issue in issues:
            console.print(f"  - {issue}")
    else:
        console.print("\n[green]✓ Configuration is valid[/green]")


def main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()