"""Collect a dated, raw public snapshot from the openFDA Drug Shortages API."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import requests


ENDPOINT = "https://api.fda.gov/drug/shortages.json"
PAGE_SIZE = 100
HTTP_SESSION = requests.Session()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def fetch_page(url: str, retries: int = 4, timeout_seconds: int = 45) -> tuple[dict[str, Any], dict[str, str], bytes]:
    error: Exception | None = None
    for attempt in range(retries):
        try:
            response = HTTP_SESSION.get(
                url,
                headers={"Accept": "application/json", "User-Agent": "PharmGraphRAG-research-snapshot/1.0"},
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            body = response.content
            headers = {key.lower(): value for key, value in response.headers.items()}
            return json.loads(body.decode("utf-8")), headers, body
        except (requests.RequestException, TimeoutError, json.JSONDecodeError) as exc:
            error = exc
            if attempt + 1 < retries:
                time.sleep(2**attempt)
    raise RuntimeError(f"openFDA request failed after {retries} attempts: {url}") from error


def collect_snapshot(
    output: Path,
    fetcher: Callable[[str], tuple[dict[str, Any], dict[str, str], bytes]] = fetch_page,
    page_size: int = PAGE_SIZE,
) -> dict[str, Any]:
    if output.exists():
        raise RuntimeError(f"refusing to overwrite existing FDA snapshot: {output}")
    if page_size < 1 or page_size > 100:
        raise ValueError("page_size must be between 1 and 100")

    output.mkdir(parents=True)
    raw_pages = output / "raw_pages"
    raw_pages.mkdir()
    try:
        probe_url = f"{ENDPOINT}?limit=1"
        probe, _headers, _body = fetcher(probe_url)
        total = int((probe.get("meta") or {}).get("results", {}).get("total", 0))
        if total < 1:
            raise RuntimeError("openFDA reported no drug-shortage records")
        pages: list[dict[str, Any]] = []
        for index, skip in enumerate(range(0, total, page_size)):
            url = f"{ENDPOINT}?limit={page_size}&skip={skip}"
            payload, headers, body = fetcher(url)
            rows = payload.get("results") or []
            page_name = f"page_{index:03d}.json"
            (raw_pages / page_name).write_bytes(body)
            pages.append({
                "page_index": index,
                "skip": skip,
                "url": url,
                "file": f"raw_pages/{page_name}",
                "record_count": len(rows),
                "sha256": sha256_bytes(body),
                "etag": headers.get("etag", ""),
                "last_modified": headers.get("last-modified", ""),
            })
        manifest = {
            "snapshot_type": "openfda_drug_shortages",
            "endpoint": ENDPOINT,
            "collected_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "page_size": page_size,
            "api_total_records": total,
            "pages": pages,
            "downloaded_record_count": sum(page["record_count"] for page in pages),
            "canonical_artifacts_replaced": False,
        }
        (output / "collection_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest
    except Exception:
        # The partial snapshot is intentionally preserved for debugging and no
        # successful manifest is emitted, so it cannot be mistaken for a run.
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect a raw openFDA drug-shortage snapshot")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    manifest = collect_snapshot(Path(args.output))
    print(json.dumps({
        "api_total_records": manifest["api_total_records"],
        "downloaded_record_count": manifest["downloaded_record_count"],
        "page_count": len(manifest["pages"]),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
