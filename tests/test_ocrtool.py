"""Chạy:  python -m unittest discover -s tests -v"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ocrtool.tess import TesseractBackend, find_executable  # noqa: E402
from ocrtool.textutil import (choose_latin, coverage, fold, has_cjk,  # noqa: E402
                              has_latin_letters, similarity, strip_edge_junk,
                              trim_stray_edge)


class TextUtil(unittest.TestCase):
    def test_cjk_detection(self):
        self.assertTrue(has_cjk("你好"))
        self.assertTrue(has_cjk("Xin chào 你好"))
        self.assertTrue(has_cjk("日本語かな"))
        self.assertFalse(has_cjk("Tiếng Việt"))

    def test_latin_letters(self):
        self.assertTrue(has_latin_letters("Việt"))
        self.assertFalse(has_latin_letters("中文 123 ,."))
        self.assertFalse(has_latin_letters("0123456789"))

    def test_fold_removes_vietnamese_marks(self):
        self.assertEqual(fold("Nguyễn Thị Đạt"), "nguyenthidat")
        self.assertEqual(fold("Tiếng Việt"), "tiengviet")

    def test_similarity_and_coverage(self):
        self.assertGreater(similarity("Tiếng Việt", "Tieng Viet"), 0.99)
        self.assertGreater(coverage("Ting Vit", "Tiếng Việt"), 0.99)
        self.assertLess(similarity("hello", "xyzzy"), 0.3)

    def test_choose_prefers_tesseract_when_paddle_drops_diacritics(self):
        text, src = choose_latin("Ting Vit: Hôm nay tri đp", 0.98,
                                 "Tiếng Việt: Hôm nay trời đẹp", 92.0)
        self.assertEqual(src, "tesseract")
        self.assertIn("Tiếng", text)

    def test_choose_trusts_confident_engine_on_disagreement(self):
        text, src = choose_latin("Hello world", 0.99, "Hxllo wxrld qq", 30.0)
        self.assertEqual(src, "paddle")
        text, src = choose_latin("zzzzzzzz", 0.40, "Hello world", 95.0)
        self.assertEqual(src, "tesseract")

    def test_choose_handles_empty(self):
        self.assertEqual(choose_latin("abc", 0.9, "", 0.0), ("abc", "paddle"))
        self.assertEqual(choose_latin("", 0.0, "abc", 90.0), ("abc", "tesseract"))

    def test_strip_edge_junk(self):
        self.assertEqual(strip_edge_junk("1.250.000đ (¡"), "1.250.000đ (")
        self.assertEqual(strip_edge_junk("° Xin chào ®"), "Xin chào")
        self.assertEqual(strip_edge_junk("Chào – bạn"), "Chào – bạn")
        self.assertEqual(strip_edge_junk("Đường Trường Chinh,"), "Đường Trường Chinh,")


    def test_trim_stray_edge(self):
        self.assertEqual(trim_stray_edge("1.250.000đ (;", "1.250.000đ("), "1.250.000đ (")
        self.assertEqual(trim_stray_edge("Xin chào.", "Xin chào."), "Xin chào.")
        self.assertEqual(trim_stray_edge("Hello...", "Hello..."), "Hello...")


class TsvParsing(unittest.TestCase):
    def test_parse_multi_page(self):
        header = "\t".join(["level", "page_num", "block_num", "par_num", "line_num", "word_num",
                            "left", "top", "width", "height", "conf", "text"])
        def row(page, conf, text):
            return "\t".join(["5", str(page), "1", "1", "1", "1", "0", "0", "9", "9", str(conf), text])
        tsv = "\n".join([header, row(1, 90, "Tiếng"), row(1, 80, "Việt"), row(3, 70, "abc")])
        out = TesseractBackend._parse_tsv(tsv, 3)
        self.assertEqual(out[0], ("Tiếng Việt", 85.0))
        self.assertEqual(out[1], ("", 0.0))      # trang không có chữ
        self.assertEqual(out[2], ("abc", 70.0))


@unittest.skipUnless(find_executable(), "Tesseract chưa được cài")
class EndToEnd(unittest.TestCase):
    sample = ROOT / "samples" / "sample_mixed.png"

    @unittest.skipUnless((ROOT / "samples" / "sample_mixed.png").exists(), "thiếu ảnh mẫu")
    def test_mixed_sample(self):
        from ocrtool import OCREngine
        engine = OCREngine()
        if engine.tess is None:
            self.skipTest("Tesseract/dữ liệu vie chưa sẵn sàng: " + "; ".join(engine.warnings))
        text = engine.recognize(self.sample).text
        for must in ("Tiếng Việt", "Nguyễn Thị Thu Hương", "quick brown fox",
                     "中文测试", "繁體中文", "你好"):
            self.assertIn(must, text)


if __name__ == "__main__":
    unittest.main()
