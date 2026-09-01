"""Rolling memory, K=4 weeks (RESEARCH.md §2.3, §7).

The Claude-Code-native implementation: one JSON file per agent under
`.agent-memory/`. RESEARCH.md §6.5 documents a Managed Agents Memory Store
as the production-grade equivalent (versioned, auditable, first-party) —
this class is deliberately storage-agnostic at the interface level (get/put
a dict keyed by ISO week) so swapping the backend later doesn't touch caller
code.

Per the paper: each memory entry records the ISO week identifier and the
agent's complete structured output for that week; when reading, entries are
prepended in reverse-chronological order (most recent first) so the agent
sees its own recent track record before reasoning about the current week.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class RollingMemory:
    def __init__(self, agent_name: str, window_weeks: int = 4, root: Path | str = ".agent-memory"):
        self.agent_name = agent_name
        self.window_weeks = window_weeks
        self.path = Path(root) / f"{agent_name}.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(json.dumps({}, indent=2))

    def _load_all(self) -> dict[str, Any]:
        return json.loads(self.path.read_text())

    def _save_all(self, data: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True))

    def record(self, iso_week: str, structured_output: dict[str, Any]) -> None:
        """Write this week's complete structured output. Overwrites if the
        same week is recorded twice (e.g. a re-run), matching the paper's
        "serialised at the end of each week" convention."""
        data = self._load_all()
        data[iso_week] = structured_output
        self._save_all(data)

    def recent(self, before_iso_week: str | None = None) -> list[tuple[str, dict[str, Any]]]:
        """Return up to `window_weeks` entries, most-recent-first, strictly
        before `before_iso_week` if given (prevents a week's own not-yet-
        written output from leaking into its own memory read)."""
        data = self._load_all()
        weeks = sorted(data.keys(), reverse=True)
        if before_iso_week is not None:
            weeks = [w for w in weeks if w < before_iso_week]
        weeks = weeks[: self.window_weeks]
        return [(w, data[w]) for w in weeks]

    def as_prompt_block(self, before_iso_week: str | None = None) -> str:
        """Render the memory window as the block the paper prepends to the
        agent's user message. Empty string if there's no history yet."""
        entries = self.recent(before_iso_week)
        if not entries:
            return ""
        lines = [f"## Your last {len(entries)} weekly outputs (most recent first):"]
        for week, payload in entries:
            lines.append(f"### {week}")
            lines.append(json.dumps(payload, indent=2))
        return "\n".join(lines)
