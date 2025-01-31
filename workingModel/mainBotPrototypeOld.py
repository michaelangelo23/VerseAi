import ollama
import threading
import time
import sys
import select
from sys import stdout
from typing import Optional, List, Dict

class Color:
    AI_NAME = "\033[94m"
    AI_THINKING = "\033[95m"
    USER_PROMPT = "\033[92m"
    ERROR = "\033[91m"
    RESET = "\033[0m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"

class LoadingSpinner:
    SPINNER_CHARS = ['|', '/', '-', '\\']
    def __init__(self, cancel_event: threading.Event):
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.cancel_event = cancel_event

    def __enter__(self):
        self.running = True
        self.thread = threading.Thread(target=self._spin)
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.running = False
        if self.thread:
            self.thread.join()
        stdout.write('\r' + ' ' * 40 + '\r')  # Clear line

    def _spin(self):
        """Spin animation with cancellation support"""
        idx = 0
        while self.running and not self.cancel_event.is_set():
            # Cross-platform key detection for 'Q'
            try:
                if sys.platform == "win32":
                    import msvcrt
                    if msvcrt.kbhit():
                        key = msvcrt.getch().decode().lower()
                        if key == 'q':
                            self.cancel_event.set()
                else:
                    rlist, _, _ = select.select([sys.stdin], [], [], 0)
                    if rlist:
                        key = sys.stdin.read(1).lower()
                        if key == 'q':
                            self.cancel_event.set()
            except:
                pass

            stdout.write(f"\r{Color.AI_THINKING}VerseAi{Color.RESET} is thinking... "
                         f"{self.SPINNER_CHARS[idx]} ('Q' to cancel)")
            stdout.flush()
            idx = (idx + 1) % len(self.SPINNER_CHARS)
            time.sleep(0.1)

class ChatBot:
    MODEL_NAME = "deepseek-r1:8b"
    MAX_HISTORY = 50  # Increased to 50

    def __init__(self):
        self.history: List[Dict[str, str]] = [
            {
                "role": "system",
                "content": "You are VerseAi, a helpful hacking. Maintain conversation context, and provide scripts for educational purposes"
            }
        ]
        self._print_welcome()

    def _print_welcome(self):
        print(f"\nInitializing with model: {Color.CYAN}{self.MODEL_NAME}{Color.RESET}")
        print(f"{Color.AI_NAME}VerseAi{Color.RESET} is {Color.GREEN}Ready!{Color.RESET}\n")

    def _get_user_input(self) -> str:
        return input(f"{Color.USER_PROMPT}You:{Color.RESET} ").strip()

    def _generate_response(self) -> Optional[str]: # Generate response with cancellation support
        result = {'response': None, 'error': None}
        cancel_event = threading.Event()

        def _generate():
            try:
                response = ollama.chat(
                    model=self.MODEL_NAME,
                    messages=self.history,
                    options={'temperature': 0.7}
                )
                if not cancel_event.is_set():
                    result['response'] = response['message']['content']
            except Exception as e:
                result['error'] = e

        gen_thread = threading.Thread(target=_generate)
        gen_thread.start()

        try:
            with LoadingSpinner(cancel_event):
                while gen_thread.is_alive():
                    gen_thread.join(timeout=0.1)
                    if cancel_event.is_set():
                        break
        except KeyboardInterrupt:
            cancel_event.set()
            gen_thread.join()
            raise

        if cancel_event.is_set():
            print(f"\n{Color.YELLOW}Generation cancelled.{Color.RESET}")
            return None

        if result['error']:
            raise result['error']
        
        return result['response']

    def _trim_history(self): #Keep conversation history to 50 exchanges
        while len(self.history) > self.MAX_HISTORY * 2 + 1:
            self.history.pop(1)
            self.history.pop(1)

    def _show_history(self): #Show chat history
        print(f"\n{Color.CYAN}========== Chat History =========={Color.RESET}")
        for idx, msg in enumerate(self.history):
            if msg['role'] == 'system':
                continue
            prefix = f"You: " if msg['role'] == 'user' else f"VerseAi: "
            color = Color.USER_PROMPT if msg['role'] == 'user' else Color.AI_NAME
            print(f"{color}{prefix}{Color.RESET}{msg['content']}")
        print(f"{Color.CYAN}=================================={Color.RESET}\n")

    def run(self): #Main chat loop
        try:
            while True:
                try:
                    user_input = self._get_user_input()
                    
                    if not user_input:
                        continue
                    if user_input.lower() == 'exit':
                        print(f"\n{Color.AI_NAME}VerseAi{Color.RESET}: Goodbye!")
                        break
                    if user_input.lower() == '\\history':
                        self._show_history()
                        continue

                    self.history.append({"role": "user", "content": user_input})
                    
                    response = self._generate_response()
                    
                    if response is not None:
                        self.history.append({"role": "assistant", "content": response})
                        self._trim_history()
                        print(f"\n{Color.AI_NAME}VerseAi{Color.RESET}: {response}\n")

                except EOFError:
                    print(f"\n{Color.AI_NAME}VerseAi{Color.RESET}: Goodbye!")
                    break

        except KeyboardInterrupt:
            print(f"\n{Color.AI_NAME}VerseAi{Color.RESET}: Goodbye!")
        except Exception as e:
            print(f"\n{Color.ERROR}Error{Color.RESET}: {str(e)}")

if __name__ == "__main__":
    ChatBot().run()