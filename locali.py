import json
import logging
from typing import AsyncGenerator, Optional
import aiohttp
from conversation import Conversation

class LocalI:
    def __init__(self, model_name: str, api_url: str, conversation: Conversation):
        self.model_name = model_name
        self.api_url = api_url
        self.conversation = conversation
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self) -> 'LocalI':
        self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._session:
            await self._session.close()

    async def generate_text(self, prompt: str) -> AsyncGenerator[str, None]:
        self.conversation.add_message("user", prompt)
        if not self._session:
            raise RuntimeError("Session not initialized. Use 'async with' context manager.")

        data = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": True,
            "history": self.conversation.get_history()
        }

        try:
            async with self._session.post(self.api_url, json=data) as response:
                response.raise_for_status()
                async for line in response.content:
                    if line:
                        try:
                            json_line = json.loads(line)
                            if 'response' in json_line:
                                self.conversation.add_message("assistant", json_line['response'])
                                yield json_line['response']
                        except json.JSONDecodeError:
                            logging.error(f"Error decoding JSON: {line.decode('utf-8')}")
        except aiohttp.ClientError as e:
            logging.error(f"HTTP request failed: {e}")
        except Exception as e:
            logging.error(f"Unexpected error: {e}")