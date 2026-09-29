"""Guided first-run LCD setup for a systemd-installed Raspberry Pi service."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable


_PIN_NAMES = ("rs", "enable", "d4", "d5", "d6", "d7")
_SAFE_PIN_CANDIDATES = frozenset(
    {4, 5, 6, 12, 13, *range(16, 28)}
)


def validate_parallel_pins(pins: tuple[int, ...], used_pins: set[int]) -> dict[str, int]:
    if len(pins) != len(_PIN_NAMES) or len(set(pins)) != len(_PIN_NAMES):
        raise ValueError("Enter six different BCM GPIO pin numbers.")
    if any(pin not in _SAFE_PIN_CANDIDATES for pin in pins):
        raise ValueError(
            "Choose BCM GPIOs from 4, 5, 6, 12, 13, or 16 through 27. "
            "GPIO2/3 (I2C), SPI, UART, and ID pins are reserved."
        )
    conflicts = set(pins) & used_pins
    if conflicts:
        raise ValueError(
            "These BCM pins are already assigned to another PORTAL peripheral: "
            + ", ".join(map(str, sorted(conflicts)))
        )
    return dict(zip(_PIN_NAMES, pins))


def _systemd_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def lcd_dropin_contents(
    *,
    interface: str,
    address: int | None = None,
    gpio: dict[str, int] | None = None,
) -> str:
    if interface == "i2c":
        if address is not None and not 0x03 <= address <= 0x77:
            raise ValueError("LCD I2C address must be a valid 7-bit address.")
        lines = [
            "[Service]",
            "Environment=PORTAL_LCD_INTERFACE=i2c",
            "Environment=PORTAL_LCD_I2C_BUS=1",
            "Environment=PORTAL_LCD_I2C_ADDRESS="
            + (f"0x{address:02x}" if address is not None else "auto"),
        ]
    elif interface == "parallel":
        if gpio is None or set(gpio) != set(_PIN_NAMES):
            raise ValueError("Parallel LCD setup requires all six GPIO signals.")
        validate_parallel_pins(tuple(gpio[name] for name in _PIN_NAMES), set())
        mapping = json.dumps(gpio, separators=(",", ":"))
        lines = [
            "[Service]",
            "Environment=PORTAL_LCD_INTERFACE=parallel",
            "Environment=PORTAL_LCD_GPIO_JSON=" + _systemd_quote(mapping),
        ]
    else:
        raise ValueError("LCD interface must be i2c or parallel.")
    return "\n".join(lines) + "\n"


def write_lcd_dropin(
    contents: str,
    path: str | Path = "/etc/systemd/system/portal-xlink.service.d/lcd.conf",
) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(contents, encoding="utf-8")
    os.replace(temporary, destination)
    try:
        destination.chmod(0o644)
    except OSError:
        if os.name != "nt":
            raise
    return destination


def _ask_yes_no(prompt: str, input_fn: Callable[[str], str]) -> bool:
    return input_fn(prompt).strip().lower() in {"y", "yes"}


def configure_lcd(
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    dropin_path: str | Path = "/etc/systemd/system/portal-xlink.service.d/lcd.conf",
    used_pins: set[int] | None = None,
) -> Path | None:
    from hardware.lcd_display import I2CBackpackLCD

    try:
        addresses = I2CBackpackLCD.detect(1, None)
    except (OSError, RuntimeError) as exc:
        output_fn(f"I2C bus detection unavailable: {exc}")
        addresses = []
    if addresses:
        selected = addresses[0]
        if len(addresses) > 1:
            listed = ", ".join(f"0x{address:02x}" for address in addresses)
            choice = input_fn(
                f"Detected I2C devices at {listed}. Enter the LCD address "
                "(hex, or blank for first): "
            ).strip()
            if choice:
                try:
                    selected = int(choice, 0)
                except ValueError as exc:
                    raise ValueError("Enter the I2C address in hexadecimal, such as 0x27.") from exc
                if selected not in addresses:
                    raise ValueError("The selected address was not detected on I2C bus 1.")
        output_fn(f"Detected I2C LCD backpack at 0x{selected:02x}.")
        contents = lcd_dropin_contents(interface="i2c", address=selected)
    else:
        output_fn("No supported I2C backpack responded on I2C bus 1.")
        if not _ask_yes_no(
            "Is this a parallel HD44780 LCD that is already wired to BCM GPIO? [y/N] ",
            input_fn,
        ):
            output_fn("Keeping automatic LCD detection enabled; no configuration changed.")
            return None
        output_fn(
            "Choose six unused BCM GPIOs for RS, E, D4, D5, D6, D7. "
            "Never use GPIO2/3 for parallel mode and check existing peripherals."
        )
        raw = input_fn("Enter the six BCM GPIO numbers separated by commas: ")
        try:
            pins = tuple(int(part.strip()) for part in raw.split(","))
        except ValueError as exc:
            raise ValueError("GPIO pin mapping must contain six comma-separated integers.") from exc
        mapping = validate_parallel_pins(pins, used_pins or set())
        contents = lcd_dropin_contents(interface="parallel", gpio=mapping)

    path = write_lcd_dropin(contents, dropin_path)
    output_fn(f"Saved guided LCD settings to {path}.")
    return path


def main() -> None:
    if sys.platform != "linux" or (hasattr(os, "geteuid") and os.geteuid() != 0):
        raise SystemExit(
            "Run this guided setup on Raspberry Pi OS with sudo, after the LCD is wired."
        )
    try:
        result = configure_lcd()
    except (OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"LCD setup was not applied: {exc}") from exc
    if result is not None:
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "restart", "portal-xlink.service"], check=True)


if __name__ == "__main__":
    main()
