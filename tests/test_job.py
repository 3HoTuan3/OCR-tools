"""Kiểm thử tiến trình chụp một lần, trình khởi động của khay và lớp phủ chọn vùng (tkinter giả)."""
import json
import os
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import ocrtool.job as job  # noqa: E402
from ocrtool import snip  # noqa: E402
from ocrtool.config import Config  # noqa: E402
from ocrtool.engine import Line, Result  # noqa: E402
from ocrtool.tess import find_executable  # noqa: E402
from ocrtool.tray import JobLauncher, describe  # noqa: E402

IMG = Image.new("RGB", (60, 30), "white")


class FakeEngine:
    warnings: list = []
    min_score = 0.0

    def __init__(self, lines=("Tiếng Việt", "你好")):
        self.lines = lines

    def recognize(self, img):
        return Result([Line(t, 0.99, [[0, 0]] * 4) for t in self.lines], 0.01)


class RunJob(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hist = Path(self.tmp.name)
        self.copied = []

    def tearDown(self):
        self.tmp.cleanup()

    def run_it(self, select=lambda: IMG, factory=FakeEngine, cfg=None):
        return job.run_job(select, factory, self.copied.append, cfg or Config(), self.hist)

    def test_ok_copies_text_and_saves_history(self):
        out = self.run_it()
        self.assertEqual(out["status"], "ok")
        self.assertEqual(self.copied, ["Tiếng Việt\n你好"])
        self.assertEqual(out["chars"], len("Tiếng Việt\n你好"))
        self.assertEqual(out["snippet"], "Tiếng Việt 你好")
        self.assertEqual(len(list(self.hist.glob("*.png"))), 1)
        self.assertEqual(next(self.hist.glob("*.txt")).read_text(encoding="utf-8"), self.copied[0])

    def test_cancel_does_not_touch_clipboard(self):
        out = self.run_it(select=lambda: None)
        self.assertEqual(out, {"status": "cancelled"})
        self.assertEqual(self.copied, [])

    def test_empty_keeps_clipboard(self):
        out = self.run_it(factory=lambda: FakeEngine(lines=()))
        self.assertEqual(out["status"], "empty")
        self.assertEqual(self.copied, [])

    def test_engine_load_failure_reported(self):
        def boom():
            raise RuntimeError("không có model")
        out = self.run_it(factory=boom)
        self.assertEqual(out["status"], "error")
        self.assertIn("không có model", out["message"])
        self.assertEqual(self.copied, [])

    def test_engine_loads_while_user_is_selecting(self):
        def slow_select():
            time.sleep(0.4)
            return IMG

        def slow_factory():
            time.sleep(0.4)
            return FakeEngine()
        t = time.perf_counter()
        out = self.run_it(select=slow_select, factory=slow_factory)
        self.assertEqual(out["status"], "ok")
        self.assertLess(time.perf_counter() - t, 0.7)    # song song, không phải 0.8 s

    def test_join_lines_and_history_off(self):
        out = self.run_it(cfg=Config(join_lines=True, keep_history=False))
        self.assertEqual(self.copied, ["Tiếng Việt你好"])   # giữa chữ Latin và CJK không chèn dấu cách
        self.assertEqual(list(self.hist.glob("*")), [])

    def test_history_pruned(self):
        cfg = Config(history_max=2)
        for _ in range(4):
            self.run_it(cfg=cfg)
            time.sleep(0.01)
        self.assertEqual(len(list(self.hist.glob("*.png"))), 2)
        self.assertEqual(len(list(self.hist.glob("*.txt"))), 2)

    def test_join_text(self):
        self.assertEqual(job.join_text(["a", "b"], False), "a\nb")
        self.assertEqual(job.join_text(["Xin chào", "các bạn"], True), "Xin chào các bạn")
        self.assertEqual(job.join_text(["你好", "世界"], True), "你好世界")


@unittest.skipUnless(find_executable(), "Tesseract chưa được cài")
class MainEndToEnd(unittest.TestCase):
    def test_main_with_real_engine(self):
        sample = ROOT / "samples" / "sample_mixed.png"
        if not sample.exists():
            self.skipTest("thiếu ảnh mẫu")
        with tempfile.TemporaryDirectory() as tmp:
            copied = []
            env = {"XDG_STATE_HOME": tmp, "LOCALAPPDATA": tmp}
            result_file = Path(tmp) / "kq.json"
            with mock.patch.dict(os.environ, env), \
                    mock.patch("ocrtool.capture.grab_screen_region",
                               lambda delay=0.0: Image.open(sample)), \
                    mock.patch("ocrtool.clipboard.set_text", copied.append):
                code = job.main(["--result", str(result_file), "--delay", "0"])
            self.assertEqual(code, 0)
            data = json.loads(result_file.read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "ok")
            ref = (ROOT / "samples" / "sample_mixed.txt").read_text(encoding="utf-8")
            self.assertEqual(copied[0], ref)
            self.assertTrue(list((Path(tmp) / "ocrtool" / "history").glob("*.png")))


def python_cmd(script):
    return lambda: [sys.executable, "-c", script]


WRITE_RESULT = ("import sys,json;p=sys.argv[sys.argv.index('--result')+1];"
                "open(p,'w',encoding='utf-8').write(json.dumps({'status':'ok','chars':5,'snippet':'Xin chào'}))")


class Launcher(unittest.TestCase):
    def collect(self, command, timeout=20):
        got, done = [], threading.Event()
        launcher = JobLauncher(lambda r: (got.append(r), done.set()), command=command, timeout=timeout)
        return launcher, got, done

    def test_reads_result_from_child(self):
        launcher, got, done = self.collect(python_cmd(WRITE_RESULT))
        self.assertTrue(launcher.start())
        self.assertTrue(done.wait(15))
        self.assertEqual(got[0], {"status": "ok", "chars": 5, "snippet": "Xin chào"})

    def test_single_flight(self):
        slow = WRITE_RESULT.replace("import sys,json;", "import sys,json,time;time.sleep(1);")
        launcher, got, done = self.collect(python_cmd(slow))
        self.assertTrue(launcher.start())
        self.assertFalse(launcher.start())          # đang chụp thì bỏ qua lần bấm thứ hai
        self.assertTrue(done.wait(15))
        time.sleep(0.2)
        self.assertTrue(launcher.start())           # xong rồi thì chụp lại được
        time.sleep(1.5)

    def test_child_crash_reports_stderr(self):
        launcher, got, done = self.collect(python_cmd("import sys;sys.stderr.write('hỏng rồi');sys.exit(7)"))
        launcher.start()
        self.assertTrue(done.wait(15))
        self.assertEqual(got[0]["status"], "error")
        self.assertIn("mã 7", got[0]["message"])
        self.assertIn("hỏng rồi", got[0]["message"])

    def test_timeout_kills_child(self):
        launcher, got, done = self.collect(python_cmd("import time;time.sleep(30)"), timeout=1)
        t = time.perf_counter()
        launcher.start()
        self.assertTrue(done.wait(10))
        self.assertLess(time.perf_counter() - t, 8)
        self.assertEqual(got[0]["status"], "error")

    def test_describe(self):
        self.assertIsNone(describe({"status": "cancelled"}))
        title, msg = describe({"status": "ok", "chars": 12, "snippet": "abc"})
        self.assertIn("12", title)
        self.assertEqual(msg, "abc")
        self.assertIn("Không nhận ra", describe({"status": "empty"})[1])
        self.assertEqual(describe({"status": "error", "message": "a\nb\nlỗi cuối"})[1], "lỗi cuối")


# --------------------------------------------------------------------------- overlay chọn vùng
class FakeCanvas:
    def __init__(self, root, **kw):
        self.items, self.binds, self._n = {}, {}, 0
        root.canvas = self

    def _new(self, kind, coords, **kw):
        self._n += 1
        self.items[self._n] = {"kind": kind, "coords": list(coords), **kw}
        return self._n

    def pack(self, **k): pass
    def create_image(self, *a, **k): return self._new("image", a, **k)
    def create_rectangle(self, *c, **k): return self._new("rect", c, **k)
    def create_text(self, x, y, **k): return self._new("text", (x, y), **k)
    def coords(self, i, *c): self.items[i]["coords"] = list(c)
    def itemconfigure(self, i, **k): self.items[i].update(k)
    def tag_raise(self, i): pass
    def bind(self, seq, fn): self.binds[seq] = fn


class FakeTk:
    script = None
    last = None

    def __init__(self):
        self.binds, self.destroyed, self.canvas = {}, False, None
        FakeTk.last = self

    def overrideredirect(self, v): pass
    def attributes(self, *a): pass
    def geometry(self, g): self.geometry_str = g
    def update_idletasks(self): pass
    def focus_force(self): pass
    def lift(self): pass
    def bind(self, seq, fn): self.binds[seq] = fn
    def mainloop(self): FakeTk.script(self)
    def destroy(self): self.destroyed = True


class Ev:
    def __init__(self, x, y):
        self.x, self.y = x, y


def run_overlay(script, size=(400, 300), mon=None):
    mon = mon or {"left": 0, "top": 0, "width": size[0], "height": size[1]}
    tkmod = types.ModuleType("tkinter")
    tkmod.Tk, tkmod.Canvas = FakeTk, FakeCanvas
    imagetk = types.ModuleType("PIL.ImageTk")
    imagetk.PhotoImage = lambda img, master=None: object()
    full = Image.new("RGB", size, (200, 10, 10))
    FakeTk.script = script
    with mock.patch.dict(sys.modules, {"tkinter": tkmod, "PIL.ImageTk": imagetk}), \
            mock.patch("PIL.ImageTk", imagetk, create=True):
        return snip.select_region(full, mon)


class Overlay(unittest.TestCase):
    def test_geometry_helpers(self):
        self.assertEqual(snip.norm_rect(50, 60, 10, 20), (10, 20, 50, 60))
        rects = snip.dim_rects((10, 20, 50, 60), 100, 80)
        self.assertEqual(len(rects), 4)
        self.assertEqual(len(snip.dim_rects(None, 100, 80)), 4)
        # bốn hình + vùng chọn phủ kín đúng diện tích màn hình
        area = sum((r - l) * (b - t) for l, t, r, b in rects) + 40 * 40
        self.assertEqual(area, 100 * 80)

    def test_drag_returns_crop(self):
        def script(root):
            c = root.canvas
            c.binds["<ButtonPress-1>"](Ev(100, 80))
            c.binds["<B1-Motion>"](Ev(160, 120))
            c.binds["<B1-Motion>"](Ev(220, 150))
            # đang kéo: viền hiện và có đúng 4 hình làm tối, kích thước hiển thị đúng
            border = [i for i in c.items.values() if i.get("outline") == "#2f9bff"][0]
            assert border["state"] == "normal" and border["coords"] == [100, 80, 220, 150]
            assert any(i.get("text") == "120 × 70" for i in c.items.values())
            c.binds["<ButtonRelease-1>"](Ev(220, 150))
        out = run_overlay(script)
        self.assertEqual(out.size, (120, 70))
        self.assertEqual(out.getpixel((0, 0)), (200, 10, 10))
        self.assertTrue(FakeTk.last.destroyed)

    def test_reverse_and_clamped_drag(self):
        def script(root):
            c = root.canvas
            c.binds["<ButtonPress-1>"](Ev(300, 200))
            c.binds["<ButtonRelease-1>"](Ev(-50, 500))     # kéo ngược, vượt ra ngoài màn hình
        out = run_overlay(script)
        self.assertEqual(out.size, (300, 100))              # kẹp vào [0,400]x[0,300]

    def test_escape_and_right_click_cancel(self):
        self.assertIsNone(run_overlay(lambda root: root.binds["<Escape>"](None)))
        self.assertIsNone(run_overlay(lambda root: root.canvas.binds["<Button-3>"](Ev(5, 5))))

    def test_tiny_drag_is_ignored(self):
        def script(root):
            root.canvas.binds["<ButtonPress-1>"](Ev(10, 10))
            root.canvas.binds["<ButtonRelease-1>"](Ev(12, 13))
        self.assertIsNone(run_overlay(script))

    def test_geometry_uses_virtual_screen_origin(self):
        mon = {"left": -1920, "top": 0, "width": 3840, "height": 1080}
        run_overlay(lambda root: root.binds["<Escape>"](None), size=(3840, 1080), mon=mon)
        self.assertEqual(FakeTk.last.geometry_str, "3840x1080+-1920+0")


if __name__ == "__main__":
    unittest.main()
