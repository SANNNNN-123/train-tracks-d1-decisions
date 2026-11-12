"""Measure track-connection failures in a saved independent rollout."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIRECTIONS = {"N": (-1, 0, "S"), "E": (0, 1, "W"),
              "S": (1, 0, "N"), "W": (0, -1, "E")}
SHAPES = {"NS", "EW", "NE", "NW", "SE", "SW"}


def assess(puzzle, actions):
    height, width = len(puzzle["rows"]), len(puzzle["columns"])
    grid = [["" for _ in range(width)] for _ in range(height)]
    expected_boundary = set()
    for shape, source_row, column, *_ in puzzle["pieces"]:
        row = height - 1 - source_row
        grid[row][column] = shape
        for direction in shape:
            dr, dc, _ = DIRECTIONS[direction]
            if not (0 <= row + dr < height and 0 <= column + dc < width):
                expected_boundary.add((row, column, direction))
    for action in actions:
        grid[action["row"] - 1][action["column"] - 1] = action["value"]
    occupied = {(row, column) for row in range(height) for column in range(width)
                if grid[row][column] in SHAPES}
    broken = 0
    boundary = set()
    edges = {cell: set() for cell in occupied}
    for row, column in occupied:
        for direction in grid[row][column]:
            dr, dc, opposite = DIRECTIONS[direction]
            neighbor = row + dr, column + dc
            if not (0 <= neighbor[0] < height and 0 <= neighbor[1] < width):
                boundary.add((row, column, direction))
            elif opposite not in grid[neighbor[0]][neighbor[1]]:
                broken += 1
            else:
                edges[row, column].add(neighbor)
    unseen = set(occupied)
    components = 0
    while unseen:
        components += 1
        stack = [unseen.pop()]
        while stack:
            for neighbor in edges[stack.pop()] & unseen:
                unseen.remove(neighbor)
                stack.append(neighbor)
    return {"broken_ports": broken, "boundary_ok": boundary == expected_boundary,
            "components": components}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    source = {Path(record["path"]).stem: record["puzzle"]
              for record in map(json.loads,
                  (ROOT / "dataset-audit/validated-puzzles.jsonl").read_text(
                      encoding="utf-8").splitlines())}
    results = {item["puzzle_id"]: assess(source[item["puzzle_id"]], item["actions"])
               for item in report["puzzles"]}
    print(json.dumps({
        "puzzles": len(results),
        "with_broken_ports": sum(row["broken_ports"] > 0 for row in results.values()),
        "total_broken_ports": sum(row["broken_ports"] for row in results.values()),
        "with_wrong_boundary": sum(not row["boundary_ok"] for row in results.values()),
        "with_multiple_components": sum(row["components"] > 1 for row in results.values()),
        "example_25022026_small": results.get("25022026-small"),
    }, indent=2))


if __name__ == "__main__":
    main()
