"""Render one saved Modal evaluation report as a PNG, without rerunning the model."""
import argparse
import json
from pathlib import Path
import sys

import pyarrow.parquet as parquet

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from board import Board

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path, help="JSON downloaded from the Modal Volume")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--step", type=int, help="Render the input before this zero-based decision")
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    puzzle = report["puzzles"][0]
    source = ROOT / "decision-dataset/huggingface/data" / f"{report['split']}.parquet"
    first = None
    targets_by_step = {}
    for batch in parquet.ParquetFile(source).iter_batches(
            batch_size=128, columns=["puzzle_id", "step_index", "state", "images", "rows", "columns"]):
        for row in batch.to_pylist():
            if row["puzzle_id"] == puzzle["puzzle_id"]:
                target = row["state"]["target_cell"]
                targets_by_step[row["step_index"]] = (target["row"] - 1,
                                                       target["column"] - 1)
                if row["step_index"] == 0:
                    first = row
    if first is None:
        raise ValueError(f"First image not found for {puzzle['puzzle_id']}")
    targets = [targets_by_step[i] for i in sorted(targets_by_step)]
    board = Board(first["images"][0], first["rows"], first["columns"], targets)
    count = len(puzzle["actions"]) if args.step is None else args.step
    if not 0 <= count <= len(puzzle["actions"]) or (args.step is not None and count == len(puzzle["actions"])):
        raise ValueError("Step must name an existing decision, starting at zero")
    for action in puzzle["actions"][:count]:
        target = action["row"] - 1, action["column"] - 1
        if action["value"] == "defer":
            board.defer(target)
        else:
            board.add(target, action["value"])
    output = args.output or (args.report.with_name(
        f"{args.report.stem}-step-{count:03}.png") if args.step is not None
        else args.report.with_suffix(".png"))
    output.parent.mkdir(parents=True, exist_ok=True)
    next_target = (puzzle["actions"][count]["row"] - 1,
                   puzzle["actions"][count]["column"] - 1) if args.step is not None else None
    board.render(next_target,
                 report.get("visual_variant", "plain")).save(output)
    print(f"{output}: {'decision input' if args.step is not None else 'final board'}")


if __name__ == "__main__":
    main()
