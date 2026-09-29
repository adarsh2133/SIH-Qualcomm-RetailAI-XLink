"""Convert the Kaggle SKU110K annotations to a YOLO dataset.

The Kaggle export contains one CSV per split with rows shaped like:
image_name,x1,y1,x2,y2,class

SKU110K is a single-class detection problem: every box is a ``商品``/SKU
instance, so the generated YOLO dataset has one class named ``sku``.
"""
from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path
from typing import Iterable


CLASS_ID = 0
CLASS_NAME = "sku"
SPLITS = ("train", "val", "test")


def _float(value: str, field: str, row_number: int) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field} on annotation row {row_number}: {value!r}") from exc


def _annotation_path(source: Path, split: str) -> Path:
    candidates = (
        source / f"{split}.csv",
        source / "annotations" / f"{split}.csv",
        source / f"{split}_annotations.csv",
        source / f"annotations_{split}.csv",
        source / "annotations" / f"annotations_{split}.csv",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"Could not find annotations for {split}; expected one of: "
        + ", ".join(str(path) for path in candidates)
    )


def _image_path(source: Path, split: str, image_name: str) -> Path:
    name = Path(image_name).name
    candidates = (
        source / split / name,
        source / "images" / split / name,
        source / "images" / name,
        source / name,
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"Image {image_name!r} referenced by {split} annotations was not found"
    )


def _normalise_box(
    x1: float, y1: float, x2: float, y2: float, width: int, height: int, row_number: int
) -> tuple[float, float, float, float]:
    left, right = sorted((max(0.0, min(float(width), x1)), max(0.0, min(float(width), x2))))
    top, bottom = sorted((max(0.0, min(float(height), y1)), max(0.0, min(float(height), y2))))
    box_width, box_height = right - left, bottom - top
    if box_width <= 0 or box_height <= 0:
        raise ValueError(f"Annotation row {row_number} has an empty bounding box")
    return (
        (left + right) / (2 * width),
        (top + bottom) / (2 * height),
        box_width / width,
        box_height / height,
    )


def _headers(fieldnames: Iterable[str] | None) -> dict[str, str]:
    if not fieldnames:
        raise ValueError("Annotation CSV has no header")
    lower = {field.strip().lower(): field for field in fieldnames}
    aliases = {
        "image": ("image_name", "image", "filename", "file_name"),
        "x1": ("x1", "xmin", "left"),
        "y1": ("y1", "ymin", "top"),
        "x2": ("x2", "xmax", "right"),
        "y2": ("y2", "ymax", "bottom"),
    }
    result: dict[str, str] = {}
    for name, choices in aliases.items():
        match = next((lower[choice] for choice in choices if choice in lower), None)
        if match is None:
            raise ValueError(f"Annotation CSV is missing a {name} column")
        result[name] = match
    return result


def prepare_dataset(source: Path, output: Path) -> int:
    """Convert all SKU110K splits and return the number of copied images."""
    from PIL import Image

    copied = 0
    for split in SPLITS:
        annotation_file = _annotation_path(source, split)
        image_dir = output / "images" / split
        label_dir = output / "labels" / split
        image_dir.mkdir(parents=True, exist_ok=True)
        label_dir.mkdir(parents=True, exist_ok=True)
        grouped: dict[str, list[str]] = {}
        with annotation_file.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            columns = _headers(reader.fieldnames)
            for row_number, row in enumerate(reader, start=2):
                image_name = Path(row[columns["image"]]).name
                image_path = _image_path(source, split, image_name)
                with Image.open(image_path) as image:
                    width, height = image.size
                box = _normalise_box(
                    _float(row[columns["x1"]], "x1", row_number),
                    _float(row[columns["y1"]], "y1", row_number),
                    _float(row[columns["x2"]], "x2", row_number),
                    _float(row[columns["y2"]], "y2", row_number),
                    width,
                    height,
                    row_number,
                )
                grouped.setdefault(image_name, []).append(
                    f"{CLASS_ID} " + " ".join(f"{value:.6f}" for value in box)
                )
        for image_name, labels in grouped.items():
            source_image = _image_path(source, split, image_name)
            destination_image = image_dir / image_name
            shutil.copy2(source_image, destination_image)
            (label_dir / f"{Path(image_name).stem}.txt").write_text(
                "\n".join(labels) + "\n", encoding="utf-8"
            )
            copied += 1
    (output / "data.yaml").write_text(
        "path: .\n"
        "train: images/train\n"
        "val: images/val\n"
        "test: images/test\n"
        "names:\n"
        f"  0: {CLASS_NAME}\n",
        encoding="utf-8",
    )
    return copied


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare SKU110K for Ultralytics YOLO")
    parser.add_argument("--source", type=Path, required=True, help="Extracted Kaggle dataset directory")
    parser.add_argument(
        "--output", type=Path, default=Path("data") / "sku110k",
        help="YOLO dataset output directory (default: data/sku110k)",
    )
    args = parser.parse_args()
    print(f"Copied {prepare_dataset(args.source, args.output)} images to {args.output}")


if __name__ == "__main__":
    main()
