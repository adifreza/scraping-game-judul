import time
import webbrowser
import re
import os
from difflib import SequenceMatcher
from http.cookiejar import Cookie, CookieJar
from typing import Callable
from urllib.parse import quote_plus, urljoin, urlparse
from urllib.request import Request, build_opener, HTTPCookieProcessor


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

BRAVE_BINARY = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
IDM_EXTENSION_HINT = "Make sure IDM Integration Module is enabled in Brave."

# Shared cookie jar so that any cf_clearance / __cf_bm cookie a site sets
# (or that we import from the user's real Brave profile) is reused across
# every request in the run instead of starting from a blank session each time.
_COOKIE_JAR = CookieJar()
_OPENER = build_opener(HTTPCookieProcessor(_COOKIE_JAR))

_BASE_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,id-ID;q=0.8,id;q=0.7",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

_synced_cookie_domains: set[str] = set()


def sync_browser_cookies(domain: str, force: bool = False) -> None:
    """Import cookies (e.g. a solved cf_clearance) for `domain` from the user's real
    Brave profile into our request session, so we ride on a challenge the user
    already passed manually instead of hitting Cloudflare cold every time."""
    if domain in _synced_cookie_domains and not force:
        return
    _synced_cookie_domains.add(domain)
    try:
        import browser_cookie3
        brave_jar = browser_cookie3.brave(domain_name=domain)
        for cookie in brave_jar:
            _COOKIE_JAR.set_cookie(cookie)
    except Exception:
        pass  # Brave profile locked/unavailable/not installed - fall back to a plain session.

LogFn = Callable[[str], None]
PauseFn = Callable[[str], None]
ResultFn = Callable[[dict[str, str | None]], None]


def sanitize_title_for_search(text: str) -> str:
    """Remove dashes and apostrophes for cleaner search"""
    sanitized = text
    for dash in ("-", "–", "—"):
        sanitized = sanitized.replace(dash, " ")
    for apostrophe in ("'", "’", "`", "´"):
        sanitized = sanitized.replace(apostrophe, "")
    sanitized = re.sub(r"[^A-Za-z0-9 ]+", " ", sanitized)
    sanitized = re.sub(r"\s+", " ", sanitized)
    return sanitized.strip()


def get_browser() -> webbrowser.BaseBrowser:
    """Get Brave browser instance"""
    if os.path.exists(BRAVE_BINARY):
        try:
            return webbrowser.BackgroundBrowser(BRAVE_BINARY)
        except Exception:
            pass
    return webbrowser


def sanitize_title_for_romsfun(text: str) -> str:
    """Sanitize title specifically for romsfun, replacing 's and ’s with space to bypass search indexing issues"""
    sanitized = text.replace("'s", " ").replace("’s", " ")
    sanitized = re.sub(r"\bcabelas\b", "cabela", sanitized, flags=re.IGNORECASE)
    for dash in ("-", "–", "—"):
        sanitized = sanitized.replace(dash, " ")
    for apostrophe in ("'", "’", "`", "´"):
        sanitized = sanitized.replace(apostrophe, "")
    sanitized = re.sub(r"[^A-Za-z0-9 ]+", " ", sanitized)
    sanitized = re.sub(r"\s+", " ", sanitized)
    return sanitized.strip()


def to_romsfun_search_url(game_name: str) -> str:
    """Build romsfun.com search URL for PS2 games"""
    clean_name = re.sub(r"\bps2\b", "", game_name, flags=re.IGNORECASE)
    clean_name = sanitize_title_for_romsfun(clean_name)
    clean_name = " ".join(clean_name.split())
    query = quote_plus(clean_name)
    return f"https://romsfun.com/roms/playstation-2/?s={query}"


def to_steamrip_search_url(game_name: str) -> str:
    """Build steamrip.com search URL for PC/console games"""
    clean_name = sanitize_title_for_search(game_name)
    clean_name = " ".join(clean_name.split())
    query = quote_plus(clean_name)
    return f"https://steamrip.com/?s={query}"


def normalize_name(text: str) -> str:
    """Normalize name for matching"""
    no_ps2 = re.sub(r"\bps2\b", "", text, flags=re.IGNORECASE)
    no_ps2 = sanitize_title_for_search(no_ps2)
    alnum_only = re.sub(r"[^a-z0-9 ]+", " ", no_ps2.lower())
    return " ".join(alnum_only.split())


def fetch_html(url: str) -> str | None:
    """Fetch HTML from URL, using a persistent cookie session and browser-like headers
    so a Cloudflare check passed once (in-session or in the user's real Brave profile)
    is reused instead of triggering a fresh challenge on every call."""
    domain = urlparse(url).netloc
    sync_browser_cookies(domain)
    try:
        headers = dict(_BASE_HEADERS)
        headers["Referer"] = f"https://{domain}/"
        req = Request(url, headers=headers)
        with _OPENER.open(req, timeout=15) as response:
            return response.read().decode("utf-8", errors="ignore")
    except Exception as error:
        print(f"Failed fetching {url}: {error}")
        return None


def looks_like_human_verification(html: str | None) -> bool:
    """Detect an actual Cloudflare interstitial/challenge page. Cloudflare injects
    lightweight background-check scripts (an analytics beacon, a
    "challenge-platform" script tag) into ordinary, successfully-loaded pages too,
    so a loose "cloudflare" substring check flags real pages as blocked. Only the
    literal interstitial title/body text - which renders on the block/challenge
    page itself - counts as a match."""
    if not html:
        return True

    text = html.lower()
    return (
        "<title>just a moment...</title>" in text
        or "verifying you are human. this may take a few seconds" in text
        or "needs to review the security of your connection before proceeding" in text
        or "enable javascript and cookies to continue" in text
        or "please stand by, while we are checking your browser" in text
        or 'id="challenge-error-text"' in text
    )


_playwright_available: bool | None = None


def _playwright_cookie_to_http(cookie: dict) -> Cookie:
    """Convert a Playwright cookie dict into an http.cookiejar.Cookie our urllib
    session can store, so a challenge solved in the headless Brave carries over
    to plain requests for the rest of the run."""
    domain = cookie["domain"]
    expires = cookie.get("expires")
    return Cookie(
        version=0,
        name=cookie["name"],
        value=cookie["value"],
        port=None,
        port_specified=False,
        domain=domain,
        domain_specified=True,
        domain_initial_dot=domain.startswith("."),
        path=cookie.get("path", "/"),
        path_specified=True,
        secure=cookie.get("secure", False),
        expires=expires if expires and expires > 0 else None,
        discard=False,
        comment=None,
        comment_url=None,
        rest={},
    )


def fetch_html_via_brave(url: str, wait_ms: int = 7000, timeout_ms: int = 30000) -> str | None:
    """Load a page in a real (headless) Brave instance so a Cloudflare JS challenge
    resolves the same way it would when the user opens the page themselves, then
    hand the solved HTML - and any cf_clearance cookie it earns - back to the
    caller. Needs `pip install playwright`; drives the existing Brave install
    directly so no separate browser download is required. Silently unavailable
    if either is missing, so plain-request scraping keeps working without it."""
    global _playwright_available
    if _playwright_available is False or not os.path.exists(BRAVE_BINARY):
        return None

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        _playwright_available = False
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=BRAVE_BINARY, headless=True)
            try:
                context = browser.new_context(user_agent=USER_AGENT)
                page = context.new_page()
                page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                # Give Cloudflare's JS challenge time to auto-resolve and redirect.
                page.wait_for_timeout(wait_ms)
                html = page.content()
                for cookie in context.cookies():
                    try:
                        _COOKIE_JAR.set_cookie(_playwright_cookie_to_http(cookie))
                    except Exception:
                        pass
                return html
            finally:
                browser.close()
    except Exception as error:
        print(f"Brave headless fetch failed for {url}: {error}")
        return None


def resolve_steamrip_html(url: str, log_fn: LogFn | None = None) -> str | None:
    """Fetch a Steamrip page, falling back to a real headless Brave load when the
    plain request hits a Cloudflare challenge, so the JS check gets solved the
    same way a human's browser would solve it - without needing a manual click."""
    html = fetch_html(url)
    if not looks_like_human_verification(html):
        return html

    if log_fn:
        log_fn(f"⚠ Cloudflare challenge at {url} - retrying with a real Brave session...")

    html = fetch_html_via_brave(url)
    if looks_like_human_verification(html):
        return None
    return html


def extract_ps2_game_links(html: str) -> list[str]:
    """Extract PS2 game links from romsfun.com HTML"""
    links = re.findall(r'href="([^"]+/roms/playstation-2/[^"]+\.html)"', html, flags=re.IGNORECASE)
    unique_links: list[str] = []
    seen: set[str] = set()
    for link in links:
        absolute = urljoin("https://romsfun.com", link)
        if absolute not in seen:
            seen.add(absolute)
            unique_links.append(absolute)
    return unique_links


def extract_romsfun_download_landing_link(html: str) -> str | None:
    """Extract romsfun download landing link from a PS2 game page."""
    # Primary CTA on game pages: <a href=".../download/...">Download ROM</a>
    match = re.search(
        r'<a[^>]+href="([^"]+/download/[^"]+)"[^>]*>\s*Download\s+ROM\s*</a>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match:
        link = match.group(1)
        return link if link.startswith("http") else urljoin("https://romsfun.com", link)

    # Fallback: first /download/ link that is not FAQ or unrelated helper page.
    candidates = re.findall(r'href="([^"]+/download/[^"]+)"', html, flags=re.IGNORECASE)
    for link in candidates:
        lower = link.lower()
        if "download-limit-faq" in lower:
            continue
        return link if link.startswith("http") else urljoin("https://romsfun.com", link)

    return None


def extract_romsfun_best_download_page_link(html: str, game_name: str) -> str | None:
    """Pick the best romsfun download page link from a PS2 game page."""
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.IGNORECASE | re.DOTALL)
    best_link = None
    best_score = -10_000

    for row in rows:
        href_match = re.search(r'href="([^"]+/download/[^"]+/\d+)"', row, flags=re.IGNORECASE)
        if not href_match:
            continue

        link = href_match.group(1)
        title_match = re.search(r'<a[^>]*>(.*?)</a>', row, flags=re.IGNORECASE | re.DOTALL)
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, flags=re.IGNORECASE | re.DOTALL)

        title_text = re.sub(r"<[^>]+>", " ", title_match.group(1)) if title_match else ""
        type_text = re.sub(r"<[^>]+>", " ", cells[1]).strip() if len(cells) > 1 else ""
        size_text = re.sub(r"<[^>]+>", " ", cells[2]).strip() if len(cells) > 2 else ""

        # Score the downloadable variant using the existing romsfun rules.
        score = score_download_file_romsfun(f"{game_name} {title_text} {type_text} {size_text}", link)

        # Prefer an exact title match when scores are tied.
        if score > best_score:
            best_score = score
            best_link = link

    return best_link


def extract_romsfun_final_download_link(html: str) -> str | None:
    """Extract the direct download target from a romsfun download page."""
    match = re.search(r'<a[^>]+id="download-link"[^>]+href="([^"]+)"', html, flags=re.IGNORECASE)
    if match:
        link = match.group(1)
        return link if link.startswith("http") else urljoin("https://romsfun.com", link)

    matches = re.findall(r'href="(https://sto\.[^"]+)"', html, flags=re.IGNORECASE)
    if matches:
        return matches[0]

    return None


def extract_steamrip_game_links(html: str) -> list[str]:
    """Extract game links from steamrip.com search results using all-over-thumb-link pattern"""
    # More accurate: target links within all-over-thumb-link class (game result cards)
    pattern = r'<a\s+href="([^"]+)"\s+class="all-over-thumb-link"'
    links = re.findall(pattern, html, flags=re.IGNORECASE)
    
    unique_links: list[str] = []
    seen: set[str] = set()
    
    for link in links:
        # Convert relative to absolute URLs
        absolute = link if link.startswith("http") else urljoin("https://steamrip.com/", link)
        
        # Filter out unwanted pages
        absolute_lower = absolute.lower()
        if any(x in absolute_lower for x in ["/page/", "/category/", "#", "/author/", "/tag/"]):
            continue
        
        if absolute not in seen:
            seen.add(absolute)
            unique_links.append(absolute)
    
    return unique_links[:10]  # Return top 10 results


_ROMAN_NUMERAL_VALUES = {
    "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5,
    "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10,
}


def _extract_sequel_number(text: str) -> int | None:
    """Extract a standalone sequel/edition number (Arabic or Roman numeral)
    from a game title, e.g. 2 from "Spider-Man 2" or 4 from "Diablo IV".
    Used so text-similarity matching can't confuse a numbered sequel with a
    different entry in the same series just because most of the title is
    otherwise identical - "Spider-Man 2" and "Spider-Man 3" score high on
    plain fuzzy similarity but are very much not the same game."""
    for word in normalize_name(text).split():
        if word.isdigit():
            return int(word)
        if word in _ROMAN_NUMERAL_VALUES:
            return _ROMAN_NUMERAL_VALUES[word]
    return None


def pick_best_game_link(game_name: str, links: list[str], site_type: str = "romsfun") -> tuple[str | None, bool]:
    """Pick the best matching game link. Returns (link, confident).

    `confident` is False when the match shouldn't be trusted enough to open
    automatically - either the text similarity is only middling, or (more
    important) the target title has a sequel/edition number that doesn't
    match the candidate's (e.g. never let "Spider-Man 2" resolve to a
    "Spider-Man" or "Spider-Man: Miles Morales" page just because the rest of
    the title text lines up). Callers should send the user to the search
    results to pick manually rather than opening an unconfident match."""
    if not links:
        return None, False

    # Every Steamrip slug ends in boilerplate like "-free-download" - strip
    # it before scoring so it doesn't dilute the similarity ratio and make a
    # genuinely correct match look "unconfident".
    noise_words = {"free", "download"}

    def _scoring_text(text: str) -> str:
        words = [w for w in normalize_name(text).split() if w not in noise_words]
        return " ".join(words)

    target = _scoring_text(game_name)
    target_number = _extract_sequel_number(game_name)

    best_link = None
    best_score = 0.0

    for link in links:
        if site_type == "romsfun":
            slug = link.rsplit("/", 1)[-1].replace(".html", "")
        else:  # steamrip - remove trailing slash first before extracting last path component
            slug = link.rstrip("/").split("/")[-1].replace("-", " ")

        if _extract_sequel_number(slug) != target_number:
            continue

        score = SequenceMatcher(None, target, _scoring_text(slug)).ratio()
        if score > best_score:
            best_score = score
            best_link = link

    if best_link is None:
        return None, False

    # Lower threshold for steamrip since titles can be more varied
    min_threshold = 0.35 if site_type == "steamrip" else 0.45
    if best_score < min_threshold:
        return None, False

    confident_threshold = 0.6 if site_type == "steamrip" else 0.65
    return best_link, best_score >= confident_threshold


def score_download_file_romsfun(text: str, href: str) -> int:
    """Score download files for PS2 ROMs (romsfun.com)"""
    text_lower = text.lower()
    href_lower = href.lower()
    
    # Check for demo - hard exclude
    if any(word in text_lower for word in ["demo", "trial", "preview"]):
        return -10000
    
    score = 0
    
    # Format preference: Redump > CHD > others
    if "redump" in text_lower:
        score += 1000
    elif "chd" in text_lower or ".chd" in href_lower:
        score += 500
    
    # Region preference
    if any(word in text_lower for word in ["europe", "pal", "eu"]):
        score += 400
    elif any(word in text_lower for word in ["usa", "ntsc-u"]):
        score += 300
    elif "japan" in text_lower or "ntsc-j" in text_lower:
        score += 200
    elif any(word in text_lower for word in ["asia", "hong kong"]):
        score += 100
    
    return score


def open_game_search_tabs(
    game_list: list[tuple[str, str]],  # List of (game_name, site_type)
    log_fn: LogFn | None = None,
    pause_fn: PauseFn | None = None,
    result_fn: ResultFn | None = None,
    open_in_browser: bool = True,
) -> list[dict[str, str | None]]:
    """
    Resolve tabs for each game on appropriate website.
    When open_in_browser is False, the function only resolves links and returns them to the caller.
    game_list: List of tuples (game_name, "romsfun" or "steamrip")
    
    For Steamrip: collects all search URLs and opens them together at the end (no pauses).
    For Romsfun: opens each game page individually with pause for download.
    """
    if not game_list:
        return
    
    browser = get_browser()
    resolved_results: list[dict[str, str | None]] = []
    steamrip_search_urls: list[str] = []
    try:
        for idx, (game_name, site_type) in enumerate(game_list, 1):
            if log_fn:
                log_fn(f"[{idx}/{len(game_list)}] Searching {site_type}: {game_name}...")

            try:
                # Build search URL based on site type
                if site_type == "romsfun":
                    search_url = to_romsfun_search_url(game_name)
                    site_domain = "romsfun.com"
                else:  # steamrip
                    search_url = to_steamrip_search_url(game_name)
                    site_domain = "steamrip.com"

                # Steamrip: Try to resolve in-app, fall back to Brave search tab if Cloudflare blocks it
                if site_type == "steamrip":
                    resolved = False
                    search_html = resolve_steamrip_html(search_url, log_fn)

                    if search_html:
                        steamrip_links = extract_steamrip_game_links(search_html)
                        best_steamrip_link, confident = pick_best_game_link(game_name, steamrip_links, "steamrip")

                        if best_steamrip_link and confident:
                            if log_fn:
                                log_fn(f"✓ Found: {best_steamrip_link}")

                            if open_in_browser:
                                if log_fn:
                                    log_fn(f"→ Opening in Brave: {best_steamrip_link}")
                                try:
                                    browser.open(best_steamrip_link)
                                    time.sleep(0.5)
                                except Exception as e:
                                    if log_fn:
                                        log_fn(f"⚠ Failed to open in Brave: {e}")

                            result = {
                                "game_name": game_name,
                                "site_type": site_type,
                                "search_url": search_url,
                                "game_url": best_steamrip_link,
                                "selected_host_name": "Steamrip Page",
                                "selected_host_link": best_steamrip_link,
                                "romsfun_download_page_link": None,
                                "romsfun_final_link": None,
                            }
                            resolved_results.append(result)
                            if result_fn:
                                result_fn(result)
                            resolved = True
                        elif best_steamrip_link and log_fn:
                            log_fn(
                                f"⚠ Match for '{game_name}' isn't confident enough "
                                f"(closest: {best_steamrip_link}) - opening search results to pick manually."
                            )

                    if not resolved:
                        steamrip_search_urls.append(search_url)
                        if log_fn:
                            log_fn(f"ℹ Steamrip: opening search results for '{game_name}' - pick manually.")

                        result = {
                            "game_name": game_name,
                            "site_type": site_type,
                            "search_url": search_url,
                            "game_url": None,
                            "selected_host_name": "Steamrip Search (Manual)",
                            "selected_host_link": search_url,
                            "romsfun_download_page_link": None,
                            "romsfun_final_link": None,
                        }
                        resolved_results.append(result)
                        if result_fn:
                            result_fn(result)
                    continue

                # Romsfun: full fetch and resolve in-app
                if log_fn:
                    log_fn(f"→ Resolving: {search_url}")

                # Fetch search results
                html = fetch_html(search_url)
                if not html:
                    if log_fn:
                        log_fn(f"✗ Failed to fetch search results for {game_name}")
                    continue

                # Extract links
                links = extract_ps2_game_links(html)
                if not links:
                    if log_fn:
                        log_fn(f"✗ No results found for {game_name} on romsfun.com")
                    continue

                # Find best matching link
                best_link, _confident = pick_best_game_link(game_name, links, site_type)
                if not best_link:
                    if log_fn:
                        log_fn(f"⚠ No close match found for {game_name}")
                    continue

                if log_fn:
                    log_fn(f"✓ Found: {best_link}")

                # Fetch game page
                game_page_html = fetch_html(best_link)
                romsfun_download_page_link = None
                
                if game_page_html:
                    landing_link = extract_romsfun_download_landing_link(game_page_html)
                    
                    if landing_link:
                        landing_html = fetch_html(landing_link)
                        if landing_html:
                            romsfun_download_page_link = extract_romsfun_best_download_page_link(landing_html, game_name)
                            if not romsfun_download_page_link:
                                romsfun_download_page_link = landing_link
                        else:
                            romsfun_download_page_link = landing_link

                if romsfun_download_page_link:
                    if log_fn:
                        log_fn(f"→ Resolved romsfun download page: {romsfun_download_page_link}")
                    
                    # Open in Brave immediately
                    if open_in_browser:
                        if log_fn:
                            log_fn(f"→ Opening in Brave: {romsfun_download_page_link}")
                        try:
                            browser.open(romsfun_download_page_link)
                            time.sleep(0.5)
                        except Exception as e:
                            if log_fn:
                                log_fn(f"⚠ Failed to open in Brave: {e}")
                    
                    result = {
                        "game_name": game_name,
                        "site_type": site_type,
                        "search_url": search_url,
                        "game_url": best_link,
                        "selected_host_name": "Romsfun Download",
                        "selected_host_link": romsfun_download_page_link,
                        "romsfun_download_page_link": romsfun_download_page_link,
                        "romsfun_final_link": None,
                        "buzzheavier_link": None,
                        "gofile_link": None,
                    }
                    resolved_results.append(result)
                    if result_fn:
                        result_fn(result)
                else:
                    if log_fn:
                        log_fn("⚠ Failed to resolve romsfun download page")

            except Exception as e:
                if log_fn:
                    log_fn(f"✗ Error processing {game_name}: {str(e)}")
                continue

            time.sleep(1)

        if log_fn:
            log_fn("All games processed!")

        # Open all Steamrip search tabs in a new Brave window
        if open_in_browser and steamrip_search_urls:
            if log_fn:
                log_fn(f"ℹ Opening {len(steamrip_search_urls)} Steamrip search tabs in a new Brave window...")
            try:
                import subprocess
                if os.path.exists(BRAVE_BINARY):
                    subprocess.Popen([BRAVE_BINARY, "--new-window"] + steamrip_search_urls)
                else:
                    for url in steamrip_search_urls:
                        browser.open(url)
                        time.sleep(0.5)
            except Exception as e:
                if log_fn:
                    log_fn(f"⚠ Failed to open Brave: {e}")

        return resolved_results
    finally:
        pass
