import click

@click.group()
def analyze():
    """Run signal analysis."""

@analyze.command("stocks")
def analyze_stocks():
    click.echo("Running analysis for stocks...")

@analyze.command("options")
def analyze_options():
    click.echo("Running analysis for options...")
