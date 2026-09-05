import os, tempfile, unittest
from unittest.mock import patch
class TestImageBackend(unittest.TestCase):
 def test_defaults(self):
  from qq.config import ImageBackendConfig
  c=ImageBackendConfig(); self.assertEqual(c.provider,"auto"); self.assertTrue(c.enabled); self.assertFalse(c.is_venice)
 def test_generate_gradio_route(self):
  from qq.image_gen import generate_image
  with patch("qq.image_gen._gradio") as g:
   g.return_value=type("R",(),{"success":True})()
   generate_image("test",method="gradio",output_path="/tmp/x.png"); g.assert_called_once()
