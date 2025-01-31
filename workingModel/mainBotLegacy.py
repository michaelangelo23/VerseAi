import ollama
import threading
import time
from sys import stdout

class LoadingSpinner:
    def __init__(self):
        self.spinner_chars = ['|', '/', '-', '\\']
        self.running = False
        self.spinner_thread = None

    def spin(self):
        idx = 0
        while self.running:
            stdout.write(f"\r\033[94mChatbot\033[0m is thinking... {self.spinner_chars[idx]}  ")
            stdout.flush()
            idx = (idx + 1) % len(self.spinner_chars)
            time.sleep(0.1)
        stdout.write('\r' + ' ' * 30 + '\r')  # Clear the spinner line

    def start(self):
        self.running = True
        self.spinner_thread = threading.Thread(target=self.spin)
        self.spinner_thread.start()

    def stop(self):
        self.running = False
        if self.spinner_thread:
            self.spinner_thread.join()

def generate_response(model_name, prompt):
    spinner = LoadingSpinner()
    result = {'response': None, 'error': None}
    
    def generate():
        try:
            response = ollama.generate(model=model_name, prompt=prompt)
            result['response'] = response['response']
        except Exception as e:
            result['error'] = e
    
    # Start the generation in a separate thread
    gen_thread = threading.Thread(target=generate)
    gen_thread.start()
    
    # Start the spinner while waiting
    spinner.start()
    
    # Wait for generation to complete
    gen_thread.join()
    spinner.stop()
    
    if result['error']:
        raise result['error']
    
    return result['response']

def chatbot():
    model_name = "dolphin3:latest"
    print(f"\033[94mChatbot\033[0m: Initializing with model: {model_name}")
    print("\033[94mChatbot\033[0m: Ready! Type 'exit' to end the conversation.\n")
    
    while True:
        try:
            user_input = input("\033[92mYou:\033[0m ")
            if user_input.lower() == 'exit':
                print(f"\n\033[94mChatbot\033[0m: Goodbye!")
                break
            
            response = generate_response(model_name, user_input)
            print(f"\033[94mChatbot\033[0m: {response}\n")
            
        except Exception as e:
            print(f"\n\033[91mError\033[0m: {str(e)}")
            break

if __name__ == "__main__":
    chatbot()