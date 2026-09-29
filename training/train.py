"""Train, validate, and export the PORTAL-XLINK YOLOv8n detector."""
from __future__ import annotations

import argparse
from pathlib import Path


def _model(weights: str):
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise SystemExit(
            "Ultralytics is required. Install the training dependencies with "
            "`pip install -r requirements.txt`."
        ) from exc
    return YOLO(weights)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the SKU110K YOLOv8n detector")
    parser.add_argument("--data", type=Path, default=Path("data/sku110k/data.yaml"))
    parser.add_argument("--weights", default="yolov8n.pt")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--device", default=None, help="cpu, 0, or a CUDA device id")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--project", type=Path, default=Path("runs/sku110k"))
    parser.add_argument("--name", default="yolov8n")
    parser.add_argument("--validate", action="store_true", help="validate existing --weights instead of training")
    parser.add_argument(
        "--export-only", action="store_true",
        help="skip training and validation and only export the supplied weights",
    )
    parser.add_argument(
        "--export", action="store_true",
        help="export the trained/validated model for deployment",
    )
    parser.add_argument(
        "--format", choices=("ncnn", "onnx"), default="ncnn",
        help="deployment format when --export is selected (default: ncnn)",
    )
    args = parser.parse_args()

    if args.export_only and not args.export:
        parser.error("--export-only requires --export")
    if not args.export_only and not args.data.is_file():
        raise SystemExit(
            f"Dataset YAML not found: {args.data}. Run "
            "`python -m training.prepare_sku110k --source <extracted-kaggle-folder>` first."
        )
    model = _model(args.weights)
    if args.export_only:
        pass
    elif args.validate:
        model.val(data=str(args.data), imgsz=args.imgsz, batch=args.batch, device=args.device)
    else:
        model.train(
            data=str(args.data),
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            device=args.device,
            workers=args.workers,
            project=str(args.project),
            name=args.name,
            pretrained=True,
            single_cls=True,
        )
    if args.export:
        model.export(
            format=args.format,
            imgsz=args.imgsz,
            **({"simplify": False} if args.format == "onnx" else {}),
        )


if __name__ == "__main__":
    main()
