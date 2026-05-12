import click
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@click.command()
@click.option("--port", default=8501, show_default=True, help="Port to listen on")
@click.option("--host", default="0.0.0.0", show_default=True, help="Bind address (0.0.0.0 = network accessible)")
def dash(port, host):
    """Launch the Stonks web dashboard."""
    app = PROJECT_ROOT / "stonkslib" / "dash" / "app.py"
    subprocess.run([
        sys.executable, "-m", "streamlit", "run", str(app),
        "--server.port", str(port),
        "--server.address", host,
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
    ])
