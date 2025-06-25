#!/bin/bash

# Docker Compose Compatibility Check Script
echo "=== Docker Compose Compatibility Check ==="

# Check if docker compose (v2) is available
if command -v docker >/dev/null 2>&1; then
    echo "✓ Docker is installed"
    
    if docker compose version >/dev/null 2>&1; then
        echo "✓ Docker Compose V2 is available"
        docker compose version
        echo ""
        echo "✅ Your system is ready for the optimized backup script!"
        echo "   Use: ansible-playbook backup.yml -e service_name=your_service"
    else
        echo "❌ Docker Compose V2 is not available"
        echo ""
        echo "Please install Docker Compose V2:"
        echo "  sudo apt update"
        echo "  sudo apt install docker-compose-plugin"
        echo ""
        echo "Or on newer systems, Docker Compose V2 comes with Docker Desktop"
        exit 1
    fi
else
    echo "❌ Docker is not installed"
    echo "Please install Docker first:"
    echo "  sudo apt update"
    echo "  sudo apt install docker.io docker-compose-plugin"
    exit 1
fi

# Check for optional performance tools
echo ""
echo "=== Optional Performance Tools ==="

if command -v pigz >/dev/null 2>&1; then
    echo "✓ pigz (parallel gzip) is installed - faster compression enabled"
else
    echo "⚠ pigz not found - install for faster compression: sudo apt install pigz"
fi

if command -v rclone >/dev/null 2>&1; then
    echo "✓ rclone is installed"
else
    echo "⚠ rclone not found - needed for OneDrive uploads"
fi

echo ""
echo "=== Ansible Collections Check ==="
if ansible-galaxy collection list community.general >/dev/null 2>&1; then
    echo "✓ community.general collection is installed"
else
    echo "❌ community.general collection not found"
    echo "  Install with: ansible-galaxy collection install community.general"
    echo "  Or run the system deploy script which includes collection installation"
fi

if ansible-galaxy collection list community.docker >/dev/null 2>&1; then
    echo "✓ community.docker collection is installed"
else
    echo "❌ community.docker collection not found"
    echo "  Install with: ansible-galaxy collection install community.docker"
    echo "  Or run the system deploy script which includes collection installation"
fi

echo ""
echo "=== System Information ==="
echo "Ansible version: $(ansible --version | head -n1)"
echo "Python version: $(python3 --version)"
echo "Available CPU cores: $(nproc)"

echo ""
echo "=== Recommended Setup ==="
echo "1. Run system deploy (includes collections): cd ../system && ansible-playbook deploy.yml"
echo "2. Or install collections manually: ansible-galaxy collection install -r requirements.yml"
echo "3. Install performance tools: sudo apt install pigz"
echo "4. Test backup: ansible-playbook backup.yml -e service_name=test --check"
