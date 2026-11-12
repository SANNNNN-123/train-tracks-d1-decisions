"""Summarize validation rollout errors against the frozen decision labels."""
import argparse
import collections
import json
from pathlib import Path
import sys

import pyarrow.parquet as parquet
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clue_state import load_clues, target_counts, target_ports

ROOT = Path(__file__).resolve().parents[2]


def summarize(report_path, labels, clues):
    report = json.loads(report_path.read_text(encoding="utf-8"))
    pairs = []
    first_errors = []
    first_error_labels = collections.Counter()
    first_error_confusions = collections.Counter()
    first_error_positions = collections.Counter()
    first_error_required_ports = 0
    first_error_port_conflicts = 0
    first_error_forced_by_count = 0
    first_error_count_conflicts = 0
    other_forced_cells_at_first_error = []
    other_exact_cells_at_first_error = []
    for puzzle in report["puzzles"]:
        actions = puzzle["actions"]
        first = len(actions)
        for step, action in enumerate(actions):
            expected = labels[puzzle["puzzle_id"], step]
            actual = action["value"]
            pairs.append((expected, actual, step, len(actions)))
            if expected != actual and first == len(actions):
                first = step
                first_error_labels[expected] += 1
                first_error_confusions[(expected, actual)] += 1
                first_error_positions[(action["row"], action["column"])] += 1
                ports = target_ports(
                    clues[puzzle["puzzle_id"]],
                    (action["row"] - 1, action["column"] - 1),
                    actions[:step],
                )["target_connection_status"]
                counts = target_counts(
                    clues[puzzle["puzzle_id"]],
                    (action["row"] - 1, action["column"] - 1),
                    actions[:step],
                )
                statuses = [counts["target_row_status"],
                            counts["target_column_status"]]
                forced_empty = any(s["remaining"] == 0 for s in statuses)
                forced_track = any(s["remaining"] == s["unassigned"]
                                   for s in statuses)
                first_error_forced_by_count += forced_empty or forced_track
                first_error_count_conflicts += (
                    (forced_empty and actual != "empty")
                    or (forced_track and actual == "empty")
                )
                first_error_required_ports += bool(ports["required_ports"])
                first_error_port_conflicts += (
                    any(direction not in actual
                        for direction in ports["required_ports"])
                    or any(direction in actual
                           for direction in ports["forbidden_ports"])
                )
        first_errors.append(first)
        if first < len(actions):
            prefix = actions[:first]
            forced_elsewhere = 0
            exact_elsewhere = 0
            for future in actions[first + 1:]:
                cell = future["row"] - 1, future["column"] - 1
                counts = target_counts(clues[puzzle["puzzle_id"]], cell,
                                       prefix)
                statuses = [counts["target_row_status"],
                            counts["target_column_status"]]
                ports = target_ports(clues[puzzle["puzzle_id"]], cell,
                                     prefix)["target_connection_status"]
                forced_empty = any(status["remaining"] == 0
                                   for status in statuses)
                forced_track = bool(ports["required_ports"]) or any(
                    status["remaining"] == status["unassigned"]
                    for status in statuses)
                forced_elsewhere += bool(ports["required_ports"]) or any(
                    status["remaining"] == 0 for status in statuses) or forced_track
                exact_elsewhere += (forced_empty or len(ports["required_ports"]) == 2
                                    or (forced_track and
                                        len(ports["required_ports"])
                                        + len(ports["unassigned_neighbor_sides"]) == 2))
            other_forced_cells_at_first_error.append(forced_elsewhere)
            other_exact_cells_at_first_error.append(exact_elsewhere)
    classes = sorted({expected for expected, _, _, _ in pairs})
    return {
        "report": report_path.name,
        "puzzles": len(first_errors),
        "first_error_median_step": sorted(first_errors)[len(first_errors) // 2],
        "first_error_at_step_zero": sum(step == 0 for step in first_errors),
        "first_errors_with_required_port": first_error_required_ports,
        "first_errors_conflicting_with_known_ports": first_error_port_conflicts,
        "first_errors_with_count_forced_occupancy": first_error_forced_by_count,
        "first_errors_conflicting_with_count_forcing": first_error_count_conflicts,
        "first_errors_with_other_forced_cells": sum(
            count > 0 for count in other_forced_cells_at_first_error),
        "median_other_forced_cells": sorted(other_forced_cells_at_first_error)[
            len(other_forced_cells_at_first_error) // 2],
        "first_errors_with_other_exact_cells": sum(
            count > 0 for count in other_exact_cells_at_first_error),
        "median_other_exact_cells": sorted(other_exact_cells_at_first_error)[
            len(other_exact_cells_at_first_error) // 2],
        "first_error_reference_labels": dict(first_error_labels),
        "first_error_confusions": {
            f"{expected}->{actual}": count
            for (expected, actual), count in first_error_confusions.most_common(5)
        },
        "first_error_positions": {
            f"r{row}c{column}": count
            for (row, column), count in first_error_positions.most_common(5)
        },
        "occupancy": {
            "true_track": sum(e != "empty" for e, _, _, _ in pairs),
            "predicted_track": sum(a != "empty" for _, a, _, _ in pairs),
            "correct_occupancy": sum(e != "empty" and a != "empty"
                                     for e, a, _, _ in pairs),
        },
        "predicted": dict(collections.Counter(actual for _, actual, _, _ in pairs)),
        "recall_by_class": {
            label: {
                "correct": sum(e == a == label for e, a, _, _ in pairs),
                "total": sum(e == label for e, _, _, _ in pairs),
            }
            for label in classes
        },
        "accuracy_by_step_quartile": [
            {
                "correct": sum(e == a and step * 4 // length == q
                               for e, a, step, length in pairs),
                "total": sum(step * 4 // length == q
                             for _, _, step, length in pairs),
            }
            for q in range(4)
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", nargs="+", type=Path)
    args = parser.parse_args()
    records = parquet.read_table(
        ROOT / "decision-dataset/huggingface/data/validation.parquet",
        columns=["puzzle_id", "step_index", "label"],
    ).to_pylist()
    labels = {(row["puzzle_id"], row["step_index"]): row["label"]
              for row in records}
    print("reference_counts", dict(collections.Counter(labels.values())))
    for path in args.reports:
        print(json.dumps(summarize(path, labels, load_clues()), indent=2))


if __name__ == "__main__":
    main()
