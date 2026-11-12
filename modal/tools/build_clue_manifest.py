"""Export source clues and given positions, without solution labels."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "dataset-audit/validated-puzzles.jsonl"
DESTINATION = Path(__file__).resolve().parents[1] / "clues.json"


def main():
    clues = {}
    for line in SOURCE.open(encoding="utf-8"):
        record = json.loads(line)
        puzzle = record["puzzle"]
        height = len(puzzle["rows"])
        puzzle_id = Path(record["path"]).stem
        if puzzle_id in clues:
            raise ValueError(f"Duplicate puzzle ID: {puzzle_id}")
        clues[puzzle_id] = {
            "rows": puzzle["rows"],
            "columns": puzzle["columns"],
            "givens": sorted([[height - 1 - piece[1], piece[2]]
                              for piece in puzzle["pieces"]]),
            "given_shapes": sorted([[height - 1 - piece[1], piece[2], piece[0]]
                                    for piece in puzzle["pieces"]]),
        }
    DESTINATION.write_text(json.dumps(clues, separators=(",", ":")) + "\n",
                           encoding="utf-8")
    print(f"Wrote source clues and givens for {len(clues)} puzzles")


if __name__ == "__main__":
    main()
