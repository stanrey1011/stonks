# stonkslib/llm/quant_assistant.py

import ollama
import os

MODEL = "llama3"  # Or 'deepseek-coder', 'mistral', etc.
STRATEGY_DIR = "stonkslib/strategies"

def ask_llm(prompt, model=MODEL, system=None):
    """Send a prompt to your local Ollama model."""
    messages = []
    if system:
        messages.append({'role': 'system', 'content': system})
    messages.append({'role': 'user', 'content': prompt})
    response = ollama.chat(model=model, messages=messages)
    return response['message']['content']

def generate_strategy_yaml(strategy_idea):
    prompt = f"Write a YAML strategy config for this quant trading idea:\n{strategy_idea}\n" \
             "Use keys: name, description, indicators (with params), patterns, and risk. " \
             "Match this schema: name (str), description (str), indicators (dict), patterns (dict), risk (dict). " \
             "Do not use lists for indicators or params. Only output valid YAML, no explanation."
    return ask_llm(prompt)

def edit_strategy_yaml(current_yaml, instruction):
    prompt = f"Here is a trading strategy YAML config:\n\n{current_yaml}\n\n" \
             f"Please {instruction}. Return only the edited YAML."
    return ask_llm(prompt)

def summarize_backtest(csv_path):
    with open(csv_path, 'r') as f:
        csv_data = f.read()
    prompt = f"Here is a CSV of trade results for a quant trading strategy:\n\n{csv_data}\n\n" \
             "Please summarize performance (win rate, drawdown, average trade, and potential improvements)."
    return ask_llm(prompt)

def get_save_path(filename):
    # Save to strategies dir by default if no path is specified
    if not os.path.isabs(filename) and not filename.startswith(STRATEGY_DIR):
        filename = os.path.join(STRATEGY_DIR, filename)
    # Ensure the directory exists
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    return filename

if __name__ == "__main__":
    print("=== Quant LLM Assistant (Ollama) ===")
    print("1. Generate new strategy YAML")
    print("2. Edit existing strategy YAML")
    print("3. Summarize backtest results")
    print("4. Exit")
    choice = input("Choose an option: ")

    if choice == "1":
        idea = input("Describe your strategy idea: ")
        yaml_config = generate_strategy_yaml(idea)
        print("\nGenerated YAML Strategy Config:\n")
        print(yaml_config)
        # Optionally save to file
        save = input("Save to file? (y/n): ")
        if save.lower() == "y":
            fname = input("Filename (e.g., my_strategy.yaml): ")
            fname = get_save_path(fname)
            with open(fname, "w") as f:
                f.write(yaml_config)
            print(f"Saved as {fname}")
    elif choice == "2":
        yaml_path = input(f"Path to YAML config (default: {STRATEGY_DIR}/): ")
        if not os.path.isabs(yaml_path) and not yaml_path.startswith(STRATEGY_DIR):
            yaml_path = os.path.join(STRATEGY_DIR, yaml_path)
        with open(yaml_path, "r") as f:
            current_yaml = f.read()
        instr = input("What do you want to change? (e.g., 'add MACD', 'set RSI period to 10'): ")
        edited = edit_strategy_yaml(current_yaml, instr)
        print("\nEdited YAML Strategy Config:\n")
        print(edited)
        # Optionally save
        save = input("Overwrite the YAML file? (y/n): ")
        if save.lower() == "y":
            with open(yaml_path, "w") as f:
                f.write(edited)
            print(f"Saved changes to {yaml_path}")
    elif choice == "3":
        csv_path = input("Path to trades CSV: ")
        summary = summarize_backtest(csv_path)
        print("\nBacktest Summary:\n")
        print(summary)
    else:
        print("Goodbye!")

