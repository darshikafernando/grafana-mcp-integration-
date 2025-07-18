"""K8s Debugger - Kubernetes debugging with Grafana MCP integration."""

try:
    from ._version import version as __version__
except ImportError:
    __version__ = "unknown"

__all__ = ["__version__"]