import unittest

from PIL import Image

from gui.main_window import _local_camera_previews


class LocalCameraPreviewTests(unittest.TestCase):
    def test_converts_online_usb_frame_from_bgr_to_rgb(self):
        import numpy as np

        class Camera:
            camera_id = "usb-01"
            latest_frame = {
                "image": np.array([[[10, 20, 30]]], dtype=np.uint8),
            }

        previews = _local_camera_previews(
            [Camera()],
            [{"camera_id": "usb-01", "state": "ONLINE"}],
        )

        self.assertIsInstance(previews["usb-01"], Image.Image)
        self.assertEqual(previews["usb-01"].getpixel((0, 0)), (30, 20, 10))

    def test_does_not_show_offline_camera_frame(self):
        import numpy as np

        class Camera:
            camera_id = "usb-01"
            latest_frame = {"image": np.zeros((1, 1, 3), dtype=np.uint8)}

        previews = _local_camera_previews(
            [Camera()],
            [{"camera_id": "usb-01", "state": "OFFLINE"}],
        )

        self.assertEqual(previews, {})


if __name__ == "__main__":
    unittest.main()
