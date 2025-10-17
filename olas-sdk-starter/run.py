#!/usr/bin/env python3
"""
Olas SDK Entry Point for Pett Agent
Compliant with: https://stack.olas.network/olas-sdk/#step-1-build-the-agent-supporting-the-following-requirements
"""

import os
import sys
import asyncio
import logging
from pathlib import Path
from typing import Optional

# Add the current directory to Python path for local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent.olas_interface import OlasInterface
from agent.pett_agent import PettAgent


def setup_olas_logging() -> logging.Logger:
    """Set up logging according to Olas SDK requirements.

    Format: [YYYY-MM-DD HH:MM:SS,mmm] [LOG_LEVEL] [agent] Your message
    """
    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)

    # Configure logging with Olas required format
    log_format = "[%(asctime)s] [%(levelname)s] [agent] %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Configure root logger
    logging.basicConfig(
        level=logging.DEBUG,
        format=log_format,
        datefmt=date_format,
        handlers=[
            # File handler for log.txt (required by Olas)
            logging.FileHandler("log.txt", mode="a"),
            # Console handler for development
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Configure specific logger for our agent
    logger = logging.getLogger("pett_agent")
    logger.setLevel(logging.DEBUG)

    return logger


def read_ethereum_private_key() -> Optional[str]:
    """Read ethereum private key from ethereum_private_key.txt (Olas SDK requirement)."""
    try:
        key_file = Path("ethereum_private_key.txt")
        if key_file.exists():
            with open(key_file, "r") as f:
                return f.read().strip()
        else:
            logging.warning("ethereum_private_key.txt not found in working directory")
            return None
    except Exception as e:
        logging.error(f"Failed to read ethereum_private_key.txt: {e}")
        return None


def check_withdrawal_mode() -> bool:
    """Check if agent should run in withdrawal mode (Olas SDK requirement)."""
    return False


async def main():
    """Main entry point for the Pett Agent."""
    logger = setup_olas_logging()
    logger.info("🚀 Starting Pett Agent with Olas SDK compliance")

    try:
        # Read Olas SDK required configurations
        ethereum_private_key = read_ethereum_private_key()
        withdrawal_mode = check_withdrawal_mode()

        # Log configuration
        logger.info(
            f"Ethereum private key: {'Found' if ethereum_private_key else 'Not found'}"
        )
        logger.info(f"Withdrawal mode: {withdrawal_mode}")

        # Initialize Olas interface layer
        olas_interface = OlasInterface(
            ethereum_private_key=ethereum_private_key,
            withdrawal_mode=withdrawal_mode,
            logger=logger,
        )

        # Initialize your Pett Agent with existing logic
        pett_agent = PettAgent(olas_interface=olas_interface, logger=logger)

        # Start the agent
        await pett_agent.run()

    except KeyboardInterrupt:
        logger.info("🛑 Agent shutdown requested by user")
    except Exception as e:
        logger.error(f"💥 Critical error in Pett Agent: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Agent stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"💥 Fatal error: {e}")
        sys.exit(1)
