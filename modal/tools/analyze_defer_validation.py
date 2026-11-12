"""Audit model-owned defer decisions against visible rules and fixed labels."""
import argparse
import collections
import json
import statistics
import sys
from pathlib import Path

import pyarrow.parquet as parquet

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clue_state import load_clues
from defer import FORCED_LOOKAHEAD, candidate_tiles, forced_other_status

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    if report["visual_variant"] != "defer":
        raise ValueError("Expected a defer rollout")
    records = parquet.read_table(
        ROOT / "decision-dataset/huggingface/data/validation.parquet",
        columns=["puzzle_id", "step_index", "state", "label"],
    ).to_pylist()
    references = collections.defaultdict(dict)
    for row in records:
        target = row["state"]["target_cell"]
        references[row["puzzle_id"]][row["step_index"]] = (
            (target["row"] - 1, target["column"] - 1), row["label"])
    clues = load_clues()
    counters = collections.Counter()
    first_wrong_steps = []
    puzzle_details = []
    for puzzle in report["puzzles"]:
        pid = puzzle["puzzle_id"]
        reference = references[pid]
        targets = [reference[i][0] for i in sorted(reference)]
        labels = {cell: label for cell, label in reference.values()}
        counters["true_track_cells"] += sum(label != "empty" for label in labels.values())
        queue = collections.deque(targets)
        placements = []
        deferrals_by_cell = collections.Counter()
        first_wrong = None
        budget = 2 * len(targets)
        for step, action in enumerate(puzzle["actions"]):
            target = queue.popleft()
            actual_target = (action["row"] - 1, action["column"] - 1)
            if target != actual_target:
                raise ValueError(f"Queue order mismatch: {pid} step {step}")
            candidates = candidate_tiles(clues[pid], target, placements)
            forced, distance = forced_other_status(clues[pid], queue, placements)
            if not candidates:
                counters["inconsistent_rule_states"] += 1
            if len(candidates) == 1:
                counters["forced_target_decisions"] += 1
            teacher_defer = (len(candidates) > 1
                             and 0 < distance <= FORCED_LOOKAHEAD
                             and budget - step > len(queue) + 1)
            if action["value"] == "defer":
                counters["deferrals"] += 1
                counters["defer_with_forced_target"] += len(candidates) == 1
                counters["defer_without_nearby_forced_cell"] += not (0 < distance <= FORCED_LOOKAHEAD)
                counters["defer_matching_teacher_policy"] += teacher_defer
                deferrals_by_cell[target] += 1
                queue.append(target)
            else:
                counters["placements"] += 1
                correct = action["value"] == labels[target]
                counters["correct_placements"] += correct
                counters["wrong_placements"] += not correct
                counters["predicted_track_cells"] += action["value"] not in {"empty", "invalid"}
                counters["correct_track_cells"] += correct and labels[target] != "empty"
                counters["correct_empty_cells"] += correct and labels[target] == "empty"
                if len(candidates) == 1:
                    counters["forced_target_placements"] += 1
                    counters["wrong_forced_target_placements"] += not correct
                if teacher_defer:
                    counters["placed_when_teacher_would_defer"] += 1
                if not correct and first_wrong is None:
                    first_wrong = step
                placements.append(action)
        if len(queue) != puzzle["unresolved_cells"]:
            raise ValueError(f"Unresolved count mismatch: {pid}")
        if sum(action["value"] == labels[(action["row"] - 1, action["column"] - 1)]
               for action in placements) != puzzle["correct_cells"]:
            raise ValueError(f"Correct-cell count mismatch: {pid}")
        counters["repeated_defer_cells"] += sum(count > 1 for count in deferrals_by_cell.values())
        if first_wrong is not None:
            first_wrong_steps.append(first_wrong)
        puzzle_details.append({
            "puzzle_id": pid, "cells": len(targets),
            "correct_cells": puzzle["correct_cells"],
            "deferrals": puzzle["deferrals"],
            "unresolved_cells": puzzle["unresolved_cells"],
            "first_wrong_decision": first_wrong,
            "seconds": puzzle["seconds"],
        })
    result = {
        "report": args.report.name,
        "puzzle_count": len(puzzle_details),
        "solved": report["valid"],
        "cells": report["total_cells"],
        "correct_cells": counters["correct_placements"],
        "decisions": report["total_decisions"],
        "deferrals": report["total_deferrals"],
        "unresolved_cells": report["unresolved_cells"],
        "puzzles_with_unresolved_cells": sum(p["unresolved_cells"] > 0 for p in puzzle_details),
        "median_first_wrong_decision": statistics.median(first_wrong_steps),
        "total_puzzle_seconds": round(sum(p["seconds"] for p in puzzle_details), 2),
        "counters": dict(counters),
        "puzzles": puzzle_details,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items()
                      if key != "puzzles"}, indent=2))


if __name__ == "__main__":
    main()
