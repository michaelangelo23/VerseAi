import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from locali import LocalI
from config import DEFAULT_API_URL, DEFAULT_MODEL_NAME_1B, DEFAULT_MODEL_NAME_3B

def get_model_name_from_user() -> str:
    while True:
        model_param = input("Select model parameter to use (1B or 3B): ").strip()
        if model_param == "1B":
            return DEFAULT_MODEL_NAME_1B
        elif model_param == "3B":
            return DEFAULT_MODEL_NAME_3B
        else:
            print("Invalid input. Please enter '1B' or '3B'.")

async def main() -> None:
    model_name = get_model_name_from_user()
    api_url = DEFAULT_API_URL

    try:
        async with LocalI(model_name, api_url) as assistant:
            with ThreadPoolExecutor() as executor:
                while True:
                    try:
                        user_input = await asyncio.get_event_loop().run_in_executor(
                            executor, input, "Enter your prompt (or 'quit' to exit): "
                        )
                        if user_input.lower() == 'quit':
                            break

                        print("Assistant: ", end="", flush=True)
                        async for text_chunk in assistant.generate_text(user_input):
                            print(text_chunk, end="", flush=True)
                        print()
                    except KeyboardInterrupt:
                        confirm_exit = input("\nDo you really want to stop the program? (yes/no): ").strip().lower()
                        if confirm_exit == 'yes':
                            print("Exiting...")
                            break
    except KeyboardInterrupt:
        confirm_exit = input("\nDo you really want to stop the program? (yes/no): ").strip().lower()
        if confirm_exit == 'yes':
            print("Exiting...")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())