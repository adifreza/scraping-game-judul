"""Smoke check: the window builds, an empty customer slot stays empty, Clear
really empties a slot, and both scan roots feed one merged index.

Creates a real Tk window, updates once, destroys it. LOCALAPPDATA is pointed
at a temp dir first so the app writes to a throwaway settings.json instead of
the real one.
"""
import os
import tempfile

import game_folder_scan as folder_scan


def test_two_roots_merge_local_wins():
    with tempfile.TemporaryDirectory() as local, tempfile.TemporaryDirectory() as hdd:
        os.mkdir(os.path.join(local, "Cyberpunk 2077"))
        os.mkdir(os.path.join(hdd, "Cyberpunk 2077"))
        os.mkdir(os.path.join(hdd, "Elden Ring"))

        index = folder_scan.scan_extracted_folders([local, hdd])
        assert len(index) == 2
        assert index[folder_scan.normalize_name("Cyberpunk 2077")][1].startswith(local)
        assert index[folder_scan.normalize_name("Elden Ring")][1].startswith(hdd)


def test_missing_root_is_ignored():
    assert folder_scan.scan_extracted_folders(["", r"Z:\nope"]) == {}


def test_window_builds_and_slots_behave():
    import pyperclip

    with tempfile.TemporaryDirectory() as fake_appdata:
        os.environ["LOCALAPPDATA"] = fake_appdata  # keep the real settings.json out of this
        import game_launcher_multi_site as gl

        pyperclip.copy("1. Should Never Autofill A Customer Slot")

        app = gl.GameLauncherMultiSite()
        try:
            app._active_list = "cust5"
            app._load_active_list()
            app.update()
            assert app.input_text.get("1.0", "end-1c").strip() == ""

            # Clear must empty the slot on disk too, not just the textbox.
            app._settings["order_lists"]["cust5"] = "1. Junk From The Old Bug"
            app._clear_inputs()
            assert app._settings["order_lists"]["cust5"] == ""

            assert app._scan_roots() == [
                (label, path)
                for label, path in (
                    ("Lokal", (app._settings.get("extracted_root") or "").strip()),
                    ("HDD", (app._settings.get("extracted_root_2") or "").strip()),
                )
                if path and os.path.isdir(path)
            ]
        finally:
            app.destroy()


if __name__ == "__main__":
    test_two_roots_merge_local_wins()
    test_missing_root_is_ignored()
    test_window_builds_and_slots_behave()
    print("ok")
