"""Test giao diện bằng Tk thật (cần tkinter + màn hình; trên Linux chạy được dưới Xvfb: xvfb-run -a ...)."""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    import tkinter as tk
    _root = tk.Tk()
    _root.destroy()
    HAVE_TK = True
except Exception:  # không có tkinter hoặc không có DISPLAY
    HAVE_TK = False

if HAVE_TK:
    from ocrtool import translate as tr
    from ocrtool.appmenu import build_menu
    from ocrtool.config import Config
    from ocrtool.menu import SEP, MenuItem, PopupMenu
    from ocrtool.result import ResultWindow
    from ocrtool.lens import LensWindow, colors_for, fit_text, group_blocks, sig_diff, signature, wrap_text
    from ocrtool.tray import App
    from ocrtool.widget import FloatingButton


def pump(root, cond, timeout=8.0):
    end = time.time() + timeout
    while time.time() < end:
        root.update()
        if cond():
            return True
        time.sleep(0.02)
    root.update()
    return cond()


@unittest.skipUnless(HAVE_TK, "không có tkinter/màn hình")
class UITestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"LOCALAPPDATA": self.tmp.name, "XDG_STATE_HOME": self.tmp.name})
        self.env.start()
        self.root = tk.Tk()

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:
            pass
        self.env.stop()
        self.tmp.cleanup()


class MenuTests(UITestBase):
    def labels(self, level):
        return [i.label for _f, _w, i in level.rows]

    def test_click_runs_action_after_close(self):
        hits = []
        m = PopupMenu(self.root)
        m.show([MenuItem(label="A", action=lambda: hits.append("a")), SEP, MenuItem(label="B", action=lambda: hits.append("b"))],
               200, 200)
        self.assertTrue(m.is_open)
        lv = m.levels[0]
        m._activate(lv, lv.rows[1][0])
        self.assertFalse(m.is_open)
        pump(self.root, lambda: hits)
        self.assertEqual(hits, ["b"])

    def test_disabled_item_does_nothing(self):
        hits = []
        m = PopupMenu(self.root)
        m.show([MenuItem(label="A", enabled=False, action=lambda: hits.append(1))], 100, 100)
        lv = m.levels[0]
        m._activate(lv, lv.rows[0][0])
        pump(self.root, lambda: False, 0.3)
        self.assertTrue(m.is_open)
        self.assertEqual(hits, [])
        m.close()

    def test_click_event_on_label_activates(self):
        hits = []
        m = PopupMenu(self.root)
        m.show([MenuItem(label="Go", action=lambda: hits.append(1))], 100, 100)
        _fr, widgets, _it = m.levels[0].rows[0]
        self.root.update()
        widgets[2].event_generate("<ButtonRelease-1>", x=3, y=3, when="now")
        pump(self.root, lambda: hits)
        self.assertEqual(hits, [1])

    def test_submenu_opens_on_hover_and_closes_on_other_hover(self):
        m = PopupMenu(self.root)
        sub = [MenuItem(label="child1"), MenuItem(label="child2", children=[MenuItem(label="deep")])]
        m.show([MenuItem(label="P", children=sub), MenuItem(label="Q")], 300, 300)
        lv = m.levels[0]
        m._hover(lv, lv.rows[0][0])
        self.assertTrue(pump(self.root, lambda: len(m.levels) == 2))
        self.assertEqual(self.labels(m.levels[1]), ["child1", "child2"])
        l1 = m.levels[1]
        m._hover(l1, l1.rows[1][0])
        self.assertTrue(pump(self.root, lambda: len(m.levels) == 3))
        m._hover(lv, lv.rows[1][0])                    # rê sang mục không có menu con -> đóng các cấp sâu
        self.assertEqual(len(m.levels), 1)
        m.close()

    def test_lazy_children_and_empty(self):
        m = PopupMenu(self.root)
        m.show([MenuItem(label="H", children=lambda: [])], 300, 300)
        lv = m.levels[0]
        m._activate(lv, lv.rows[0][0])                  # bấm vào mục có menu con cũng mở
        self.assertEqual(self.labels(m.levels[1]), ["(trống)"])
        m.close()

    def test_escape_and_outside_click_close(self):
        m = PopupMenu(self.root)
        m.show([MenuItem(label="A")], 100, 100)
        m.levels[0].win.event_generate("<Escape>")
        self.root.update()
        self.assertFalse(m.is_open)
        # bấm ra ngoài (mô phỏng nút chuột đang giữ và con trỏ ở xa)
        m.show([MenuItem(label="A")], 100, 100)
        with mock.patch("ocrtool.menu.button_down", side_effect=[False, True, True, True, True]), \
                mock.patch.object(self.root, "winfo_pointerxy", return_value=(900, 900)):
            self.assertTrue(pump(self.root, lambda: not m.is_open, 3))
        self.assertGreater(m.closed_at, 0)

    def test_menu_stays_inside_screen(self):
        m = PopupMenu(self.root)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        m.show([MenuItem(label=f"item {i}") for i in range(6)], sw - 5, sh - 5)
        w = m.levels[0].win
        self.assertLessEqual(w.winfo_rootx() + w.winfo_width(), sw + 2)
        self.assertLessEqual(w.winfo_rooty() + w.winfo_height(), sh + 2)
        self.assertGreaterEqual(w.winfo_rootx(), 0)
        self.assertGreaterEqual(w.winfo_rooty(), 0)
        m.close()


class FloatingButtonTests(UITestBase):
    def make(self, **cfgkw):
        cfg = Config()
        cfg.float_x, cfg.float_y = 100, 100
        for k, v in cfgkw.items():
            setattr(cfg, k, v)
        log = SimpleNamespace(clicks=0, menus=[], moved=[])
        fb = FloatingButton(self.root, cfg, lambda: setattr(log, "clicks", log.clicks + 1),
                            lambda x, y: log.menus.append((x, y)), lambda x, y: log.moved.append((x, y)))
        self.root.update()
        return fb, log

    @staticmethod
    def ev(x_root, y_root, x=5, y=5):
        return SimpleNamespace(x_root=x_root, y_root=y_root, x=x, y=y)

    def test_click_is_not_drag(self):
        fb, log = self.make()
        fb._on_press(self.ev(110, 110)); fb._on_motion(self.ev(112, 111)); fb._on_release(self.ev(112, 111))
        self.assertEqual((log.clicks, log.moved), (1, []))

    def test_drag_moves_and_reports(self):
        fb, log = self.make()
        x0, y0 = fb.position()
        fb._on_press(self.ev(110, 110)); fb._on_motion(self.ev(160, 150)); fb._on_release(self.ev(160, 150))
        self.root.update()
        self.assertEqual(log.clicks, 0)
        self.assertEqual(fb.position(), (x0 + 50, y0 + 40))
        self.assertEqual(log.moved, [(x0 + 50, y0 + 40)])

    def test_drag_clamped_to_screen(self):
        fb, log = self.make()
        fb._on_press(self.ev(110, 110)); fb._on_motion(self.ev(-5000, -5000)); fb._on_release(self.ev(-5000, -5000))
        self.root.update()
        self.assertEqual(fb.position(), (0, 0))

    def test_right_click_opens_menu_at_pointer(self):
        fb, log = self.make()
        fb.canvas.event_generate("<Button-3>", x=4, y=4)
        self.root.update()
        self.assertEqual(len(log.menus), 1)

    def test_default_position_and_hide_show_state(self):
        fb, _ = self.make(float_x=-1, float_y=-1)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x, y = fb.position()
        self.assertTrue(0 <= x <= sw - fb.size and 0 <= y <= sh - fb.size)
        self.assertGreater(x, sw // 2)
        fb.hide(); self.assertFalse(fb.visible)
        fb.show(); self.assertTrue(fb.visible)

    def test_resize(self):
        fb, _ = self.make()
        fb.cfg.float_size = 64
        fb.apply_size(); self.root.update()
        self.assertEqual(self.root.winfo_reqwidth(), fb.size)


class ResultWindowTests(UITestBase):
    def make(self, text="Hello world", translate_fn=None, **kw):
        cfg = Config()
        copied = []
        calls = []

        def default(t, target):
            calls.append((t, target))
            return tr.Translation(f"[{target}] {t}", "en")

        w = ResultWindow(self.root, text, cfg, translate_fn or default, copied.append, **kw)
        self.root.update()
        return w, copied, calls

    def test_orig_tab_shows_text_without_recopy(self):
        w, copied, _ = self.make("Xin chào")
        self.assertEqual(w.current_text(), "Xin chào")
        self.assertEqual(copied, [])                    # job đã chép rồi, không chép lại

    def test_translate_tab_translates_and_autocopies(self):
        w, copied, calls = self.make("Hello world")
        w.show_tab("trans")
        self.assertTrue(pump(self.root, lambda: copied))
        self.assertEqual(w.current_text(), "[vi] Hello world")
        self.assertEqual(copied, ["[vi] Hello world"])
        self.assertEqual(calls, [("Hello world", "vi")])
        w.show_tab("orig")                              # quay lại: chữ gốc được chép
        self.assertEqual(copied[-1], "Hello world")
        w.show_tab("trans")                             # lần hai dùng kết quả đã có, không dịch lại
        self.assertEqual(len(calls), 1)
        self.assertEqual(copied[-1], "[vi] Hello world")

    def test_same_language_flips_target(self):
        w, _, calls = self.make("Xin chào các bạn")
        w.show_tab("trans")
        pump(self.root, lambda: calls)
        self.assertEqual(calls[0][1], "en")

    def test_start_in_translate_tab(self):
        w, copied, calls = self.make("Hello", start_tab="trans")
        self.assertTrue(pump(self.root, lambda: copied))
        self.assertEqual(calls[0], ("Hello", "vi"))

    def test_pick_language_retranslates_and_saves(self):
        saved = []
        w, copied, calls = self.make("Hello world", save_cfg=lambda: saved.append(1))
        w.show_tab("trans")
        pump(self.root, lambda: copied)
        w.set_target("ja")
        self.assertTrue(pump(self.root, lambda: len(calls) == 2))
        self.assertEqual(calls[1][1], "ja")
        self.assertEqual(w.cfg.target_lang, "ja")
        self.assertTrue(saved)

    def test_edited_original_is_what_gets_translated(self):
        w, copied, calls = self.make("Helo wrld")
        w.text.delete("1.0", "end"); w.text.insert("1.0", "Hello world")
        w.show_tab("trans")
        pump(self.root, lambda: calls)
        self.assertEqual(calls[0][0], "Hello world")

    def test_error_is_shown_not_raised(self):
        def boom(t, target):
            raise tr.TranslateError("Không kết nối được tới dịch vụ dịch.")
        w, copied, _ = self.make("Hello", translate_fn=boom)
        w.show_tab("trans")
        self.assertTrue(pump(self.root, lambda: "Không kết nối" in w.status.cget("text")))
        self.assertEqual(copied, [])

    def test_stale_result_ignored(self):
        import threading
        gate = threading.Event()

        def slow(t, target):
            if target == "ja":
                gate.wait(3)
            return tr.Translation(f"[{target}]", "en")
        w, copied, _ = self.make("Hello world", translate_fn=slow)
        w.show_tab("trans")
        w.set_target("ja")                               # yêu cầu chậm
        w.set_target("fr")                               # yêu cầu mới thay thế
        pump(self.root, lambda: w.current_text() == "[fr]")
        gate.set()
        pump(self.root, lambda: False, 0.4)
        self.assertEqual(w.current_text(), "[fr]")

    def test_autocopy_off(self):
        w, copied, calls = self.make("Hello")
        w.cfg.translate_autocopy = False
        w.show_tab("trans")
        pump(self.root, lambda: calls)
        pump(self.root, lambda: False, 0.3)
        self.assertEqual(copied, [])
        w.copy_current()                                 # nút Chép vẫn chép
        self.assertEqual(copied, ["[vi] Hello"])

    def test_close_and_callback(self):
        closed = []
        w, _, _ = self.make("x", on_close=closed.append)
        w.close(); w.close()
        self.assertEqual(closed, [w])


class FakeClient:
    """Thay OcrClient: ghi lại yêu cầu, trả lời bằng tay qua reply()."""

    def __init__(self):
        self.requests, self.warms, self.idle_s, self.closed = [], 0, 900, False

    busy = property(lambda self: bool(self.requests))
    running = property(lambda self: self.warms > 0)

    def warm(self):
        self.warms += 1

    def ocr(self, img, cb, **opts):
        self.requests.append((img, cb, opts))

    def reply(self, msg):
        img, cb, _ = self.requests.pop(0)
        cb(msg)

    def shutdown(self):
        pass

    def close(self):
        self.closed = True


def ok_lines(*texts):
    return {"ok": True, "lines": [{"text": t, "score": 0.9, "box": [[0, 20 * i], [100, 20 * i], [100, 20 * i + 15],
                                                                     [0, 20 * i + 15]], "source": "paddle"}
                                  for i, t in enumerate(texts)], "warnings": [], "seconds": 0.3}


def find_overlay(root):
    for w in root.winfo_children():
        if isinstance(w, tk.Toplevel):
            for c in w.winfo_children():
                if isinstance(c, tk.Canvas) and str(c.cget("cursor")) == "crosshair":
                    return c
    return None


class AppTests(UITestBase):
    def make_app(self, **cfgkw):
        cfg = Config()
        cfg.float_x, cfg.float_y = 100, 100
        cfg.delay_ms = 10
        for k, v in cfgkw.items():
            setattr(cfg, k, v)
        self.client = FakeClient()
        app = App(self.root, cfg, client=self.client, prewarm_ms=-1)
        self.root.update()
        return app

    def drag_select(self, canvas, a=(20, 20), b=(220, 90)):
        canvas.event_generate("<ButtonPress-1>", x=a[0], y=a[1], when="now")
        canvas.event_generate("<B1-Motion>", x=b[0], y=b[1], when="now")
        canvas.event_generate("<ButtonRelease-1>", x=b[0], y=b[1], when="now")

    def test_capture_flow_real_overlay_and_warm_engine(self):
        app = self.make_app()
        with mock.patch("ocrtool.clipboard.set_text") as cp:
            app.capture()
            self.assertFalse(app.widget.visible)             # ẩn khi chụp để khỏi lọt vào ảnh
            self.assertEqual(app.widget.state, "busy")
            self.assertEqual(self.client.warms, 1)           # engine nạp song song lúc kéo chọn
            app.capture()                                    # bấm lần nữa khi đang chụp: bỏ qua
            self.assertTrue(pump(self.root, lambda: find_overlay(self.root) is not None))
            self.drag_select(find_overlay(self.root))
            self.assertTrue(pump(self.root, lambda: self.client.requests))
            img = self.client.requests[0][0]
            self.assertEqual(img.size, (200, 70))
            self.assertTrue(app.widget.visible)              # hiện lại (đang quay) trong lúc nhận dạng
            self.client.reply(ok_lines("Xin chào", "thế giới"))
            self.assertTrue(pump(self.root, lambda: app.result_win is not None))
            cp.assert_called_once_with("Xin chào\nthế giới")
        self.assertEqual(app.widget.state, "idle")
        self.assertFalse(app.capturing)
        self.assertEqual(app.result_win.current_text(), "Xin chào\nthế giới")
        self.assertIsNone(find_overlay(self.root))

    def test_capture_cancel_with_escape(self):
        app = self.make_app()
        app.capture()
        self.assertTrue(pump(self.root, lambda: find_overlay(self.root) is not None))
        find_overlay(self.root).winfo_toplevel().event_generate("<Escape>", when="now")
        self.assertTrue(pump(self.root, lambda: not app.capturing))
        self.assertEqual(self.client.requests, [])
        self.assertTrue(app.widget.visible)

    def test_capture_ocr_error_and_empty(self):
        app = self.make_app()
        with mock.patch.object(app, "toast") as toast, mock.patch("ocrtool.clipboard.set_text") as cp:
            for reply in ({"ok": False, "error": "Traceback\nboom"}, ok_lines()):
                app.capture()
                pump(self.root, lambda: find_overlay(self.root) is not None)
                self.drag_select(find_overlay(self.root))
                pump(self.root, lambda: self.client.requests)
                self.client.reply(reply)
                pump(self.root, lambda: not app.capturing)
            self.assertEqual(toast.call_count, 2)
            cp.assert_not_called()

    def test_table_mode_and_history_on_capture(self):
        from ocrtool.config import history_dir
        app = self.make_app(table_mode=True, after_capture="copy")
        msg = {"ok": True, "warnings": [], "lines": [
            {"text": "A", "score": 1, "box": [[0, 0], [20, 0], [20, 15], [0, 15]]},
            {"text": "B", "score": 1, "box": [[200, 0], [220, 0], [220, 15], [200, 15]]}]}
        from PIL import Image
        with mock.patch("ocrtool.clipboard.set_text") as cp, mock.patch.object(app, "toast"):
            app.capturing = True
            app._finish_capture(Image.new("RGB", (30, 20), "white"), msg)
        cp.assert_called_once_with("A\tB")
        self.assertEqual(len(list(history_dir().glob("*.txt"))), 1)

    def test_translate_mode_starts_on_translate_tab(self):
        app = self.make_app(after_capture="translate")
        with mock.patch("ocrtool.translate.translate", return_value=tr.Translation("Hello", "vi")) as t, \
                mock.patch("ocrtool.clipboard.set_text") as cp:
            app.handle_result({"status": "ok", "text": "Xin chào", "warnings": []})
            self.assertTrue(pump(self.root, lambda: cp.called))
            self.assertEqual(app.result_win.tab, "trans")
            self.assertEqual(t.call_args[0][:2], ("Xin chào", "en"))        # cùng ngôn ngữ đích -> đảo sang en
            cp.assert_called_with("Hello")

    def test_copy_mode_shows_toast_only(self):
        app = self.make_app(after_capture="copy")
        with mock.patch.object(app, "toast") as toast:
            app.handle_result({"status": "ok", "text": "abc", "chars": 3, "snippet": "abc", "warnings": []})
        self.assertIsNone(app.result_win)
        toast.assert_called_once()

    def test_empty_and_error_notify_and_cancel_silent(self):
        app = self.make_app()
        with mock.patch.object(app, "toast") as toast:
            app.handle_result({"status": "empty", "warnings": []})
            app.handle_result({"status": "error", "message": "x\nboom"})
            app.handle_result({"status": "cancelled"})
        self.assertEqual(toast.call_count, 2)
        self.assertIsNone(app.result_win)
        self.assertTrue(app.widget.visible)

    def test_hidden_widget_stays_hidden_after_capture(self):
        app = self.make_app(float_visible=False)
        self.assertFalse(app.widget.visible)
        app.capture()
        pump(self.root, lambda: find_overlay(self.root) is not None)
        find_overlay(self.root).winfo_toplevel().event_generate("<Escape>", when="now")
        pump(self.root, lambda: not app.capturing)
        self.assertFalse(app.widget.visible)

    def test_hide_requires_tray(self):
        app = self.make_app()
        with mock.patch.object(app, "toast") as toast:
            app.hide_widget()
            self.assertTrue(app.widget.visible)
            toast.assert_called_once()
            app.tray_ok = True
            app.hide_widget()
        self.assertFalse(app.widget.visible)
        self.assertFalse(app.cfg.float_visible)
        app.show_widget()
        self.assertTrue(app.widget.visible)

    def test_click_right_after_menu_close_is_ignored(self):
        app = self.make_app()
        with mock.patch.object(app, "capture") as cap:
            app.show_menu(300, 300)
            app.menu.close()
            app._on_click()
            self.assertFalse(cap.called)
            app.menu.closed_at -= 1
            app._on_click()
            self.assertTrue(cap.called)

    def test_post_from_thread(self):
        import threading
        app = self.make_app()
        got = []
        threading.Thread(target=lambda: app.post(lambda: got.append(1))).start()
        self.assertTrue(pump(self.root, lambda: got))

    def test_options_persist_and_apply(self):
        app = self.make_app()
        app.set_option("float_size", 64)
        app.set_option("target_lang", "ja")
        app.set_output_mode("table")
        self.assertEqual((app.cfg.table_mode, app.cfg.join_lines), (True, False))
        app.set_output_mode("single")
        self.assertEqual((app.cfg.table_mode, app.cfg.join_lines), (False, True))
        c = Config.load()
        self.assertEqual((c.float_size, c.target_lang, c.join_lines), (64, "ja", True))

    def test_drag_saves_position(self):
        app = self.make_app()
        app._on_moved(321, 123)
        c = Config.load()
        self.assertEqual((c.float_x, c.float_y), (321, 123))

    def test_history_list_and_copy(self):
        from ocrtool.config import history_dir
        d = history_dir()
        for i, t in enumerate(["một hai ba", "bốn năm\nsáu"]):
            p = d / f"2026-0{i}.txt"; p.write_text(t, encoding="utf-8")
            os.utime(p, (1000 + i, 1000 + i))
        app = self.make_app(after_capture="copy")
        items = app.history_items()
        self.assertEqual([l for l, _ in items], ["bốn năm sáu", "một hai ba"])      # mới nhất trước
        with mock.patch("ocrtool.clipboard.set_text") as cp, mock.patch.object(app, "toast"):
            app.copy_history(items[0][1])
        cp.assert_called_once_with("bốn năm\nsáu")

    def test_build_menu_reflects_config(self):
        app = self.make_app(target_lang="ja", after_capture="copy", table_mode=True)
        items = build_menu(app)
        top = {i.label: i for i in items if not i.separator}
        self.assertIn("Chụp vùng để OCR", top)
        self.assertEqual(top["Dịch sang: 日本語"].children[[c.label for c in top["Dịch sang: 日本語"].children].index("日本語")].checked, True)
        after = top["Sau khi chụp"].children
        self.assertEqual([c.checked for c in after], [False, False, True])
        out = top["Kiểu chữ xuất ra"].children
        self.assertEqual([c.checked for c in out], [False, False, True])
        self.assertEqual(top["Ẩn cửa sổ nổi"].enabled, False)        # chưa có khay
        app.tray_ok = True
        self.assertTrue({i.label: i for i in build_menu(app) if not i.separator}["Ẩn cửa sổ nổi"].enabled)

    def test_every_menu_action_is_callable_and_menu_renders(self):
        app = self.make_app()
        def walk(items, depth=0):
            for it in items:
                if it.separator:
                    continue
                kids = it.children() if callable(it.children) else it.children
                if kids is not None:
                    walk(kids, depth + 1)
                else:
                    self.assertTrue(callable(it.action) or not it.enabled, it.label)
        walk(build_menu(app))
        app.show_menu(400, 400)
        self.assertTrue(app.menu.is_open)
        app.menu.close()

    def test_lens_toggle_from_menu_shift_click_and_quit(self):
        app = self.make_app()
        app.toggle_lens()
        self.assertIsNotNone(app.lens)
        labels = {i.label: i for i in build_menu(app) if not i.separator}
        self.assertTrue(labels["Lăng kính dịch"].checked)
        app.toggle_lens()
        self.assertIsNone(app.lens)
        app.widget._on_press(SimpleNamespace(x_root=110, y_root=110, x=5, y=5, state=0x0001))   # Shift giữ
        app.widget._on_release(SimpleNamespace(x_root=110, y_root=110, x=5, y=5))
        self.assertIsNotNone(app.lens)
        app.widget.canvas.event_generate("<Button-2>", x=3, y=3)                         # chuột giữa
        self.root.update()
        self.assertIsNone(app.lens)
        app.open_lens()
        app.quit()
        self.assertIsNone(app.lens)
        self.assertTrue(self.client.closed)

    def test_keep_engine_option(self):
        app = self.make_app()
        app.set_option("keep_engine_min", 5)
        self.assertEqual(self.client.idle_s, 300)
        app.set_option("keep_engine_min", -1)
        self.assertEqual(self.client.idle_s, -1)

    def test_toggle_hotkey_noop_off_windows(self):
        app = self.make_app()
        app.toggle_hotkey()
        self.assertEqual(app.cfg.hotkey, "ctrl+alt+o")
        self.assertIsNone(app.hotkey)                                  # không phải Windows
        app.toggle_hotkey()
        self.assertEqual(app.cfg.hotkey, "")



def L(*texts, h=20, x=10):
    """Các dòng OCR giả (toạ độ trong khung): mỗi dòng cao h, cách nhau 4px."""
    return [{"text": t, "box": [[x, 5 + i * (h + 4)], [x + 12 * len(t), 5 + i * (h + 4)],
                                [x + 12 * len(t), 5 + i * (h + 4) + h], [x, 5 + i * (h + 4) + h]]}
            for i, t in enumerate(texts)]


class LensTests(UITestBase):
    def make(self, frames=None, **kw):
        from PIL import Image, ImageDraw
        cfg = Config()
        cfg.lens_x, cfg.lens_y, cfg.lens_w, cfg.lens_h = 200, 200, 300, 80
        cfg.lens_mode = kw.pop("mode", "panel")
        self.frames = frames or {"img": Image.new("RGB", (300, 80), "white")}
        self.ocr_calls, self.tr_calls, self.copied = [], [], []

        def grab(rect):
            self.rects.append(rect)
            return self.frames["img"]

        def ocr(img, cb):
            self.ocr_calls.append(cb)

        def translate(text, target):
            self.tr_calls.append((text, target))
            return tr.Translation("\n".join(f"<{target}> {p}" for p in text.split("\n")), "en")
        self.rects = []
        lens = LensWindow(self.root, cfg, ocr, translate, self.copied.append, grab_fn=grab, interval_ms=10**6, **kw)
        self.root.update()
        return lens

    def frame(self, text):
        from PIL import Image, ImageDraw
        im = Image.new("RGB", (300, 80), "white")
        ImageDraw.Draw(im).rectangle((10, 10, 10 + 25 * len(text), 40), fill="black")
        return im

    def test_layout_hole_is_free(self):
        lens = self.make()
        x, y, w, h = lens.rect()
        self.assertEqual((x, y, w, h), (200, 200, 300, 80))
        for part in (lens.top, lens.left, lens.right, lens.bottom):
            px, py = part.winfo_rootx(), part.winfo_rooty()
            pw, ph = part.winfo_width(), part.winfo_height()
            overlap = not (px + pw <= x or px >= x + w or py + ph <= y or py >= y + h)
            self.assertFalse(overlap, "khung không được che vùng đọc")
        self.assertGreaterEqual(lens.panel.winfo_rooty(), y + h)

    def test_ocr_only_after_content_settles_then_translates(self):
        lens = self.make()
        lens.step()                                # khung đầu tiên: "đổi" so với không có gì -> chờ
        self.assertEqual(self.ocr_calls, [])
        lens.step()                                # đứng yên -> đọc
        self.assertEqual(len(self.ocr_calls), 1)
        self.assertEqual(self.rects[-1], (200, 200, 300, 80))
        lens.step()                                # đang chờ OCR -> không gửi thêm
        self.assertEqual(len(self.ocr_calls), 1)
        self.ocr_calls.pop()(L("Hello world"), None)
        self.assertTrue(pump(self.root, lambda: lens.translated))
        self.assertEqual(lens.translated, "<vi> Hello world")
        self.assertEqual(lens.out_lbl.cget("text"), "<vi> Hello world")
        lens.step(); lens.step()                   # không đổi gì -> không đọc lại
        self.assertEqual(self.ocr_calls, [])
        self.frames["img"] = self.frame("scroll")  # cuộn trang
        lens.step()
        self.assertEqual(self.ocr_calls, [])       # đang chuyển động -> chờ
        lens.step()
        self.assertEqual(len(self.ocr_calls), 1)
        self.ocr_calls.pop()(L("Hello world"), None)  # cùng chữ -> không dịch lại
        pump(self.root, lambda: False, 0.2)
        self.assertEqual(len(self.tr_calls), 1)

    def test_language_change_retranslates_and_flips(self):
        lens = self.make()
        lens.step(); lens.step()
        self.ocr_calls.pop()(L("Xin chào các bạn"), None)
        self.assertTrue(pump(self.root, lambda: lens.translated))
        self.assertEqual(self.tr_calls[-1], ("Xin chào các bạn", "en"))      # chữ Việt + đích Việt -> sang English
        lens.set_target("ja")
        self.assertTrue(pump(self.root, lambda: len(self.tr_calls) == 2))
        self.assertEqual(self.tr_calls[-1][1], "ja")
        self.assertEqual(lens.cfg.target_lang, "ja")

    def test_pause_errors_copy_and_close(self):
        closed = []
        lens = self.make(on_close=closed.append)
        lens.toggle_pause()
        lens.step(); lens.step()
        self.assertEqual(self.ocr_calls, [])
        lens.toggle_pause()
        lens.step(); lens.step()
        self.ocr_calls.pop()(None, "Traceback\nOCR hỏng")
        self.assertTrue(pump(self.root, lambda: "OCR hỏng" in lens.status.cget("text")))
        self.frames["img"] = self.frame("x"); lens.step(); lens.step()
        self.ocr_calls.pop()([], None)
        self.assertTrue(pump(self.root, lambda: "Không thấy chữ" in lens.status.cget("text")))
        lens.translated = "abc"
        lens.copy_translation()
        self.assertEqual(self.copied, ["abc"])
        lens.close(); lens.close()
        self.assertEqual(closed, [lens])

    def test_move_and_resize_save_geometry(self):
        saved = []
        lens = self.make(save_cfg=lambda: saved.append(1))
        ev = lambda x, y: SimpleNamespace(x_root=x, y_root=y)  # noqa: E731
        lens._move_start(ev(250, 190)); lens._move(ev(300, 240)); lens._drag_end()
        self.assertEqual(lens.rect()[:2], (250, 250))
        lens._resize_start(ev(0, 0)); lens._resize(ev(-1000, -1000)); lens._drag_end()
        self.assertEqual(lens.rect()[2:], (80, 28))                         # cỡ tối thiểu
        self.assertEqual((lens.cfg.lens_x, lens.cfg.lens_w), (250, 80))
        self.assertEqual(len(saved), 2)

    def test_overlay_mode_draws_blocks_over_text_and_clears_on_scroll(self):
        lens = self.make(mode="overlay")
        self.assertEqual(lens.panel.state(), "withdrawn")         # đè lên chữ: không có bảng bên dưới
        lens.step(); lens.step()
        lines = L("The quick brown fox", "jumps over the dog.") + [
            {"text": "Footer", "box": [[10, 60], [80, 60], [80, 75], [10, 75]]}]
        lines[2]["box"] = [[200, 56], [290, 56], [290, 68], [200, 68]]    # chữ nhỏ hơn hẳn, chỗ khác -> đoạn riêng
        self.ocr_calls.pop()(lines, None)
        self.assertTrue(pump(self.root, lambda: lens.block_wins))
        self.assertEqual(self.tr_calls[0][0], "The quick brown fox jumps over the dog.\nFooter")
        self.assertEqual(len(lens.block_wins), 2)
        w0 = lens.block_wins[0]
        self.root.update()
        self.assertEqual((w0.winfo_rootx(), w0.winfo_rooty()), (206, 200))   # lề che dấu bị chặn ở mép khung   # đúng chỗ chữ gốc
        for w in lens.block_wins:                                   # nằm trong vùng nhìn
            self.assertTrue(200 <= w.winfo_rootx() and w.winfo_rootx() + w.winfo_width() <= 500)
        # không phải Windows mới: khối dịch được ẩn thoáng qua lúc chụp để không đọc lại chính bản dịch
        seen = []
        self.frames_states = seen
        orig = lens.grab_fn
        lens.grab_fn = lambda r: (seen.append([w.state() for w in lens.block_wins]), orig(r))[1]
        lens.step()
        self.assertEqual(seen[-1], ["withdrawn", "withdrawn"])
        self.assertTrue(all(w.state() == "normal" for w in lens.block_wins))
        self.frames["img"] = self.frame("scroll")                  # cuộn trang -> bỏ bản dịch cũ ngay
        lens.step()
        self.assertEqual(lens.block_wins, [])

    def test_mode_toggle(self):
        saved = []
        lens = self.make(mode="overlay", save_cfg=lambda: saved.append(1))
        lens.step(); lens.step()
        self.ocr_calls.pop()(L("Hello"), None)
        pump(self.root, lambda: lens.block_wins)
        lens.toggle_mode()
        self.assertEqual((lens.mode, lens.cfg.lens_mode), ("panel", "panel"))
        self.assertEqual(lens.block_wins, [])
        self.root.update()
        self.assertNotEqual(lens.panel.state(), "withdrawn")
        lens.toggle_mode()
        self.assertEqual(len(lens.block_wins), 1)
        self.assertEqual(lens.panel.state(), "withdrawn")
        lens.close()
        self.assertEqual(lens.block_wins, [])

    def test_signature_diff(self):
        a, b = signature(self.frame("aaa")), signature(self.frame("aaaaaaa"))
        self.assertEqual(sig_diff(a, a), 0)
        self.assertGreater(sig_diff(a, b), 3)
        self.assertEqual(sig_diff(None, a), 255)



@unittest.skipUnless(HAVE_TK, "không có tkinter/màn hình")
class LensHelperTests(unittest.TestCase):
    def test_group_blocks(self):
        lines = L("Dòng một của đoạn", "dòng hai của đoạn") + [
            {"text": "Tiêu đề lớn", "box": [[10, 100], [200, 100], [200, 140], [10, 140]]},
            {"text": "你好", "box": [[10, 150], [50, 150], [50, 170], [10, 170]]},
            {"text": "世界", "box": [[10, 174], [50, 174], [50, 194], [10, 194]]},
            {"text": "  ", "box": [[0, 0], [1, 0], [1, 1], [0, 1]]}]
        blocks = group_blocks(lines)
        self.assertEqual([b["text"] for b in blocks], ["Dòng một của đoạn dòng hai của đoạn", "Tiêu đề lớn", "你好世界"])
        self.assertEqual(blocks[0]["rect"][1], 5)
        self.assertEqual(group_blocks([]), [])

    def test_side_by_side_columns_stay_separate(self):
        a = {"text": "left", "box": [[0, 0], [100, 0], [100, 20], [0, 20]]}
        b = {"text": "right", "box": [[300, 24], [400, 24], [400, 44], [300, 44]]}
        self.assertEqual(len(group_blocks([a, b])), 2)

    def test_wrap_and_fit(self):
        m = lambda s: 10 * len(s)  # noqa: E731
        self.assertEqual(wrap_text("aa bb cc dd", 50, m), ["aa bb", "cc dd"])
        self.assertEqual(wrap_text("你好世界和平", 30, m), ["你好世", "界和平"])
        root = tk.Tk()
        try:
            import tkinter.font as tkf
            mk = lambda px: tkf.Font(root=root, family="DejaVu Sans", size=-px)  # noqa: E731
            f, lines, total = fit_text("a fairly long translated sentence here", 120, 40, 20, mk)
            self.assertLessEqual(total, 40)
            self.assertLess(-f.cget("size"), 20)
            f2, lines2, _ = fit_text("x", 120, 40, 16, mk)
            self.assertEqual(f2.cget("size"), -16)
        finally:
            root.destroy()

    def test_colors(self):
        from PIL import Image
        light = Image.new("RGB", (100, 40), (250, 250, 240))
        dark = Image.new("RGB", (100, 40), (20, 22, 30))
        self.assertEqual(colors_for(light, (10, 10, 60, 30)), ("#fafaf0", "#111111"))
        self.assertEqual(colors_for(dark, (10, 10, 60, 30))[1], "#f5f5f5")


if __name__ == "__main__":
    unittest.main()
