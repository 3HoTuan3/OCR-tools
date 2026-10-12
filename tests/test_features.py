"""Test phần không cần giao diện: bảng, dịch, phím tắt, ghép văn bản, cấu hình."""
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ocrtool import translate as tr
from ocrtool.config import Config
from ocrtool.hotkey import parse_hotkey
from ocrtool.job import compose_text
from ocrtool.layout import lines_to_table


def box(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


class TableTests(unittest.TestCase):
    def test_grid(self):
        items = [("Tên", box(10, 10, 60, 30)), ("Tuổi", box(200, 10, 250, 30)),
                 ("An", box(10, 50, 40, 70)), ("21", box(200, 50, 230, 70)),
                 ("Bình", box(10, 90, 55, 110)), ("34", box(200, 90, 230, 110))]
        self.assertEqual(lines_to_table(items), "Tên\tTuổi\nAn\t21\nBình\t34")

    def test_order_independent(self):
        items = [("21", box(200, 50, 230, 70)), ("Tên", box(10, 10, 60, 30)),
                 ("An", box(10, 50, 40, 70)), ("Tuổi", box(200, 10, 250, 30))]
        self.assertEqual(lines_to_table(items), "Tên\tTuổi\nAn\t21")

    def test_missing_cell_keeps_columns(self):
        items = [("A", box(10, 10, 40, 30)), ("B", box(200, 10, 230, 30)), ("C", box(400, 10, 430, 30)),
                 ("1", box(10, 50, 40, 70)), ("3", box(400, 50, 430, 70))]
        self.assertEqual(lines_to_table(items), "A\tB\tC\n1\t\t3")

    def test_plain_lines_stay_lines(self):
        items = [("dòng một", box(10, 10, 200, 30)), ("dòng hai", box(10, 40, 180, 60))]
        self.assertEqual(lines_to_table(items), "dòng một\ndòng hai")

    def test_adjacent_fragments_merge_and_tabs_removed(self):
        items = [("Xin", box(10, 10, 40, 30)), ("chào", box(46, 10, 90, 30)), ("a\tb", box(10, 50, 60, 70))]
        self.assertEqual(lines_to_table(items), "Xin chào\na b")

    def test_empty(self):
        self.assertEqual(lines_to_table([]), "")
        self.assertEqual(lines_to_table([("  ", box(0, 0, 1, 1))]), "")


class ComposeTests(unittest.TestCase):
    def lines(self):
        return [SimpleNamespace(text="A", box=box(0, 0, 20, 20)), SimpleNamespace(text="B", box=box(200, 0, 220, 20)),
                SimpleNamespace(text="C", box=box(0, 40, 20, 60)), SimpleNamespace(text="D", box=box(200, 40, 220, 60))]

    def test_modes(self):
        c = Config()
        self.assertEqual(compose_text(self.lines(), c), "A\nB\nC\nD")
        c.join_lines = True
        self.assertEqual(compose_text(self.lines(), c), "A B C D")
        c.table_mode = True
        self.assertEqual(compose_text(self.lines(), c), "A\tB\nC\tD")

    def test_table_mode_without_boxes_falls_back(self):
        c = Config(); c.table_mode = True
        self.assertEqual(compose_text([SimpleNamespace(text="x"), SimpleNamespace(text="y")], c), "x\ny")


class DetectTests(unittest.TestCase):
    def test_detect(self):
        self.assertEqual(tr.detect_lang("Tiếng Việt rất hay"), "vi")
        self.assertEqual(tr.detect_lang("Hello world"), "en")
        self.assertEqual(tr.detect_lang("你好，世界"), "zh-CN")
        self.assertEqual(tr.detect_lang("こんにちは"), "ja")
        self.assertEqual(tr.detect_lang("안녕하세요"), "ko")
        self.assertEqual(tr.detect_lang("Привет мир"), "ru")
        self.assertEqual(tr.detect_lang("1234 !!"), "")

    def test_effective_target_flips_when_same_language(self):
        self.assertEqual(tr.effective_target("Xin chào các bạn", "vi"), "en")
        self.assertEqual(tr.effective_target("Hello there", "en"), "vi")
        self.assertEqual(tr.effective_target("Hello there", "vi"), "vi")
        self.assertEqual(tr.effective_target("你好", "zh-TW"), "en")


def fake_response(payload):
    resp = mock.MagicMock()
    resp.read.return_value = json.dumps(payload).encode("utf-8")
    resp.__enter__.return_value = resp
    return resp


class TranslateTests(unittest.TestCase):
    def setUp(self):
        tr._cache.clear()

    def test_google_parse_and_cache(self):
        payload = [[["Xin chào", "Hello", None, None, 1], [" thế giới", " world", None, None, 1]], None, "en"]
        with mock.patch("urllib.request.urlopen", return_value=fake_response(payload)) as m:
            r = tr.translate("Hello world", "vi")
            self.assertEqual((r.text, r.source), ("Xin chào thế giới", "en"))
            req = m.call_args[0][0]
            self.assertIn("tl=vi", req.full_url)
            self.assertIn("client=gtx", req.full_url)
            tr.translate("Hello world", "vi")
            self.assertEqual(m.call_count, 1)                     # lần hai lấy từ bộ nhớ đệm
            tr.translate("Hello world", "ja")
            self.assertEqual(m.call_count, 2)

    def test_long_text_uses_post_and_chunks(self):
        text = "\n".join(["dòng số %d " % i + "x" * 80 for i in range(120)])   # ~11 KB
        payload = lambda *a, **k: fake_response([[["T", "S", None, None, 1]], None, "vi"])  # noqa: E731
        with mock.patch("urllib.request.urlopen", side_effect=payload) as m:
            r = tr.translate(text, "en")
            self.assertGreaterEqual(m.call_count, 3)
            self.assertTrue(all(c[0][0].data is not None for c in m.call_args_list))   # POST
            self.assertEqual(r.text.count("T"), m.call_count)

    def test_chunks_respect_limit(self):
        parts = tr._chunks("\n".join("a" * 100 for _ in range(200)), 1000)
        self.assertTrue(all(len(p) <= 1000 for p in parts))
        self.assertEqual("\n".join(parts), "\n".join("a" * 100 for _ in range(200)))
        self.assertEqual(tr._chunks("x" * 2500, 1000), ["x" * 1000, "x" * 1000, "x" * 500])

    def test_errors_are_translated_to_vietnamese(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            with self.assertRaisesRegex(tr.TranslateError, "Internet"):
                tr.translate("Hello", "vi")
        err = urllib.error.HTTPError("u", 429, "Too Many", {}, io.BytesIO(b""))
        with mock.patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaisesRegex(tr.TranslateError, "429"):
                tr.translate("Hello again", "vi")
        with mock.patch("urllib.request.urlopen", return_value=fake_response({"x": 1})):
            with self.assertRaises(tr.TranslateError):
                tr.translate("Hello third", "vi")

    def test_empty_and_bad_engine(self):
        self.assertEqual(tr.translate("  \n ", "vi").text, "")
        with self.assertRaises(tr.TranslateError):
            tr.translate("x", "vi", engine="nope")

    def test_argos_missing_message(self):
        with mock.patch.object(tr, "argos_available", return_value=False):
            with self.assertRaisesRegex(tr.TranslateError, "Argos"):
                tr.translate("Hello", "vi", engine="argos")


class HotkeyTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_hotkey("ctrl+alt+o"), (0x2 | 0x1, ord("O")))
        self.assertEqual(parse_hotkey("Win+Shift+F9"), (0x8 | 0x4, 0x78))
        self.assertEqual(parse_hotkey("ctrl+1"), (0x2, ord("1")))

    def test_invalid(self):
        for bad in ("o", "ctrl+", "foo+o", "ctrl+f13", "ctrl+enter"):
            with self.assertRaises(ValueError, msg=bad):
                parse_hotkey(bad)


class ConfigTests(unittest.TestCase):
    def test_new_fields_roundtrip(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"LOCALAPPDATA": d, "XDG_STATE_HOME": d}):
            c = Config()
            c.target_lang, c.float_opacity, c.after_capture, c.table_mode = "ja", 0.5, "translate", True
            c.save()
            c2 = Config.load()
            self.assertEqual((c2.target_lang, c2.float_opacity, c2.after_capture, c2.table_mode),
                             ("ja", 0.5, "translate", True))
            Config.path().write_text(json.dumps({"float_size": "big", "float_opacity": 1, "notify": False}))
            c3 = Config.load()
            self.assertEqual(c3.float_size, 48)          # sai kiểu -> bỏ qua
            self.assertEqual(c3.float_opacity, 1.0)      # int không thay được float -> giữ mặc định
            self.assertFalse(c3.notify)


if __name__ == "__main__":
    unittest.main()


class SingleInstanceTests(unittest.TestCase):
    def test_second_instance_pings_first(self):
        import threading
        import time
        from ocrtool import tray

        lock = tray._single_instance()
        if lock is None:
            self.skipTest("cổng khoá đang bị bản OCR thật chiếm")
        got = []
        t = threading.Thread(target=tray._serve_lock, args=(lock, lambda: got.append(1)), daemon=True)
        t.start()
        self.assertIsNone(tray._single_instance())      # bản thứ hai không giành được khoá
        tray._ping_existing()
        for _ in range(50):
            if got:
                break
            time.sleep(0.05)
        lock.close()
        self.assertEqual(got, [1])


FAKE_WORKER = r"""
import sys, json, time, os
for raw in sys.stdin:
    req = json.loads(raw)
    if req.get("op") == "quit":
        break
    if req.get("op") == "die":
        os._exit(3)
    if req.get("op") == "ocr" and "slow" in req.get("path", ""):
        time.sleep(5)
    out = {"id": req["id"], "ok": True, "op": req["op"], "lang": req.get("lang"), "lines": [{"text": "hi", "box": [[0,0],[1,0],[1,1],[0,1]], "score": 1}]}
    sys.stdout.write(json.dumps(out) + "\n"); sys.stdout.flush()
"""


class ClientTests(unittest.TestCase):
    def make(self, **kw):
        from ocrtool.client import OcrClient
        c = OcrClient(command=lambda: [sys.executable, "-c", FAKE_WORKER], **kw)
        self.addCleanup(c.close)
        return c

    def call(self, c, img=None, **opts):
        import threading
        from PIL import Image
        ev, box = threading.Event(), {}
        c.ocr(img or Image.new("RGB", (10, 10)), lambda m: (box.update(m), ev.set()), **opts)
        self.assertTrue(ev.wait(15))
        return box

    def test_roundtrip_reuses_process_and_cleans_files(self):
        c = self.make(lang_fn=lambda: "vie+eng")
        r = self.call(c, min_score=0.5)
        self.assertTrue(r["ok"])
        self.assertEqual(r["lang"], "vie+eng")
        pid = c._proc.pid
        self.call(c)
        self.assertEqual(c._proc.pid, pid)            # dùng lại tiến trình đã nạp engine
        self.assertEqual(list(c._tmp.glob("req_*.png")), [])
        self.assertFalse(c.busy)

    def test_worker_crash_reports_error_and_restarts(self):
        import threading
        c = self.make()
        self.call(c)
        ev, box = threading.Event(), {}
        c._request({"op": "die"}, lambda m: (box.update(m), ev.set()))
        self.assertTrue(ev.wait(10))
        self.assertFalse(box["ok"])
        self.assertIn("dừng", box["error"])
        self.assertTrue(self.call(c)["ok"])            # tự khởi động lại

    def test_idle_shutdown(self):
        import time
        c = self.make(idle_s=1)
        self.call(c)
        self.assertTrue(c.running)
        for _ in range(60):
            if not c.running:
                break
            time.sleep(0.1)
        self.assertFalse(c.running)

    def test_no_keep_mode_exits_after_each_request(self):
        import time
        c = self.make(idle_s=0)
        self.call(c)
        for _ in range(30):
            if not c.running:
                break
            time.sleep(0.1)
        self.assertFalse(c.running)

    def test_timeout(self):
        import ocrtool.client as cl
        from PIL import Image
        c = self.make()
        with mock.patch.object(cl, "REQUEST_TIMEOUT_S", 0.5):
            img = Image.new("RGB", (5, 5))
            orig = c._tmp
            import threading
            ev, box = threading.Event(), {}
            path = orig / "slow.png"
            img.save(path)
            c._request({"op": "ocr", "path": str(path)}, lambda m: (box.update(m), ev.set()), str(path))
            self.assertTrue(ev.wait(10))
        self.assertIn("Quá thời gian", box["error"])


class RealWorkerTest(unittest.TestCase):
    """Chạy tiến trình engine thật (cần rapidocr + Tesseract)."""

    def test_real_engine(self):
        try:
            import rapidocr  # noqa: F401
        except Exception:
            self.skipTest("không có rapidocr")
        import threading
        from PIL import Image
        from ocrtool.client import OcrClient
        sample = os.path.join(os.path.dirname(__file__), "..", "samples", "sample_mixed.png")
        c = OcrClient()
        self.addCleanup(c.close)
        c.warm()
        ev, box = threading.Event(), {}
        c.ocr(Image.open(sample), lambda m: (box.update(m), ev.set()))
        self.assertTrue(ev.wait(120))
        self.assertTrue(box.get("ok"), box.get("error"))
        self.assertGreater(len(box["lines"]), 2)
