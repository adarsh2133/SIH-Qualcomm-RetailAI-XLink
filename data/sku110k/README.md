# SKU110K dataset

This directory is generated locally and is intentionally not populated in the
repository. Download and extract the SKU110K Kaggle dataset, then run from the
repository root:

```powershell
python -m training.prepare_sku110k --source C:\path\to\sku110k
python -m training.train --epochs 100 --imgsz 640 --batch 16 --device 0
```

The converter expects `train.csv`, `val.csv`, and `test.csv` (or the equivalent
`annotations_train.csv`, `annotations_val.csv`, and `annotations_test.csv`
files) and image files in each split, `images\<split>`,
`images`, or the source root. It writes YOLO labels under `labels\<split>` and
the generated dataset manifest to `data.yaml`.
