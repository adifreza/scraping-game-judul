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


def sanitize_title_for_search(text: str) -> str:
    """Remove dashes and apostrophes for cleaner search"""
    sanitized = text
    for dash in ("-", "–", "—"):
        sanitized = sanitized.replace(dash, " ")
    for apostrophe in ("'", "'"):
        sanitized = sanitized.replace(apostrophe, "")
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


def to_romsfun_search_url(game_name: str) -> str:
    """Build romsfun.com search URL for PS2 games"""
    clean_name = re.sub(r"\bps2\b", "", game_name, flags=re.IGNORECASE)
    clean_name = sanitize_title_for_search(clean_name)
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


def extract_steamrip_game_links(html: str) -> list[str]:
    """Extract game links from steamrip.com HTML"""
    # Look for post links and game titles on steamrip
    links = re.findall(r'href="([^"]*steamrip\.com[^"]*)"', html, flags=re.IGNORECASE)
    unique_links: list[str] = []
    seen: set[str] = set()
    for link in links:
        if "/page/" not in link and "/category/" not in link and "#" not in link:
            absolute = link if link.startswith("http") else urljoin("https://steamrip.com", link)
            if absolute not in seen and "steamrip.com" in absolute:
                seen.add(absolute)
                unique_links.append(absolute)
    return unique_links[:10]  # Return top 10 results


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
        else:  # steamrip
            slug = link.split("/")[-1].replace("-", " ")
        
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
) -> None:
    """
    Open tabs for each game on appropriate website
    game_list: List of tuples (game_name, "romsfun" or "steamrip")
    """
    if not game_list:
        return
    
    browser = get_browser()
    
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
            
            if log_fn:
                log_fn(f"→ Opening: {search_url}")
            
            # Open search page
            browser.open(search_url)
            time.sleep(2)
            
            # Fetch search results
            html = fetch_html(search_url)
            if not html:
                if log_fn:
                    log_fn(f"✗ Failed to fetch search results for {game_name}")
                continue
            
            # Extract links based on site type
            if site_type == "romsfun":
                links = extract_ps2_game_links(html)
            else:  # steamrip
                links = extract_steamrip_game_links(html)
            
            if not links:
                if log_fn:
                    log_fn(f"✗ No results found for {game_name} on {site_domain}")
                continue
            
            # Find best matching link
            best_link = pick_best_game_link(game_name, links, site_type)
            
            if best_link:
                if log_fn:
                    log_fn(f"✓ Found: {best_link}")
                
                # Open the game page
                browser.open(best_link)
                time.sleep(1)
                
                # Wait for user to manually click download
                if pause_fn:
                    pause_fn(f"Click 'Download' for: {game_name}")
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
