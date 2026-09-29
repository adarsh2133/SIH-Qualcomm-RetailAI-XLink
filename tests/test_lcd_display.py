from __future__ import annotations

import logging
import sys
import threading
import time
import types
import unittest
from unittest.mock import patch

from hardware.lcd_display import (
    ALERT_TITLES,
    CustomerLCDWorker,
    LCDSettings,
    I2CBackpackLCD,
    ParallelGPIOHD44780,
    format_lcd_line,
    select_alert,
)


def settings(**overrides: object) -> LCDSettings:
    values: dict[str, object] = {
        "interface": "disabled",
        "bus": 1,
        "address": None,
        "gpio": {},
        "backpack": {
            "rs": 0,
            "rw": 1,
            "enable": 2,
            "backlight": 3,
            "d4": 4,
            "d5": 5,
            "d6": 6,
            "d7": 7,
        },
        "rotation_s": 5.0,
        "scroll_interval_s": 0.45,
        "priority": {
            "OUT_OF_STOCK": 3,
            "CRITICAL_STOCK": 2,
            "LOW_STOCK": 1,
        },
        "camera_gpio_pins": frozenset(),
    }
    values.update(overrides)
    return LCDSettings(**values)  # type: ignore[arg-type]


def alert(alert_type: str, product: str, alert_id: str = "id") -> dict[str, object]:
    return {
        "id": alert_id,
        "type": alert_type,
        "product": product,
        "notification_suppressed": False,
        "resolved": False,
    }


class LCDFormattingTests(unittest.TestCase):
    def test_status_and_each_customer_alert_render_to_two_fixed_width_lines(self) -> None:
        worker = CustomerLCDWorker(settings())
        self.assertEqual(
            worker.render(now=0),
            ("PORTAL-XLINK    ", "System Online   "),
        )
        for alert_type, product in (
            ("LOW_STOCK", "Cola 500ml"),
            ("CRITICAL_STOCK", "Cola 500ml"),
            ("OUT_OF_STOCK", "Cola 500ml"),
        ):
            worker.set_alerts([alert(alert_type, product)])
            line1, line2 = worker.render(now=0)
            self.assertEqual(line1.strip(), ALERT_TITLES[alert_type])
            self.assertEqual(line2.strip(), product)
            self.assertEqual((len(line1), len(line2)), (16, 16))

    def test_long_names_scroll_and_short_names_are_padded(self) -> None:
        self.assertEqual(format_lcd_line("Cola", 0), "Cola            ")
        name = "Extra Long Product Name"
        first = format_lcd_line(name, 0)
        second = format_lcd_line(name, 4)
        self.assertEqual(len(first), 16)
        self.assertEqual(len(second), 16)
        self.assertNotEqual(first, second)
        self.assertEqual(format_lcd_line("Café"), "Cafe            ")

    def test_alert_priority_and_stable_rotation(self) -> None:
        alerts = [
            alert("LOW_STOCK", "A"),
            alert("OUT_OF_STOCK", "B", "b"),
            alert("CRITICAL_STOCK", "C", "c"),
        ]
        selected = select_alert(
            alerts, settings().priority, now=4, rotation_s=5
        )
        self.assertEqual(selected["product"], "B")

        same_priority = [
            alert("LOW_STOCK", "A", "a"),
            alert("LOW_STOCK", "B", "b"),
        ]
        first = select_alert(
            same_priority, settings().priority, now=0, rotation_s=5
        )
        second = select_alert(
            same_priority, settings().priority, now=5, rotation_s=5
        )
        self.assertNotEqual(first["id"], second["id"])

    def test_alert_resolution_returns_to_normal_or_next_alert(self) -> None:
        worker = CustomerLCDWorker(settings())
        worker.set_alerts([
            alert("LOW_STOCK", "Cola"),
            alert("CRITICAL_STOCK", "Milk", "milk"),
        ])
        self.assertEqual(worker.render(now=0)[0].strip(), "CRITICAL STOCK")
        worker.set_alerts([alert("LOW_STOCK", "Cola")])
        self.assertEqual(worker.render(now=0)[0].strip(), "LOW STOCK!")
        worker.set_alerts([])
        self.assertEqual(worker.render(now=0)[0].strip(), "PORTAL-XLINK")


class LCDBackendTests(unittest.TestCase):
    def test_parallel_lcd_initializes_and_writes_via_gpiozero(self) -> None:
        created: dict[str, object] = {}

        class OutputDeviceFake:
            def __init__(self, pin: int, **kwargs: object) -> None:
                self.pin = pin
                self.value = bool(kwargs["initial_value"])
                self.closed = False
                created[str(pin)] = self

            def on(self) -> None:
                self.value = True

            def off(self) -> None:
                self.value = False

            def close(self) -> None:
                self.closed = True

        gpiozero = types.ModuleType("gpiozero")
        gpiozero.OutputDevice = OutputDeviceFake
        mapping = {"rs": 4, "enable": 5, "d4": 6, "d5": 7, "d6": 8, "d7": 9}
        backend = ParallelGPIOHD44780(mapping)
        with patch.dict(sys.modules, {"gpiozero": gpiozero}):
            backend.initialize()
            backend.display("LOW STOCK!", "Cola 500ml")
            backend.close()
        self.assertEqual(len(created), 6)
        self.assertTrue(all(device.closed for device in created.values()))
        self.assertEqual(backend.interface, "parallel")

    def test_parallel_gpio_pin_conflicts_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "I2C bus"):
            ParallelGPIOHD44780({
                "rs": 2, "enable": 5, "d4": 6, "d5": 7, "d6": 8, "d7": 9,
            })
        with self.assertRaisesRegex(ValueError, "distinct"):
            ParallelGPIOHD44780({
                "rs": 4, "enable": 4, "d4": 6, "d5": 7, "d6": 8, "d7": 9,
            })

    def test_i2c_lcd_initializes_and_writes_over_configured_bus(self) -> None:
        writes: list[tuple[int, int]] = []
        opened: list[int] = []

        class SMBusFake:
            def __init__(self, bus_number: int) -> None:
                opened.append(bus_number)

            def write_byte(self, address: int, value: int) -> None:
                writes.append((address, value))

            def close(self) -> None:
                return

        smbus2 = types.ModuleType("smbus2")
        smbus2.SMBus = SMBusFake
        backend = I2CBackpackLCD(1, 0x27, settings().backpack)
        with patch.dict(sys.modules, {"smbus2": smbus2}):
            backend.initialize()
            backend.display("OUT OF STOCK", "Cola 500ml")
            backend.display("OUT OF STOCK", "Cola 500ml")
            backend.close()
        self.assertEqual(opened, [1])
        self.assertGreater(len(writes), 0)
        self.assertTrue(all(address == 0x27 for address, _ in writes))

    def test_auto_detection_prefers_a_unique_i2c_lcd(self) -> None:
        configured = settings(interface="auto")
        with patch.object(I2CBackpackLCD, "detect", return_value=[0x27]):
            from hardware.lcd_display import create_lcd_backend

            backend = create_lcd_backend(configured)
        self.assertEqual(backend.interface, "i2c")
        self.assertEqual(backend.address, 0x27)

    def test_auto_detection_uses_configured_parallel_pins_without_i2c_device(self) -> None:
        configured = settings(
            interface="auto",
            gpio={"rs": 4, "enable": 5, "d4": 6, "d5": 7, "d6": 8, "d7": 9},
        )
        with patch.object(I2CBackpackLCD, "detect", return_value=[]):
            from hardware.lcd_display import create_lcd_backend

            backend = create_lcd_backend(configured)
        self.assertEqual(backend.interface, "parallel")


class LCDWorkerFailureTests(unittest.TestCase):
    def test_worker_writes_changes_without_retriggering_unchanged_alert(self) -> None:
        writes: list[tuple[str, str]] = []
        changed = threading.Event()

        class RecordingBackend:
            interface = "test"

            def initialize(self) -> None:
                return

            def display(self, line1: str, line2: str) -> None:
                writes.append((line1, line2))
                changed.set()

            def close(self) -> None:
                return

        worker = CustomerLCDWorker(
            settings(interface="auto"),
            backend_factory=RecordingBackend,
        )
        worker.start()
        self.assertTrue(changed.wait(1))
        changed.clear()
        worker.set_alerts([alert("LOW_STOCK", "Cola")])
        self.assertTrue(changed.wait(1))
        self.assertEqual(writes[-1][0].strip(), "LOW STOCK!")
        count = len(writes)
        time.sleep(0.05)
        self.assertEqual(len(writes), count)
        worker.set_alerts([])
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline and writes[-1][0].strip() != "PORTAL-XLINK":
            time.sleep(0.01)
        self.assertEqual(writes[-1][0].strip(), "PORTAL-XLINK")
        worker.stop()

    def test_gpio_i2c_failure_is_logged_and_does_not_escape_worker(self) -> None:
        started = threading.Event()

        class BrokenBackend:
            interface = "i2c"

            def initialize(self) -> None:
                started.set()
                raise OSError("I2C bus unavailable")

            def display(self, line1: str, line2: str) -> None:
                raise AssertionError("display must not be called after init fails")

            def close(self) -> None:
                return

        with self.assertLogs("hardware.lcd_display", level=logging.WARNING) as logs:
            worker = CustomerLCDWorker(
                settings(interface="auto"),
                backend_factory=BrokenBackend,
            )
            worker.start()
            self.assertTrue(started.wait(1))
            self.assertTrue(worker._thread.is_alive())
            worker.stop()
        self.assertIn("I2C bus unavailable", "\n".join(logs.output))


class LCDConfigTests(unittest.TestCase):
    def test_parallel_gpio_mapping_is_explicit_and_conflicts_are_rejected(self) -> None:
        env = {
            "PORTAL_LCD_INTERFACE": "parallel",
            "PORTAL_LCD_GPIO_JSON": (
                '{"rs":4,"enable":5,"d4":6,"d5":7,"d6":8,"d7":9}'
            ),
            "PORTAL_GPIO_PINS": "10,11",
        }
        with patch.dict("os.environ", env, clear=True):
            configured = LCDSettings.from_env()
        self.assertEqual(configured.gpio["rs"], 4)
        self.assertEqual(configured.camera_gpio_pins, frozenset({10, 11}))

        env["PORTAL_GPIO_PINS"] = "4,11"
        with patch.dict("os.environ", env, clear=True):
            with self.assertRaisesRegex(ValueError, "conflicts"):
                LCDSettings.from_env()


if __name__ == "__main__":
    unittest.main()
