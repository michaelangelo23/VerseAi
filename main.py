import ollama
import threading
import time
import sys
import select
import os
import json
from sys import stdout
from typing import List, Dict, Optional
import psutil
import platform
import subprocess
from enum import Enum
import shutil
from pathlib import Path

class Color:
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    ORANGE = "\033[38;5;214m"
    MAGENTA = "\033[35m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    RESET = "\033[0m"

class Command(Enum):
    EXIT = "exit"
    HISTORY = "history"
    HELP = "help"
    CLEAR = "clear"
    MODEL = "model"
    STATS = "stats"
    SWITCH = "switch"

class LoadingSpinner:
    SPINNER_CHARS = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
    
    def __init__(self, cancel_event: threading.Event):
        self.cancel_event = cancel_event
        self.thread: Optional[threading.Thread] = None
        self.running = False
        self.start_time = 0

    def __enter__(self):
        if sys.stderr.isatty():
            self.running = True
            self.start_time = time.time()
            self.thread = threading.Thread(target=self._spin)
            self.thread.start()
        return self

    def __exit__(self, *args):
        self.running = False
        if self.thread:
            self.thread.join()
        self._clear_line()

    def _spin(self):
        idx = 0
        while self.running and not self.cancel_event.is_set():
            self._check_cancel()
            self._update_spinner(idx)
            idx = (idx + 1) % len(self.SPINNER_CHARS)
            time.sleep(0.1)

    def _check_cancel(self):
        if self.cancel_event.is_set():
            return

        if sys.platform == "win32":
            self._windows_cancel_check()
        else:
            self._unix_cancel_check()

    def _windows_cancel_check(self):
        import msvcrt
        if msvcrt.kbhit() and msvcrt.getch().decode().lower() == 'q':
            self.cancel_event.set()

    def _unix_cancel_check(self):
        rlist, _, _ = select.select([sys.stdin], [], [], 0)
        if rlist and sys.stdin.read(1).lower() == 'q':
            self.cancel_event.set()

    def _update_spinner(self, idx: int):
        elapsed = time.time() - self.start_time
        spinner = f"\r{Color.BLUE}Thinking {self.SPINNER_CHARS[idx]} ({elapsed:.1f}s){Color.RESET}"
        stdout.write(spinner)
        stdout.flush()

    def _clear_line(self):
        if sys.stderr.isatty():
            stdout.write('\r' + ' ' * shutil.get_terminal_size().columns + '\r')

class ChatBot:
    DEFAULT_MODEL = "llama3.2:latest"
    MAX_CONTEXT_TOKENS = 12000

    def __init__(self):
        self.history: List[Dict[str, str]] = []
        self.model = self.DEFAULT_MODEL
        self.system_info = SystemMonitor()
        self._init_history()

    def _init_history(self, swicth_mode: bool = False):
        if swicth_mode:
            system_message = (
                "You are VerseAi, a cybersecurity expert assistant. Provide concise, "
                "actionable advice. Always explain security concepts clearly. "
                "Verify information when uncertain."
            )
        else:
            system_message = (
                "You are VerseAi, an expert assistant. Provide focused, actionable answers. "
                "Avoid formatting notes and unnecessary commentary. Be technical but clear."
            )
        
        self.history = [{"role": "system", "content": system_message}]

    def run(self):
        self._print_welcome()
        while True:
            try:
                user_input = input(f"{Color.GREEN}You:{Color.RESET} ").strip()
                if user_input:
                    self._process_input(user_input)
            except (EOFError, KeyboardInterrupt):
                self._exit()

    def _process_input(self, user_input: str):
        if user_input.startswith('\\'):
            self._handle_command(user_input)
        else:
            self._clear_screen()
            print(f"{Color.GREEN}You:{Color.RESET} {user_input}")
            self._generate_response(user_input)

    def _handle_command(self, command: str):
        cmd, *args = command[1:].split(maxsplit=1)
        try:
            cmd_enum = Command(cmd.lower())
            {
                Command.EXIT: lambda: self._exit(),
                Command.HISTORY: self._show_history,
                Command.HELP: self._print_help,
                Command.CLEAR: self._clear_history,
                Command.MODEL: lambda: self._change_model(args[0] if args else ""),
                Command.STATS: self.system_info.print_system_status,
                Command.SWITCH: lambda: self._toggle_swicth_mode(),
            }[cmd_enum]()
        except ValueError:
            print(f"{Color.RED}Unknown command: {cmd}{Color.RESET}")

    def _generate_response(self, user_input: str):
        self.history.append({"role": "user", "content": user_input})
        cancel_event = threading.Event()
        
        try:
            with LoadingSpinner(cancel_event):
                start_time = time.time()
                response = self._get_ollama_response()
                elapsed = time.time() - start_time
                
                if response:
                    self._handle_successful_response(response, elapsed)
        except KeyboardInterrupt:
            cancel_event.set()
            print(f"\n{Color.YELLOW}Operation cancelled{Color.RESET}")

    def _get_ollama_response(self) -> Optional[str]:
        try:
            response = ollama.chat(
                model=self.model,
                messages=self.history,
                stream=False,
                options={'temperature': 0.7, 'num_ctx': 4096}
            )
            return response['message']['content']
        except ollama.ResponseError as e:
            print(f"{Color.RED}API Error: {e.error}{Color.RESET}")
        except Exception as e:
            print(f"{Color.RED}Generation error: {str(e)}{Color.RESET}")
        return None

    def _handle_successful_response(self, response: str, elapsed: float):
        self.history.append({"role": "assistant", "content": response})
        self._trim_history()
        
        tokens = len(response.split())
        speed = tokens / elapsed if elapsed > 0 else 0
        
        print(f"\n{Color.CYAN}VerseAi ({speed:.1f}t/s):{Color.RESET}")
        print(f"{response}\n")
        print(f"{Color.ORANGE}―――― Response Time: {elapsed:.2f}s ――――{Color.RESET}\n")

    def _trim_history(self):
        current_tokens = sum(len(m["content"].split()) for m in self.history)
        while current_tokens > self.MAX_CONTEXT_TOKENS and len(self.history) > 2:
            removed = self.history.pop(1)
            current_tokens -= len(removed["content"].split())

    def _show_history(self):
        print(f"\n{Color.CYAN}―――― Chat History ({len(self.history)-1} messages) ――――{Color.RESET}")
        for idx, msg in enumerate(self.history[1:], 1):
            role_color = Color.GREEN if msg['role'] == 'user' else Color.CYAN
            content = msg['content']
            if len(content) > 300:
                content = content[:300] + "... [truncated]"
            print(f"{idx:2}. {role_color}{msg['role'].title()}:{Color.RESET} {content}")
        print(f"{Color.CYAN}――――――――――――――――――――――――――――――――――――{Color.RESET}\n")

    def _print_help(self):
        commands = {
            Command.EXIT: "End conversation",
            Command.HISTORY: "Show chat history",
            Command.CLEAR: "Reset conversation",
            Command.MODEL: "Change AI model [name]",
            Command.STATS: "Show system metrics",
            Command.HELP: "Show this help",
            Command.SWITCH: "Toggle cybersecurity expert mode",
        }
        print(f"\n{Color.MAGENTA}Available Commands:{Color.RESET}")
        for cmd, desc in commands.items():
            print(f"  {Color.CYAN}\\{cmd.value.ljust(8)}{Color.RESET} {desc}")

    def _clear_history(self):
        self._init_history()
        print(f"{Color.GREEN}Conversation history cleared{Color.RESET}")

    def _change_model(self, model_name: str):
        if model_name:
            try:
                ollama.show(model_name)
                self.model = model_name
                print(f"{Color.GREEN}Model changed to {model_name}{Color.RESET}")
            except ollama.ResponseError:
                print(f"{Color.RED}Model not found: {model_name}{Color.RESET}")
        else:
            try:
                models = ollama.list().get('models', [])
                if not models:
                    print(f"{Color.YELLOW}No models available{Color.RESET}")
                    return

                print(f"\n{Color.CYAN}Available Models:{Color.RESET}")
                for idx, model in enumerate(models, 1):
                    size_gb = model['size'] / 1e9
                    print(f"{Color.MAGENTA}{idx:2}.{Color.RESET} {model['model']:30} {size_gb:.1f} GB")

                selection = input(f"\n{Color.GREEN}Enter model number: {Color.RESET}")
                index = int(selection) - 1
                self.model = models[index]['model']
                print(f"{Color.GREEN}Active model: {self.model}{Color.RESET}")
            except (ValueError, IndexError):
                print(f"{Color.RED}Invalid selection{Color.RESET}")
            except Exception as e:
                print(f"{Color.RED}Model error: {str(e)}{Color.RESET}")

    def _toggle_swicth_mode(self):
        current_mode = "cybersecurity expert" in self.history[0]['content']
        self._init_history(not current_mode)
        mode = "Cybersecurity Expert" if not current_mode else "General Expert"
        print(f"{Color.GREEN}Switched to {mode} mode{Color.RESET}")

    def _print_welcome(self):
        self._clear_screen()
        self.system_info.print_system_status()
        print(f"\n{Color.CYAN}Initialized Model:{Color.RESET} {self.model}")
        self._print_help()
        print(f"\n{Color.BLUE}VerseAi {Color.GREEN}ready!{Color.RESET}\n")

    def _clear_screen(self):
        os.system('cls' if os.name == 'nt' else 'clear')

    def _exit(self):
        print(f"\n{Color.BLUE}VerseAi{Color.RESET}: {Color.GREEN}Goodbye!{Color.RESET}")
        sys.exit(0)

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
        print(f"CPU Usage: {psutil.cpu_percent()}%")
        print(f"Memory Usage: {psutil.virtual_memory().percent}%")
        
        if self.gpu_available:
            try:
                output = subprocess.check_output([
                    'nvidia-smi', 
                    '--query-gpu=utilization.gpu,temperature.gpu',
                    '--format=csv,noheader,nounits'
                ])
                gpu_util, gpu_temp = output.decode().strip().split(', ')
                print(f"GPU Usage: {gpu_util}%")
                print(f"GPU Temperature: {gpu_temp}°C")
            except Exception:
                print(f"{Color.RED}GPU monitoring failed{Color.RESET}")
        
        print(f"{Color.CYAN}――――――――――――――――――――――{Color.RESET}")

if __name__ == "__main__":
    ChatBot().run()