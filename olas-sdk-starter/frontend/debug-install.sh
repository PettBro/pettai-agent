#!/bin/bash

echo "🔍 Debugging React Frontend Setup..."
echo ""

# Check if we're in the right directory
if [ ! -f "package.json" ]; then
    echo "❌ Error: package.json not found. Run this from the frontend directory."
    exit 1
fi

echo "📦 Installing dependencies..."
npm install

echo ""
echo "🎨 Checking Tailwind CSS setup..."

# Check if tailwind.config.js exists
if [ -f "tailwind.config.js" ]; then
    echo "✅ tailwind.config.js exists"
else
    echo "❌ tailwind.config.js missing"
fi

# Check if postcss.config.js exists
if [ -f "postcss.config.js" ]; then
    echo "✅ postcss.config.js exists"
else
    echo "❌ postcss.config.js missing"
fi

# Check .env file
echo ""
echo "🔐 Checking .env configuration..."
if [ -f ".env" ]; then
    echo "✅ .env file exists"
    if grep -q "REACT_APP_PRIVY_APP_ID" .env; then
        echo "✅ REACT_APP_PRIVY_APP_ID is set"
    else
        echo "⚠️  REACT_APP_PRIVY_APP_ID not found in .env"
    fi
else
    echo "⚠️  .env file not found, creating default..."
    cat > .env << 'EOF'
REACT_APP_PRIVY_APP_ID=cm7gev5s600vbk2lsj6e1e9g7
PORT=3000
BROWSER=none
GENERATE_SOURCEMAP=false
EOF
    echo "✅ Created .env with default settings"
fi

echo ""
echo "🚀 Attempting to start React dev server..."
echo "   Press Ctrl+C to stop"
echo ""

npm start

