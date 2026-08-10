"""Task-level outcome tracking.

V0's scorecard equated "recovered" with "process didn't crash" -- an agent
that silently accepts corrupted data and reports a wrong answer scored a
perfect resilience score. mark_success/mark_failure and the run() context
manager let the agent (or the test harness around it) report whether the
task actually succeeded, which is what the PRD's resilience test is meant
to measure. Process-crash detection is kept as a fallback for callers who
don't use either.
"""
from .state import STATE
from ..reporters.console import scorecard


def mark_success():
    """Call after the agent's task is verified correct despite any chaos."""
    STATE.task_result = "success"
    STATE.task_reason = None


def mark_failure(reason="unspecified"):
    """Call when the agent's output was wrong, even if nothing crashed."""
    STATE.task_result = "failure"
    STATE.task_reason = reason


class run:
    """Context manager for one chaos experiment.

        with agentchaos.run():
            result = my_agent(...)
            if result.balance == expected:
                agentchaos.mark_success()
            else:
                agentchaos.mark_failure("wrong balance reported")

    Resets event history on entry so repeated experiments in one process
    don't bleed into each other, and prints the scorecard on exit using
    whatever outcome was reported (falling back to crash-detection if the
    caller never marked one).
    """

    def __enter__(self):
        STATE.reset_run()
        return STATE

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None:
            STATE.crashed = True
            if STATE.events:
                STATE.events[-1]["fatal"] = True
            if STATE.task_result is None:
                STATE.task_result = "failure"
                STATE.task_reason = f"unhandled {exc_type.__name__}: {exc}"
        scorecard(STATE.events, STATE.task_result, STATE.task_reason, STATE.crashed)
        STATE._reported = True
        return False  # never suppress the agent's own exceptions
