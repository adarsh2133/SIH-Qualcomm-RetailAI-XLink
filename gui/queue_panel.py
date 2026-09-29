from .ui_components import ScrollPage, MetricCard


class QueuePanel(ScrollPage):
    def __init__(self, master, settings=None, **kwargs):
        super().__init__(master, "Queue", "Queue intelligence from validated current detections only", **kwargs)
        for i, (name, label) in enumerate((("current", "Current queue"), ("wait", "Average wait"))):
            card = MetricCard(self.body, label, icon="queue" if name == "current" else "timer")
            card.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 8, 8 if i == 0 else 0))
        self.body.grid_columnconfigure(0, weight=1); self.body.grid_columnconfigure(1, weight=1)
