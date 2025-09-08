#!/bin/bash
# ------------------------------------------------------------------------------
#
#   Copyright 2025 pettai
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
# ------------------------------------------------------------------------------

# ABCI Pett Agent deployment script for Olas Network
# Based on: https://stack.olas.network/open-autonomy/guides/deploy_service/

set -e

echo "🚀 ABCI Pett Agent - Olas Network Deployment Script"
echo "=================================================="

# Configuration
SERVICE_NAME="pett_autonomy_agent"
PACKAGE_PATH="packages/pettai"
KEYS_FILE="keys.json"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_step() {
    echo -e "${BLUE}📋 STEP: $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check if required commands are available
check_requirements() {
    print_step "Checking requirements..."
    
    commands=("autonomy" "docker" "python3")
    for cmd in "${commands[@]}"; do
        if ! command -v $cmd &> /dev/null; then
            print_error "$cmd is not installed or not in PATH"
            exit 1
        fi
    done
    
    print_success "All required commands are available"
}

# Generate example keys file if it doesn't exist
generate_keys_file() {
    if [ ! -f "$KEYS_FILE" ]; then
        print_step "Generating example keys file..."
        print_warning "WARNING: This generates example keys for TESTING ONLY!"
        print_warning "DO NOT use these keys in production!"
        
        cat > $KEYS_FILE << 'EOF'
[
  {
      "address": "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65",
      "private_key": "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a"
  },
  {
      "address": "0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc",
      "private_key": "0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba"
  },
  {
      "address": "0x976EA74026E726554dB657fA54763abd0C3a0aa9",
      "private_key": "0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e"
  },
  {
      "address": "0x14dC79964da2C08b23698B3D3cc7Ca32193d9955",
      "private_key": "0x4bbbf85ce3377467afe5d46f804f221813b2bb87f24d81f60f1fcdbf7cbf4356"
  }
]
EOF
        print_success "Generated $KEYS_FILE with example keys"
        print_warning "Remember to replace with your actual keys for production!"
    else
        print_success "Keys file $KEYS_FILE already exists"
    fi
}

# Set up environment variables
setup_environment() {
    print_step "Setting up environment variables..."
    
    # Set ALL_PARTICIPANTS - these should match the addresses in your keys.json
    export ALL_PARTICIPANTS='[
        "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65",
        "0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc",
        "0x976EA74026E726554dB657fA54763abd0C3a0aa9",
        "0x14dC79964da2C08b23698B3D3cc7Ca32193d9955"
    ]'
    
    print_success "Environment variables set"
    echo "ALL_PARTICIPANTS=$ALL_PARTICIPANTS"
}

# Build the service
build_service() {
    print_step "Building ABCI service deployment..."
    
    # Clean up previous builds
    rm -rf abci_build_*
    print_success "Cleaned up previous builds"
    
    # Build the deployment
    print_step "Building deployment with keys..."
    autonomy deploy build $KEYS_FILE -ltm
    
    print_success "Service deployment built successfully!"
    print_success "Deployment created in: $(ls -d abci_build_* | head -1)"
}

# Deploy the service
deploy_service() {
    print_step "Deploying the ABCI service..."
    
    # Find the build directory
    BUILD_DIR=$(ls -d abci_build_* | head -1)
    
    if [ ! -d "$BUILD_DIR" ]; then
        print_error "Build directory not found. Run build first."
        exit 1
    fi
    
    print_step "Navigating to build directory: $BUILD_DIR"
    cd $BUILD_DIR
    
    print_step "Starting service deployment..."
    print_warning "This will start the service. Press Ctrl+C to stop."
    
    # Run the deployment
    autonomy deploy run
}

# Build Docker image
build_image() {
    print_step "Building Docker image for the agent..."
    
    autonomy build-image --service-dir .
    
    print_success "Docker image built successfully!"
}

# Show deployment status
show_status() {
    print_step "Checking deployment status..."
    
    # Check if containers are running
    if docker ps | grep -q "abci"; then
        print_success "ABCI containers are running:"
        docker ps | grep abci
    else
        print_warning "No ABCI containers found running"
    fi
    
    # Show logs from the latest container
    LATEST_CONTAINER=$(docker ps --format "table {{.Names}}" | grep abci | head -1)
    if [ ! -z "$LATEST_CONTAINER" ]; then
        print_step "Recent logs from $LATEST_CONTAINER:"
        docker logs --tail 20 $LATEST_CONTAINER
    fi
}

# Main menu
show_menu() {
    echo ""
    echo "🎯 ABCI Pett Agent Deployment Options:"
    echo "1. Check requirements"
    echo "2. Generate example keys file"
    echo "3. Setup environment"
    echo "4. Build service"
    echo "5. Build Docker image"
    echo "6. Deploy service (local)"
    echo "7. Show deployment status"
    echo "8. Full deployment (steps 1-6)"
    echo "9. Clean up deployments"
    echo "0. Exit"
    echo ""
}

# Clean up function
cleanup() {
    print_step "Cleaning up deployments..."
    rm -rf abci_build_*
    
    # Stop running containers
    docker ps | grep abci | awk '{print $1}' | xargs -r docker stop
    
    print_success "Cleanup complete"
}

# Full deployment
full_deployment() {
    print_step "Starting full deployment process..."
    
    check_requirements
    generate_keys_file
    setup_environment
    build_image
    build_service
    
    print_success "Full deployment preparation complete!"
    print_step "To start the service, run: ./deploy_olas.sh and select option 6"
}

# Main script logic
if [ $# -eq 0 ]; then
    # Interactive mode
    while true; do
        show_menu
        read -p "Choose an option (0-9): " choice
        
        case $choice in
            1) check_requirements ;;
            2) generate_keys_file ;;
            3) setup_environment ;;
            4) build_service ;;
            5) build_image ;;
            6) deploy_service ;;
            7) show_status ;;
            8) full_deployment ;;
            9) cleanup ;;
            0) echo "👋 Goodbye!"; exit 0 ;;
            *) print_error "Invalid option. Please choose 0-9." ;;
        esac
        
        echo ""
        read -p "Press Enter to continue..."
    done
else
    # Command line mode
    case $1 in
        "check") check_requirements ;;
        "keys") generate_keys_file ;;
        "env") setup_environment ;;
        "build") build_service ;;
        "image") build_image ;;
        "deploy") deploy_service ;;
        "status") show_status ;;
        "full") full_deployment ;;
        "clean") cleanup ;;
        *) 
            echo "Usage: $0 [check|keys|env|build|image|deploy|status|full|clean]"
            echo "Or run without arguments for interactive mode"
            exit 1
            ;;
    esac
fi

print_success "Script completed successfully!"
