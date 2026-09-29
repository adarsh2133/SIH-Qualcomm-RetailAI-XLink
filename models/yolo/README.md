# Raspberry Pi NCNN model

Export the trained Ultralytics `best.pt` on the training computer using
`python -m training.train --export-only --export --weights <path-to-best.pt>`.
Copy the generated `best_ncnn_model` directory here. It must contain a
matching `.param` and `.bin` model pair. The training `.pt` file is not loaded
by the Raspberry Pi NCNN runtime.
