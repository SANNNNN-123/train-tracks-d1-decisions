"""Check board grid detection on every train and validation decision image."""
import argparse
from pathlib import Path
from io import BytesIO
import sys

import cv2
import numpy as np
import pyarrow.parquet as parquet
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from board import detect_grid, grid_lines

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--first", action="store_true")
    args = parser.parse_args()
    failures = []
    grids = {}
    for split in ("train", "validation"):
        path = ROOT / "decision-dataset/huggingface/data" / f"{split}.parquet"
        checked = 0
        for batch in parquet.ParquetFile(path).iter_batches(
                batch_size=64,
                columns=["id", "puzzle_id", "images", "rows", "columns"]):
            for row in batch.to_pylist():
                try:
                    image = Image.open(BytesIO(row["images"][0]["bytes"]))
                    detected = detect_grid(image, row["rows"], row["columns"])
                    expected = grids.setdefault(row["puzzle_id"], detected)
                    if detected != expected:
                        raise ValueError("Grid coordinates drift within puzzle")
                except ValueError:
                    failures.append(row["id"])
                    if len(failures) == 1:
                        output = ROOT / "modal/results/grid-detection-failure.png"
                        image.save(output)
                        raw = np.asarray(image.crop((30, 0, image.width,
                                                      image.height - 30)))
                        dark = (cv2.cvtColor(raw, cv2.COLOR_RGB2GRAY) < 130).astype(np.uint8)
                        print(f"first failure: {row['id']}; expected: "
                              f"{row['rows'] + 1} horizontal and "
                              f"{row['columns'] + 1} vertical lines")
                        print("candidates:",
                              grid_lines(dark.sum(1), raw.shape[1] * .60),
                              grid_lines(dark.sum(0), raw.shape[0] * .60))
                    if args.first:
                        return
                checked += 1
        print(f"{split}: {checked} images checked")
    print(f"grid failures: {len(failures)}")
    for row_id in failures[:20]:
        print(row_id)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
