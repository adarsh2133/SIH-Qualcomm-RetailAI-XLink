"""Reusable visual primitives for the PORTAL-XLINK command centre."""
from __future__ import annotations

import customtkinter as ctk
from .icons import Icon, status_icon_name


COLORS = {
    "bg": "#0b1118", "surface": "#121c27", "surface_alt": "#172535",
    "border": "#243548", "text": "#f3f7fb", "muted": "#8da1b5",
    "blue": "#4ea1ff", "green": "#43d17a", "amber": "#f5c451", "red": "#ff6b6b",
}

BADGE_BACKGROUNDS = {
    "ONLINE": "#183d2a",
    "AVAILABLE": "#183d2a",
    "CONNECTING": "#403617",
    "DEGRADED": "#403617",
    "OFFLINE": "#451f25",
    "NOT CONFIGURED": "#26313c",
    "N/A": "#26313c",
}


class ScrollPage(ctk.CTkScrollableFrame):
    def __init__(self, master, title: str, subtitle: str, **kwargs):
        super().__init__(master, fg_color=COLORS["bg"], corner_radius=0,
                         scrollbar_button_color=COLORS["border"], **kwargs)
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text=title, font=ctk.CTkFont(size=26, weight="bold"),
                     text_color=COLORS["text"]).grid(row=0, column=0, sticky="w", pady=(8, 2))
        ctk.CTkLabel(self, text=subtitle, text_color=COLORS["muted"],
                     font=ctk.CTkFont(size=12)).grid(row=1, column=0, sticky="w", pady=(0, 20))
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=2, column=0, sticky="nsew")
        self.body.grid_columnconfigure(0, weight=1)


class Card(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=COLORS["surface"], border_color=COLORS["border"],
                         border_width=1, corner_radius=12, **kwargs)


class Badge(ctk.CTkFrame):
    def __init__(self, master, text="N/A", state="N/A", **kwargs):
        color = {"ONLINE": COLORS["green"], "AVAILABLE": COLORS["green"],
                 "CONNECTING": COLORS["amber"], "DEGRADED": COLORS["amber"],
                 "OFFLINE": COLORS["red"], "NOT CONFIGURED": COLORS["muted"],
                 "N/A": COLORS["muted"]}.get(state, COLORS["muted"])
        super().__init__(master, fg_color=BADGE_BACKGROUNDS.get(state, "#26313c"),
                         corner_radius=8, **kwargs)
        Icon(self, status_icon_name(state), size=14, color=color,
             bg=BADGE_BACKGROUNDS.get(state, "#26313c")).pack(side="left", padx=(7, 2), pady=4)
        ctk.CTkLabel(self, text=text, text_color=color,
                     font=ctk.CTkFont(size=11, weight="bold"),
                     fg_color="transparent").pack(side="left", padx=(0, 7), pady=3)


class MetricCard(Card):
    def __init__(self, master, label: str, value="N/A", detail="No validated live data",
                 icon: str | None = None, **kwargs):
        super().__init__(master, **kwargs)
        title = ctk.CTkFrame(self, fg_color="transparent")
        title.pack(anchor="w", padx=16, pady=(12, 2))
        if icon:
            Icon(title, icon, size=16, color=COLORS["blue"], bg=COLORS["surface"]).pack(side="left", padx=(0, 7))
        ctk.CTkLabel(title, text=label.upper(), text_color=COLORS["muted"],
                     font=ctk.CTkFont(size=11, weight="bold")).pack(side="left")
        self.value_label = ctk.CTkLabel(self, text=str(value), text_color=COLORS["text"],
                                        font=ctk.CTkFont(size=27, weight="bold"))
        self.value_label.pack(anchor="w", padx=16, pady=(2, 0))
        self.detail_label = ctk.CTkLabel(self, text=detail, text_color=COLORS["muted"],
                                         font=ctk.CTkFont(size=11))
        self.detail_label.pack(anchor="w", padx=16, pady=(0, 14))

    def set_value(self, value, detail=None):
        self.value_label.configure(text=str(value))
        if detail is not None:
            self.detail_label.configure(text=detail)


def empty_state(master, title="No validated data", detail="This view will populate when current live telemetry is available."):
    card = Card(master)
    ctk.CTkLabel(card, text="—", text_color=COLORS["muted"],
                 font=ctk.CTkFont(size=32, weight="bold")).pack(pady=(22, 0))
    ctk.CTkLabel(card, text=title, text_color=COLORS["text"],
                 font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(0, 4))
    ctk.CTkLabel(card, text=detail, text_color=COLORS["muted"],
                 wraplength=680, justify="center").pack(padx=20, pady=(0, 22))
    return card
