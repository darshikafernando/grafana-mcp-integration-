"""Debugging tools that combine data from multiple sources."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import boto3
from kubernetes import client as k8s_client, config as k8s_config

from .grafana_mcp_client import GrafanaMCPClient
from ..config import Settings

logger = logging.getLogger(__name__)


class DebugTools:
    """Tools for Kubernetes debugging using multiple data sources."""
    
    def __init__(self, grafana_mcp_client: GrafanaMCPClient, settings: Optional[Settings] = None):
        self.grafana_mcp_client = grafana_mcp_client
        self.settings = settings
        self._setup_k8s_client()
        self._setup_aws_client()
    
    def _setup_k8s_client(self) -> None:
        """Set up Kubernetes client."""
        try:
            k8s_config.load_incluster_config()
        except k8s_config.ConfigException:
            try:
                k8s_config.load_kube_config()
            except k8s_config.ConfigException:
                logger.warning("Could not load Kubernetes config")
                self.k8s_client = None
                return
        
        self.k8s_client = k8s_client.CoreV1Api()
    
    def _setup_aws_client(self) -> None:
        """Set up AWS clients for CloudWatch and EKS."""
        try:
            session_kwargs = {}
            if self.settings and self.settings.aws_profile:
                session_kwargs['profile_name'] = self.settings.aws_profile
            if self.settings and self.settings.aws_region:
                session_kwargs['region_name'] = self.settings.aws_region
            
            session = boto3.Session(**session_kwargs)
            self.cloudwatch_client = session.client('cloudwatch')
            self.eks_client = session.client('eks')
        except Exception as e:
            logger.warning(f"Could not initialize AWS clients: {e}")
            self.cloudwatch_client = None
            self.eks_client = None
    
    def _time_range_to_timestamps(self, time_range: str) -> tuple[str, str]:
        """Convert time range string to start/end timestamps."""
        now = datetime.utcnow()
        
        # Parse time range (e.g., "1h", "30m", "2d")
        if time_range.endswith('h'):
            hours = int(time_range[:-1])
            start = now - timedelta(hours=hours)
        elif time_range.endswith('m'):
            minutes = int(time_range[:-1])
            start = now - timedelta(minutes=minutes)
        elif time_range.endswith('d'):
            days = int(time_range[:-1])
            start = now - timedelta(days=days)
        else:
            # Default to 1 hour
            start = now - timedelta(hours=1)
        
        return start.isoformat() + 'Z', now.isoformat() + 'Z'
    
    async def get_pod_logs(
        self,
        namespace: str,
        pod_name: Optional[str] = None,
        label_selector: Optional[str] = None,
        time_range: str = "1h"
    ) -> Dict[str, Any]:
        """Get pod logs from Loki."""
        start_time, end_time = self._time_range_to_timestamps(time_range)
        
        # Build Loki query
        if pod_name:
            query = f'{{namespace="{namespace}", pod="{pod_name}"}}'
        elif label_selector:
            # Convert k8s label selector to Loki query
            labels = [f'{k}="{v}"' for k, v in 
                     [label.split('=') for label in label_selector.split(',')]]
            query = '{' + f'namespace="{namespace}", {", ".join(labels)}' + '}'
        else:
            query = f'{{namespace="{namespace}"}}'
        
        try:
            result = await self.grafana_mcp_client.query_loki(
                query=query,
                start_time=start_time,
                end_time=end_time
            )
            
            return {
                "logs": result.get("data", {}).get("result", []),
                "query": query,
                "time_range": {"start": start_time, "end": end_time}
            }
        except Exception as e:
            logger.error(f"Error querying logs: {e}")
            return {"error": str(e)}
    
    async def get_pod_metrics(
        self,
        namespace: str,
        pod_name: Optional[str] = None,
        label_selector: Optional[str] = None,
        time_range: str = "1h"
    ) -> Dict[str, Any]:
        """Get pod metrics from Prometheus."""
        start_time, end_time = self._time_range_to_timestamps(time_range)
        
        # Build Prometheus queries
        if pod_name:
            pod_filter = f'pod="{pod_name}"'
        elif label_selector:
            # This would need more sophisticated label matching
            pod_filter = f'namespace="{namespace}"'
        else:
            pod_filter = f'namespace="{namespace}"'
        
        queries = {
            "cpu_usage": f'rate(container_cpu_usage_seconds_total{{{pod_filter}}}[5m])',
            "memory_usage": f'container_memory_working_set_bytes{{{pod_filter}}}',
            "network_rx": f'rate(container_network_receive_bytes_total{{{pod_filter}}}[5m])',
            "network_tx": f'rate(container_network_transmit_bytes_total{{{pod_filter}}}[5m])'
        }
        
        results = {}
        for metric_name, query in queries.items():
            try:
                result = await self.grafana_mcp_client.query_prometheus(
                    query=query,
                    start_time=start_time,
                    end_time=end_time
                )
                results[metric_name] = result.get("data", {}).get("result", [])
            except Exception as e:
                logger.error(f"Error querying {metric_name}: {e}")
                results[metric_name] = {"error": str(e)}
        
        return {
            "metrics": results,
            "time_range": {"start": start_time, "end": end_time}
        }
    
    async def get_cluster_events(
        self,
        namespace: str = "default",
        time_range: str = "1h"
    ) -> Dict[str, Any]:
        """Get Kubernetes cluster events."""
        if not self.k8s_client:
            return {"error": "Kubernetes client not available"}
        
        try:
            # Get events from Kubernetes API
            events = self.k8s_client.list_namespaced_event(namespace=namespace)
            
            # Filter events by time range
            start_time, _ = self._time_range_to_timestamps(time_range)
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            
            filtered_events = []
            for event in events.items:
                if event.first_timestamp and event.first_timestamp >= start_dt:
                    filtered_events.append({
                        "name": event.metadata.name,
                        "namespace": event.metadata.namespace,
                        "reason": event.reason,
                        "message": event.message,
                        "type": event.type,
                        "object": {
                            "kind": event.involved_object.kind,
                            "name": event.involved_object.name
                        },
                        "first_timestamp": event.first_timestamp.isoformat(),
                        "last_timestamp": event.last_timestamp.isoformat() if event.last_timestamp else None,
                        "count": event.count
                    })
            
            return {
                "events": filtered_events,
                "namespace": namespace,
                "time_range": time_range
            }
        except Exception as e:
            logger.error(f"Error getting cluster events: {e}")
            return {"error": str(e)}
    
    async def correlate_pod_data(
        self,
        namespace: str,
        pod_name: Optional[str] = None,
        label_selector: Optional[str] = None,
        time_range: str = "1h"
    ) -> Dict[str, Any]:
        """Correlate logs, metrics, and events for comprehensive pod debugging."""
        # Run all queries concurrently
        tasks = [
            self.get_pod_logs(namespace, pod_name, label_selector, time_range),
            self.get_pod_metrics(namespace, pod_name, label_selector, time_range),
            self.get_cluster_events(namespace, time_range)
        ]
        
        logs_result, metrics_result, events_result = await asyncio.gather(*tasks)
        
        return {
            "correlation": {
                "namespace": namespace,
                "pod_name": pod_name,
                "label_selector": label_selector,
                "time_range": time_range
            },
            "logs": logs_result,
            "metrics": metrics_result,
            "events": events_result,
            "summary": self._generate_summary(logs_result, metrics_result, events_result)
        }
    
    def _generate_summary(
        self,
        logs_result: Dict[str, Any],
        metrics_result: Dict[str, Any],
        events_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate a summary of the debugging data."""
        summary = {
            "log_entries": 0,
            "error_logs": 0,
            "warning_events": 0,
            "error_events": 0,
            "high_cpu_usage": False,
            "high_memory_usage": False
        }
        
        # Analyze logs
        if "logs" in logs_result:
            for stream in logs_result["logs"]:
                if "values" in stream:
                    summary["log_entries"] += len(stream["values"])
                    # Count error logs (simple heuristic)
                    for entry in stream["values"]:
                        if len(entry) > 1 and ("error" in entry[1].lower() or "exception" in entry[1].lower()):
                            summary["error_logs"] += 1
        
        # Analyze events
        if "events" in events_result:
            for event in events_result["events"]:
                if event.get("type") == "Warning":
                    summary["warning_events"] += 1
                elif event.get("type") == "Error":
                    summary["error_events"] += 1
        
        # TODO: Analyze metrics for high usage patterns
        
        return summary
    
    async def get_cloudwatch_events(
        self,
        cluster_name: str,
        time_range: str = "1h"
    ) -> Dict[str, Any]:
        """Get EKS events from CloudWatch."""
        if not self.cloudwatch_client:
            return {"error": "CloudWatch client not available"}
        
        start_time, end_time = self._time_range_to_timestamps(time_range)
        
        try:
            # Convert to Unix timestamps for CloudWatch
            import time as time_module
            start_timestamp = int(datetime.fromisoformat(start_time.replace('Z', '+00:00')).timestamp())
            end_timestamp = int(datetime.fromisoformat(end_time.replace('Z', '+00:00')).timestamp())
            
            # Query CloudWatch Logs for EKS events
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.cloudwatch_client.filter_log_events(
                    logGroupName=f'/aws/eks/{cluster_name}/cluster',
                    startTime=start_timestamp * 1000,
                    endTime=end_timestamp * 1000,
                    limit=1000
                )
            )
            
            events = []
            for event in response.get('events', []):
                events.append({
                    "timestamp": datetime.fromtimestamp(event['timestamp'] / 1000).isoformat() + 'Z',
                    "message": event['message'],
                    "log_stream": event.get('logStreamName', ''),
                    "cluster": cluster_name
                })
            
            return {
                "events": events,
                "cluster": cluster_name,
                "time_range": time_range,
                "total_events": len(events)
            }
        
        except Exception as e:
            logger.error(f"Error getting CloudWatch events: {e}")
            return {"error": str(e)}
    
    async def get_enhanced_correlation(
        self,
        namespace: str,
        pod_name: Optional[str] = None,
        label_selector: Optional[str] = None,
        time_range: str = "1h",
        include_cloudwatch: bool = True
    ) -> Dict[str, Any]:
        """Enhanced correlation including CloudWatch data."""
        tasks = [
            self.get_pod_logs(namespace, pod_name, label_selector, time_range),
            self.get_pod_metrics(namespace, pod_name, label_selector, time_range),
            self.get_cluster_events(namespace, time_range)
        ]
        
        # Add CloudWatch data if available and requested
        if include_cloudwatch and self.settings and self.settings.eks_cluster_name:
            tasks.append(self.get_cloudwatch_events(self.settings.eks_cluster_name, time_range))
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle results safely
        logs_result = results[0] if not isinstance(results[0], Exception) else {"error": str(results[0])}
        metrics_result = results[1] if not isinstance(results[1], Exception) else {"error": str(results[1])}
        events_result = results[2] if not isinstance(results[2], Exception) else {"error": str(results[2])}
        cloudwatch_result = results[3] if len(results) > 3 and not isinstance(results[3], Exception) else None
        
        correlation_data = {
            "correlation": {
                "namespace": namespace,
                "pod_name": pod_name,
                "label_selector": label_selector,
                "time_range": time_range,
                "includes_cloudwatch": cloudwatch_result is not None
            },
            "logs": logs_result,
            "metrics": metrics_result,
            "events": events_result,
            "summary": self._generate_enhanced_summary(
                logs_result, metrics_result, events_result, cloudwatch_result
            )
        }
        
        if cloudwatch_result:
            correlation_data["cloudwatch"] = cloudwatch_result
            
        return correlation_data
    
    def _generate_enhanced_summary(
        self,
        logs_result: Dict[str, Any],
        metrics_result: Dict[str, Any],
        events_result: Dict[str, Any],
        cloudwatch_result: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generate enhanced summary including CloudWatch data."""
        summary = self._generate_summary(logs_result, metrics_result, events_result)
        
        # Add CloudWatch insights
        if cloudwatch_result and "events" in cloudwatch_result:
            cloudwatch_events = cloudwatch_result["events"]
            summary["cloudwatch_events"] = len(cloudwatch_events)
            
            # Analyze CloudWatch events for patterns
            error_patterns = ["error", "failed", "exception", "timeout"]
            cloudwatch_errors = sum(
                1 for event in cloudwatch_events 
                if any(pattern in event.get("message", "").lower() for pattern in error_patterns)
            )
            summary["cloudwatch_errors"] = cloudwatch_errors
            
            # Check for recent control plane issues
            recent_threshold = datetime.utcnow() - timedelta(minutes=30)
            recent_events = [
                event for event in cloudwatch_events
                if datetime.fromisoformat(event["timestamp"].replace('Z', '+00:00')) > recent_threshold
            ]
            summary["recent_cloudwatch_issues"] = len(recent_events)
        
        return summary
    
    async def analyze_time_correlation(
        self,
        namespace: str,
        pod_name: str,
        time_range: str = "2h",
        window_size: str = "15m"
    ) -> Dict[str, Any]:
        """Analyze data correlation across sliding time windows."""
        start_time, end_time = self._time_range_to_timestamps(time_range)
        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        
        # Parse window size
        if window_size.endswith('m'):
            window_minutes = int(window_size[:-1])
        elif window_size.endswith('h'):
            window_minutes = int(window_size[:-1]) * 60
        else:
            window_minutes = 15  # Default
        
        window_delta = timedelta(minutes=window_minutes)
        
        # Generate time windows
        windows = []
        current_time = start_dt
        while current_time < end_dt:
            window_end = min(current_time + window_delta, end_dt)
            windows.append({
                "start": current_time.isoformat() + 'Z',
                "end": window_end.isoformat() + 'Z',
                "duration": f"{window_minutes}m"
            })
            current_time += window_delta
        
        # Analyze each window
        window_analyses = []
        for window in windows:
            window_range = f"{window_minutes}m"
            
            # Get data for this window
            tasks = [
                self.get_pod_logs(namespace, pod_name, None, window_range),
                self.get_pod_metrics(namespace, pod_name, None, window_range),
            ]
            
            try:
                logs_result, metrics_result = await asyncio.gather(*tasks)
                
                # Analyze this window
                window_summary = {
                    "time_window": window,
                    "log_count": self._count_logs(logs_result),
                    "error_count": self._count_errors(logs_result),
                    "metrics_available": "error" not in metrics_result,
                    "anomalies": self._detect_anomalies(logs_result, metrics_result)
                }
                
                window_analyses.append(window_summary)
                
            except Exception as e:
                logger.error(f"Error analyzing window {window}: {e}")
                window_analyses.append({
                    "time_window": window,
                    "error": str(e)
                })
        
        return {
            "analysis": {
                "namespace": namespace,
                "pod_name": pod_name,
                "total_time_range": time_range,
                "window_size": window_size,
                "total_windows": len(windows)
            },
            "windows": window_analyses,
            "trends": self._analyze_trends(window_analyses)
        }
    
    def _count_logs(self, logs_result: Dict[str, Any]) -> int:
        """Count total log entries."""
        if "error" in logs_result or "logs" not in logs_result:
            return 0
        return sum(len(stream.get("values", [])) for stream in logs_result["logs"])
    
    def _count_errors(self, logs_result: Dict[str, Any]) -> int:
        """Count error log entries."""
        if "error" in logs_result or "logs" not in logs_result:
            return 0
        
        error_count = 0
        for stream in logs_result["logs"]:
            for entry in stream.get("values", []):
                if len(entry) > 1 and ("error" in entry[1].lower() or "exception" in entry[1].lower()):
                    error_count += 1
        return error_count
    
    def _detect_anomalies(self, logs_result: Dict[str, Any], metrics_result: Dict[str, Any]) -> List[str]:
        """Detect anomalies in logs and metrics."""
        anomalies = []
        
        # Check for log anomalies
        log_count = self._count_logs(logs_result)
        error_count = self._count_errors(logs_result)
        
        if error_count > 0:
            error_rate = error_count / max(log_count, 1)
            if error_rate > 0.1:  # More than 10% errors
                anomalies.append(f"High error rate: {error_rate:.1%}")
        
        # Check for sudden log volume changes
        if log_count == 0:
            anomalies.append("No logs detected")
        elif log_count > 1000:
            anomalies.append("Unusually high log volume")
        
        return anomalies
    
    def _analyze_trends(self, window_analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze trends across time windows."""
        if not window_analyses:
            return {}
        
        # Extract metrics
        log_counts = [w.get("log_count", 0) for w in window_analyses if "error" not in w]
        error_counts = [w.get("error_count", 0) for w in window_analyses if "error" not in w]
        
        if not log_counts:
            return {"error": "No valid windows to analyze"}
        
        trends = {
            "log_volume": {
                "average": sum(log_counts) / len(log_counts),
                "peak": max(log_counts),
                "minimum": min(log_counts),
                "trend": "stable"
            },
            "error_pattern": {
                "total_errors": sum(error_counts),
                "peak_errors": max(error_counts),
                "error_windows": len([c for c in error_counts if c > 0])
            }
        }
        
        # Determine trend direction
        if len(log_counts) >= 3:
            first_half = sum(log_counts[:len(log_counts)//2])
            second_half = sum(log_counts[len(log_counts)//2:])
            
            if second_half > first_half * 1.2:
                trends["log_volume"]["trend"] = "increasing"
            elif second_half < first_half * 0.8:
                trends["log_volume"]["trend"] = "decreasing"
        
        return trends