"""Shared scheduling and visible-rule checks for the defer experiment."""

from board import CHOICES
from clue_state import target_counts, target_ports

DEFER = "defer"
DEFER_NOTE = (
    " You may choose defer when the visible counts and connections do not"
    " determine this cell. Defer leaves it unassigned and moves it to the end"
    " of the queue. A small question mark marks a deferred cell; X means"
    " confirmed empty. Revisit deferred cells after other placements."
    " If a full pass made no placements, make your best tile choice."
)
DEFER_DESCRIPTION = "Leave this cell unassigned and revisit it later"
MAX_DECISIONS_PER_CELL = 2
FORCED_LOOKAHEAD = 4


def question_with_defer(question):
    return {
        **question,
        "criteria": {**question["criteria"], DEFER: DEFER_DESCRIPTION},
        "instructions": question["instructions"] + " Choose defer to revisit later.",
    }


def candidate_tiles(clue, target, actions):
    """Possible tiles from visible counts and neighboring assigned ports only."""
    counts = target_counts(clue, target, actions)
    row = counts["target_row_status"]
    column = counts["target_column_status"]
    ports = target_ports(clue, target, actions)["target_connection_status"]
    required = set(ports["required_ports"])
    forbidden = set(ports["forbidden_ports"])
    occupied = bool(required) or any(
        line["remaining"] == line["unassigned"] for line in (row, column)
    )
    empty = not required and all(line["remaining"] >= 0 for line in (row, column))
    candidates = []
    if empty and not occupied:
        candidates.append("empty")
    if all(line["remaining"] > 0 for line in (row, column)):
        candidates.extend(
            shape for shape in CHOICES[1:]
            if required.issubset(shape) and not forbidden.intersection(shape)
        )
    return candidates


def forced_other_status(clue, targets, actions):
    forced = [index + 1 for index, target in enumerate(targets)
              if len(candidate_tiles(clue, target, actions)) == 1]
    return len(forced), forced[0] if forced else 0


def teacher_trajectory(rows, clue, max_decisions_per_cell=MAX_DECISIONS_PER_CELL):
    """Yield (source, label, placements, deferred, streak, budget, forced, distance)."""
    if not rows:
        return
    ordered = sorted(rows, key=lambda row: row["step_index"])
    if [row["step_index"] for row in ordered] != list(range(len(ordered))):
        raise ValueError("Incomplete or duplicate puzzle decisions")
    queue = list(ordered)
    actions = []
    deferred = set()
    streak = 0
    budget = max_decisions_per_cell * len(queue)
    for step in range(budget):
        if not queue:
            break
        row = queue.pop(0)
        target = (row["state"]["target_cell"]["row"] - 1,
                  row["state"]["target_cell"]["column"] - 1)
        candidates = candidate_tiles(clue, target, actions)
        other_targets = [
            (item["state"]["target_cell"]["row"] - 1,
             item["state"]["target_cell"]["column"] - 1) for item in queue
        ]
        forced, distance = forced_other_status(clue, other_targets, actions)
        # Commit unless a nearby queued cell has an exact locally forced tile.
        should_defer = (len(candidates) > 1 and 0 < distance <= FORCED_LOOKAHEAD
                        and budget - step > len(queue) + 1)
        label = DEFER if should_defer else row["label"]
        yield (row, label, list(actions), sorted(deferred), streak,
               budget - step, forced, distance)
        if should_defer:
            deferred.add(target)
            queue.append(row)
            streak += 1
        else:
            deferred.discard(target)
            actions.append({"row": target[0] + 1, "column": target[1] + 1,
                            "value": row["label"]})
            streak = 0
    if queue:
        raise ValueError("Teacher trajectory exceeded decision budget")
