# 🚀 ABCI Pett Agent - Olas Network Deployment Guide

This guide explains how to deploy your Pett Agent to the Olas Network using the ABCI (Application Blockchain Interface) framework.

## 🎯 What We've Built

Your existing Pett Agent has been **wrapped** with ABCI components to make it compatible with the Olas Network while **preserving all your original functionality**:

```
┌─────────────────────────────────────┐
│          ABCI Framework             │ ← New ABCI wrapper
├─────────────────────────────────────┤
│ handlers.py  ← Handle external msgs │
│ behaviours.py ← Orchestrate actions │
│ rounds.py    ← Define state machine │
│ models.py    ← Manage shared state  │
│ external_interface.py ← Bridge      │
└─────────────────────────────────────┘
         │ (wraps & preserves)
         ▼
┌─────────────────────────────────────┐
│       Your Original Logic           │ ← Unchanged!
├─────────────────────────────────────┤
│ pett_websocket_client.py            │
│ pett_tools.py                       │
│ telegram_bot.py                     │
│ main.py                             │
└─────────────────────────────────────┘
```

## 🔧 Key Components

### **1. ABCI Wrapper Components** (New)

- **`handlers.py`** - Now handles external messages (HTTP, webhooks, etc.)
- **`behaviours.py`** - Orchestrates your pet actions using your existing WebSocket client
- **`rounds.py`** - Defines the state machine for ABCI consensus
- **`models.py`** - Enhanced to manage ABCI shared state + your WebSocket client
- **`external_interface.py`** - Bridges external requests with ABCI state machine
- **`main_abci.py`** - ABCI-compatible entry point

### **2. Your Original Components** (Preserved)

- **`pett_websocket_client.py`** - ✅ Unchanged - still handles Pett.ai API
- **`pett_tools.py`** - ✅ Unchanged - still provides pet interaction tools
- **`telegram_bot.py`** - ✅ Unchanged - still handles Telegram integration
- **`main.py`** - ✅ Unchanged - still works for standalone mode

## 🚀 Deployment Options

### **Option 1: Quick Deployment (Recommended)**

Use the provided deployment script:

```bash
# Make script executable (if not already)
chmod +x deploy_olas.sh

# Run interactive deployment
./deploy_olas.sh

# Or run specific steps
./deploy_olas.sh full    # Complete deployment
./deploy_olas.sh deploy  # Just deploy
./deploy_olas.sh status  # Check status
```

### **Option 2: Manual Deployment**

Follow the [Olas deployment guide](https://stack.olas.network/open-autonomy/guides/deploy_service/):

```bash
# 1. Check requirements
autonomy --version
docker --version

# 2. Set up environment
export ALL_PARTICIPANTS='[
    "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65",
    "0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc",
    "0x976EA74026E726554dB657fA54763abd0C3a0aa9",
    "0x14dC79964da2C08b23698B3D3cc7Ca32193d9955"
]'

# 3. Build the deployment
rm -rf abci_build_*
autonomy deploy build keys.json -ltm

# 4. Deploy locally
cd abci_build_*
autonomy deploy run
```

## 🔑 Keys Configuration

### **For Testing** (keys.json)

The script generates example keys automatically. **⚠️ These are for testing only!**

### **For Production**

Replace `keys.json` with your actual wallet keys:

```json
[
  {
    "address": "0xYourAddress1",
    "private_key": "0xYourPrivateKey1"
  },
  {
    "address": "0xYourAddress2",
    "private_key": "0xYourPrivateKey2"
  }
]
```

## 🌐 Network Deployment

### **Local Testing**

```bash
# Deploy locally for testing
./deploy_olas.sh deploy
```

### **Olas Network (Production)**

Follow the [Olas publishing guide](https://stack.olas.network/open-autonomy/guides/publish_mint_packages/):

```bash
# 1. Publish packages to registry
autonomy push-all

# 2. Mint service on-chain
autonomy mint service

# 3. Deploy to Olas network
autonomy deploy build keys.json --use-mode
```

## 📊 Monitoring & Management

### **Check Status**

```bash
# Using script
./deploy_olas.sh status

# Manual Docker commands
docker ps | grep abci
docker logs <container_name>
```

### **View Logs**

```bash
# Agent logs
docker logs <agent_container> --follow

# Tendermint logs
docker logs <tendermint_container> --follow
```

### **Stop Services**

```bash
# Stop all containers
docker ps | grep abci | awk '{print $1}' | xargs docker stop

# Or use script
./deploy_olas.sh clean
```

## 🔄 How It Works

### **1. External Request Flow**

```
User Request → Handler → Shared State → Behaviour → Your WebSocket Client → Pett.ai
```

### **2. ABCI Consensus Flow**

```
Agent 1 ─┐
Agent 2 ─┼─→ Consensus ─→ State Update ─→ Pet Action
Agent 3 ─┘
```

### **3. Integration Points**

**Your Original Logic** remains unchanged:

- Telegram bot still handles user messages
- WebSocket client still connects to Pett.ai
- Pet tools still provide action methods

**ABCI Wrapper** adds:

- Multi-agent consensus
- Blockchain integration
- Olas network compatibility
- State machine management

## 🎯 Benefits of ABCI Deployment

### **1. Monetization**

- Deploy on Olas Network for potential rewards
- Participate in the autonomous agent economy

### **2. Decentralization**

- Multi-agent consensus for reliability
- No single point of failure

### **3. Blockchain Integration**

- On-chain transactions
- Cryptographic verification
- Transparent operations

### **4. Scalability**

- Professional-grade infrastructure
- Load distribution across agents

## 🛠️ Development Workflow

### **1. Test Locally First**

```bash
# Test your original agent
python3 pett_agent/main.py

# Test ABCI version locally
./deploy_olas.sh full
```

### **2. Deploy to Olas**

```bash
# When ready for production
autonomy push-all
autonomy mint service
```

### **3. Monitor & Iterate**

```bash
# Check performance
./deploy_olas.sh status

# Update and redeploy
./deploy_olas.sh clean
./deploy_olas.sh full
```

## 🔧 Troubleshooting

### **Common Issues**

1. **Connection Failed**

   ```bash
   # Check environment variables
   echo $PRIVY_TOKEN
   echo $WEBSOCKET_URL
   ```

2. **Docker Issues**

   ```bash
   # Restart Docker
   docker system prune -f
   ./deploy_olas.sh clean
   ```

3. **Consensus Problems**

   ```bash
   # Check all agents are running
   docker ps | grep abci

   # Check Tendermint connectivity
   docker logs <tendermint_container>
   ```

### **Getting Help**

- **Olas Documentation**: https://stack.olas.network/
- **GitHub Issues**: Create issues in your repo
- **Community**: Join Olas developer community

## 📈 Next Steps

1. **✅ Deploy locally** - Test the ABCI integration
2. **✅ Monitor performance** - Ensure everything works
3. **🚀 Deploy to Olas** - Go live on the network
4. **💰 Start earning** - Participate in the agent economy

---

**🎉 Congratulations!** Your Pett Agent is now ready for the Olas Network while keeping all your original functionality intact!
