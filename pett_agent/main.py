import os
import asyncio
from dotenv import load_dotenv
import logging
from pett_agent.telegram_bot import PetTelegramBot

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


async def main():
    """Main function to run both Telegram bot and agent loop."""
    logger.info("Starting Pett Agent application")

    # Check if we should run in Telegram bot mode
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    is_prod = os.environ.get("NODE_ENV") == "production"

    if telegram_token:
        logger.info("Telegram bot token found, initializing Telegram bot mode")
        try:
            # Initialize and run Telegram bot
            logger.info("Creating PetTelegramBot instance")
            bot = PetTelegramBot()
            logger.info("Telegram bot initialized successfully")

            # Run Telegram bot (it handles its own WebSocket connections per user)
            logger.info("Starting Telegram bot event loop")
            await bot.run()

        except Exception as e:
            logger.error(f"Error running Telegram bot: {e}", exc_info=True)
            raise
    else:
        logger.warning("No Telegram bot token found in environment variables")
        logger.info("Running in agent loop only mode")
        # TODO: Implement standalone agent loop functionality


if __name__ == "__main__":
    try:
        logger.info("Application startup initiated")
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application shutdown requested by user")
    except Exception as e:
        logger.critical(
            f"Critical error during application startup: {e}", exc_info=True
        )
        raise
    finally:
        logger.info("Application shutdown complete")
