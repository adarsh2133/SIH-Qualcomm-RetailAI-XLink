"""Asynchronous HD44780 16x2 customer alert display for Raspberry Pi."""
from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
import threading
import time
import unicodedata
from typing import Any, Callable, Protocol


LCD_WIDTH = 16
LCD_ROWS = 2
ALERT_TYPES = {"LOW_STOCK", "CRITICAL_STOCK", "OUT_OF_STOCK"}
DEFAULT_PRIORITY = {
    "OUT_OF_STOCK": 3,
    "CRITICAL_STOCK": 2,
    "LOW_STOCK": 1,
}
ALERT_TITLES = {
    "OUT_OF_STOCK": "OUT OF STOCK",
    "CRITICAL_STOCK": "CRITICAL STOCK",
    "LOW_STOCK": "LOW STOCK!",
}


class LCDBackend(Protocol):
    interface: str

    def initialize(self) -> None: ...
    def display(self, line1: str, line2: str) -> None: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class LCDSettings:
    interface: str
    bus: int
    address: int | None
    gpio: dict[str, int]
    backpack: dict[str, int]
    rotation_s: float
    scroll_interval_s: float
    priority: dict[str, int]
    camera_gpio_pins: frozenset[int]

    @classmethod
    def disabled(cls) -> "LCDSettings":
        return cls(
            interface="disabled",
            bus=1,
            address=None,
            gpio={},
            backpack={
                "rs": 0,
                "rw": 1,
                "enable": 2,
                "backlight": 3,
                "d4": 4,
                "d5": 5,
                "d6": 6,
                "d7": 7,
            },
            rotation_s=5.0,
            scroll_interval_s=0.45,
            priority=dict(DEFAULT_PRIORITY),
            camera_gpio_pins=frozenset(),
        )

    @classmethod
    def from_env(cls) -> "LCDSettings":
        interface = os.getenv("PORTAL_LCD_INTERFACE", "auto").strip().lower()
        if interface not in {"auto", "i2c", "parallel", "disabled"}:
            raise ValueError(
                "PORTAL_LCD_INTERFACE must be auto, i2c, parallel, or disabled"
            )
        try:
            bus = int(os.getenv("PORTAL_LCD_I2C_BUS", "1"))
        except ValueError as exc:
            raise ValueError("PORTAL_LCD_I2C_BUS must be an integer") from exc
        if bus < 0:
            raise ValueError("PORTAL_LCD_I2C_BUS cannot be negative")
        address_raw = os.getenv("PORTAL_LCD_I2C_ADDRESS", "auto").strip().lower()
        if address_raw in {"", "auto"}:
            address = None
        else:
            try:
                address = int(address_raw, 0)
            except ValueError as exc:
                raise ValueError(
                    "PORTAL_LCD_I2C_ADDRESS must be auto or a value such as 0x27"
                ) from exc
            if not 0x03 <= address <= 0x77:
                raise ValueError("PORTAL_LCD_I2C_ADDRESS must be a valid 7-bit address")

        gpio = _parse_mapping(
            os.getenv("PORTAL_LCD_GPIO_JSON", ""),
            "PORTAL_LCD_GPIO_JSON",
            expected={"rs", "enable", "d4", "d5", "d6", "d7"},
            minimum=0,
            maximum=27,
        )
        backpack = _parse_mapping(
            os.getenv(
                "PORTAL_LCD_I2C_PCF8574_MAP_JSON",
                '{"rs":0,"rw":1,"enable":2,"backlight":3,'
                '"d4":4,"d5":5,"d6":6,"d7":7}',
            ),
            "PORTAL_LCD_I2C_PCF8574_MAP_JSON",
            expected={"rs", "rw", "enable", "backlight", "d4", "d5", "d6", "d7"},
            minimum=0,
            maximum=7,
        )
        if len(set(backpack.values())) != 8:
            raise ValueError("LCD backpack bit mapping must use each bit exactly once")
        camera_pins_raw = os.getenv("PORTAL_GPIO_PINS", "")
        try:
            camera_pins = frozenset(
                int(value.strip()) for value in camera_pins_raw.split(",")
                if value.strip()
            )
        except ValueError as exc:
            raise ValueError("PORTAL_GPIO_PINS must contain comma-separated BCM integers") from exc
        overlap = set(gpio.values()) & camera_pins
        if overlap:
            raise ValueError(
                "LCD GPIO pin mapping conflicts with PORTAL_GPIO_PINS: "
                + ", ".join(map(str, sorted(overlap)))
            )

        try:
            rotation_s = float(os.getenv("PORTAL_LCD_ROTATION_S", "5"))
            scroll_interval_s = float(os.getenv("PORTAL_LCD_SCROLL_INTERVAL_S", "0.45"))
        except ValueError as exc:
            raise ValueError("LCD rotation and scroll intervals must be numbers") from exc
        if rotation_s < 2 or scroll_interval_s < 0.2:
            raise ValueError(
                "PORTAL_LCD_ROTATION_S must be >= 2 and "
                "PORTAL_LCD_SCROLL_INTERVAL_S must be >= 0.2"
            )

        priority_raw = os.getenv("PORTAL_LCD_ALERT_PRIORITY_JSON", "").strip()
        try:
            priority_overrides = json.loads(priority_raw) if priority_raw else {}
        except json.JSONDecodeError as exc:
            raise ValueError("PORTAL_LCD_ALERT_PRIORITY_JSON must be valid JSON") from exc
        if not isinstance(priority_overrides, dict) or any(
            key not in ALERT_TYPES
            or not isinstance(value, int)
            or isinstance(value, bool)
            for key, value in priority_overrides.items()
        ):
            raise ValueError(
                "PORTAL_LCD_ALERT_PRIORITY_JSON must map supported alert types to integers"
            )
        priority = {**DEFAULT_PRIORITY, **priority_overrides}
        return cls(
            interface=interface,
            bus=bus,
            address=address,
            gpio=gpio,
            backpack=backpack,
            rotation_s=rotation_s,
            scroll_interval_s=scroll_interval_s,
            priority=priority,
            camera_gpio_pins=camera_pins,
        )


def _parse_mapping(
    raw: str,
    variable: str,
    *,
    expected: set[str],
    minimum: int,
    maximum: int,
) -> dict[str, int]:
    if not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{variable} must be valid JSON") from exc
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{variable} must define exactly: {', '.join(sorted(expected))}")
    if any(
        not isinstance(pin, int)
        or isinstance(pin, bool)
        or not minimum <= pin <= maximum
        for pin in value.values()
    ):
        raise ValueError(f"{variable} values must be integers from {minimum} to {maximum}")
    if len(set(value.values())) != len(expected):
        raise ValueError(f"{variable} must use unique pins/bits")
    return dict(value)


def format_lcd_line(text: str, offset: int = 0) -> str:
    """Return a fixed-width line, scrolling long text and padding short text."""
    normalized = unicodedata.normalize("NFKD", str(text))
    ascii_text = "".join(
        character for character in normalized
        if not unicodedata.combining(character)
    ).encode("ascii", "replace").decode("ascii")
    value = " ".join(ascii_text.split())
    if len(value) <= LCD_WIDTH:
        return value.ljust(LCD_WIDTH)
    cycle = value + "   "
    start = offset % len(cycle)
    rotated = cycle[start:] + cycle[:start]
    return rotated[:LCD_WIDTH]


def select_alert(
    alerts: list[dict[str, Any]],
    priority: dict[str, int],
    *,
    now: float,
    rotation_s: float,
) -> dict[str, Any] | None:
    eligible = [
        alert for alert in alerts
        if alert.get("type") in ALERT_TYPES
        and not alert.get("resolved", False)
        and not alert.get("notification_suppressed", False)
        and isinstance(alert.get("product"), str)
    ]
    if not eligible:
        return None
    eligible.sort(key=lambda alert: (
        -priority.get(str(alert["type"]), 0),
        str(alert.get("timestamp", "")),
        str(alert.get("id", "")),
    ))
    priority_value = priority.get(str(eligible[0]["type"]), 0)
    top_priority = [
        alert for alert in eligible
        if priority.get(str(alert["type"]), 0) == priority_value
    ]
    index = int(now // rotation_s) % len(top_priority)
    return top_priority[index]


class I2CBackpackLCD:
    """HD44780 4-bit driver for a PCF8574-compatible I2C backpack."""

    def __init__(self, bus_number: int, address: int, bits: dict[str, int]) -> None:
        self.bus_number = bus_number
        self.address = address
        self.bits = bits
        self.interface = "i2c"
        self._bus: Any = None
        self._backlight = 1 << self.bits["backlight"]
        self._last_lines: tuple[str, str] | None = None

    @staticmethod
    def detect(bus_number: int, configured_address: int | None) -> list[int]:
        try:
            from smbus2 import SMBus
        except ImportError as exc:
            raise RuntimeError("smbus2 is required for LCD I2C detection") from exc
        candidates = (
            [configured_address]
            if configured_address is not None
            else [*range(0x20, 0x28), *range(0x38, 0x40)]
        )
        found = []
        with SMBus(bus_number) as bus:
            for address in candidates:
                try:
                    bus.read_byte(address)
                except OSError:
                    continue
                found.append(address)
        return found

    def initialize(self) -> None:
        from smbus2 import SMBus

        self._bus = SMBus(self.bus_number)
        time.sleep(0.05)
        self._write_nibble(0x03, register_select=False)
        time.sleep(0.005)
        self._write_nibble(0x03, register_select=False)
        time.sleep(0.001)
        self._write_nibble(0x03, register_select=False)
        self._write_nibble(0x02, register_select=False)
        self._command(0x28)
        self._command(0x0C)
        self._command(0x06)
        self._command(0x01)
        time.sleep(0.002)

    def display(self, line1: str, line2: str) -> None:
        if self._bus is None:
            raise RuntimeError("LCD I2C backend is not initialized")
        lines = (line1[:LCD_WIDTH].ljust(LCD_WIDTH), line2[:LCD_WIDTH].ljust(LCD_WIDTH))
        if lines == self._last_lines:
            return
        self._command(0x80)
        for character in lines[0]:
            self._write_byte(ord(character), register_select=True)
        self._command(0xC0)
        for character in lines[1]:
            self._write_byte(ord(character), register_select=True)
        self._last_lines = lines

    def _command(self, value: int) -> None:
        self._write_byte(value, register_select=False)

    def _write_byte(self, value: int, *, register_select: bool) -> None:
        self._write_nibble(value >> 4, register_select)
        self._write_nibble(value & 0x0F, register_select)

    def _write_nibble(self, value: int, register_select: bool) -> None:
        data = self._backlight
        if register_select:
            data |= 1 << self.bits["rs"]
        for offset, label in enumerate(("d4", "d5", "d6", "d7")):
            if value & (1 << offset):
                data |= 1 << self.bits[label]
        self._expander_write(data)
        self._expander_write(data | (1 << self.bits["enable"]))
        time.sleep(0.0005)
        self._expander_write(data)
        time.sleep(0.0001)

    def _expander_write(self, value: int) -> None:
        self._bus.write_byte(self.address, value)

    def close(self) -> None:
        if self._bus is not None:
            self._bus.close()
            self._bus = None


class ParallelGPIOHD44780:
    """4-bit parallel LCD backend using gpiozero output devices."""

    def __init__(self, mapping: dict[str, int]) -> None:
        required = {"rs", "enable", "d4", "d5", "d6", "d7"}
        if set(mapping) != required or len(set(mapping.values())) != len(required):
            raise ValueError("parallel LCD requires six distinct configured BCM pins")
        if set(mapping.values()) & {2, 3}:
            raise ValueError("BCM GPIO 2 and 3 are reserved for the I2C bus")
        self.mapping = mapping
        self.interface = "parallel"
        self._outputs: dict[str, Any] = {}
        self._last_lines: tuple[str, str] | None = None

    def initialize(self) -> None:
        try:
            from gpiozero import OutputDevice
        except ImportError as exc:
            raise RuntimeError("gpiozero is required for parallel LCD GPIO output") from exc
        try:
            self._outputs = {
                name: OutputDevice(pin, active_high=True, initial_value=False)
                for name, pin in self.mapping.items()
            }
        except Exception:
            self.close()
            raise
        time.sleep(0.05)
        self._write_nibble(0x03, False)
        time.sleep(0.005)
        self._write_nibble(0x03, False)
        time.sleep(0.001)
        self._write_nibble(0x03, False)
        self._write_nibble(0x02, False)
        self._command(0x28)
        self._command(0x0C)
        self._command(0x06)
        self._command(0x01)
        time.sleep(0.002)

    def display(self, line1: str, line2: str) -> None:
        if not self._outputs:
            raise RuntimeError("LCD GPIO backend is not initialized")
        lines = (line1[:LCD_WIDTH].ljust(LCD_WIDTH), line2[:LCD_WIDTH].ljust(LCD_WIDTH))
        if lines == self._last_lines:
            return
        self._command(0x80)
        for character in lines[0]:
            self._write_byte(ord(character), True)
        self._command(0xC0)
        for character in lines[1]:
            self._write_byte(ord(character), True)
        self._last_lines = lines

    def _command(self, value: int) -> None:
        self._write_byte(value, False)

    def _write_byte(self, value: int, register_select: bool) -> None:
        self._outputs["rs"].value = register_select
        self._write_nibble(value >> 4, register_select)
        self._write_nibble(value & 0x0F, register_select)

    def _write_nibble(self, value: int, register_select: bool) -> None:
        self._outputs["rs"].value = register_select
        for offset, label in enumerate(("d4", "d5", "d6", "d7")):
            self._outputs[label].value = bool(value & (1 << offset))
        self._outputs["enable"].on()
        time.sleep(0.0005)
        self._outputs["enable"].off()
        time.sleep(0.0001)

    def close(self) -> None:
        outputs, self._outputs = self._outputs, {}
        for output in outputs.values():
            output.close()


def create_lcd_backend(settings: LCDSettings) -> LCDBackend:
    if settings.interface == "disabled":
        raise RuntimeError("LCD is disabled")
    if settings.interface in {"auto", "i2c"}:
        try:
            addresses = I2CBackpackLCD.detect(settings.bus, settings.address)
        except (OSError, RuntimeError):
            if settings.interface != "auto" or not settings.gpio:
                raise
            addresses = []
        if len(addresses) > 1:
            raise RuntimeError(
                "multiple LCD I2C addresses detected; set PORTAL_LCD_I2C_ADDRESS"
            )
        if addresses:
            return I2CBackpackLCD(settings.bus, addresses[0], settings.backpack)
        if settings.interface == "i2c":
            raise RuntimeError(
                "no supported PCF8574 LCD backpack detected; check I2C bus/address"
            )
    if settings.interface == "parallel":
        if not settings.gpio:
            raise RuntimeError("parallel LCD requires PORTAL_LCD_GPIO_JSON")
        return ParallelGPIOHD44780(settings.gpio)
    if settings.gpio:
        return ParallelGPIOHD44780(settings.gpio)
    raise RuntimeError(
        "no LCD detected over I2C and no parallel GPIO mapping configured"
    )


class CustomerLCDWorker:
    """Owns LCD I/O on one daemon thread; camera/inference code only enqueues state."""

    def __init__(
        self,
        settings: LCDSettings,
        *,
        backend_factory: Callable[[], LCDBackend] | None = None,
        alert_provider: Callable[[], list[dict[str, Any]]] | None = None,
        logger: logging.Logger | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings = settings
        self.backend_factory = backend_factory or (
            lambda: create_lcd_backend(settings)
        )
        self.alert_provider = alert_provider or (lambda: [])
        self.logger = logger or logging.getLogger(__name__)
        self.clock = clock
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._alerts_lock = threading.Lock()
        self._alerts: list[dict[str, Any]] = []
        self._last_rendered: tuple[str, str] | None = None
        self._failure_log_at = 0.0

    def start(self) -> None:
        if self.settings.interface == "disabled":
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run,
            name="customer-lcd",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=max(0.0, timeout))

    def set_alerts(self, alerts: list[dict[str, Any]]) -> None:
        safe_alerts = [
            dict(alert) for alert in alerts
            if isinstance(alert, dict)
        ]
        with self._alerts_lock:
            self._alerts = safe_alerts
        self._wake.set()

    def render(self, now: float | None = None) -> tuple[str, str]:
        moment = self.clock() if now is None else now
        with self._alerts_lock:
            alerts = [dict(alert) for alert in self._alerts]
        if not alerts:
            try:
                alerts = self.alert_provider()
            except Exception:
                self.logger.exception("Unable to read active inventory alerts for LCD")
        alert = select_alert(
            alerts,
            self.settings.priority,
            now=moment,
            rotation_s=self.settings.rotation_s,
        )
        if alert is None:
            return "PORTAL-XLINK".ljust(LCD_WIDTH), "System Online".ljust(LCD_WIDTH)
        title = ALERT_TITLES[str(alert["type"])]
        product = str(alert.get("product", "Product"))
        scroll_offset = int(moment / self.settings.scroll_interval_s)
        return (
            format_lcd_line(title),
            format_lcd_line(product, scroll_offset),
        )

    def _run(self) -> None:
        backend: LCDBackend | None = None
        initialized = False
        try:
            while not self._stop.is_set():
                self._wake.clear()
                if backend is None:
                    try:
                        backend = self.backend_factory()
                        backend.initialize()
                        initialized = True
                        self.logger.info(
                            "[LCD] Initialized 16x2 HD44780 display via %s",
                            backend.interface,
                        )
                    except Exception as exc:
                        if backend is not None:
                            try:
                                backend.close()
                            except Exception:
                                self.logger.exception("[LCD] Backend cleanup failed")
                        backend = None
                        initialized = False
                        self._log_failure(exc)
                        self._wake.wait(5.0)
                        continue
                try:
                    content = self.render()
                    if content != self._last_rendered:
                        backend.display(*content)
                        self._last_rendered = content
                except Exception as exc:
                    self._log_failure(exc)
                    if backend is not None:
                        try:
                            backend.close()
                        except Exception:
                            self.logger.exception("[LCD] Backend cleanup failed")
                    backend = None
                    initialized = False
                    self._last_rendered = None
                wait = (
                    self.settings.scroll_interval_s
                    if initialized and self._has_long_product()
                    else min(0.5, self.settings.rotation_s / 4)
                )
                self._wake.wait(wait)
        finally:
            if backend is not None:
                try:
                    backend.close()
                except Exception:
                    self.logger.exception("[LCD] Backend shutdown failed")

    def _has_long_product(self) -> bool:
        with self._alerts_lock:
            return any(
                alert.get("type") in ALERT_TYPES
                and len(str(alert.get("product", ""))) > LCD_WIDTH
                for alert in self._alerts
            )

    def _log_failure(self, exc: Exception) -> None:
        now = self.clock()
        if now - self._failure_log_at >= 30:
            self.logger.warning("[LCD] Display unavailable: %s", exc)
            self._failure_log_at = now
