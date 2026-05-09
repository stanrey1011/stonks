import click
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"


def _get_token():
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if line.startswith("DISCORD_BOT_TOKEN="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("DISCORD_BOT_TOKEN")


@click.command()
def bot():
    """Start the Stonks Discord bot."""
    token = _get_token()
    if not token:
        print("[!] DISCORD_BOT_TOKEN not set — add it to .env")
        return
    from stonkslib.bot.discord_bot import run_bot
    print("[*] Starting Stonks bot... (Ctrl+C to stop)")
    run_bot(token)
