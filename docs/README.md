# K8s Debugger Usage Examples

Hack Day ramblings to integrate Grafana with Claude Code

## Server Setup

### Starting the Server

```bash
# Configure environment
export GRAFANA_URL="https://your-grafana.com"
export GRAFANA_API_KEY="your-api-token"
export AWS_PROFILE="your-aws-profile"

# Start the server (automatically connects to official Grafana MCP server)
k8s-debugger server --host 0.0.0.0 --port 8000
```

## Example User Interactions

### 1. Debug a Specific Pod

```bash
k8s-debugger debug production my-app-pod-123 --time 2h
```

### 2. Debug by Label Selector

```bash
k8s-debugger labels production "app=web,version=v2" --time 1h
```

### 3. Historical Analysis

```bash
k8s-debugger history production crashed-pod-456 --days 3
```

### 4. Namespace Overview

```bash
k8s-debugger analyze production --time 4h
```

### 5. Health Check

```bash
k8s-debugger health
```

## Common Use Cases

### Post-Incident Debugging
```bash
# Investigate a recent outage
k8s-debugger debug production failed-service-pod --time 6h

# Check related services
k8s-debugger labels production "app=service,tier=backend" --time 6h

# Get namespace overview during incident window
k8s-debugger analyze production --time 8h
```

### Proactive Monitoring
```bash
# Daily health check
k8s-debugger health

# Check for resource pressure
k8s-debugger analyze production --time 24h

# Monitor high-traffic services
k8s-debugger labels production "tier=frontend" --time 2h
```

### Historical Analysis
```bash
# Investigate terminated pods
k8s-debugger history production old-pod-name --days 7

# Compare current vs historical performance
k8s-debugger debug production current-pod --time 24h
```
