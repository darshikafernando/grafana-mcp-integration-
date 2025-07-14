"""Configuration settings for K8s Debugger."""

import os
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""
    
    model_config = SettingsConfigDict(
        env_file=[".env", ".env.local"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="forbid"
    )
    
    # Application
    app_name: str = Field(default="k8s-debugger", description="Application name")
    debug: bool = Field(default=False, description="Enable debug mode")
    log_level: str = Field(default="INFO", description="Log level")
    
    # Server
    server_host: str = Field(default="0.0.0.0", description="Server host")
    server_port: int = Field(default=8000, description="Server port")
    
    # Grafana
    grafana_url: str = Field(..., description="Grafana base URL")
    grafana_token: Optional[str] = Field(default=None, description="Grafana API key (for backward compatibility)")
    grafana_api_key: Optional[str] = Field(default=None, description="Grafana API key")
    grafana_org_id: Optional[int] = Field(default=None, description="Grafana organization ID")
    
    @property
    def grafana_key(self) -> str:
        """Get the Grafana API key, preferring grafana_api_key over grafana_token."""
        key = self.grafana_api_key or self.grafana_token
        if not key:
            raise ValueError("Either GRAFANA_API_KEY or GRAFANA_TOKEN must be provided")
        return key
    
    # Data Sources
    loki_datasource: str = Field(default="Loki", description="Loki datasource name")
    prometheus_datasource: str = Field(default="Prometheus", description="Prometheus datasource name")
    
    # AWS
    aws_region: str = Field(default="us-east-1", description="AWS region")
    aws_profile: Optional[str] = Field(default=None, description="AWS profile name")
    eks_cluster_name: Optional[str] = Field(default=None, description="EKS cluster name")
    
    # Kubernetes
    kubeconfig_path: Optional[str] = Field(default=None, description="Path to kubeconfig file")
    k8s_namespace: str = Field(default="default", description="Default Kubernetes namespace")
    
    # Performance
    query_timeout: float = Field(default=30.0, description="Query timeout in seconds")
    max_concurrent_queries: int = Field(default=10, description="Maximum concurrent queries")
    cache_ttl: int = Field(default=300, description="Cache TTL in seconds")
    
    # Retry settings
    max_retry_attempts: int = Field(default=3, description="Maximum retry attempts")
    retry_delay: float = Field(default=1.0, description="Retry delay in seconds")
    
    # Monitoring
    metrics_enabled: bool = Field(default=True, description="Enable metrics collection")
    health_check_interval: int = Field(default=60, description="Health check interval in seconds")
    
    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.debug
    
    @property
    def log_config(self) -> Dict[str, any]:
        """Get logging configuration."""
        return {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                },
                "detailed": {
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(pathname)s:%(lineno)d - %(message)s"
                }
            },
            "handlers": {
                "default": {
                    "formatter": "default",
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout"
                }
            },
            "root": {
                "level": self.log_level,
                "handlers": ["default"]
            }
        }


def load_settings(config_path: Optional[Path] = None) -> Settings:
    """Load settings from environment and optional config file."""
    if config_path and config_path.exists():
        # If a specific config file is provided, use it
        return Settings(_env_file=str(config_path))
    
    # Try to find config files in standard locations
    possible_paths = [
        Path.cwd() / ".env",
        Path.cwd() / ".env.local",
        Path.cwd() / "config" / "local.yaml",
        Path.home() / ".k8s-debugger" / "config.yaml"
    ]
    
    for path in possible_paths:
        if path.exists():
            if path.suffix in [".yaml", ".yml"]:
                # Handle YAML config files
                import yaml
                with open(path) as f:
                    config_data = yaml.safe_load(f)
                return Settings(**config_data)
            else:
                # Handle .env files
                return Settings(_env_file=str(path))
    
    # Fall back to environment variables only
    return Settings()


def validate_configuration(settings: Settings) -> List[str]:
    """Validate configuration and return list of issues."""
    issues = []
    
    # Required fields
    if not settings.grafana_url:
        issues.append("GRAFANA_URL is required")
    
    try:
        settings.grafana_key  # This will raise ValueError if neither key is provided
    except ValueError:
        issues.append("GRAFANA_API_KEY or GRAFANA_TOKEN is required")
    
    # URL validation
    if settings.grafana_url and not settings.grafana_url.startswith(('http://', 'https://')):
        issues.append("GRAFANA_URL must start with http:// or https://")
    
    # Port validation
    if not (1 <= settings.server_port <= 65535):
        issues.append("SERVER_PORT must be between 1 and 65535")
    
    # Log level validation
    valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    if settings.log_level.upper() not in valid_log_levels:
        issues.append(f"LOG_LEVEL must be one of: {', '.join(valid_log_levels)}")
    
    return issues