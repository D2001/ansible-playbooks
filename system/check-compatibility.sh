#!/usr/bin/env bash
# System Compatibility Checker for Ansible Infrastructure Deployment
# ===================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
PASSED=0
FAILED=0
WARNINGS=0

print_header() {
    echo -e "${BLUE}=================================="
    echo -e "System Compatibility Checker"
    echo -e "==================================${NC}"
    echo
}

print_check() {
    local status="$1"
    local message="$2"
    case "$status" in
        "PASS")
            echo -e "[${GREEN}✓${NC}] $message"
            ((PASSED++))
            ;;
        "FAIL")
            echo -e "[${RED}✗${NC}] $message"
            ((FAILED++))
            ;;
        "WARN")
            echo -e "[${YELLOW}!${NC}] $message"
            ((WARNINGS++))
            ;;
    esac
}

check_os() {
    echo -e "${BLUE}Checking Operating System...${NC}"
    
    if [[ -f /etc/os-release ]]; then
        source /etc/os-release
        echo "  Detected: $NAME $VERSION"
        
        case "$ID" in
            ubuntu)
                if [[ "${VERSION_ID}" =~ ^(18|20|22|24) ]]; then
                    print_check "PASS" "Ubuntu ${VERSION_ID} is supported"
                else
                    print_check "WARN" "Ubuntu ${VERSION_ID} may have compatibility issues"
                fi
                ;;
            debian)
                if [[ "${VERSION_ID}" =~ ^(10|11|12) ]]; then
                    print_check "PASS" "Debian ${VERSION_ID} is supported"
                else
                    print_check "WARN" "Debian ${VERSION_ID} may have compatibility issues"
                fi
                ;;
            *)
                print_check "FAIL" "Unsupported OS: $NAME (Only Ubuntu/Debian supported)"
                ;;
        esac
    else
        print_check "FAIL" "Cannot detect OS version"
    fi
    echo
}

check_architecture() {
    echo -e "${BLUE}Checking Architecture...${NC}"
    
    ARCH=$(uname -m)
    echo "  Detected: $ARCH"
    
    case "$ARCH" in
        x86_64)
            print_check "PASS" "x86_64 architecture supported"
            ;;
        aarch64)
            print_check "PASS" "ARM64 architecture supported"
            ;;
        armv7l|armv6l)
            print_check "PASS" "ARM architecture supported"
            ;;
        *)
            print_check "FAIL" "Unsupported architecture: $ARCH"
            ;;
    esac
    echo
}

check_sudo() {
    echo -e "${BLUE}Checking Privileges...${NC}"
    
    if sudo -n true 2>/dev/null; then
        print_check "PASS" "Sudo access available"
    elif groups | grep -q sudo; then
        print_check "WARN" "User in sudo group but may need password"
    else
        print_check "FAIL" "No sudo access - required for system deployment"
    fi
    echo
}

check_packages() {
    echo -e "${BLUE}Checking Package Manager...${NC}"
    
    if command -v apt >/dev/null 2>&1; then
        print_check "PASS" "APT package manager available"
        
        # Check if we can update package lists
        if sudo apt update -qq 2>/dev/null; then
            print_check "PASS" "Package lists can be updated"
        else
            print_check "WARN" "Cannot update package lists - check internet connection"
        fi
    else
        print_check "FAIL" "APT package manager not found"
    fi
    echo
}

check_internet() {
    echo -e "${BLUE}Checking Internet Connectivity...${NC}"
    
    if ping -c 1 8.8.8.8 >/dev/null 2>&1; then
        print_check "PASS" "Internet connectivity available"
    else
        print_check "FAIL" "No internet connectivity - required for package installation"
    fi
    
    if curl -s --connect-timeout 5 https://github.com >/dev/null; then
        print_check "PASS" "HTTPS connectivity to GitHub available"
    else
        print_check "WARN" "Cannot reach GitHub - may affect some installations"
    fi
    echo
}

check_existing_services() {
    echo -e "${BLUE}Checking Existing Services...${NC}"
    
    # Check Docker
    if systemctl is-active --quiet docker 2>/dev/null; then
        print_check "WARN" "Docker is already running - will be reconfigured"
    elif command -v docker >/dev/null 2>&1; then
        print_check "WARN" "Docker is installed but not running"
    else
        print_check "PASS" "Docker not installed - will be installed fresh"
    fi
    
    # Check WireGuard
    if systemctl is-active --quiet wg-quick@wg0 2>/dev/null; then
        print_check "WARN" "WireGuard wg0 interface is active - will be reconfigured"
    elif command -v wg >/dev/null 2>&1; then
        print_check "WARN" "WireGuard is installed but not configured"
    else
        print_check "PASS" "WireGuard not installed - will be installed fresh"
    fi
    
    # Check rclone
    if command -v rclone >/dev/null 2>&1; then
        RCLONE_VERSION=$(rclone version | head -n1)
        print_check "WARN" "rclone already installed: $RCLONE_VERSION"
    else
        print_check "PASS" "rclone not installed - will be installed fresh"
    fi
    echo
}

check_config_files() {
    echo -e "${BLUE}Checking Configuration Files...${NC}"
    
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    FILES_DIR="$SCRIPT_DIR/files"
    
    if [[ -f "$FILES_DIR/wg0.conf" ]]; then
        print_check "PASS" "WireGuard config found"
    else
        print_check "FAIL" "WireGuard config missing: $FILES_DIR/wg0.conf"
    fi
    
    if [[ -f "$FILES_DIR/smb_credentials" ]]; then
        print_check "PASS" "SMB credentials found"
    else
        print_check "FAIL" "SMB credentials missing: $FILES_DIR/smb_credentials"
    fi
    
    if [[ -f "$FILES_DIR/rclone.conf" ]]; then
        print_check "PASS" "rclone config found"
    else
        print_check "WARN" "rclone config missing: $FILES_DIR/rclone.conf (optional)"
    fi
    echo
}

check_ansible() {
    echo -e "${BLUE}Checking Ansible...${NC}"
    
    if command -v ansible-playbook >/dev/null 2>&1; then
        ANSIBLE_VERSION=$(ansible --version | head -n1)
        print_check "PASS" "Ansible available: $ANSIBLE_VERSION"
        
        # Check if we can run a simple playbook
        if ansible localhost -m setup -a 'filter=ansible_distribution' >/dev/null 2>&1; then
            print_check "PASS" "Ansible can gather facts from localhost"
        else
            print_check "WARN" "Ansible may have configuration issues"
        fi
    else
        print_check "FAIL" "Ansible not installed - run: sudo apt install ansible"
    fi
    echo
}

print_summary() {
    echo -e "${BLUE}=================================="
    echo -e "Summary"
    echo -e "==================================${NC}"
    echo -e "Passed:   ${GREEN}$PASSED${NC}"
    echo -e "Warnings: ${YELLOW}$WARNINGS${NC}"
    echo -e "Failed:   ${RED}$FAILED${NC}"
    echo
    
    if [[ $FAILED -eq 0 ]]; then
        if [[ $WARNINGS -eq 0 ]]; then
            echo -e "${GREEN}✓ System is ready for deployment!${NC}"
            echo "Run: sudo ansible-playbook system/deploy.yml"
        else
            echo -e "${YELLOW}⚠ System can be deployed but has warnings${NC}"
            echo "Review warnings above and run: sudo ansible-playbook system/deploy.yml"
        fi
    else
        echo -e "${RED}✗ System is not ready for deployment${NC}"
        echo "Fix the failed checks above before proceeding."
        exit 1
    fi
}

# Main execution
main() {
    print_header
    check_os
    check_architecture
    check_sudo
    check_packages
    check_internet
    check_existing_services
    check_config_files
    check_ansible
    print_summary
}

main "$@"
