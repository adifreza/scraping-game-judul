"""Check the cross-customer order-list detection (no tkinter needed)."""
from game_scraper_multi_site import normalize_name
from game_launcher_multi_site import LIST_DEFS, build_also_map, norm_keys_in_text


def test_norm_keys_only_numbered_lines():
    text = "Daftar Game\n\n1. Hollow Knight\n2. Hades 2\nTotal Size: 5 GB"
    assert norm_keys_in_text(text) == {normalize_name("Hollow Knight"), normalize_name("Hades 2")}


def test_also_map_lists_other_customers_wanting_same_game():
    order_lists = {
        "cust1": "1. Hollow Knight\n2. Hades 2",
        "cust3": "1. Hades 2",
        "cust5": "1. Elden Ring",
    }
    m = build_also_map("pesanan", LIST_DEFS, order_lists)
    assert sorted(m[normalize_name("Hades 2")]) == ["Cust 1", "Cust 3"]
    assert m[normalize_name("Hollow Knight")] == ["Cust 1"]
    assert m[normalize_name("Elden Ring")] == ["Cust 5"]


def test_active_list_excluded_from_its_own_map():
    order_lists = {"cust1": "1. Hades 2", "cust2": "1. Hades 2"}
    m = build_also_map("cust1", LIST_DEFS, order_lists)
    assert m[normalize_name("Hades 2")] == ["Cust 2"]


if __name__ == "__main__":
    test_norm_keys_only_numbered_lines()
    test_also_map_lists_other_customers_wanting_same_game()
    test_active_list_excluded_from_its_own_map()
    print("ok")
