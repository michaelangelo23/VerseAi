import asyncio
import logging
from aioconsole import ainput
from locali import LocalI
from config import DEFAULT_API_URL, DEFAULT_MODEL_NAME_1B, DEFAULT_MODEL_NAME_3B
from conversation import Conversation

def get_model_name_from_user() -> str:
    while True:
        try:
            print("Select model parameter to use:")
            print("(1) 1B")
            print("(2) 3B")
            model_param = input("Choose what parameter to use: ").strip()
            if model_param == "1":
                return DEFAULT_MODEL_NAME_1B
            elif model_param == "2":
                return DEFAULT_MODEL_NAME_3B
            else:
                print("Invalid input. Please enter '1' or '2'.")
        except EOFError:
            print("\nEOF received.\nExiting...")
            exit(0)

def handle_keyboard_interrupt() -> bool:
    confirm_exit = input("\nDo you really want to stop the program? (yes/no): ").strip().lower()
    if confirm_exit == 'yes':
        print("Exiting...")
        return True
    return False

async def main() -> None:
    model_name = get_model_name_from_user()
    api_url = DEFAULT_API_URL
    conversation = Conversation()

    try:
        async with LocalI(model_name, api_url, conversation) as assistant:
            while True:
                try:
                    user_input = await ainput("Enter your prompt (or 'quit' to exit): ")
                    if user_input.lower() == 'quit':
                        break

                    print("Assistant: ", end="", flush=True)
                    async for text_chunk in assistant.generate_text(user_input):
                        print(text_chunk, end="", flush=True)
                    print()
                except KeyboardInterrupt:
                    if handle_keyboard_interrupt():
                        break
    except asyncio.CancelledError:
        logging.info("Event loop was cancelled.")
    except KeyboardInterrupt:
        if handle_keyboard_interrupt():
            pass
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
    finally:
        logging.info("Shutting down...")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("\nProgram interrupted by user.")