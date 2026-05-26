from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any, Callable

from app.services import process_control


@dataclass(frozen=True)
class EventProcessResult:
    return_code: int
    output_lines: list[str]

    @property
    def details(self) -> str:
        return "\n".join(self.output_lines).strip()


def run_event_process(
    *,
    cmd: list[str],
    job_id: str | None,
    on_event: Callable[[dict[str, Any]], None] | None = None,
    cancel_message: str,
    env: dict[str, str] | None = None,
) -> EventProcessResult:
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
        env=env,
    )
    process_control.register_process(job_id, proc)
    assert proc.stdout is not None
    output_lines: list[str] = []
    try:
        for line in proc.stdout:
            output_lines.append(line)
            if '"event"' not in line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if on_event is not None:
                on_event(event)
        return_code = proc.wait()
    finally:
        try:
            proc.stdout.close()
        except Exception:
            pass
        process_control.unregister_process(job_id, proc)
    if process_control.is_cancelled(job_id):
        raise process_control.JobCancelled(cancel_message)
    return EventProcessResult(return_code=return_code, output_lines=output_lines)
