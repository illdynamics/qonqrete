#!/usr/bin/env python3
import os
import sys
import argparse
from openai import OpenAI

class DeepSeekProvider:
    def __init__(self, api_key=None, model="deepseek-chat"):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        self.model = model
        self.base_url = "https://api.deepseek.com"

        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY not found in environment or arguments.")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

    def query(self, prompt, stream=False):
        """
        Sends a prompt to the DeepSeek API and returns the response.
        """
        if not prompt:
            return "Prompt cannot be empty."

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                stream=stream,
            )
            return resp.choices[0].message.content
        except Exception as e:
            return f"Error querying DeepSeek API: {e}"

def main():
    """
    Provides a command-line interface for the DeepSeekProvider.
    """
    parser = argparse.ArgumentParser(
        description="A command-line interface to interact with the DeepSeek API."
    )
    parser.add_argument(
        "--model",
        type=str,
        default="deepseek-chat",
        help='The model to use (e.g., "deepseek-chat", "deepseek-coder", "deepseek-reasoner").',
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        default=None,
        help="The prompt to send to the model. Reads from stdin if not provided.",
    )

    args = parser.parse_args()

    prompt_content = args.prompt
    if not prompt_content:
        if sys.stdin.isatty():
            print("Usage: deepseek_provider.py 'your prompt' [--model model_name] OR echo 'txt' | deepseek_provider.py [--model model_name]", file=sys.stderr)
            sys.exit(1)
        prompt_content = sys.stdin.read().strip()

    if not prompt_content:
        print("ERROR: Prompt is empty.", file=sys.stderr)
        sys.exit(1)
        
    try:
        provider = DeepSeekProvider(model=args.model)
        response = provider.query(prompt_content)
        print(response)
    except ValueError as ve:
        print(f"ERROR: {ve}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
