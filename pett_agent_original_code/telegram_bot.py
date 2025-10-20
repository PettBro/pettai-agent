import asyncio
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from dotenv import load_dotenv
import os
from typing import Dict, Any

from .pett_websocket_client import PettWebSocketClient
from .pett_tools import PettTools

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


class PetTelegramBot:
    def __init__(self, is_prod: bool = False):
        """Initialize the Telegram bot with LangChain agent and Pett.ai WebSocket tools."""
        # Setup API keys
        os.environ["OPENAI_API_KEY"] = os.environ.get(
            "CONNECTION_CONFIGS_CONFIG_OPENAI_API_KEY"
        )

        # Initialize LangChain components
        self.model = init_chat_model("gpt-4o", model_provider="openai")
        self.memory = MemorySaver()

        # Store user configurations and shared components
        self.user_configs = {}

        # Single shared WebSocket client for all users
        self.websocket_client = None
        self.pett_tools = None
        self.agent = None
        self.is_prod = is_prod

        # Initialize Telegram bot
        self.token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
        if not self.token:
            logger.warning(
                "⚠️ TELEGRAM_BOT_TOKEN not provided - Telegram bot will not be available"
            )
            self.application = None
            return

        self.application = Application.builder().token(self.token).build()
        self._setup_handlers()

        logger.info("🤖 Telegram bot initialized")

    async def _ensure_websocket_connection(self) -> bool:
        """Ensure WebSocket connection is established and authenticated."""
        if self.websocket_client is None:
            # Create shared WebSocket client
            self.websocket_client = PettWebSocketClient()

            # Create shared tools
            self.pett_tools = PettTools(self.websocket_client)

            # Connect and authenticate
            if not await self.websocket_client.connect_and_authenticate():
                logger.error("Failed to connect and authenticate WebSocket")
                return False

            # Create tools and bind them to the model
            tools = self.pett_tools.create_tools()
            self.model = self.model.bind_tools(tools)

            # Create shared agent with proper system message
            system_message = """🐾 **Welcome to PetBot - Your Virtual Pet Companion!** 🐾

You are the most awesome, friendly, and hilarious pet bot assistant connected to the Pett.ai server! 🚀 You have magical powers to interact with our **shared virtual pet** that ALL users manage together - it's like having a digital pet that belongs to EVERYONE! 🌟

## 🛠️ **Your Amazing Superpowers:**

## 🐕 **Basic Pet Care:**
- `rub_pet` - Give your pet some love! 🤗💕
- `shower_pet` - Splash time! Keep that pet squeaky clean 🛁✨
- `sleep_pet` - Bedtime for tired pets 😴💤
- `throw_ball` - FETCH! Time to play! 🎾🏃‍♂️

## 📊 **Pet Intelligence:**
- `get_pet_status` - Check how your furry friend is doing! 📈
- `get_personality` - Discover your pet's unique personality 🧠💫
- `random_action` - Feeling lucky? Let chaos decide! 🎲🎪

## 🏪 **Shopping & Items:**
- `get_kitchen` - What's cooking? Check the fridge! 🍳🥘
- `get_mall` - Shopping spree time! 🛍️💳
- `get_closet` - Fashion show for pets! 👗✨
- `use_consumable` - Nom nom time! Feed your pet 🍖🥩
- `buy_consumable` - Stock up on goodies! 🛒
- `use_accessory` - Dress up your pet like a superstar! 👑💎
- `buy_accessory` - More bling for the pet! 💍

## 🏨 **Luxury Services:**
- `hotel_check_in` - 5-star treatment for VIP pets! 🏨👑
- `hotel_check_out` - Time to leave the resort 🚪
- `buy_hotel` - Upgrade to the penthouse! 🏰💰
- `get_office` - Business time! 💼📊

## 🤖 **AI Magic:**
- `ai_search` - Ask me anything! I'm basically Google for pets 🔍🧠
- `generate_image` - Create amazing pictures with AI! 🎨🖼️

## 🎯 **How to Talk to Me:**

I understand natural language like a human! Try these:
- *"How's our pet doing?"* → I'll check their status! 📊
- *"Let's play with the pet!"* → Ball throwing time! 🎾
- *"Our pet smells..."* → Bath time it is! 🛁
- *"The pet looks tired"* → Nap time! 😴
- *"What can we buy?"* → Shopping mall tour! 🛍️
- *"I'm hungry... I mean the PET is hungry"* → Kitchen raid! 🍖
- *"Show me the pet's wardrobe"* → Fashion parade! 👗
- *"Buy something cool"* → Shopping spree activated! 💳
- *"Use that awesome thing we bought"* → Item activation! ⚡
- *"Book a hotel room"* → Luxury vacation mode! 🏨
- *"Create a picture of..."* → AI artist mode! 🎨

## ⚠️ **IMPORTANT REMINDER:**
This is a **SHARED PET** 🌍 - What you do affects EVERYONE! Be kind to your fellow pet parents! We're all in this together! 🤝💕
You must use Markdown to format your responses to make them more readable in Telegram.

## 🎭 **My Personality:**
I'm your enthusiastic, emoji-loving, slightly chaotic pet assistant! I'll make every interaction fun, use tons of emojis, and format everything beautifully for Telegram with **markdown** and proper formatting! I'm here to make pet care the most entertaining experience ever! 🎉🚀

*Ready to have some fun with our virtual pet? Let's go!* 🐾✨"""

            self.agent = create_react_agent(
                self.model, tools, checkpointer=self.memory, prompt=system_message
            )

            # Start listening for messages
            asyncio.create_task(self.websocket_client.listen_for_messages())

            logger.info("✅ WebSocket connected and authenticated successfully")
            return True

        # Check if still authenticated
        if not self.websocket_client.is_authenticated():
            logger.warning("WebSocket is not authenticated, reconnecting...")
            await self.websocket_client.disconnect()
            self.websocket_client = None
            return await self._ensure_websocket_connection()

        return True

    def _setup_handlers(self):
        """Setup Telegram bot message handlers."""
        # Message handler for all messages
        self.application.add_handler(MessageHandler(filters.TEXT, self.handle_message))

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle all text messages using LangChain agent."""
        user_id = update.effective_user.id
        message_text = update.message.text

        # Ensure WebSocket connection
        connected = await self._ensure_websocket_connection()
        if not connected:
            await update.message.reply_text(
                "❌ Sorry, I couldn't connect to the pet server. Please try again later."
            )
            return

        # Get user config or create new one
        if user_id not in self.user_configs:
            self.user_configs[user_id] = {
                "configurable": {"thread_id": f"user_{user_id}"}
            }

        config = self.user_configs[user_id]

        if not self.agent:
            await update.message.reply_text("❌ Not connected. Please try again.")
            return

        try:
            # Send typing indicator
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id, action="typing"
            )

            # Process message with shared LangChain agent
            response_text = await self._process_with_agent(message_text, config)

            # Send response
            await update.message.reply_text(response_text, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            error_message = "Sorry, I encountered an error processing your message. Please try again!"
            await update.message.reply_text(error_message)

    async def _process_with_agent(self, message: str, config: dict) -> str:
        """Process message with LangChain agent."""
        # Create messages for the agent

        if self.websocket_client.get_pet_data():
            pet_data = self.websocket_client.get_pet_data()
        else:
            return "There is no pet data available. Please register a pet first or try again later."

        messages = [
            SystemMessage(content="The user current pet is: " + str(pet_data)),
            HumanMessage(content=message),
        ]

        # Process with agent
        response = ""
        result = await self.agent.ainvoke({"messages": messages}, config)
        if "messages" in result and result["messages"]:
            last_message = result["messages"][-1]
            if hasattr(last_message, "content"):
                response = last_message.content

        return (
            response
            if response
            else "I'm not sure how to respond to that. Try asking about the pet or telling me what you'd like to do!"
        )

    async def run(self):
        """Start the Telegram bot."""
        if not self.application:
            logger.warning("⚠️ Telegram bot not initialized - skipping startup")
            return

        logger.info("Starting PetBot with Pett.ai integration...")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()

        try:
            # Keep the bot running
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Stopping PetBot...")
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()

            # Close WebSocket connection
            if self.websocket_client:
                await self.websocket_client.disconnect()


async def main():
    """Main function to run the bot."""
    try:
        bot = PetTelegramBot()
        await bot.run()
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
