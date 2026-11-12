"""Check clue arithmetic against audited solutions, never used by inference."""
import json
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clue_state import load_clues, target_counts, target_ports

ROOT = Path(__file__).resolve().parents[2]


class ClueStateTests(unittest.TestCase):
    def test_all_audited_prefixes(self):
        clues = load_clues()
        seen = set()
        records = (ROOT / "dataset-audit/validated-puzzles.jsonl").read_text(
            encoding="utf-8").splitlines()
        for line in records:
            record = json.loads(line)
            puzzle_id = Path(record["path"]).stem
            seen.add(puzzle_id)
            solution = record["solution"]
            height, width = len(solution), len(solution[0])
            givens = {tuple(cell) for cell in clues[puzzle_id]["givens"]}
            actions = []
            for row in range(height):
                for column in range(width):
                    if (row, column) in givens:
                        continue
                    status = target_counts(clues[puzzle_id], (row, column), actions)
                    connection = target_ports(clues[puzzle_id], (row, column),
                                              actions)["target_connection_status"]
                    self.assertEqual(
                        set(connection["required_ports"])
                        | set(connection["forbidden_ports"])
                        | set(connection["unassigned_neighbor_sides"]),
                        set("NESW"),
                    )
                    self.assertFalse(set(connection["required_ports"])
                                     & set(connection["forbidden_ports"]))
                    for direction in connection["required_ports"]:
                        self.assertIn(direction, solution[row][column])
                    for direction in connection["forbidden_ports"]:
                        self.assertNotIn(direction, solution[row][column])
                    for axis, index, key, length in (
                        (0, row, "target_row_status", width),
                        (1, column, "target_column_status", height),
                    ):
                        expected_occupied = sum(
                            bool(solution[r][c])
                            for r, c in givens.union(
                                (action["row"] - 1, action["column"] - 1)
                                for action in actions
                            ) if (r, c)[axis] == index
                        )
                        expected_open = length - sum(
                            (r, c)[axis] == index
                            for r, c in givens.union(
                                (action["row"] - 1, action["column"] - 1)
                                for action in actions
                            )
                        )
                        self.assertEqual(status[key]["occupied"], expected_occupied)
                        self.assertEqual(status[key]["unassigned"], expected_open)
                        self.assertEqual(
                            status[key]["remaining"],
                            status[key]["clue"] - expected_occupied,
                        )
                    actions.append({"row": row + 1, "column": column + 1,
                                    "value": solution[row][column] or "empty"})
        self.assertEqual(seen, set(clues))

    def test_wrong_earlier_move_is_counted(self):
        clue = {"rows": [0], "columns": [0, 0], "givens": []}
        status = target_counts(clue, (0, 1),
                               [{"row": 1, "column": 1, "value": "EW"}])
        self.assertEqual(status["target_row_status"]["remaining"], -1)
        self.assertEqual(status["target_column_status"]["remaining"], 0)

    def test_ports_follow_earlier_choices(self):
        clue = {"rows": [1, 1], "columns": [1, 1], "givens": [],
                "given_shapes": []}
        status = target_ports(clue, (1, 0),
                              [{"row": 1, "column": 1, "value": "NS"}])
        self.assertEqual(status["target_connection_status"]["required_ports"],
                         ["N"])
        self.assertEqual(status["target_connection_status"]["forbidden_ports"],
                         ["S", "W"])


if __name__ == "__main__":
    unittest.main()
