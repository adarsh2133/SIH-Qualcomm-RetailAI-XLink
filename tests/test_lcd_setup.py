from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hardware.lcd_setup import (
    configure_lcd,
    lcd_dropin_contents,
    validate_parallel_pins,
)
from hardware.lcd_display import I2CBackpackLCD


class GuidedLCDSetupTests(unittest.TestCase):
    def test_i2c_detection_creates_systemd_configuration_without_prompting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "lcd.conf"
            output: list[str] = []
            with patch.object(I2CBackpackLCD, "detect", return_value=[0x27]):
                result = configure_lcd(
                    input_fn=lambda prompt: self.fail("unexpected prompt"),
                    output_fn=output.append,
                    dropin_path=destination,
                )
            self.assertEqual(result, destination)
            self.assertIn("PORTAL_LCD_INTERFACE=i2c", destination.read_text())
            self.assertIn("PORTAL_LCD_I2C_ADDRESS=0x27", destination.read_text())
            self.assertTrue(output)

    def test_parallel_setup_is_guided_and_persists_validated_bcm_mapping(self) -> None:
        answers = iter(("yes", "17,27,22,23,24,25"))
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "lcd.conf"
            with patch.object(I2CBackpackLCD, "detect", return_value=[]):
                configure_lcd(
                    input_fn=lambda prompt: next(answers),
                    output_fn=lambda message: None,
                    dropin_path=destination,
                )
            contents = destination.read_text(encoding="utf-8")
        self.assertIn("PORTAL_LCD_INTERFACE=parallel", contents)
        self.assertIn(r'PORTAL_LCD_GPIO_JSON="{\"rs\":17', contents)

    def test_parallel_pin_conflicts_and_reserved_lines_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "already assigned"):
            validate_parallel_pins((17, 27, 22, 23, 24, 25), {22})
        with self.assertRaisesRegex(ValueError, "GPIO2/3"):
            validate_parallel_pins((2, 27, 22, 23, 24, 25), set())

    def test_systemd_configuration_rejects_unknown_interface_or_bad_mapping(self) -> None:
        with self.assertRaisesRegex(ValueError, "interface"):
            lcd_dropin_contents(interface="unknown")
        with self.assertRaisesRegex(ValueError, "six GPIO"):
            lcd_dropin_contents(interface="parallel", gpio={"rs": 17})


if __name__ == "__main__":
    unittest.main()
