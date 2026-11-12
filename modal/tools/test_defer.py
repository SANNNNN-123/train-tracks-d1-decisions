"""Check the defer teacher and queue against the local training export."""
import collections
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from defer import candidate_tiles, teacher_trajectory

ROOT = Path(__file__).resolve().parents[2]


class DeferTests(unittest.TestCase):
    def test_visible_candidates(self):
        clue = {"rows": [1, 1], "columns": [1, 1], "givens": [], "given_shapes": []}
        self.assertEqual(candidate_tiles(clue, (0, 0), []), ["empty", "SE"])
        empty_clue = {"rows": [0], "columns": [0, 0], "givens": [],
                      "given_shapes": []}
        self.assertEqual(candidate_tiles(empty_clue, (0, 1), []), ["empty"])

    def test_defer_then_revisit(self):
        clue = {"rows": [0, 1, 1], "columns": [0, 1, 1],
                "givens": [], "given_shapes": []}
        rows = [
            {"step_index": 0, "state": {"target_cell": {"row": 2, "column": 2}}, "label": "SE"},
            {"step_index": 1, "state": {"target_cell": {"row": 1, "column": 1}}, "label": "empty"},
        ]
        trajectory = list(teacher_trajectory(rows, clue))
        self.assertEqual([item[1] for item in trajectory], ["defer", "empty", "SE"])
        self.assertEqual(trajectory[-1][3], [(1, 1)])

    def test_training_trajectories_fit_budget_and_labels(self):
        import pyarrow.parquet as parquet
        from clue_state import load_clues

        groups = collections.defaultdict(list)
        source = ROOT / "decision-dataset/huggingface/data/train.parquet"
        for batch in parquet.ParquetFile(source).iter_batches(
                batch_size=256, columns=["puzzle_id", "step_index", "state", "label"]):
            for row in batch.to_pylist():
                groups[row["puzzle_id"]].append(row)
        clues = load_clues()
        decisions = 0
        deferrals = 0
        first_puzzle_id = next(iter(groups))
        for puzzle_id, rows in groups.items():
            trajectory = list(teacher_trajectory(rows, clues[puzzle_id]))
            if puzzle_id == first_puzzle_id:
                self.assertTrue(any(item[1] == "defer" for item in trajectory))
            decisions += len(trajectory)
            deferrals += sum(item[1] == "defer" for item in trajectory)
            self.assertLessEqual(len(trajectory), 2 * len(rows), puzzle_id)
            placements = [item for item in trajectory if item[1] != "defer"]
            self.assertEqual(len(placements), len(rows), puzzle_id)
            for source_row, label, *_ in placements:
                self.assertEqual(label, source_row["label"])
            for source_row, _, actions, *_ in trajectory:
                target = (source_row["state"]["target_cell"]["row"] - 1,
                          source_row["state"]["target_cell"]["column"] - 1)
                candidates = candidate_tiles(clues[puzzle_id], target, actions)
                if len(candidates) == 1:
                    self.assertEqual(candidates[0], source_row["label"])
        print(f"{len(groups)} training puzzles, {decisions} teacher decisions, "
              f"{deferrals} deferrals")


if __name__ == "__main__":
    unittest.main()
