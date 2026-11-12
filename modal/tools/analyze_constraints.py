"""Audit row and column clue counts in saved independent rollouts."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clue_state import load_clues

ROOT = Path(__file__).resolve().parents[2]


def analyze(report_path):
    report = json.loads(report_path.read_text(encoding="utf-8"))
    source = {}
    for line in (ROOT / "dataset-audit/validated-puzzles.jsonl").open(encoding="utf-8"):
        record = json.loads(line)
        source[Path(record["path"]).stem] = record["puzzle"]
    clues = load_clues()
    row_exact = column_exact = both_exact = 0
    row_abs_error = column_abs_error = 0
    row_total = column_total = 0
    output = []
    for item in report["puzzles"]:
        puzzle = source[item["puzzle_id"]]
        occupied = {tuple(cell) for cell in clues[item["puzzle_id"]]["givens"]}
        for action in item["actions"]:
            if action["value"] == "defer":
                continue
            cell = action["row"] - 1, action["column"] - 1
            if action["value"] in {"NS", "EW", "NE", "NW", "SE", "SW"}:
                occupied.add(cell)
            else:
                occupied.discard(cell)
        rows = [sum(cell[0] == row for cell in occupied)
                for row in range(len(puzzle["rows"]))]
        columns = [sum(cell[1] == column for cell in occupied)
                   for column in range(len(puzzle["columns"]))]
        r_ok = rows == puzzle["rows"]
        c_ok = columns == puzzle["columns"]
        row_exact += r_ok
        column_exact += c_ok
        both_exact += r_ok and c_ok
        row_abs_error += sum(abs(a-b) for a, b in zip(rows, puzzle["rows"]))
        column_abs_error += sum(abs(a-b) for a, b in zip(columns, puzzle["columns"]))
        row_total += len(rows)
        column_total += len(columns)
        output.append({"puzzle_id": item["puzzle_id"], "row_counts_match": r_ok,
                       "column_counts_match": c_ok, "predicted_rows": rows,
                       "expected_rows": puzzle["rows"], "predicted_columns": columns,
                       "expected_columns": puzzle["columns"]})
    return {"model": report["run_id"] or "base", "puzzles": len(output),
            "all_rows_correct_puzzles": row_exact,
            "all_columns_correct_puzzles": column_exact,
            "both_correct_puzzles": both_exact,
            "mean_absolute_row_clue_error": row_abs_error / row_total,
            "mean_absolute_column_clue_error": column_abs_error / column_total,
            "details": output}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", nargs="+", type=Path)
    args = parser.parse_args()
    for path in args.reports:
        result = analyze(path)
        print(json.dumps({key: value for key, value in result.items() if key != "details"}, indent=2))


if __name__ == "__main__":
    main()
