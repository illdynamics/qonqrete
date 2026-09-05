import os, tempfile, unittest
from unittest.mock import patch
class TestImageSmoke(unittest.TestCase):
 def test_smoke_fallback(self):
  from qq.image_smoke import run_image_smoke_test
  with tempfile.TemporaryDirectory() as d:
   with patch("qq.image_gen.generate_image") as g:
    g.return_value=type("R",(),{"success":False,"error":"offline","metadata":{},"model_used":""})()
    self.assertEqual(run_image_smoke_test(d),0)
   self.assertTrue(os.path.isfile(os.path.join(d,"qonqrete_cybersquid.png")))
