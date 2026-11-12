# Train Tracks d1-2B experiment

This experiment is archived. See the [final report](../README.md) for the
counts, ports, and defer validation results.

Run these commands from the project root. Both scripts default to the uploaded [Train Tracks dataset](https://huggingface.co/datasets/zuhairsan/train-tracks-decisions). GPU jobs require your Modal account. The `hf-train-tracks` Modal Secret should contain the token under `HF_TOKEN`; `HUGGINGFACE_TOKEN` and `HUGGINGFACE_HUB_TOKEN` are also accepted.

## Folder map

| Path | Purpose |
| --- | --- |
| `train.py`, `evaluate_puzzles.py` | Modal entrypoints; commands below keep these paths |
| `board.py`, `clue_state.py`, `clues.json` | Shared rendering and source-clue inputs |
| `tools/` | Local diagnostics, tests, plotting, and report generators |
| `docs/` | Experiment plans and completed evaluation reports |
| `training-logs/` | Committed graphs and CSVs |
| `eval-gallery/` | Generated side-by-side HTML galleries; ignored by Git |
| `results/` | Downloaded JSON reports are committed; local logs and previews are ignored |

## Run an experiment

1. Set up Modal and measure the unmodified model on validation. First try one puzzle, then all 46:

   ```powershell
   uv sync
   uv run modal setup
   uv run modal run modal/evaluate_puzzles.py --limit-puzzles 1
   uv run modal run --detach modal/evaluate_puzzles.py
   ```

2. Run the 16-row, four-step smoke training job, then the one-epoch SFT pilot:

   ```powershell
   uv run modal run modal/train.py --mode smoke
   uv run modal run --detach modal/train.py --mode full
   ```

3. Copy the full training `run_id` from its output and compare on validation:

   ```powershell
   uv run modal run --detach modal/evaluate_puzzles.py --run-id RUN_ID
   ```

4. After the prompt and checkpoint are frozen, evaluate both models on each held-out split with `--split test_small` or `--split test_medium`, and `--allow-test`.

The rollout loads images, targets, and labels directly from `zuhairsan/train-tracks-decisions`. It starts from each puzzle's first image, renders the model's own actions, and sends seven tile choices to native `system_one`; the defer variant adds an eighth choice. It never uses labels while choosing moves. After all moves, it scores exact match to the verified solution. The audit established one valid solution per puzzle, so this is a whole-puzzle success measure for this dataset. Reports, action histories, boards, and checkpoints are in the `train-tracks-d1-training` Modal Volume. No solver is called during rollout.

The original example remains in `finetune-liquid-image-decisions/` as a reference.

## Experiment reports

| Variant | Setup and results |
| --- | --- |
| Plain baseline | [Base versus SFT evaluation](docs/BASELINE_EVALUATION.md) |
| Focus | [Visual focus experiment](docs/FOCUS_EXPERIMENT.md) |
| Counts | [Setup](docs/COUNTS_EXPERIMENT.md), [training log](docs/COUNTS_FULL_TRAINING.md), [validation and gallery](docs/COUNTS_VALIDATION.md) |
| Counts + ports | [Setup](docs/PORTS_EXPERIMENT.md), [training log](docs/PORTS_FULL_TRAINING.md), [validation and gallery](docs/PORTS_VALIDATION.md) |
| Defer | [Experiment method and commands](docs/NEXT_EXPERIMENT.md) |
| Defer full run | [Training curves and three-run comparison](../README.md) |
| Defer validation | [46-puzzle analysis and HTML gallery](docs/DEFER_VALIDATION.md) |

## View a completed puzzle

The evaluation output includes a JSON path in the Modal Volume. Download that report, then render its first puzzle using the local Hugging Face Parquet export. The viewer uses Python 3.11 with `pyarrow`, `opencv-python`, and `Pillow` installed.

```powershell
$env:PYTHONIOENCODING = "utf-8"
uv run modal volume get train-tracks-d1-training rollouts/REPORT.json modal/results/REPORT.json
py -3.11 modal/tools/view_result.py modal/results/REPORT.json
```

Open `modal/results/REPORT.png`. The report also contains every chosen cell and its per-puzzle score.
To inspect the image the model saw before a particular decision, add `--step 0` (the first decision) or another zero-based step number. The focused row and column appear when the report used the `focus` variant.

For a browsable gallery of every puzzle in a report, run:

```powershell
py -3.11 modal/tools/render_gallery.py modal/results/REPORT.json
```

The HTML and board images are saved under `modal/eval-gallery/REPORT/` and can be
[regenerated from the saved rollout JSON](docs/GALLERIES.md). The recorded
base-model validation result is in [BASELINE_EVALUATION.md](docs/BASELINE_EVALUATION.md).
