# Recreate the board galleries

The HTML galleries and their board PNGs are generated review files, so they
are kept out of Git. The saved rollout JSON reports remain in `modal/results/`.

From the project root, with the local Hugging Face validation export at
`decision-dataset/huggingface/data/validation.parquet`, run:

```powershell
py -3.11 modal/tools/render_gallery.py modal/results/validation-defer-sft-d1-2b-defer-full-train-tracks-decisions-20261111T194102Z-20261111T210400Z.json
```

Open the `index.html` path printed by the command. Each page shows the model's
predicted board beside the verified board for all 46 puzzles. The generated
files go under `modal/eval-gallery/` and are ignored by Git.

To inspect another variant, pass its full validation report from
`modal/results/` to the same command. The archived report includes small
representative images in `modal/docs/figures/` for viewing without regeneration.
