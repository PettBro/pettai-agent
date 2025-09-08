#!/bin/bash
# Build and Test Script for Pett Agent - Olas SDK

set -e

echo "🚀 Pett Agent - Olas SDK Build and Test"
echo "======================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
AUTHOR_NAME="pettai"
AGENT_NAME="pett_agent"
VERSION="0.1.0"
AGENT_HASH="bafybeigh54vwypnmvrcyphwhzshr6ubunrbggwm5dekdbohiww6on5opsq"  # Placeholder
IMAGE_NAME="${AUTHOR_NAME}/oar-${AGENT_NAME}:${AGENT_HASH}"

echo -e "${BLUE}📦 Building Docker image: ${IMAGE_NAME}${NC}"

# Check if Dockerfile exists
if [ ! -f "Dockerfile" ]; then
    echo -e "${RED}❌ Dockerfile not found!${NC}"
    exit 1
fi

# Check if requirements.txt exists
if [ ! -f "requirements.txt" ]; then
    echo -e "${RED}❌ requirements.txt not found!${NC}"
    exit 1
fi

# Build Docker image
echo -e "${YELLOW}🔨 Building Docker image...${NC}"
docker build -t "${IMAGE_NAME}" .

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Docker image built successfully${NC}"
else
    echo -e "${RED}❌ Docker build failed${NC}"
    exit 1
fi

# Create ethereum_private_key.txt if it doesn't exist
if [ ! -f "ethereum_private_key.txt" ]; then
    echo -e "${YELLOW}📝 Creating placeholder ethereum_private_key.txt${NC}"
    touch ethereum_private_key.txt
fi

# Option to run the container for testing
read -p "🤔 Do you want to run the container for testing? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${BLUE}🚀 Starting container for testing...${NC}"
    
    # Create .env file if it doesn't exist
    if [ ! -f ".env" ]; then
        echo -e "${YELLOW}📝 Creating .env from example...${NC}"
        cp .env.example .env
        echo -e "${YELLOW}⚠️  Please edit .env file with your actual values${NC}"
    fi
    
    # Run container with port mapping and environment
    docker run -d \
        --name pett_agent_test \
        -p 8716:8716 \
        --env-file .env \
        -v "$(pwd)/ethereum_private_key.txt:/app/ethereum_private_key.txt" \
        -v "$(pwd)/logs:/app/logs" \
        "${IMAGE_NAME}"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Container started successfully${NC}"
        echo -e "${BLUE}🌐 Health check: http://localhost:8716/healthcheck${NC}"
        echo -e "${BLUE}🎛️  Agent UI: http://localhost:8716/${NC}"
        echo -e "${YELLOW}💡 Run 'python test_agent.py' to test the agent${NC}"
        echo -e "${YELLOW}💡 Run 'docker logs pett_agent_test' to see logs${NC}"
        echo -e "${YELLOW}💡 Run 'docker stop pett_agent_test' to stop${NC}"
    else
        echo -e "${RED}❌ Failed to start container${NC}"
        exit 1
    fi
fi

echo -e "${GREEN}🎉 Build complete!${NC}"
echo
echo -e "${BLUE}📋 Next steps:${NC}"
echo "1. Update .env with your actual values"
echo "2. Add your ethereum private key to ethereum_private_key.txt"
echo "3. Test the agent with: python test_agent.py"
echo "4. Push to Docker Hub: docker push ${IMAGE_NAME}"
echo "5. Follow Olas SDK guide to mint and deploy"
echo
echo -e "${BLUE}🔗 Useful links:${NC}"
echo "- Olas SDK Guide: https://stack.olas.network/olas-sdk/"
echo "- Mint Agent: https://stack.olas.network/olas-sdk/#step-3-mint-it"
