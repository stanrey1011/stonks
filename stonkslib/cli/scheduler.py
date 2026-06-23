import click


@click.command("scheduler-tick")
def scheduler_tick():
    """Run any optimize schedules due this minute (launched by supercronic).

    Reads data/optimize_schedules.json and launches each enabled schedule whose
    UTC day/time matches now, as a detached background process. Wired into
    docker/crontab as `* * * * * stonks scheduler-tick`.
    """
    from stonkslib.utils.scheduler import tick
    launched = tick()
    if launched:
        for j in launched:
            click.echo(f"[scheduler] launched {j['id']} → PID {j['pid']} ({j['log']})")
    # silent when nothing is due — it runs every minute


@click.command("scheduler-list")
def scheduler_list():
    """List configured optimize schedules and their next UTC run."""
    from stonkslib.utils.scheduler import list_schedules, next_run
    scheds = list_schedules()
    if not scheds:
        click.echo("No schedules configured.")
        return
    for s in scheds:
        nr = next_run(s)
        days = ",".join(str(d) for d in s.get("days", []))
        state = "on " if s.get("enabled") else "off"
        click.echo(f"[{state}] {s['id']:20} days={days} {s['hour']:02d}:{s['minute']:02d}Z "
                   f"next={nr.isoformat() if nr else '—'}")
        click.echo(f"        stonks {' '.join(s['args'])}")
