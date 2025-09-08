# Pett Agent - Olas SDK Integration

🐾 **Pett.ai autonomous agent for virtual pet management, fully compliant with Olas SDK requirements.**

## 🎯 What This Is

This is your original Pett Agent (`pett_agent/`) logic, now fully integrated with the [Olas SDK](https://stack.olas.network/olas-sdk/) for deployment on the Olas network. All your existing functionality is preserved and wrapped with Olas SDK compliance.

## ✅ Olas SDK Requirements Met

### ✅ **Core Requirements**

- **ENTRYPOINT**: `run.py` - Main entry script
- **AGENT EOA**: Reads `ethereum_private_key.txt` from working directory
- **SERVICE SAFE**: Handles `CONNECTION_CONFIGS_CONFIG_SAFE_CONTRACT_ADDRESSES` env var
- **LOGS**: Generates `log.txt` with format `[YYYY-MM-DD HH:MM:SS,mmm] [LOG_LEVEL] [agent] Message`
- **HEALTHCHECK**: `GET http://localhost:8716/healthcheck` with required JSON
- **AGENT UI**: `GET http://localhost:8716/` with POST support
- **ENVIRONMENT VARIABLES**: All standard Olas vars supported
- **WITHDRAWAL**: Optional withdrawal mode when `WITHDRAWAL_MODE=true`

### 🏗️ **Architecture**

```
olas-sdk-starter/
├── run.py                    # 🚀 ENTRYPOINT (Olas required)
├── agent/
│   ├── olas_interface.py     # 🔧 Olas SDK compliance layer
│   ├── pett_agent.py         # 🎯 Main agent orchestrator
│   ├── pett_websocket_client.py  # 🔌 Your WebSocket logic
│   ├── pett_tools.py         # 🛠️ Your tools logic
│   ├── telegram_bot.py       # 🤖 Your Telegram logic
│   └── __init__.py
├── packages/valory/
│   ├── agents/pett_agent/    # 📦 Agent config
│   └── services/pett_agent/  # 🚀 Service config
├── Dockerfile               # 🐳 Docker build
├── requirements.txt         # 📋 Dependencies
├── build_and_test.sh        # 🔨 Build script
└── test_agent.py           # 🧪 Test script
```

## 🚀 Quick Start

### 1. **Setup Environment**

```bash
# Copy environment template
cp .env.example .env

# Edit with your values
nano .env
```

### 2. **Add Your Private Key**

```bash
# Add your ethereum private key
echo "your_private_key_here" > ethereum_private_key.txt
```

### 3. **Build & Test**

```bash
# Install dependencies
pip install -r requirements.txt

# Run the agent locally
python run.py

# Or build and test with Docker
./build_and_test.sh
```

### 4. **Verify Olas Compliance**

```bash
# Test all Olas SDK requirements
python test_agent.py
```

## 🌐 **Endpoints**

- **Health Check**: `http://localhost:8716/healthcheck` - JSON with WebSocket & Pet status
- **Agent UI**: `http://localhost:8716/` - Beautiful dashboard with real-time status
- **API**: `POST http://localhost:8716/` (for commands)

### **Enhanced Dashboard Features**

- 🔌 **WebSocket Connection Status**: URL, connection state, authentication status
- 🐾 **Pet Connection Status**: Real-time pet health and connection status
- ⏱️ **Activity Monitoring**: Last activity timestamps and health metrics
- 🎨 **Visual Indicators**: Color-coded status (🟢 Connected, 🔴 Disconnected, 🟡 Limited)

## 🔧 **Environment Variables**

### Required by Olas SDK:

```bash
ETHEREUM_LEDGER_RPC=https://your-eth-rpc
GNOSIS_LEDGER_RPC=https://your-gnosis-rpc
SAFE_CONTRACT_ADDRESSES={"gnosis": "0xYourSafeAddress"}
CONNECTION_CONFIGS_CONFIG_SAFE_CONTRACT_ADDRESSES={"gnosis": "0xYourSafeAddress"}
```

### Your Pett Agent Variables:

```bash
TELEGRAM_BOT_TOKEN=your_telegram_token
PRIVY_TOKEN=your_privy_token
WEBSOCKET_URL=ws://localhost:3005
OPENAI_API_KEY=your_openai_key
LANGSMITH_API_KEY=your_langsmith_key
```

### Optional:

```bash
WITHDRAWAL_MODE=false
MY_API_KEY=your_custom_key
```

## 🐳 **Docker Deployment**

### Build Image (Olas naming convention):

```bash
# Format: <author_name>/oar-<agent_name>:<agent_package_hash>
docker build -t pettai/oar-pett_agent:0.1.0 .
```

### Run Container:

```bash
docker run -d \
  --name pett_agent \
  -p 8716:8716 \
  --env-file .env \
  -v "$(pwd)/ethereum_private_key.txt:/app/ethereum_private_key.txt" \
  pettai/oar-pett_agent:0.1.0
```

## 📤 **Deploy to Olas Network**

### 1. **Build Agent Configuration**

Follow: [Olas SDK Starter Guide](https://github.com/valory-xyz/olas-sdk-starter/blob/main/README.md)

### 2. **Mint Your Agent**

Follow: [Mint Agent Guide](https://stack.olas.network/olas-sdk/#step-3-mint-it)

### 3. **Deploy via Quickstart**

```bash
# Push to Docker Hub
docker push pettai/oar-pett_agent:0.1.0

# Clone quickstart
git clone https://github.com/valory-xyz/quickstart

# Add your config.json and run
./run_service.sh config_pett_agent.json
```

## 🧪 **Testing**

```bash
# Test Olas compliance
python test_agent.py

# Test enhanced UI with WebSocket & Pet status
python test_enhanced_ui.py

# Check health endpoint (now includes WebSocket & Pet info)
curl http://localhost:8716/healthcheck | jq

# View enhanced agent UI
open http://localhost:8716/

# Check logs
tail -f log.txt
```

### **Enhanced Health Check Response**

```json
{
  "status": "running",
  "seconds_since_last_transition": 45.2,
  "is_transitioning_fast": false,
  "websocket": {
    "url": "wss://petbot-monorepo-websocket-333713154917.europe-west1.run.app",
    "connected": true,
    "authenticated": true,
    "last_activity_seconds_ago": 12.5
  },
  "pet": {
    "connected": true,
    "status": "Active"
  },
  "timestamp": "2024-01-15T10:30:45.123456"
}
```

## 📋 **What Changed from Original**

✅ **Preserved**: All your original `pett_agent/` logic  
✅ **Added**: Olas SDK compliance layer (`olas_interface.py`)  
✅ **Added**: Health check and UI endpoints  
✅ **Added**: Proper logging format  
✅ **Added**: Environment variable handling  
✅ **Added**: Docker configuration

## 🔗 **Links**

- [Olas SDK Documentation](https://stack.olas.network/olas-sdk/)
- [Olas SDK Starter](https://github.com/valory-xyz/olas-sdk-starter)
- [Mint Agent Guide](https://stack.olas.network/olas-sdk/#step-3-mint-it)
- [Deploy Service Guide](https://stack.olas.network/olas-sdk/#step-4-execute-it)

---

🎉 **Your Pett Agent is now ready for the Olas network!**
