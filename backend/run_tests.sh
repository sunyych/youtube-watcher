#!/bin/bash
# Run tests script

echo "Running unit tests..."

# Run unit tests (excluding integration tests)
pytest tests/ -v -m "not integration" --tb=short

echo ""
echo "To run integration tests (requires services running):"
echo "  pytest tests/ -v -m integration"
