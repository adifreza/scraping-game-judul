"""Check cleanup classification: wanted folders are kept, the rest are deletable,
and delete_entry removes both folders and files."""
import os
import tempfile

import game_cleanup


def test_classify_keeps_wanted_deletes_the_rest():
    with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as dl:
        os.mkdir(os.path.join(root, "Elden Ring"))
        os.mkdir(os.path.join(root, "Hollow Knight"))
        os.mkdir(os.path.join(root, "Some Old Junk"))
        open(os.path.join(dl, "Hades.II-CODEX.rar"), "w").close()

        order_lists = {"cust1": "1. Elden Ring\n2. Hades II", "cust3": "1. Elden Ring"}
        entries = {e.label: e for e in game_cleanup.classify([root], dl, order_lists)}

        assert sorted(entries["Elden Ring"].wanted_by) == ["Cust 1", "Cust 3"]
        assert entries["Elden Ring"].deletable is False
        assert entries["Hades.II-CODEX.rar"].wanted_by == ["Cust 1"]
        assert entries["Hades.II-CODEX.rar"].extracted is False
        assert entries["Hollow Knight"].deletable is True
        assert entries["Some Old Junk"].deletable is True


def test_delete_entry_handles_folder_and_file():
    with tempfile.TemporaryDirectory() as root:
        folder = os.path.join(root, "game")
        os.mkdir(folder)
        open(os.path.join(folder, "data.bin"), "w").close()
        game_cleanup.delete_entry(folder)
        assert not os.path.exists(folder)

        f = os.path.join(root, "loose.iso")
        open(f, "w").close()
        game_cleanup.delete_entry(f)
        assert not os.path.exists(f)


if __name__ == "__main__":
    test_classify_keeps_wanted_deletes_the_rest()
    test_delete_entry_handles_folder_and_file()
    print("ok")
