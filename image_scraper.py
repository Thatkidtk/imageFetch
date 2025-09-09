#!/usr/bin/env python3
import concurrent.futures
import hashlib
import json
import os
import re
import sys
import threading
import time
import platform
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Iterable, Set, Tuple, Dict, List

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urldefrag
import shutil
from requests import exceptions as req_exc
import argparse


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

HEADERS = {"User-Agent": USER_AGENT}
REQUEST_TIMEOUT = 15

IMG_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".avif", ".tiff", ".tif"}


def is_probable_image_url(url: str) -> bool:
    lower = url.lower().split("?", 1)[0].split("#", 1)[0]
    return any(lower.endswith(ext) for ext in IMG_EXTENSIONS)


def absolute_url(href: str, base_url: str) -> str:
    if not href:
        return ""
    return urljoin(base_url, href)


def same_site(url: str, origin: str) -> bool:
    try:
        u, o = urlparse(url), urlparse(origin)
        return (u.scheme in {"http", "https"}) and (u.netloc == o.netloc)
    except Exception:
        return False


def extract_image_urls_from_html(html: str, base_url: str) -> Tuple[Set[str], Set[str]]:
    """
    Returns (image_urls, css_urls)
    """
    soup = BeautifulSoup(html, "html.parser")
    images: Set[str] = set()
    css_links: Set[str] = set()

    # <img src> and srcset
    for img in soup.find_all("img"):
        src = img.get("src")
        if src:
            images.add(absolute_url(src, base_url))
        srcset = img.get("srcset")
        if srcset:
            for item in srcset.split(","):
                url_part = item.strip().split(" ", 1)[0]
                if url_part:
                    images.add(absolute_url(url_part, base_url))

    # <source srcset> inside <picture>
    for source in soup.find_all("source"):
        srcset = source.get("srcset")
        if srcset:
            for item in srcset.split(","):
                url_part = item.strip().split(" ", 1)[0]
                if url_part:
                    images.add(absolute_url(url_part, base_url))

    # Meta images (OG/Twitter)
    for meta in soup.find_all("meta"):
        prop = (meta.get("property") or meta.get("name") or "").lower()
        if prop in {"og:image", "og:image:url", "twitter:image", "twitter:image:src"}:
            content = meta.get("content")
            if content:
                images.add(absolute_url(content, base_url))

    # Preloaded images
    for link in soup.find_all("link"):
        rel = (" ".join(link.get("rel", []))).lower()
        as_type = (link.get("as") or "").lower()
        href = link.get("href")
        if href and ("preload" in rel and as_type == "image"):
            images.add(absolute_url(href, base_url))

    # Inline style attributes with url(...)
    url_pattern = re.compile(r"url\(\s*['\"]?([^'\"\)]+)['\"]?\s*\)")
    for el in soup.find_all(style=True):
        style = el.get("style") or ""
        for match in url_pattern.findall(style):
            images.add(absolute_url(match, base_url))

    # <style> blocks: capture url(...) for potential images
    for style_tag in soup.find_all("style"):
        css_text = style_tag.get_text("\n")
        for match in url_pattern.findall(css_text):
            images.add(absolute_url(match, base_url))

    # Linked CSS files to parse later
    for link in soup.find_all("link", rel=True, href=True):
        rel_vals = {r.lower() for r in link.get("rel", [])}
        if "stylesheet" in rel_vals:
            css_links.add(absolute_url(link["href"], base_url))

    return images, css_links


def extract_image_urls_from_css(css_text: str, base_url: str) -> Set[str]:
    images: Set[str] = set()
    # Match url(...) while ignoring data URIs unless image
    for match in re.findall(r"url\(\s*(['\"]?)([^'\"\)]+)\1\s*\)", css_text):
        url_candidate = match[1]
        if url_candidate.startswith("data:"):
            # Only save if data URL is an image
            if url_candidate.startswith("data:image/"):
                images.add(url_candidate)
            continue
        images.add(absolute_url(url_candidate, base_url))
    return images


def safe_filename_from_url(url: str, content_type: str | None) -> str:
    parsed = urlparse(url)
    name = os.path.basename(parsed.path)
    name = name.split("?")[0]

    # Fallback to hash if no basename
    if not name or name in {"/", ".", ".."}:
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
        name = f"image_{digest}"

    root, ext = os.path.splitext(name)
    if (not ext or ext.lower() not in IMG_EXTENSIONS) and content_type:
        if content_type.startswith("image/"):
            guessed_ext = "." + content_type.split("/", 1)[1].split(";", 1)[0].strip()
            # Normalize some content types
            mapping = {"jpeg": ".jpg", "svg+xml": ".svg"}
            guessed_ext = mapping.get(guessed_ext, "." + guessed_ext if not guessed_ext.startswith(".") else guessed_ext)
            if guessed_ext:
                ext = guessed_ext if guessed_ext.startswith(".") else "." + guessed_ext

    if not ext:
        ext = ".jpg"
    # Ensure clean characters
    clean_root = re.sub(r"[^A-Za-z0-9._-]", "_", root)
    return clean_root[:120] + ext


def fetch_text(url: str) -> str | None:
    # Retry a few times for transient network issues
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if 200 <= r.status_code < 300:
                r.encoding = r.apparent_encoding or r.encoding
                return r.text
            # Non-2xx; do not retry for 4xx except 408/429
            if r.status_code in {408, 429, 500, 502, 503, 504}:
                time.sleep(0.5 * (2 ** attempt))
                continue
            return None
        except (req_exc.Timeout, req_exc.ConnectionError):
            time.sleep(0.5 * (2 ** attempt))
        except Exception:
            return None
    return None


def fetch_bytes(url: str) -> Tuple[bytes | None, str | None]:
    for attempt in range(3):
        try:
            with requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, stream=True) as r:
                if 200 <= r.status_code < 300:
                    content_type = r.headers.get("Content-Type")
                    content = r.content
                    return content, content_type
                if r.status_code in {408, 429, 500, 502, 503, 504}:
                    time.sleep(0.5 * (2 ** attempt))
                    continue
                return None, None
        except (req_exc.Timeout, req_exc.ConnectionError):
            time.sleep(0.5 * (2 ** attempt))
        except Exception:
            return None, None
    return None, None


def collect_images_from_page(url: str) -> Tuple[Set[str], Set[str]]:
    html = fetch_text(url)
    if not html:
        return set(), set()
    img_urls, css_urls = extract_image_urls_from_html(html, url)

    # Parse CSS files to find images
    for css_url in list(css_urls):
        css_text = fetch_text(css_url)
        if css_text:
            css_imgs = extract_image_urls_from_css(css_text, css_url)
            img_urls.update(css_imgs)

    # Filter by probable images or data:image
    resolved: Set[str] = set()
    for u in img_urls:
        if u.startswith("data:image/") or is_probable_image_url(u):
            resolved.add(u)
        else:
            # Keep it, we will validate via content-type when downloading
            resolved.add(u)
    return resolved, css_urls


def crawl_site(start_url: str, max_pages: int = 20) -> List[str]:
    start = urldefrag(start_url)[0]
    origin = start

    queue: List[str] = [start]
    seen: Set[str] = set()
    pages: List[str] = []

    while queue and len(pages) < max_pages:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        pages.append(url)
        html = fetch_text(url)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = absolute_url(a["href"], url)
            href, _ = urldefrag(href)
            if same_site(href, origin) and href not in seen:
                queue.append(href)
    return pages


def download_one(url: str, out_dir: Path) -> Tuple[str, str | None]:
    data, content_type = fetch_bytes(url)
    if not data:
        return url, None
    if not (is_probable_image_url(url) or (content_type and content_type.startswith("image/"))):
        return url, None
    name = safe_filename_from_url(url, content_type)
    path = out_dir / name
    # Ensure uniqueness
    counter = 1
    while path.exists():
        stem, ext = os.path.splitext(name)
        path = out_dir / f"{stem}_{counter}{ext}"
        counter += 1
    try:
        path.write_bytes(data)
    except OSError:
        # Fallback to a hashed filename if something about the name/path fails
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
        fallback = out_dir / f"image_{digest}.bin"
        try:
            fallback.write_bytes(data)
            return url, str(fallback)
        except Exception:
            return url, None
    return url, str(path)


def download_all(urls: Iterable[str], out_dir: Path, max_workers: int = 8, progress_cb=None) -> Tuple[List[Tuple[str, str]], List[str]]:
    successes: List[Tuple[str, str]] = []
    failures: List[str] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    urls_list = list(urls)
    total = len(urls_list)
    completed = 0

    if progress_cb:
        try:
            progress_cb(total, completed)
        except Exception:
            pass

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(download_one, url, out_dir) for url in urls_list]
        for fut in concurrent.futures.as_completed(futures):
            try:
                url, saved_path = fut.result()
                with lock:
                    if saved_path:
                        successes.append((url, saved_path))
                    else:
                        failures.append(f"{url} — download failed")
            except Exception as e:
                with lock:
                    failures.append(f"<exception> {e}")
            finally:
                completed += 1
                if progress_cb:
                    try:
                        progress_cb(total, completed)
                    except Exception:
                        pass
    return successes, failures


def zip_output_folder(out_dir: Path) -> Path:
    base = out_dir.resolve()
    zip_base = base.parent / base.name
    # shutil.make_archive returns the filename including extension
    zip_path = shutil.make_archive(str(zip_base), "zip", root_dir=str(base))
    return Path(zip_path)


def _open_path_cross_platform(path: Path) -> bool:
    try:
        if platform.system() == "Windows":
            os.startfile(path)  # type: ignore[attr-defined]
            return True
        elif platform.system() == "Darwin":
            opener = shutil.which("open")
            if opener:
                subprocess.run([opener, str(path)], check=False)
                return True
            return False
        else:
            opener = shutil.which("xdg-open")
            if opener:
                subprocess.run([opener, str(path)], check=False)
                return True
            return False
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description="Save all images from a page or site")
    parser.add_argument("--open-output", "-O", action="store_true", help="Open the output folder when done")
    args, _unknown = parser.parse_known_args()

    print("Image Scraper - Save all images from a page or site")
    url = input("Enter a URL: ").strip()
    if not url:
        print("No URL provided. Exiting.")
        sys.exit(1)
    if not urlparse(url).scheme:
        url = "https://" + url
    parsed = urlparse(url)
    if not parsed.netloc:
        print("Invalid URL. Please include a valid domain.")
        sys.exit(1)

    default_dir_name = f"images_{urlparse(url).netloc}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    out_dir_input = input(f"Output folder [{default_dir_name}]: ").strip()
    out_dir = Path(out_dir_input or default_dir_name)

    recursive_ans = input("Crawl same-site links? [y/N]: ").strip().lower()
    do_recursive = recursive_ans.startswith("y")
    pages: List[str]
    if do_recursive:
        max_pages_str = input("Max pages to crawl [20]: ").strip()
        max_pages = 20
        if max_pages_str:
            try:
                max_pages = max(1, int(max_pages_str))
            except ValueError:
                pass
        print(f"Crawling up to {max_pages} pages on {urlparse(url).netloc}...")
        pages = crawl_site(url, max_pages=max_pages)
    else:
        pages = [url]

    print(f"Scanning {len(pages)} page(s) for images...")
    all_images: Set[str] = set()
    all_css: Set[str] = set()
    for p in pages:
        imgs, css = collect_images_from_page(p)
        all_images.update(imgs)
        all_css.update(css)

    # Remove data URLs from download set; optionally save them later
    data_images = {u for u in all_images if u.startswith("data:image/")}
    http_images = [u for u in all_images if not u.startswith("data:")]

    print(f"Found {len(all_images)} images ({len(http_images)} downloadable, {len(data_images)} data URLs).")
    print(f"Downloading to {out_dir.resolve()} ...")

    def cli_progress(total, completed):
        # Simple CLI progress output
        print(f"Progress: {completed}/{total}", end="\r", flush=True)

    successes, failures = download_all(http_images, out_dir, progress_cb=cli_progress)

    manifest = {
        "source_pages": pages,
        "downloaded": [{"url": u, "path": p} for (u, p) in successes],
        "failed": failures,
        "data_urls": list(data_images)[:50],  # limit manifest size
        "css_files": list(all_css),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    try:
        (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"Failed to write manifest.json: {e}")

    summary = (
        f"Downloaded {len(successes)} images. "
        f"Failed {len(failures)}. "
        f"Saved manifest.json in output folder."
    )
    print(summary)

    try:
        zip_path = zip_output_folder(out_dir)
        print(f"\nCreated ZIP archive: {zip_path}")
    except Exception as e:
        print(f"\nFailed to create ZIP: {e}")

    print("Done.")

    if args.open_output:
        # Warn if opener missing on non-Windows
        if platform.system() == "Darwin" and not shutil.which("open"):
            print(f"Note: 'open' command not found; cannot auto-open. Folder: {out_dir}")
        elif platform.system() not in ("Windows", "Darwin") and not shutil.which("xdg-open"):
            print(f"Note: 'xdg-open' not found; cannot auto-open. Folder: {out_dir}")
        else:
            ok = _open_path_cross_platform(out_dir)
            if not ok:
                print(f"Could not open folder automatically: {out_dir}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)
