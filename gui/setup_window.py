"""Secure first-run discovery and pairing wizard for the Windows dashboard."""
from __future__ import annotations

import logging
import threading
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

import customtkinter as ctk

from desktop_config import load_connection, save_connection, validate_connection
from integration.pi_discovery import discover_pis
from integration.pi_provisioning import check_pi_health, pair_with_pi
from .ui_components import COLORS, Card


class SetupWindow(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.connection: dict[str, str] | None = None
        self._saved_connection: dict[str, str] | None = None
        self._fingerprint = ""
        self._fingerprint_confirmed = ctk.BooleanVar(value=False)
        self._discovered_devices: dict[str, dict[str, str]] = {}
        self.logger = logging.getLogger(__name__)
        self.title("PORTAL-XLINK setup")
        self.geometry("620x590")
        self.resizable(False, False)
        self.configure(fg_color=COLORS["bg"])
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        ctk.CTkLabel(
            self,
            text="Connect your dashboard",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=COLORS["text"],
        ).pack(anchor="w", padx=28, pady=(26, 4))
        ctk.CTkLabel(
            self,
            text="Find your Raspberry Pi automatically. First-time pairing needs "
            "the local approval code and a one-time check that the Pi certificate "
            "matches the fingerprint shown on its local console. Your API credential "
            "is transferred securely and stored with Windows DPAPI.",
            text_color=COLORS["muted"],
            wraplength=550,
            justify="left",
        ).pack(anchor="w", padx=28, pady=(0, 18))

        card = Card(self)
        card.pack(fill="x", padx=24, pady=(0, 16))
        ctk.CTkLabel(
            card,
            text="RASPBERRY PI",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=11, weight="bold"),
        ).pack(anchor="w", padx=16, pady=(16, 5))
        self.url_entry = ctk.CTkEntry(
            card,
            placeholder_text="Automatically discovered on your local network",
            width=540,
            height=38,
        )
        self.url_entry.pack(padx=16, fill="x")
        self.fingerprint_label = ctk.CTkLabel(
            card,
            text="TLS identity fingerprint will appear after discovery.",
            text_color=COLORS["muted"],
            wraplength=530,
            justify="left",
            font=ctk.CTkFont(size=10),
        )
        self.fingerprint_label.pack(anchor="w", padx=16, pady=(8, 2))
        self.fingerprint_check = ctk.CTkCheckBox(
            card,
            text="I verified this fingerprint against the Pi's local console",
            variable=self._fingerprint_confirmed,
            text_color=COLORS["text"],
        )
        self.fingerprint_check.pack(anchor="w", padx=16, pady=(2, 4))
        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.pack(fill="x", padx=16, pady=(8, 0))
        self.discover_button = ctk.CTkButton(
            actions,
            text="Find Pi on this network",
            fg_color=COLORS["surface_alt"],
            command=self._discover,
        )
        self.discover_button.pack(side="left")
        self.device_menu = ctk.CTkOptionMenu(
            actions,
            values=["No Pi found"],
            command=self._select_device,
            width=230,
            state="disabled",
        )
        self.device_menu.pack(side="right")
        ctk.CTkLabel(
            card,
            text="ONE-TIME LOCAL APPROVAL CODE",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=11, weight="bold"),
        ).pack(anchor="w", padx=16, pady=(14, 5))
        self.code_entry = ctk.CTkEntry(
            card,
            placeholder_text="Only needed for first-time pairing or re-pairing",
            width=540,
            height=38,
        )
        self.code_entry.pack(padx=16, pady=(0, 16), fill="x")
        self.status_label = ctk.CTkLabel(
            self,
            text="",
            text_color=COLORS["muted"],
            wraplength=550,
            justify="left",
        )
        self.status_label.pack(anchor="w", padx=28, pady=(0, 14))
        self.connect_button = ctk.CTkButton(
            self,
            text="Connect securely",
            fg_color=COLORS["blue"],
            command=self._connect,
        )
        self.connect_button.pack(anchor="e", padx=24)
        self._load_existing_settings()
        if not self.url_entry.get().strip():
            self.after(200, self._discover)

    def _load_existing_settings(self) -> None:
        try:
            existing = load_connection()
        except ValueError as exc:
            self.status_label.configure(
                text=f"Saved connection needs attention: {exc}",
                text_color=COLORS["amber"],
            )
            return
        if existing is not None:
            self._saved_connection = existing
            self._fingerprint = existing.get("certificate_sha256", "")
            self._fingerprint_confirmed.set(bool(self._fingerprint))
            self.url_entry.insert(0, existing["api_url"])
            self.fingerprint_label.configure(
                text=(
                    "Previously paired Pi TLS fingerprint: "
                    + (self._fingerprint or "not pinned (legacy connection)")
                )
            )
            self.status_label.configure(
                text="Saved pairing found. Connect to reuse it, or enter a new "
                "local approval code to pair again.",
                text_color=COLORS["green"],
            )

    def _discover(self) -> None:
        self.discover_button.configure(state="disabled", text="Searching...")
        self.status_label.configure(
            text="Searching for PORTAL-XLINK devices on this local network...",
            text_color=COLORS["muted"],
        )

        def search() -> None:
            try:
                devices = discover_pis()
                message = ""
            except (OSError, ValueError) as exc:
                devices = []
                message = f"Pi discovery failed: {exc}"
            try:
                self.after(0, self._show_devices, devices, message)
            except RuntimeError:
                self.logger.debug("Pi discovery finished after setup window closed")

        threading.Thread(target=search, daemon=True, name="pi-device-discovery").start()

    def _show_devices(
        self, devices: list[dict[str, str]], error: str = ""
    ) -> None:
        if not self.winfo_exists():
            return
        self.discover_button.configure(state="normal", text="Find Pi on this network")
        if error:
            self.status_label.configure(text=error, text_color=COLORS["red"])
            return
        if not devices:
            self.status_label.configure(
                text="No Pi was found. Check that the Pi is powered on and both "
                "devices are on the same local network, then try again.",
                text_color=COLORS["amber"],
            )
            return
        self._discovered_devices = {
            f"Pi at {urlsplit(device['api_url']).hostname}": device
            for device in devices
        }
        labels = list(self._discovered_devices)
        self.device_menu.configure(values=labels, state="normal")
        self.device_menu.set(labels[0])
        self._select_device(labels[0])
        suffix = f" ({len(devices)} found)" if len(devices) > 1 else ""
        self.status_label.configure(
            text=f"Secure Pi endpoint discovered{suffix}.",
            text_color=COLORS["green"],
        )

    def _select_device(self, label: str) -> None:
        device = self._discovered_devices.get(label)
        if device is None:
            return
        self.url_entry.delete(0, "end")
        self.url_entry.insert(0, device["api_url"])
        self._fingerprint = device["certificate_sha256"]
        previously_trusted = (
            self._saved_connection is not None
            and self._saved_connection.get("api_url") == device["api_url"]
            and self._saved_connection.get("certificate_sha256") == self._fingerprint
        )
        self._fingerprint_confirmed.set(previously_trusted)
        self.fingerprint_label.configure(
            text="Pi TLS SHA-256 fingerprint (must match the local Pi console):\n"
            + self._fingerprint
        )

    def _connect(self) -> None:
        api_url = self.url_entry.get().strip().rstrip("/")
        code = self.code_entry.get().strip()
        if not self._fingerprint:
            self.status_label.configure(
                text="Find the Pi on this network before connecting so its TLS "
                "identity can be verified.",
                text_color=COLORS["amber"],
            )
            return
        saved = self._saved_connection
        if not code and saved and saved["api_url"] == api_url:
            connection = saved
            action = lambda: check_pi_health(connection)
        else:
            if not self._fingerprint_confirmed.get():
                self.status_label.configure(
                    text="Compare the full SHA-256 fingerprint above with the "
                    "fingerprint printed on the Pi console, then confirm the checkbox.",
                    text_color=COLORS["amber"],
                )
                return
            if not code:
                self.status_label.configure(
                    text="Enter the one-time local approval code from the Pi "
                    "service log. API tokens are never entered or displayed.",
                    text_color=COLORS["amber"],
                )
                return
            try:
                validate_connection(api_url, "temporary-validation")
            except ValueError as exc:
                self.status_label.configure(text=str(exc), text_color=COLORS["red"])
                return
            action = lambda: pair_with_pi(api_url, code, self._fingerprint)
            connection = None

        self.connect_button.configure(state="disabled", text="Connecting...")

        def connect() -> None:
            message = ""
            result: dict[str, str] | None = None
            try:
                if connection is not None:
                    action()
                    result = connection
                else:
                    result = action()
                save_connection(
                    result["api_url"],
                    result["token"],
                    result.get("certificate_sha256", ""),
                )
            except (HTTPError, URLError, OSError, RuntimeError, ValueError) as exc:
                message = f"Could not securely connect to the Pi: {exc}"
                result = None
            try:
                self.after(0, self._finish_connect, result, message)
            except RuntimeError:
                self.logger.debug("Pi setup finished after window closed")

        threading.Thread(target=connect, daemon=True, name="pi-secure-pairing").start()

    def _finish_connect(
        self, connection: dict[str, str] | None, error: str
    ) -> None:
        if not self.winfo_exists():
            return
        self.connect_button.configure(state="normal", text="Connect securely")
        if error or connection is None:
            self.status_label.configure(
                text=error or "The Pi connection could not be established.",
                text_color=COLORS["red"],
            )
            return
        self.connection = connection
        self.destroy()

    def _cancel(self) -> None:
        self.connection = None
        self.destroy()
