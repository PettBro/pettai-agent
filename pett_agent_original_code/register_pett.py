#!/usr/bin/env python3
"""
Pet Registration Script
Registers a new pet using Privy authentication via WebSocket.
This script is designed to run once to register a pet.
"""

import asyncio
import os
import sys
import json
import base64
from datetime import datetime
from dotenv import load_dotenv
from pett_websocket_client import PettWebSocketClient
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def decode_jwt_payload(token):
    """Decode JWT payload to check expiration."""
    try:
        # Split the token and get the payload part
        parts = token.split('.')
        if len(parts) != 3:
            return None
        
        # Decode the payload
        payload = parts[1]
        # Add padding if needed
        payload += '=' * (4 - len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception as e:
        logger.error(f"Error decoding JWT: {e}")
        return None

def validate_token(token):
    """Validate the Privy token and check if it's expired."""
    payload = decode_jwt_payload(token)
    if not payload:
        logger.error("❌ Invalid JWT token format")
        return False
    
    # Check expiration
    exp = payload.get('exp')
    if exp:
        exp_time = datetime.fromtimestamp(exp)
        current_time = datetime.now()
        
        if current_time > exp_time:
            logger.error(f"❌ Token expired at {exp_time}")
            logger.error(f"Current time: {current_time}")
            return False
        else:
            logger.info(f"✅ Token is valid until {exp_time}")
    
    # Log token info for debugging
    logger.info(f"Token payload: {json.dumps(payload, indent=2)}")
    return True

def load_environment():
    """Load environment variables from .env file."""
    load_dotenv()
    
    privy_token = os.getenv('PRIVY_TOKEN')
    if not privy_token:
        logger.error("PRIVY_TOKEN not found in .env file")
        sys.exit(1)
    
    # Validate the token
    if not validate_token(privy_token):
        logger.error("❌ Token validation failed")
        sys.exit(1)
    
    return privy_token

async def register_pet(pet_name: str, privy_token: str):
    """
    Register a new pet using Privy authentication.
    
    Args:
        pet_name (str): Name of the pet to register
        privy_token (str): Privy authentication token
    """
    client = PettWebSocketClient()
    registration_success = False
    registration_error = None
    
    # Create a custom message handler for registration responses
    async def handle_registration_response(message):
        nonlocal registration_success, registration_error
        message_type = message.get("type")
        
        logger.info(f"📨 Received message: {json.dumps(message, indent=2)}")
        
        if message_type == "auth_result":
            success = message.get("success", False)
            
            if success:
                registration_success = True
                logger.info("✅ Registration successful!")
                user_data = message.get("user", {})
                
                # Log user information
                user_id = user_data.get("id", "Unknown")
                user_name = user_data.get("name", "Unknown")
                username = user_data.get("username", "Unknown")
                telegram_id = user_data.get("telegramId", "Unknown")
                
                logger.info(f"User ID: {user_id}")
                logger.info(f"User Name: {user_name}")
                logger.info(f"Username: {username}")
                logger.info(f"Telegram ID: {telegram_id}")
                
                # Log pet information
                pets = user_data.get("pets", [])
                if pets:
                    pet = pets[0]
                    pet_id = pet.get("id", "Unknown")
                    pet_name = pet.get("name", "Unknown")
                    current_hotel_tier = pet.get("currentHotelTier", 0)
                    balance = pet.get("balance", "0")
                    
                    logger.info(f"Pet registered: {pet_name}")
                    logger.info(f"Pet ID: {pet_id}")
                    logger.info(f"Hotel Tier: {current_hotel_tier}")
                    logger.info(f"Balance: {balance}")
                    
                    # Log pet stats if available
                    pet_stats = pet.get("PetStats", {})
                    if pet_stats:
                        logger.info("Pet Stats:")
                        logger.info(f"Hunger: {pet_stats.get('hunger', 'Unknown')}")
                        logger.info(f"Health: {pet_stats.get('health', 'Unknown')}")
                        logger.info(f"Energy: {pet_stats.get('energy', 'Unknown')}")
                        logger.info(f"Happiness: {pet_stats.get('happiness', 'Unknown')}")
                        logger.info(f"Hygiene: {pet_stats.get('hygiene', 'Unknown')}")
            else:
                error = message.get("error", "Unknown error")
                registration_error = error
                logger.error(f"❌ Registration failed: {error}")
        
        elif message_type == "error":
            error_msg = message.get("data", {}).get("error", "Unknown error")
            registration_error = error_msg
            logger.error(f"❌ Server error: {error_msg}")
    
    # Register the custom handler
    client.register_message_handler("auth_result", handle_registration_response)
    client.register_message_handler("error", handle_registration_response)
    
    try:
        # Connect to WebSocket
        logger.info("🔌 Connecting to WebSocket server...")
        if not await client.connect():
            logger.error("❌ Failed to connect to WebSocket server")
            return False
        
        # Register the pet
        logger.info(f"🐾 Registering pet: {pet_name}")
        logger.info("📤 Sending registration request...")
        
        # Log the exact message being sent
        registration_message = {
            "type": "REGISTER",
            "data": {
                "params": {
                    "registerHash": {
                        "name": pet_name,
                        "hash": f"Bearer {privy_token}"
                    },
                    "authType": "privy"
                }
            }
        }

        logger.info(f"📤 Sending message: {json.dumps(registration_message, indent=2)}")
        
        success = await client.register_privy(pet_name, f"Bearer {privy_token}")
        
        if success:
            logger.info("📨 Registration request sent successfully")
            logger.info("⏳ Waiting for server response...")
            
            # Listen for response with timeout
            try:
                await asyncio.wait_for(client.listen_for_messages(), timeout=30.0)
            except asyncio.TimeoutError:
                logger.error("⏰ Timeout waiting for registration response")
                return False
            
            # Check registration result
            if registration_success:
                logger.info("🎉 Pet registration completed successfully!")
                return True
            elif registration_error:
                logger.error(f"❌ Registration failed: {registration_error}")
                return False
            else:
                logger.warning("⚠️ No clear response received from server")
                return False
        else:
            logger.error("❌ Failed to send registration request")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error during registration: {e}")
        return False
    finally:
        # Disconnect from WebSocket
        await client.disconnect()
        logger.info("🔌 WebSocket connection closed")

def main():
    """Main function to run the registration script."""
    print("🐾 Pet Registration Script")
    print("=" * 40)
    
    # Load environment variables
    privy_token = load_environment()
    logger.info("✅ Environment variables loaded successfully")
    
    # Get pet name from user input
    pet_name = input("Enter pet name: ").strip()
    if not pet_name:
        logger.error("❌ Pet name cannot be empty")
        sys.exit(1)
    
    print(f"\n🐾 Registering pet: {pet_name}")
    print("Please wait...")
    
    # Run the registration
    success = asyncio.run(register_pet(pet_name, privy_token))
    
    if success:
        print("\n🎉 Registration completed successfully!")
        print("You can now use your pet in the Pett.ai application.")
    else:
        print("\n❌ Registration failed!")
        print("Please check your Privy token and try again.")
        print("Note: The token might be expired or invalid.")
        sys.exit(1)

if __name__ == "__main__":
    main()
