import time
import webbrowser
import re
import os
from difflib import SequenceMatcher
from typing import Callable
from urllib.parse import quote_plus, urljoin
from urllib.request import Request, urlopen


games = [
    "Ghost Rider PS2",
    "FIFA Street 2 PS2",
    "Guitar Hero II PS2",
    "Need for Speed Most Wanted PS2",
    "PES 6 Absolute Patch 2006 PS2",
    "PES 2013 Pro Evolution Soccer PS2",
    "Grand Theft Auto San Andreas Remastered PS2",
    "Grand Theft Auto San Andreas Upin Ipin PS2",
    "GTA San Andreas Opera Van Java PS2",
    "Burnout 3 Takedown PS2",
    "WRC World Rally Championship PS2",
    "Call of Duty 3 PS2",
    "Captain Tsubasa PS2",
    "Conflict Desert Storm II Back to Baghdad PS2",
    "Conflict Global Terror PS2",
    "Freedom Fighters PS2",
    "FIFA 14 Legacy Edition PS2",
    "Grand Theft Auto Vice City PS2",
    "Gran Turismo 4 Spec II PS2",
    "NBA Street V3 PS2",
    "MotoGP 3 PS2",
    "MotoGP 4 PS2",
    "Motocross Mania 3 PS2",
    "Tenchu Wrath of Heaven PS2",
    "Shadow of the Colossus PS2",
    "Tony Hawks Underground PS2",
    "Okami PS2",
    "Marvel Ultimate Alliance 2 PS2",
    "Twisted Metal Black PS2",
    "Crash Nitro Kart PS2",
    "Devil May Cry 3 Dantes Awakening PS2",
    "eFootball 2026 PS2",
    "SBK-09 Superbike World Championship PS2",
    "Yakuza 2 PS2",
    "Need for Speed Hot Pursuit 2 PS2",
    "Super Bomba Patch 2026 PS2",
    "Jet Li Rise to Honor PS2",
    "Red Dead Revolver PS2",
    "Grand Theft Auto V Legacy PS2",
    "Spider-Man 3 PS2",
    "Dynasty Warriors 6 PS2",
    "The Lord of the Rings The Return of the King PS2",
    "Disney Pixar Cars PS2",
    "Auto Modellista PS2",
    "Sonic Unleashed PS2",
    "Ben 10 Alien Force Vilgax Attacks PS2",
    "Jak 3 PS2",
    "Formula One 06 PS2",
]


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

BRAVE_BINARY = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
IDM_EXTENSION_HINT = "Make sure IDM Integration Module is enabled in Brave."

LogFn = Callable[[str], None]
PauseFn = Callable[[str], None]


def sanitize_title_for_search(text: str) -> str:
    sanitized = text
    for dash in ("-", "–", "—"):
        sanitized = sanitized.replace(dash, " ")
    for apostrophe in ("'", "’"):
        sanitized = sanitized.replace(apostrophe, "")
    sanitized = re.sub(r"\s+", " ", sanitized)
    return sanitized.strip()


def get_browser() -> webbrowser.BaseBrowser:
    if os.path.exists(BRAVE_BINARY):
        try:
            return webbrowser.BackgroundBrowser(BRAVE_BINARY)
        except Exception:
            pass
    return webbrowser


def to_search_url(game_name: str) -> str:
    clean_name = re.sub(r"\bps2\b", "", game_name, flags=re.IGNORECASE)
    clean_name = sanitize_title_for_search(clean_name)
    clean_name = " ".join(clean_name.split())
    query = quote_plus(clean_name)
    return f"https://romsfun.com/roms/playstation-2/?s={query}"


def normalize_name(text: str) -> str:
    no_ps2 = re.sub(r"\bps2\b", "", text, flags=re.IGNORECASE)
    no_ps2 = sanitize_title_for_search(no_ps2)
    alnum_only = re.sub(r"[^a-z0-9 ]+", " ", no_ps2.lower())
    return " ".join(alnum_only.split())


def fetch_html(url: str) -> str | None:
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=15) as response:
            return response.read().decode("utf-8", errors="ignore")
    except Exception as error:
        print(f"Failed fetching {url}: {error}")
        return None


def extract_ps2_game_links(html: str) -> list[str]:
    links = re.findall(r'href="([^"]+/roms/playstation-2/[^"]+\.html)"', html, flags=re.IGNORECASE)
    unique_links: list[str] = []
    seen: set[str] = set()
    for link in links:
        absolute = urljoin("https://romsfun.com", link)
        if absolute not in seen:
            seen.add(absolute)
            unique_links.append(absolute)
    return unique_links


def pick_best_game_link(game_name: str, links: list[str]) -> str | None:
    if not links:
        return None

    target = normalize_name(game_name)
    best_link = None
    best_score = 0.0

    for link in links:
        slug = link.rsplit("/", 1)[-1].replace(".html", "")
        score = SequenceMatcher(None, target, normalize_name(slug)).ratio()
        if score > best_score:
            best_score = score
            best_link = link

    if best_score < 0.45:
        return None
    return best_link


def extract_download_rom_link(game_page_html: str, game_page_url: str) -> str | None:
    match = re.search(
        r'<a[^>]+href="([^"]+)"[^>]*>(?:(?!</a>).)*download\s*rom(?:(?!</a>).)*</a>',
        game_page_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    return urljoin(game_page_url, match.group(1))


def extract_download_file_links(download_page_html: str, download_page_url: str) -> list[tuple[str, str]]:
    matches = re.findall(r'<a[^>]+href="([^"]*?/download/[^"]+)"[^>]*>(.*?)</a>', download_page_html, flags=re.IGNORECASE | re.DOTALL)
    links: list[tuple[str, str]] = []
    seen: set[str] = set()

    for href, raw_text in matches:
        absolute_href = urljoin(download_page_url, href)
        if absolute_href in seen:
            continue
        seen.add(absolute_href)
        text = re.sub(r"<[^>]+>", " ", raw_text)
        text = re.sub(r"\s+", " ", text).strip()
        links.append((text, absolute_href))

    return links


def wait_for_manual_download_click(game: str, pause_fn: PauseFn | None = None) -> None:
    if pause_fn is not None:
        pause_fn(game)
        return

    print(f"Ready to download: {game}")
    print("Please click 'Download Now' manually in Brave so IDM can capture it.")
    input("After IDM popup appears (or download starts), press Enter to continue...")


def score_download_file(text: str, href: str) -> int:
    candidate = f"{text} {href}".lower()
    if "demo" in candidate:
        return -10_000

    score = 0
    if "redump" in candidate:
        score += 1_000
    elif "chd" in candidate:
        score += 500

    if "europe australia" in candidate:
        score += 400
    elif "europe" in candidate or "pal" in candidate:
        score += 350

    if "usa" in candidate:
        score += 300
    if "japan" in candidate:
        score += 200
    if "asia" in candidate:
        score += 100

    return score


def pick_best_download_file(download_page_html: str, download_page_url: str) -> str | None:
    file_links = extract_download_file_links(download_page_html, download_page_url)
    if not file_links:
        return None

    best_href = None
    best_score = -10_000

    for text, href in file_links:
        score = score_download_file(text, href)
        if score > best_score:
            best_score = score
            best_href = href

    if best_score < 0:
        return None
    return best_href


def open_game_search_tabs(
    game_list: list[str],
    log_fn: LogFn | None = None,
    pause_fn: PauseFn | None = None,
) -> None:
    browser = get_browser()
    log = log_fn or print

    for game in game_list:
        search_url = to_search_url(game)
        log(f"Opening: {game}")

        search_html = fetch_html(search_url)
        if not search_html:
            log(f"Search page not available: {search_url}")
            browser.open_new_tab(search_url)
            time.sleep(2)
            continue

        game_links = extract_ps2_game_links(search_html)
        best_game_link = pick_best_game_link(game, game_links)

        if not best_game_link:
            log(f"Game page not found: {game}")
            browser.open_new_tab(search_url)
            time.sleep(2)
            continue

        log(f"Game page: {best_game_link}")
        browser.open_new_tab(best_game_link)
        time.sleep(2)

        game_html = fetch_html(best_game_link)
        if not game_html:
            continue

        download_page_link = extract_download_rom_link(game_html, best_game_link)
        if not download_page_link:
            log(f"Download button not found for: {game}")
            continue

        log(f"Download page: {download_page_link}")
        browser.open_new_tab(download_page_link)
        time.sleep(2)

        download_html = fetch_html(download_page_link)
        preferred_file_link = pick_best_download_file(download_html or "", download_page_link)
        if not preferred_file_link and download_html:
            fallback_download_html = fetch_html(download_page_link)
            if fallback_download_html:
                preferred_file_link = pick_best_download_file(fallback_download_html, download_page_link)

        if not preferred_file_link:
            log(f"No preferred file found for: {game}")
            continue

        log(f"Selected file: {preferred_file_link}")
        browser.open_new_tab(preferred_file_link)

        log("Waiting 10 seconds before manual Download Now click...")
        time.sleep(10)
        log(IDM_EXTENSION_HINT)
        wait_for_manual_download_click(game, pause_fn=pause_fn)

        time.sleep(2)


if __name__ == "__main__":
    open_game_search_tabs(games)
