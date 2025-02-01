import ollama
import threading
import time
import sys
import select
import os
import json
from sys import stdout
from typing import Optional, List, Dict, Tuple
import psutil
import platform
import subprocess
from enum import Enum
import shutil
from pathlib import Path

class Color:
    AI_NAME = "\033[94m"
    AI_THINKING = "\033[95m"
    USER_PROMPT = "\033[92m"
    ERROR = "\033[91m"
    RESET = "\033[0m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    ORANGE = "\033[38;5;214m"
    MAGENTA = "\033[35m"

class Command(Enum):
    EXIT = "exit"
    HISTORY = "history"
    SAVE = "save"
    LOAD = "load"
    HELP = "help"
    CLEAR = "clear"
    MODEL = "model"
    STATS = "stats"

class LoadingSpinner:
    SPINNER_CHARS = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
    def __init__(self, cancel_event: threading.Event):
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.cancel_event = cancel_event
        self.start_time = 0

    def __enter__(self):
        if sys.stderr.isatty():
            self.running = True
            self.start_time = time.time()
            self.thread = threading.Thread(target=self._spin)
            self.thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.running = False
        if self.thread:
            self.thread.join()
        if sys.stderr.isatty():
            stdout.write('\r' + ' ' * shutil.get_terminal_size().columns + '\r')

    def _spin(self):
        idx = 0
        while self.running and not self.cancel_event.is_set():
            self._check_cancel()
            elapsed = time.time() - self.start_time
            spinner = f"\r{Color.AI_THINKING}Thinking {self.SPINNER_CHARS[idx]} ({elapsed:.1f}s){Color.RESET}"
            stdout.write(spinner)
            stdout.flush()
            idx = (idx + 1) % len(self.SPINNER_CHARS)
            time.sleep(0.1)

    def _check_cancel(self):
        if sys.platform == "win32":
            import msvcrt
            if msvcrt.kbhit():
                if msvcrt.getch().decode().lower() == 'q':
                    self.cancel_event.set()
        else:
            rlist, _, _ = select.select([sys.stdin], [], [], 0)
            if rlist and sys.stdin.read(1).lower() == 'q':
                self.cancel_event.set()

class ChatBot:
    DEFAULT_MODEL = "llama3.2:latest"
    MAX_HISTORY = 50
    SESSION_DIR = Path.home() / ".verseai_sessions"

    def __init__(self):
        self.history: List[Dict[str, str]] = []
        self._init_history()
        self.model = self.DEFAULT_MODEL
        self._ensure_session_dir()
        self.system_info = SystemMonitor()
        self._current_metrics: List[Dict] = []

    def _init_history(self):
        self.history = [{
            "role": "system",
            "content": (
                # "You are VerseAi, a cybersecurity expert assistant. Provide concise, "
                # "actionable advice. Always explain security concepts clearly. "
                # "Verify information when uncertain."
                "Summarize each output, no more redundant explanation."
                "Explain the request briefly and accurately with related information."
            )
        }]

    def _ensure_session_dir(self):
        self.SESSION_DIR.mkdir(exist_ok=True, parents=True)

    def _print_welcome(self):
        self.system_info.print_system_status()
        print(f"\n{Color.CYAN}Initialized model:{Color.RESET} {self.model}")
        print(f"{Color.GREEN}Available commands:{Color.RESET}")
        self._print_help()
        print(f"\n{Color.AI_NAME}VerseAi{Color.RESET} {Color.GREEN}ready!{Color.RESET}\n")

    def _handle_command(self, command: str) -> bool:
        cmd, *args = command[1:].split(maxsplit=1)
        args = args[0] if args else ""
        
        try:
            cmd_enum = Command(cmd.lower())
            {
                Command.EXIT: lambda _: self._exit(),
                Command.HISTORY: lambda _: self._show_history(),
                Command.SAVE: lambda a: self._save_session(a),
                Command.LOAD: lambda a: self._load_session(a),
                Command.HELP: lambda _: self._print_help(),
                Command.CLEAR: lambda _: self._clear_history(),
                Command.MODEL: lambda a: self._change_model(a),
                Command.STATS: lambda _: self.system_info.print_system_status(),
            }[cmd_enum](args)
            return True
        except ValueError:
            print(f"{Color.ERROR}Unknown command: {cmd}{Color.RESET}")
            return True
        except KeyError:
            return False

    def _generate_response(self, cancel_event: threading.Event) -> Optional[str]:
        try:
            response = ollama.chat(
                model=self.model,
                messages=self.history,
                stream=False,
                options={'temperature': 0.7, 'num_ctx': 4096}
            )
            return response['message']['content']
        except ollama.ResponseError as e:
            print(f"{Color.ERROR}API Error: {e.error}{Color.RESET}")
        except Exception as e:
            print(f"{Color.ERROR}Generation error: {str(e)}{Color.RESET}")
        return None

    def _process_user_input(self, user_input: str):
        if user_input.startswith('\\'):
            return self._handle_command(user_input)
        
        self.history.append({"role": "user", "content": user_input})
        
        cancel_event = threading.Event()
        try:
            with LoadingSpinner(cancel_event):
                start_time = time.time()
                response = self._generate_response(cancel_event)
                elapsed = time.time() - start_time
                
                if response:
                    self.history.append({"role": "assistant", "content": response})
                    self._trim_history()
                    self._print_response(response, elapsed)
        except KeyboardInterrupt:
            cancel_event.set()
            print(f"\n{Color.YELLOW}Operation cancelled{Color.RESET}")
        return True

    def _print_response(self, response: str, elapsed: float):
        tokens = len(response.split())
        speed = tokens / elapsed if elapsed > 0 else 0
        print(f"\n{Color.AI_NAME}VerseAi{Color.RESET} ({Color.CYAN}{speed:.1f}t/s{Color.RESET}):")
        print(f"{response}\n")
        print(f"{Color.ORANGE}―――― Response Time: {elapsed:.2f}s ――――{Color.RESET}\n\n")

    def _trim_history(self):
        max_tokens = 12000  # Approximate context window size
        current_tokens = sum(len(m["content"].split()) for m in self.history)
        
        while current_tokens > max_tokens and len(self.history) > 2:
            removed = self.history.pop(1)
            current_tokens -= len(removed["content"].split())

    def _save_session(self, filename: str):
        if not filename:
            filename = "default_session.json"
        path = self.SESSION_DIR / filename
        
        try:
            with path.open('w') as f:
                json.dump(self.history, f, indent=2)
            print(f"{Color.GREEN}Session saved to {path}{Color.RESET}")
        except Exception as e:
            print(f"{Color.ERROR}Save error: {str(e)}{Color.RESET}")

    def _load_session(self, filename: str):
        path = self.SESSION_DIR / filename
        try:
            with path.open() as f:
                self.history = json.load(f)
            print(f"{Color.GREEN}Loaded session from {path}{Color.RESET}")
        except FileNotFoundError:
            print(f"{Color.ERROR}Session not found: {filename}{Color.RESET}")
        except json.JSONDecodeError:
            print(f"{Color.ERROR}Invalid session file{Color.RESET}")
        except Exception as e:
            print(f"{Color.ERROR}Load error: {str(e)}{Color.RESET}")

    def _print_help(self):
        commands = {
            Command.EXIT: "End the conversation",
            Command.HISTORY: "Show chat history",
            Command.SAVE: "[filename] Save session",
            Command.LOAD: "[filename] Load session",
            Command.CLEAR: "Reset conversation",
            Command.MODEL: "[name] Change AI model",
            Command.STATS: "Show system metrics",
            Command.HELP: "Show this help"
        }
        for cmd, desc in commands.items():
            print(f"  {Color.MAGENTA}\\{cmd.value.ljust(8)}{Color.RESET} {desc}")

    def _clear_history(self):
        self._init_history()
        print(f"{Color.GREEN}Conversation history cleared{Color.RESET}")

    def _change_model(self, model_name: str):
        if model_name:
            try:
                ollama.show(model_name)  # Verify model exists
                self.model = model_name
                print(f"{Color.GREEN}Model changed to {model_name}{Color.RESET}")
            except ollama.ResponseError:
                print(f"{Color.ERROR}Model not found: {model_name}{Color.RESET}")
        else:
            print(f"{Color.CYAN}Current model: {self.model}{Color.RESET}")

    def _exit(self):
        print(f"\n{Color.AI_NAME}VerseAi{Color.RESET}: Goodbye!")
        sys.exit(0)

    def _clear_screen(self):
        """Clear the terminal screen."""
        os.system('cls' if os.name == 'nt' else 'clear')

    def run(self):
        self._print_welcome()
        while True:
            try:
                user_input = input(f"{Color.USER_PROMPT}You:{Color.RESET} ").strip()
                if not user_input:
                    continue

                if user_input.startswith('\\'):
                    # Process commands without clearing screen
                    self._process_user_input(user_input)
                else:
                    # Clear screen and show only current interaction
                    self._clear_screen()
                    print(f"{Color.USER_PROMPT}You:{Color.RESET} {user_input}")
                    self._process_user_input(user_input)

            except (EOFError, KeyboardInterrupt):
                self._exit()

class SystemMonitor:
    def __init__(self):
        self.gpu_available = self._check_gpu_support()

    def _check_gpu_support(self) -> bool:
        try:
            subprocess.run(['nvidia-smi'], check=True, 
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False

    def print_system_status(self):
        print(f"\n{Color.CYAN}―――― System Status ――――{Color.RESET}")
        print(f"OS: {platform.system()} {platform.release()}")
        print(f"CPU: {psutil.cpu_percent()}% | Memory: {psutil.virtual_memory().percent}%")
        
        if self.gpu_available:
            try:
                output = subprocess.check_output(['nvidia-smi', '--query-gpu=utilization.gpu,temperature.gpu', 
                                                '--format=csv,noheader,nounits'])
                gpu_util, gpu_temp = output.decode().strip().split(', ')
                print(f"GPU: {gpu_util}% | Temp: {gpu_temp}°C")
            except Exception as e:
                print(f"GPU: {Color.ERROR}Monitoring failed{Color.RESET}")
        
        print(f"{Color.CYAN}――――――――――――――――――――――{Color.RESET}")

if __name__ == "__main__":
    ChatBot().run()