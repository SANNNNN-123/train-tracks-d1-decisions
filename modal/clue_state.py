"""Arithmetic clue state from source clues and already visible assignments."""
import json
from pathlib import Path

COUNTS_NOTE = (
    " Target row and column status show clue, occupied, unassigned, and "
    "remaining track cells. Occupied includes blue givens and earlier nonempty "
    "choices. Remaining is clue minus occupied. When remaining is 0, an "
    "unassigned cell in that line is empty; when remaining equals unassigned, "
    "it needs track. A negative remaining value indicates an earlier mistake."
)
PORTS_NOTE = (
    " Target connection status lists required ports, forbidden ports, and "
    "unassigned neighbor sides. Every nonempty track tile has exactly two "
    "ports. Connect to every required port and avoid every forbidden port. "
    "A required port comes from an earlier track pointing into the target."
)

DIRECTIONS = {"N": (-1, 0, "S"), "E": (0, 1, "W"),
              "S": (1, 0, "N"), "W": (0, -1, "E")}


def load_clues():
    return json.loads(Path(__file__).with_name("clues.json").read_text(
        encoding="utf-8"))


def target_counts(clue, target, actions):
    """Describe the target row and column without using a solved board."""
    rows, columns = clue["rows"], clue["columns"]
    height, width = len(rows), len(columns)
    row, column = target
    if not (0 <= row < height and 0 <= column < width):
        raise ValueError("Target outside clue grid")
    givens = {tuple(cell) for cell in clue["givens"]}
    assigned = set(givens)
    occupied = set(givens)
    for action in actions:
        cell = action["row"] - 1, action["column"] - 1
        if not (0 <= cell[0] < height and 0 <= cell[1] < width):
            raise ValueError("Action outside clue grid")
        if cell in assigned:
            raise ValueError("Duplicate action or action on a given")
        assigned.add(cell)
        if action["value"] not in {"empty", "invalid"}:
            occupied.add(cell)
    if (row, column) in assigned:
        raise ValueError("Target is already assigned")

    def status(axis, index, clue_value, length):
        selected = (lambda cell: cell[axis] == index)
        filled = sum(selected(cell) for cell in occupied)
        unassigned = length - sum(selected(cell) for cell in assigned)
        return {"clue": clue_value, "occupied": filled,
                "unassigned": unassigned, "remaining": clue_value - filled}

    return {
        "target_row_status": status(0, row, rows[row], width),
        "target_column_status": status(1, column, columns[column], height),
    }


def target_ports(clue, target, actions):
    """Describe neighboring assigned ports without choosing or filtering a tile."""
    height, width = len(clue["rows"]), len(clue["columns"])
    row, column = target
    if not (0 <= row < height and 0 <= column < width):
        raise ValueError("Target outside clue grid")
    assigned = {(r, c): shape for r, c, shape in clue["given_shapes"]}
    for action in actions:
        cell = action["row"] - 1, action["column"] - 1
        if not (0 <= cell[0] < height and 0 <= cell[1] < width):
            raise ValueError("Action outside clue grid")
        if cell in assigned:
            raise ValueError("Duplicate action or action on a given")
        assigned[cell] = action["value"]
    if (row, column) in assigned:
        raise ValueError("Target is already assigned")
    required, forbidden, unassigned = [], [], []
    for direction, (dr, dc, opposite) in DIRECTIONS.items():
        neighbor = row + dr, column + dc
        if not (0 <= neighbor[0] < height and 0 <= neighbor[1] < width):
            forbidden.append(direction)
        elif neighbor not in assigned:
            unassigned.append(direction)
        elif opposite in assigned[neighbor]:
            required.append(direction)
        else:
            forbidden.append(direction)
    return {"target_connection_status": {
        "required_ports": required,
        "forbidden_ports": forbidden,
        "unassigned_neighbor_sides": unassigned,
    }}
