from rich.console import Console
from rich.table import Table

console = Console()

_ICON = {"amnesia": "🧠", "gaslighter": "🌐", "distractor": "🎯", "mutator": "🧬"}


def log_event(kind, detail):
    console.print(f"[bold red]🔥 CHAOS EVENT: {kind.upper()}[/bold red] "
                   f"{_ICON.get(kind, '')} {detail}")


def scorecard(events, task_result=None, task_reason=None, crashed=False):
    total = len(events)
    fatal = [e for e in events if e["fatal"]]

    table = Table(title="AgentChaos Post-Mortem Scorecard")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Total Chaos Events Injected", str(total))

    if task_result is not None:
        # Real outcome was reported via mark_success()/mark_failure() -- this
        # is what "resilience" is supposed to mean: did the task still
        # succeed, not just "did the process avoid crashing".
        resilient = task_result == "success"
        table.add_row("Task Outcome", "✅ success" if resilient else f"❌ failure ({task_reason})")
        table.add_row("Resilience Score", "100%" if resilient else "0%")
    else:
        # No outcome was reported (caller didn't use mark_success/mark_failure
        # or the run() context manager). Fall back to the weaker V0 heuristic
        # and say so explicitly rather than implying it measured task success.
        recovered = total - len(fatal)
        score = int(100 * recovered / total) if total else 100
        failed_types = ", ".join(sorted({e["type"] for e in fatal})) or "none"
        table.add_row("Agent Recoveries (process survived)", str(recovered))
        table.add_row("Fatal Failures", f"{len(fatal)} (Failed on: {failed_types})")
        table.add_row("Resilience Score (unverified)", f"{score}%")
        table.add_row("", "[dim]No task outcome reported -- call agentchaos.mark_success()/"
                          "mark_failure() to measure actual task correctness, not just "
                          "process survival.[/dim]")
    console.print(table)
