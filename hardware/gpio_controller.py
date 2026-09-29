"""GPIO abstraction with a lightweight simulation mode."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class GPIOController:
    pins: Dict[int, bool] = field(default_factory=dict)
    simulated: bool = True
    _gpio: object = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        try:
            import RPi.GPIO as gpio  # type: ignore
            gpio.setmode(gpio.BCM)
            self._gpio = gpio
            self.simulated = False
        except ImportError:
            self.simulated = True

    @classmethod
    def from_settings(cls, settings: object) -> "GPIOController":
        pins = {pin: False for pin in getattr(settings, "gpio_pins", ())}
        return cls(pins=pins)

    def set_pin(self, pin_number: int, value: bool) -> None:
        self.pins[pin_number] = value
        if not self.simulated:
            self._gpio.setup(pin_number, self._gpio.OUT)
            self._gpio.output(pin_number, self._gpio.HIGH if value else self._gpio.LOW)

    def read_pin(self, pin_number: int) -> bool:
        if not self.simulated:
            self._gpio.setup(pin_number, self._gpio.IN)
            return bool(self._gpio.input(pin_number))
        return self.pins.get(pin_number, False)

    def status(self) -> dict[str, object]:
        return {
            "available": not self.simulated,
            "simulated": self.simulated,
            "mode": "simulation" if self.simulated else "raspberry-pi-gpio",
            "pins": dict(self.pins),
        }

    def close(self) -> None:
        if not self.simulated:
            self._gpio.cleanup()
