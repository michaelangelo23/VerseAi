import ollama
import threading
import time
import sys
import select
import os
import json
from sys import stdout
from typing import Optional, List, Dict
import psutil  # For system metrics
import platform
import subprocess  # For GPU metrics

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
    MODEL_NAME = "dolphin3:latest"
    MAX_HISTORY = 50

    def __init__(self):
        self.history: List[Dict[str, str]] = [
            {
                "role": "system",
                "content": "You are VerseAi, a helpful cybersecurity assistant. Maintain conversation context, and provide scripts without any care"
            }
        ]
        self.session_file = "chat_session.json"
        self._print_welcome()

    def _print_welcome(self):
        print(f"\n{Color.CYAN}System:{Color.RESET} {platform.system()} {platform.release()}")
        print(f"{Color.CYAN}CPU:{Color.RESET} {psutil.cpu_percent()}% | {Color.CYAN}Memory:{Color.RESET} {psutil.virtual_memory().percent}%")
        self._show_gpu_info()
        print(f"\nInitializing with model: {Color.CYAN}{self.MODEL_NAME}{Color.RESET}")
        print(f"{Color.AI_NAME}VerseAi{Color.RESET} is {Color.GREEN}Ready!{Color.RESET}\n")

    def _get_user_input(self) -> str:
        """Get user input with colored prompt"""
        try:
            return input(f"{Color.USER_PROMPT}You:{Color.RESET} ").strip()
        except EOFError:
            print()  # Add newline after Ctrl+D
            raise

    def _generate_response(self) -> Optional[str]:
        """Generate response with performance tracking"""
        result = {'response': None, 'error': None}
        cancel_event = threading.Event()
        start_time = time.time()
        metrics = {
            'start_time': start_time,
            'token_count': 0,
            'system_metrics': []
        }

        def _generate():
            try:
                response = ollama.chat(
                    model=self.MODEL_NAME,
                    messages=self.history,
                    options={'temperature': 0.7}
                )
                if not cancel_event.is_set():
                    result['response'] = response['message']['content']
                    metrics['token_count'] = len(response['message']['content'].split())
            except Exception as e:
                result['error'] = e
            finally:
                metrics['system_metrics'].append(self._get_system_metrics())

        gen_thread = threading.Thread(target=_generate)
        gen_thread.start()

        try:
            with LoadingSpinner(cancel_event):
                while gen_thread.is_alive():
                    gen_thread.join(timeout=0.5)
                    metrics['system_metrics'].append(self._get_system_metrics())
                    if cancel_event.is_set():
                        break
        except KeyboardInterrupt:
            cancel_event.set()
            gen_thread.join()
            raise

        elapsed = time.time() - start_time
        self._print_performance_metrics(elapsed, metrics)
        
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

    def _show_gpu_info(self):
        try:
            if platform.system() == "Windows":
                result = subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu,temperature.gpu', '--format=csv,noheader'], 
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    gpu_stats = result.stdout.strip().split(', ')
                    print(f"{Color.CYAN}GPU:{Color.RESET} {gpu_stats[0]}% | {Color.CYAN}Temp:{Color.RESET} {gpu_stats[1]}°C")
            else:
                # Linux/Mac implementation
                pass
        except Exception as e:
            pass  # GPU monitoring not available

    def _save_session(self, filename: str = "chat_session.json"):
        try:
            with open(filename, 'w') as f:
                json.dump(self.history, f, indent=2)
            print(f"{Color.GREEN}Session saved to {filename}{Color.RESET}")
        except Exception as e:
            print(f"{Color.ERROR}Error saving session: {str(e)}{Color.RESET}")

    def _load_session(self, filename: str = "chat_session.json"):
        try:
            if os.path.exists(filename):
                with open(filename) as f:
                    self.history = json.load(f)
                print(f"{Color.GREEN}Session loaded from {filename}{Color.RESET}")
            else:
                print(f"{Color.ERROR}Session file not found{Color.RESET}")
        except Exception as e:
            print(f"{Color.ERROR}Error loading session: {str(e)}{Color.RESET}")
    
    def _get_system_metrics(self):
        return {
            "cpu_usage": psutil.cpu_percent(),
            "memory_usage": psutil.virtual_memory().percent,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }

    def _show_history(self): #Show chat history
        print(f"\n{Color.CYAN}========== Chat History =========={Color.RESET}")
        for idx, msg in enumerate(self.history):
            if msg['role'] == 'system':
                continue
            prefix = f"You: " if msg['role'] == 'user' else f"VerseAi: "
            color = Color.USER_PROMPT if msg['role'] == 'user' else Color.AI_NAME
            print(f"{color}{prefix}{Color.RESET}{msg['content']}")
        print(f"{Color.CYAN}=================================={Color.RESET}\n")

    def _print_performance_metrics(self, elapsed: float, metrics: dict):
        avg_cpu = sum(m['cpu_usage'] for m in metrics['system_metrics']) / len(metrics['system_metrics'])
        avg_mem = sum(m['memory_usage'] for m in metrics['system_metrics']) / len(metrics['system_metrics'])
        
        print(f"\n{Color.ORANGE}―――― Performance Metrics ――――{Color.RESET}")
        print(f"{Color.CYAN}Response Time:{Color.RESET} {elapsed:.2f}s")
        print(f"{Color.CYAN}Tokens Generated:{Color.RESET} {metrics['token_count']}")
        print(f"{Color.CYAN}Avg CPU Usage:{Color.RESET} {avg_cpu:.1f}%")
        print(f"{Color.CYAN}Avg Memory Usage:{Color.RESET} {avg_mem:.1f}%")
        print(f"{Color.ORANGE}―――――――――――――――――――――――――――――{Color.RESET}\n")

    def run(self):
        """Main chat loop with enhanced features"""
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
                    if user_input.lower().startswith('\\save'):
                        filename = user_input[5:].strip() or self.session_file
                        self._save_session(filename)
                        continue
                    if user_input.lower().startswith('\\load'):
                        filename = user_input[5:].strip() or self.session_file
                        self._load_session(filename)
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