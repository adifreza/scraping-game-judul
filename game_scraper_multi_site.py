import time
import webbrowser
import re
import os
from difflib import SequenceMatcher
from typing import Callable
from urllib.parse import quote_plus, urljoin
from urllib.request import Request, urlopen


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

BRAVE_BINARY = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
IDM_EXTENSION_HINT = "Make sure IDM Integration Module is enabled in Brave."

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
    """Fetch HTML from URL"""
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=15) as response:
            return response.read().decode("utf-8", errors="ignore")
    except Exception as error:
        print(f"Failed fetching {url}: {error}")
        return None


def looks_like_human_verification(html: str | None) -> bool:
    """Detect common Steamrip human-verification or anti-bot pages."""
    if not html:
        return True

    text = html.lower()
    return any(
        phrase in text
        for phrase in (
            "just a moment",
            "verify you are human",
            "checking your browser",
            "attention required",
            "cloudflare",
            "human verification",
        )
    )


def fetch_steamrip_html_with_verification(
    url: str,
    game_name: str,
    stage: str,
    browser: webbrowser.BaseBrowser | None,
    log_fn: LogFn | None = None,
    pause_fn: PauseFn | None = None,
) -> str | None:
    """Fetch Steamrip HTML and pause in Brave if a human-verification page appears."""

    html = fetch_html(url)
    if not looks_like_human_verification(html):
        return html

    if log_fn:
        log_fn(f"⚠ Steamrip human verification detected at {stage}: {url}")

    try:
        browser.open(url)
    except Exception:
        pass

    if pause_fn:
        pause_fn(
            f"Steamrip human verification for {game_name} ({stage}).\n\n"
            f"Complete the check in Brave, then click OK to continue.\n"
            f"If the page still shows verification after OK, Steamrip is blocking automation and the item will be skipped."
        )

    html = fetch_html(url)
    if looks_like_human_verification(html):
        if log_fn:
            log_fn(f"⚠ Steamrip still blocked after manual verification at {stage}; skipping {game_name}")
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


def extract_steamrip_priority_host_links(html: str) -> tuple[str | None, str | None]:
    """
    Extract Steamrip download links from game page with priority: Buzzheavier first, then Gofile.
    
    HTML Structure on game page:
    <p>
      <strong>Buzzheavier</strong><br>
      <a href="//bzzhr.to/..." class="shortc-button medium purple">DOWNLOAD HERE</a>
    </p>
    
    <p>
      <span style="color: #ff9900;"><strong>GOFILE</strong></span><br>
      <a href="//www.filecrypt.cc/..." class="shortc-button medium purple">DOWNLOAD HERE</a>
    </p>
    
    Returns: (buzzheavier_link, gofile_link)
    """
    buzzheavier_link = None
    gofile_link = None

    def _normalize_protocol_relative(link: str) -> str:
        return link if link.startswith("http") else "https:" + link
    
    # Pattern 1: Find Buzzheavier link first, even if the label is wrapped or spaced differently.
    # Steamrip sometimes renders this as plain <strong>Buzzheavier</strong> and sometimes with extra markup around it.
    buzzheavier_pattern = r'Buzzheavier.*?<a\s+href="([^"]+)"'
    buzzheavier_matches = re.findall(buzzheavier_pattern, html, re.IGNORECASE | re.DOTALL)
    if buzzheavier_matches:
        link = buzzheavier_matches[0]
        buzzheavier_link = _normalize_protocol_relative(link)
    
    # Pattern 2: Find Gofile link (may be wrapped in <span>, look for "GOFILE" followed by href)
    # Handles both: <strong>GOFILE</strong> and <span>...<strong>GOFILE</strong></span>
    gofile_pattern = r'<strong>(?:GOFILE|GoFile|Gofile)</strong>.*?<a\s+href="([^"]+)"'
    gofile_matches = re.findall(gofile_pattern, html, re.IGNORECASE | re.DOTALL)
    if gofile_matches:
        link = gofile_matches[0]
        gofile_link = _normalize_protocol_relative(link)
    
    return (buzzheavier_link, gofile_link)


def pick_best_game_link(game_name: str, links: list[str], site_type: str = "romsfun") -> str | None:
    """Pick best matching game link"""
    if not links:
        return None

    target = normalize_name(game_name)
    best_link = None
    best_score = 0.0

    for link in links:
        if site_type == "romsfun":
            slug = link.rsplit("/", 1)[-1].replace(".html", "")
        else:  # steamrip - remove trailing slash first before extracting last path component
            slug = link.rstrip("/").split("/")[-1].replace("-", " ")
        
        score = SequenceMatcher(None, target, normalize_name(slug)).ratio()
        if score > best_score:
            best_score = score
            best_link = link

    # Lower threshold for steamrip since titles can be more varied
    min_threshold = 0.35 if site_type == "steamrip" else 0.45
    if best_score < min_threshold:
        return None
    return best_link


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


def score_download_file_steamrip(text: str, href: str) -> int:
    """Score download files for PC/console games (steamrip.com)"""
    text_lower = text.lower()
    
    # Check for unwanted variants
    if any(word in text_lower for word in ["demo", "trial", "preview", "test"]):
        return -10000
    
    score = 100  # Base score for valid files
    
    # Prefer non-Japanese language releases
    if "japanese" in text_lower or "jap" in text_lower:
        score -= 50
    
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
                    search_html = fetch_html(search_url)
                    
                    if search_html and not looks_like_human_verification(search_html):
                        steamrip_links = extract_steamrip_game_links(search_html)
                        best_steamrip_link = pick_best_game_link(game_name, steamrip_links, "steamrip")
                        
                        if best_steamrip_link:
                            game_page_html = fetch_html(best_steamrip_link)
                            if game_page_html and not looks_like_human_verification(game_page_html):
                                buzz_link, go_link = extract_steamrip_priority_host_links(game_page_html)
                                
                                # Select priority host
                                selected_host_link = buzz_link if buzz_link else go_link
                                selected_host_name = "Buzzheavier" if buzz_link else ("Gofile" if go_link else None)
                                
                                if selected_host_link:
                                    if log_fn:
                                        log_fn(f"✓ Resolved Steamrip host: {selected_host_name} -> {selected_host_link}")
                                    
                                    result = {
                                        "game_name": game_name,
                                        "site_type": site_type,
                                        "search_url": search_url,
                                        "game_url": best_steamrip_link,
                                        "selected_host_name": selected_host_name,
                                        "selected_host_link": selected_host_link,
                                        "romsfun_download_page_link": None,
                                        "romsfun_final_link": None,
                                        "buzzheavier_link": buzz_link,
                                        "gofile_link": go_link,
                                    }
                                    resolved_results.append(result)
                                    if result_fn:
                                        result_fn(result)
                                    resolved = True
                    
                    if not resolved:
                        steamrip_search_urls.append(search_url)
                        if log_fn:
                            log_fn(f"ℹ Steamrip queued (Cloudflare active or no match): {search_url}")
                        
                        result = {
                            "game_name": game_name,
                            "site_type": site_type,
                            "search_url": search_url,
                            "game_url": None,
                            "selected_host_name": "Steamrip Search",
                            "selected_host_link": search_url,
                            "romsfun_download_page_link": None,
                            "romsfun_final_link": None,
                            "buzzheavier_link": None,
                            "gofile_link": None,
                        }
                        resolved_results.append(result)
                        if result_fn:
                            result_fn(result)
                    continue

                if log_fn:
                    if open_in_browser:
                        log_fn(f"→ Opening: {search_url}")
                    else:
                        log_fn(f"→ Resolving: {search_url}")

                # Fetch search results (romsfun only)
                html = fetch_html(search_url)

                if not html:
                    if log_fn:
                        log_fn(f"✗ Failed to fetch search results for {game_name}")
                    continue

                # Extract links (romsfun only)
                links = extract_ps2_game_links(html)

                if not links:
                    if log_fn:
                        log_fn(f"✗ No results found for {game_name} on {site_domain}")
                    continue

                # Find best matching link
                best_link = pick_best_game_link(game_name, links, site_type)

                if best_link:
                    if log_fn:
                        log_fn(f"✓ Found: {best_link}")

                    selected_host = None
                    host_name = None
                    buzzheavier_link = None
                    gofile_link = None
                    romsfun_download_page_link = None
                    romsfun_final_link = None

                    # Romsfun only at this point (Steamrip already skipped above with continue)
                    game_page_html = fetch_html(best_link)
                    if game_page_html:
                        landing_link = extract_romsfun_download_landing_link(game_page_html)

                        if not landing_link:
                            if log_fn:
                                log_fn("⚠ No romsfun download landing link found on PS2 game page")
                        else:
                            landing_html = fetch_html(landing_link)
                            if landing_html:
                                romsfun_download_page_link = extract_romsfun_best_download_page_link(landing_html, game_name)
                                # If table parsing fails, still keep landing page as a fallback.
                                if not romsfun_download_page_link:
                                    romsfun_download_page_link = landing_link
                            else:
                                romsfun_download_page_link = landing_link

                        if romsfun_download_page_link:
                            selected_host = romsfun_download_page_link
                            host_name = "romsfun download"
                            if log_fn:
                                log_fn(f"→ Resolved romsfun download page: {selected_host}")
                        elif log_fn:
                            log_fn("⚠ No romsfun download page link could be resolved")
                    elif log_fn:
                        log_fn("⚠ Failed to fetch romsfun game page for download page extraction")

                    result = {
                        "game_name": game_name,
                        "site_type": site_type,
                        "search_url": search_url,
                        "game_url": best_link if site_type == "romsfun" else None,
                        "selected_host_name": host_name,
                        "selected_host_link": selected_host,
                        "romsfun_download_page_link": romsfun_download_page_link if site_type == "romsfun" else None,
                        "romsfun_final_link": None,
                        "buzzheavier_link": None,
                        "gofile_link": None,
                    }
                    resolved_results.append(result)
                    if result_fn:
                        result_fn(result)
                else:
                    if log_fn:
                        log_fn(f"⚠ No close match found for {game_name}")

            except Exception as e:
                if log_fn:
                    log_fn(f"✗ Error processing {game_name}: {str(e)}")
                continue

            time.sleep(1)

        if log_fn:
            log_fn("All games processed!")

        # Open all Steamrip search tabs together in a new Brave window
        if steamrip_search_urls:
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
