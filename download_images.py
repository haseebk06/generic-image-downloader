#!/usr/bin/env python3
"""
Generic image downloader for JSON API responses.

Works on ANY JSON structure (list of objects, nested objects, etc.) - it
recursively walks the JSON and downloads every string value that looks like
an image path (ends with .png/.jpg/.jpeg/.webp/.svg/.bmp), regardless of
the field name (gift_image, avatar, thumbnail, whatever). .gif and .json
are intentionally excluded.

Run with no arguments and it will interactively ask for the API URL,
base/CDN URL, and auth token (press Enter to accept the shown default,
the token has no default and is entered hidden). Or pass everything as
flags for non-interactive / scripted use:

    python download_images.py --api-url ... --base-url ... --token ...
"""

import argparse
import getpass
import json
import os
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

# Shown as defaults in the prompts below - press Enter to accept, or type your own.
DEFAULT_API_URL = "https://api.dreamlived.com/admin/giftlisting/getGiftListing/undefined/undefined"
DEFAULT_BASE_URL = "https://dreamapp.b-cdn.net/"

IMAGE_EXT_RE = re.compile(r"\.(png|jpe?g|webp|svg|bmp)$", re.IGNORECASE)


def fetch_json(api_url, extra_headers=None):
    headers = {"User-Agent": "Mozilla/5.0"}
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(api_url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_headers(header_args):
    headers = {}
    for h in header_args or []:
        if ":" not in h:
            print(f"Ignoring malformed header (expected 'Name: value'): {h}", file=sys.stderr)
            continue
        name, value = h.split(":", 1)
        headers[name.strip()] = value.strip()
    return headers


def find_image_paths(obj, found=None):
    """Recursively walk any JSON structure and collect strings that look like image paths."""
    if found is None:
        found = set()

    if isinstance(obj, dict):
        for v in obj.values():
            find_image_paths(v, found)
    elif isinstance(obj, list):
        for item in obj:
            find_image_paths(item, found)
    elif isinstance(obj, str):
        if IMAGE_EXT_RE.search(obj):
            found.add(obj)

    return found


def download_one(rel_path, base_url, out_dir):
    full_url = urljoin(base_url, rel_path.lstrip("/"))
    dest_path = os.path.join(out_dir, rel_path.replace("\\", "/"))
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    if os.path.exists(dest_path):
        return rel_path, "skipped (already exists)"

    try:
        req = urllib.request.Request(full_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp, open(dest_path, "wb") as f:
            f.write(resp.read())
        return rel_path, "ok"
    except Exception as e:
        return rel_path, f"FAILED: {e}"


def main():
    parser = argparse.ArgumentParser(description="Download all images referenced in a JSON API response.")
    parser.add_argument("--api-url", help="URL to fetch JSON from")
    parser.add_argument("--input-file", help="Path to a local JSON file (skips API prompts entirely)")
    parser.add_argument("--base-url", help="CDN/base URL to prepend to relative image paths")
    parser.add_argument("--out-dir", default="img", help="Output directory (default: img)")
    parser.add_argument("--workers", type=int, default=8, help="Parallel download workers (default: 8)")
    parser.add_argument("--dry-run", action="store_true", help="List found images without downloading")
    parser.add_argument("--token", help="Bearer token for Authorization header")
    parser.add_argument("--header", action="append", help="Extra HTTP header 'Name: value', repeatable")
    args = parser.parse_args()

    if not args.base_url:
        typed = input(f"Base/CDN URL [{DEFAULT_BASE_URL}]: ").strip()
        args.base_url = typed if typed else DEFAULT_BASE_URL

    if args.input_file:
        with open(args.input_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        api_url = args.api_url
        if not api_url:
            typed = input(f"API URL [{DEFAULT_API_URL}]: ").strip()
            api_url = typed if typed else DEFAULT_API_URL

        token = args.token
        if not token:
            token = getpass.getpass("Auth token (Bearer, input hidden): ").strip()

        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        headers.update(parse_headers(args.header))

        print(f"Fetching JSON from {api_url} ...")
        data = fetch_json(api_url, headers)

    image_paths = sorted(find_image_paths(data))
    print(f"Found {len(image_paths)} image reference(s).")

    if args.dry_run:
        for p in image_paths:
            print(" -", p)
        return

    if not image_paths:
        print("Nothing to download.")
        return

    os.makedirs(args.out_dir, exist_ok=True)

    ok, skipped, failed = 0, 0, 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(download_one, p, args.base_url, args.out_dir): p for p in image_paths}
        for future in as_completed(futures):
            rel_path, status = future.result()
            print(f"[{status}] {rel_path}")
            if status == "ok":
                ok += 1
            elif status.startswith("skipped"):
                skipped += 1
            else:
                failed += 1

    print(f"\nDone. Downloaded: {ok}, skipped: {skipped}, failed: {failed}")
    print(f"Images saved under: {os.path.abspath(args.out_dir)}")


if __name__ == "__main__":
    main()
