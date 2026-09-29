"""Serial controller using the standard library only."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SerialController:
    port: str = "/dev/ttyUSB0"
    baudrate: int = 9600
    last_payload: str = ""
    simulated: bool = True
    _serial: Any = None

    def open(self) -> bool:
        if not self.port:
            self.simulated = True
            return True
        try:
            import serial  # type: ignore
            self._serial = serial.Serial(self.port, self.baudrate, timeout=1)
            self.simulated = False
        except ImportError:
            self.simulated = True
        except (OSError, ValueError):
            self.simulated = True
        return True

    @classmethod
    def from_settings(cls, settings: Any) -> "SerialController":
        return cls(port=settings.serial_port, baudrate=settings.serial_baudrate)

    def write(self, payload: str) -> str:
        self.last_payload = payload
        if not self.simulated and self._serial is not None:
            self._serial.write(payload.encode("utf-8"))
        return payload

    def close(self) -> None:
        if self._serial is not None:
            self._serial.close()
        self._serial = None

    def status(self) -> dict[str, object]:
        return {
            "port": self.port,
            "baudrate": self.baudrate,
            "available": not self.simulated,
            "mode": "simulation" if self.simulated else "serial",
        }
