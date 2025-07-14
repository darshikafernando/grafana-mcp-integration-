#!/bin/bash
# Development environment setup script

set -e

echo "Setting up K8s Debugger development environment..."

# Check if Python 3.10+ is available
python_version=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
required_version="3.10"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "Error: Python 3.10 or higher is required. Found: $python_version"
    exit 1
fi

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install development dependencies
echo "Installing development dependencies..."
pip install -r requirements-dev.txt

# Install package in editable mode
echo "Installing package in editable mode..."
pip install -e .

# # Set up pre-commit hooks
# echo "Setting up pre-commit hooks..."
# pre-commit install

# # Create example config if it doesn't exist
# if [ ! -f ".env" ]; then
#     echo "Creating .env file from example..."
#     cp config/example.env .env
#     echo "Please edit .env with your configuration values"
# fi

# # Set up official Grafana MCP server
# echo "Setting up official Grafana MCP server..."
# if command -v go &> /dev/null || command -v docker &> /dev/null; then
#     ./scripts/setup-grafana-mcp.sh
# else
#     echo "Warning: Neither Go nor Docker found. Grafana MCP server not installed."
#     echo "Install Go or Docker and run ./scripts/setup-grafana-mcp.sh manually."
# fi

# # Run tests to verify setup
# echo "Running tests to verify setup..."
# pytest tests/unit/ -v

# echo "Development environment setup complete!"
# echo ""
# echo "To activate the environment:"
# echo "  source venv/bin/activate"
# echo ""
# echo "To run tests:"
# echo "  pytest"
# echo ""
# echo "To run linting:"
# echo "  ruff check src/ tests/"
# echo ""
# echo "To run type checking:"
# echo "  mypy src/"
# echo ""
# echo "To set up official Grafana MCP server (if not done automatically):"
# echo "  ./scripts/setup-grafana-mcp.sh"