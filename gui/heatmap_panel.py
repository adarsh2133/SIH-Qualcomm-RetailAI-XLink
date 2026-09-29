from .ui_components import ScrollPage, empty_state


class HeatmapPanel(ScrollPage):
    def __init__(self, master, settings=None, **kwargs):
        super().__init__(master, "Heatmap", "Live dwell density from validated detections", **kwargs)
        empty_state(self.body, "Heatmap unavailable",
                    "A heatmap is shown only when the active inference pipeline provides current valid coordinates.").grid(row=0, column=0, sticky="ew")
