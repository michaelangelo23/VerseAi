import argparse
from config import DEFAULT_MODEL_NAME_1B, DEFAULT_MODEL_NAME_3B, DEFAULT_API_URL

def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI Assistant")
    parser.add_argument("--model", choices=["1B", "3B"], default="1B", help="Model parameter to use (1B or 3B)")
    parser.add_argument("--url", default=DEFAULT_API_URL, help="API URL")
    return parser.parse_args()

def get_model_name(model_param: str) -> str:
    if model_param == "1B":
        return DEFAULT_MODEL_NAME_1B
    elif model_param == "3B":
        return DEFAULT_MODEL_NAME_3B
    else:
        raise ValueError("Invalid model parameter")