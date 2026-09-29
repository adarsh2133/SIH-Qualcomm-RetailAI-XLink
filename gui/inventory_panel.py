import customtkinter as ctk

from .ui_components import ScrollPage, MetricCard, Card, COLORS


class InventoryPanel(ScrollPage):
    def __init__(self, master, settings=None, **kwargs):
        super().__init__(
            master,
            "Inventory",
            "Shelf quantities require a configured, stabilized inventory estimate; raw boxes are not stock counts",
            **kwargs,
        )
        self.units_card = MetricCard(
            self.body,
            "Visible SKU boxes (estimate)",
            detail="Waiting for the live shelf-camera estimate",
            icon="inventory",
        )
        self.units_card.grid(row=0, column=0, sticky="ew")
        self.detection_card = Card(self.body)
        self.detection_card.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        ctk.CTkLabel(
            self.detection_card,
            text="CURRENT YOLO DETECTIONS",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=11, weight="bold"),
        ).pack(anchor="w", padx=16, pady=(13, 8))
        self.detection_list = ctk.CTkFrame(self.detection_card, fg_color="transparent")
        self.detection_list.pack(fill="x", padx=16, pady=(0, 13))
        self._detections_label = ctk.CTkLabel(
            self.detection_list,
            text="",
            text_color=COLORS["muted"],
            anchor="w",
            justify="left",
        )
        self._detections_label.pack(fill="x")
        self.update_detections([], live=False)

    def update_inventory_estimate(self, estimate):
        if not isinstance(estimate, dict) or estimate.get("state") != "AVAILABLE":
            self.units_card.set_value(
                "N/A",
                "Shelf camera inference is not currently available",
            )
            return
        units = estimate.get("visible_sku_boxes")
        if not isinstance(units, int) or isinstance(units, bool) or units < 0:
            self.units_card.set_value(
                "N/A",
                "Shelf camera returned an invalid unit estimate",
            )
            return
        camera_id = estimate.get("camera_id", "shelf camera")
        self.units_card.set_value(
            units,
            (
                f"{camera_id} · visible SKU boxes in latest frame; "
                "estimate only, not verified physical stock"
            ),
        )

    def update_detections(self, detections, live):
        if not live:
            self._detections_label.configure(
                text="Waiting for live detection data from the Raspberry Pi.",
                text_color=COLORS["muted"],
            )
            return
        if not detections:
            self._detections_label.configure(
                text="Live feed connected; no SKU detections in the latest frame.",
                text_color=COLORS["muted"],
            )
            return
        lines = []
        for detection in detections[:20]:
            camera_id = detection.get("camera_id", "unknown")
            class_id = detection.get("class_id", "N/A")
            confidence = detection.get("confidence")
            confidence_text = (f"{float(confidence):.1%}"
                               if isinstance(confidence, (int, float)) else "N/A")
            bbox = detection.get("bbox", [])
            box_text = ", ".join(f"{float(value):.0f}" for value in bbox) if bbox else "N/A"
            lines.append(
                f"{camera_id}  |  SKU class {class_id}  |  "
                f"{confidence_text}  |  box [{box_text}]"
            )
        if len(detections) > 20:
            lines.append(f"Showing 20 of {len(detections)} detections.")
        self._detections_label.configure(
            text="\n".join(lines),
            text_color=COLORS["text"],
        )
