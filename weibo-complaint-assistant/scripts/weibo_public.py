#!/usr/bin/env python3
"""Read public Weibo post data without API keys, cookies, or user login.

This helper is deliberately best-effort. Platform blocking, deleted posts, and
field-level omissions are returned as structured status values instead of
raising fatal errors, so complaint drafting can continue from user-provided
screenshots and text.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener


ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
ALLOWED_HOSTS = {
    "weibo.com",
    "www.weibo.com",
    "m.weibo.cn",
    "t.cn",
}
MOBILE_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "MWeibo-Pwa": "1",
    "Referer": "https://m.weibo.cn/",
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 "
        "Mobile/15E148 Safari/604.1"
    ),
    "X-Requested-With": "XMLHttpRequest",
}
DESKTOP_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://weibo.com/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
    ),
}


class TextExtractor(HTMLParser):
    """Convert Weibo's small HTML fragments to readable plain text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "br":
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"p", "div"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        joined = html.unescape("".join(self.parts)).replace("\u200b", "")
        joined = re.sub(r"[ \t\r\f\v]+", " ", joined)
        joined = re.sub(r" *\n *", "\n", joined)
        joined = re.sub(r"\n{3,}", "\n\n", joined)
        return joined.strip()


def strip_html(value: Any) -> str | None:
    if value is None:
        return None
    parser = TextExtractor()
    try:
        parser.feed(str(value))
        return parser.text()
    except Exception:
        cleaned = re.sub(r"<[^>]+>", " ", str(value))
        cleaned = re.sub(r"\s+", " ", html.unescape(cleaned)).strip()
        return cleaned or None


def base62_decode(value: str) -> int:
    total = 0
    for char in value:
        try:
            digit = ALPHABET.index(char)
        except ValueError as exc:
            raise ValueError(f"Invalid Base62 character: {char}") from exc
        total = total * 62 + digit
    return total


def bid_to_mid(bid: str) -> str:
    """Convert the Base62 code in a desktop Weibo URL to numeric MID."""

    if not re.fullmatch(r"[0-9A-Za-z]+", bid):
        raise ValueError("Weibo BID must contain only letters and digits")
    chunks: list[str] = []
    for end in range(len(bid), 0, -4):
        start = max(0, end - 4)
        decoded = str(base62_decode(bid[start:end]))
        if start > 0:
            decoded = decoded.zfill(7)
        chunks.append(decoded)
    return "".join(reversed(chunks)).lstrip("0") or "0"


@dataclass
class Target:
    input_value: str
    input_url: str | None = None
    resolved_url: str | None = None
    uid: str | None = None
    bid: str | None = None
    mid: str | None = None
    warnings: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_value": self.input_value,
            "input_url": self.input_url,
            "resolved_url": self.resolved_url,
            "uid": self.uid,
            "bid": self.bid,
            "mid": self.mid,
            "warnings": self.warnings or [],
        }


def normalize_host(host: str | None) -> str:
    return (host or "").split(":", 1)[0].lower().rstrip(".")


def ensure_allowed_url(value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http/https Weibo URLs are supported")
    if normalize_host(parsed.hostname) not in ALLOWED_HOSTS:
        raise ValueError("Only weibo.com, m.weibo.cn, and t.cn URLs are supported")


def parse_target(value: str) -> Target:
    raw = value.strip()
    target = Target(input_value=raw, warnings=[])
    if not raw:
        target.warnings.append("empty input")
        return target

    if re.fullmatch(r"\d+", raw):
        target.mid = raw
        return target

    if re.fullmatch(r"[0-9A-Za-z]+", raw) and "/" not in raw and "." not in raw:
        target.bid = raw
        try:
            target.mid = bid_to_mid(raw)
        except ValueError as exc:
            target.warnings.append(str(exc))
        return target

    candidate = raw if "://" in raw else f"https://{raw}"
    try:
        ensure_allowed_url(candidate)
    except ValueError as exc:
        target.warnings.append(str(exc))
        return target

    target.input_url = candidate
    parsed = urlparse(candidate)
    host = normalize_host(parsed.hostname)
    segments = [segment for segment in parsed.path.split("/") if segment]

    if host == "m.weibo.cn":
        if len(segments) >= 2 and segments[0] in {"detail", "status"}:
            code = segments[1]
            if code.isdigit():
                target.mid = code
            elif re.fullmatch(r"[0-9A-Za-z]+", code):
                target.bid = code
                target.mid = bid_to_mid(code)
        elif len(segments) >= 2 and segments[0] in {"u", "profile"}:
            target.uid = segments[1] if segments[1].isdigit() else None
        query = parse_qs(parsed.query)
        for key in ("id", "mid"):
            if not target.mid and query.get(key) and query[key][0].isdigit():
                target.mid = query[key][0]
    elif host in {"weibo.com", "www.weibo.com"} and len(segments) >= 2:
        if segments[0] == "u" and segments[1].isdigit():
            target.uid = segments[1]
            target.warnings.append("account profile URL does not identify a specific post")
        else:
            uid, bid = segments[0], segments[1]
            if uid.isdigit():
                target.uid = uid
            if uid.isdigit() and re.fullmatch(r"[0-9A-Za-z]+", bid):
                target.bid = bid
                target.mid = bid if bid.isdigit() else bid_to_mid(bid)

    if host == "t.cn":
        target.warnings.append("short URL requires network resolution")
    elif not target.mid and not any("account profile URL" in item for item in target.warnings):
        target.warnings.append("could not identify a post ID from this URL")
    return target


class PublicClient:
    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def request_bytes(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        method: str = "GET",
    ) -> tuple[bytes, str, str | None]:
        request = Request(url, headers=headers or MOBILE_HEADERS, method=method)
        with self.opener.open(request, timeout=self.timeout) as response:
            body = response.read()
            content_type = response.headers.get("Content-Type")
            final_url = response.geturl()
        if final_url:
            ensure_allowed_url(final_url)
        return body, final_url, content_type

    def request_json(
        self, url: str, headers: dict[str, str] | None = None
    ) -> tuple[dict[str, Any], str]:
        body, final_url, _ = self.request_bytes(url, headers=headers)
        decoded = body.decode("utf-8", errors="replace")
        parsed = json.loads(decoded)
        if not isinstance(parsed, dict):
            raise ValueError("Weibo endpoint returned a non-object JSON value")
        return parsed, final_url

    def warm_up(self) -> None:
        try:
            self.request_bytes("https://m.weibo.cn/", headers=MOBILE_HEADERS)
        except Exception:
            pass


def resolve_short_url(client: PublicClient, target: Target) -> None:
    if not target.input_url or normalize_host(urlparse(target.input_url).hostname) != "t.cn":
        return
    try:
        _, final_url, _ = client.request_bytes(target.input_url, headers=DESKTOP_HEADERS)
        target.resolved_url = final_url
        resolved = parse_target(final_url)
        target.uid = resolved.uid
        target.bid = resolved.bid
        target.mid = resolved.mid
        target.warnings.extend(resolved.warnings or [])
    except Exception as exc:
        target.warnings.append(f"short URL resolution failed: {compact_error(exc)}")


def compact_error(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        return f"HTTP {exc.code}"
    if isinstance(exc, URLError):
        return f"network error: {exc.reason}"
    return re.sub(r"\s+", " ", str(exc)).strip()[:240] or exc.__class__.__name__


def unwrap_status(payload: dict[str, Any]) -> dict[str, Any] | None:
    data = payload.get("data")
    if isinstance(data, dict) and ("id" in data or "mid" in data or "text" in data):
        return data
    if "id" in payload or "mid" in payload or "text" in payload:
        return payload
    status = payload.get("status")
    return status if isinstance(status, dict) else None


def extract_balanced_object(text: str, start_index: int) -> str | None:
    """Extract one balanced JSON object starting at or after start_index."""

    brace = text.find("{", start_index)
    if brace < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(brace, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[brace : index + 1]
    return None


def status_from_detail_html(value: str) -> dict[str, Any] | None:
    for marker in ('"status":', "'status':"):
        start = value.find(marker)
        if start < 0:
            continue
        object_text = extract_balanced_object(value, start + len(marker))
        if not object_text:
            continue
        try:
            parsed = json.loads(object_text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    return None


def first_nonempty(mapping: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def normalize_timestamp(value: Any) -> str | None:
    if value in (None, ""):
        return None
    raw = str(value).strip()
    try:
        parsed = parsedate_to_datetime(raw)
        return parsed.isoformat()
    except (TypeError, ValueError, OverflowError):
        pass
    for pattern in ("%a %b %d %H:%M:%S %z %Y", "%Y-%m-%d %H:%M:%S"):
        try:
            parsed = datetime.strptime(raw, pattern)
            return parsed.isoformat()
        except ValueError:
            continue
    return raw


def extract_media(status: dict[str, Any]) -> dict[str, Any]:
    images: list[str] = []
    pics = status.get("pics")
    if isinstance(pics, list):
        for pic in pics:
            if not isinstance(pic, dict):
                continue
            candidates: list[Any] = []
            for key in ("large", "original"):
                nested = pic.get(key)
                if isinstance(nested, dict):
                    candidates.append(nested.get("url"))
            candidates.append(pic.get("url"))
            image_url = next((str(item) for item in candidates if item), None)
            if image_url and image_url not in images:
                images.append(image_url)

    video_url = None
    page_info = status.get("page_info")
    if isinstance(page_info, dict):
        media_info = page_info.get("media_info")
        if not isinstance(media_info, dict):
            media_info = {}
        video_url = first_nonempty(
            media_info,
            (
                "mp4_720p_mp4",
                "mp4_hd_url",
                "hevc_mp4_hd",
                "mp4_sd_url",
                "mp4_ld_mp4",
                "stream_url_hd",
                "stream_url",
            ),
        )
        urls = page_info.get("urls")
        if not video_url and isinstance(urls, dict):
            video_url = first_nonempty(
                urls,
                ("mp4_720p_mp4", "mp4_hd_url", "mp4_sd_url", "stream_url"),
            )

    live_photo = status.get("live_photo")
    if not isinstance(live_photo, list):
        live_photo = []
    return {
        "images": images,
        "video": video_url,
        "live_photo": [str(item) for item in live_photo if item],
    }


def normalize_status(status: dict[str, Any], target: Target) -> dict[str, Any]:
    user = status.get("user") if isinstance(status.get("user"), dict) else {}
    numeric_id = first_nonempty(status, ("id", "mid", "idstr")) or target.mid
    bid = first_nonempty(status, ("bid", "mblogid")) or target.bid
    user_id = first_nonempty(user, ("id", "idstr")) or target.uid

    canonical_url = None
    if user_id and bid:
        canonical_url = f"https://weibo.com/{user_id}/{bid}"
    elif numeric_id:
        canonical_url = f"https://m.weibo.cn/detail/{numeric_id}"
    elif target.resolved_url or target.input_url:
        canonical_url = target.resolved_url or target.input_url

    profile_url = None
    if user_id:
        profile_url = f"https://weibo.com/u/{user_id}"
    elif user.get("profile_url"):
        profile_url = str(user["profile_url"])

    return {
        "canonical_url": canonical_url,
        "id": str(numeric_id) if numeric_id is not None else None,
        "bid": str(bid) if bid is not None else None,
        "created_at": normalize_timestamp(status.get("created_at")),
        "text": strip_html(status.get("text")),
        "source": strip_html(status.get("source")),
        "user": {
            "id": str(user_id) if user_id is not None else None,
            "screen_name": user.get("screen_name"),
            "profile_url": profile_url,
            "verified": user.get("verified"),
            "verified_reason": user.get("verified_reason"),
        },
        "reposts_count": status.get("reposts_count"),
        "comments_count": status.get("comments_count"),
        "attitudes_count": status.get("attitudes_count"),
        "media": extract_media(status),
    }


def fetch_status(client: PublicClient, target: Target) -> tuple[dict[str, Any] | None, list[str]]:
    warnings: list[str] = []
    if not target.mid:
        return None, ["no numeric post ID was available for public endpoint lookup"]

    attempts = [
        (f"https://m.weibo.cn/statuses/show?id={quote(target.mid)}", MOBILE_HEADERS, "json"),
        (f"https://m.weibo.cn/detail/{quote(target.mid)}", MOBILE_HEADERS, "html"),
        (f"https://weibo.com/ajax/statuses/show?id={quote(target.mid)}", DESKTOP_HEADERS, "json"),
    ]
    for url, headers, response_type in attempts:
        try:
            if response_type == "json":
                payload, _ = client.request_json(url, headers=headers)
                status = unwrap_status(payload)
                if status:
                    return status, warnings
                code = payload.get("ok")
                message = payload.get("msg") or payload.get("message")
                warnings.append(f"{urlparse(url).netloc} returned ok={code}: {message or 'no status data'}")
            else:
                body, _, _ = client.request_bytes(url, headers=headers)
                status = status_from_detail_html(body.decode("utf-8", errors="replace"))
                if status:
                    return status, warnings
                warnings.append("public detail page did not expose parseable status data")
        except Exception as exc:
            warnings.append(f"{urlparse(url).netloc}: {compact_error(exc)}")
    return None, warnings


def fetch_long_text(client: PublicClient, status: dict[str, Any]) -> str | None:
    if not status.get("isLongText"):
        return None
    identifier = first_nonempty(status, ("id", "mid", "idstr"))
    if not identifier:
        return None
    url = f"https://m.weibo.cn/statuses/extend?id={quote(str(identifier))}"
    try:
        payload, _ = client.request_json(url, headers=MOBILE_HEADERS)
        data = payload.get("data")
        if isinstance(data, dict):
            return strip_html(data.get("longTextContent") or data.get("longText"))
    except Exception:
        return None
    return None


def collect(target_value: str, timeout: float) -> dict[str, Any]:
    target = parse_target(target_value)
    client = PublicClient(timeout=timeout)
    if target.input_url and normalize_host(urlparse(target.input_url).hostname) == "t.cn":
        resolve_short_url(client, target)

    if not target.mid:
        return {
            "status": "unavailable",
            "target": target.to_dict(),
            "post": None,
            "warnings": list(target.warnings or []),
            "next_step": "Use the user's screenshot, copied text, and factual explanation; continue drafting.",
        }

    client.warm_up()
    status, fetch_warnings = fetch_status(client, target)
    warnings = list(target.warnings or []) + fetch_warnings
    if not status:
        return {
            "status": "partial",
            "target": target.to_dict(),
            "post": {
                "canonical_url": target.resolved_url or target.input_url or f"https://m.weibo.cn/detail/{target.mid}",
                "id": target.mid,
                "bid": target.bid,
                "created_at": None,
                "text": None,
                "source": None,
                "user": {
                    "id": target.uid,
                    "screen_name": None,
                    "profile_url": f"https://weibo.com/u/{target.uid}" if target.uid else None,
                    "verified": None,
                    "verified_reason": None,
                },
                "reposts_count": None,
                "comments_count": None,
                "attitudes_count": None,
                "media": {"images": [], "video": None, "live_photo": []},
            },
            "warnings": warnings,
            "next_step": "Keep the parsed URL/ID and use user-provided screenshots or text for missing fields.",
        }

    full_text = fetch_long_text(client, status)
    normalized = normalize_status(status, target)
    if full_text:
        normalized["text"] = full_text
    critical_values = [normalized.get("text"), normalized.get("user", {}).get("screen_name")]
    result_status = "ok" if all(critical_values) else "partial"
    if result_status == "partial":
        warnings.append("one or more main public fields were unavailable")
    return {
        "status": result_status,
        "target": target.to_dict(),
        "post": normalized,
        "warnings": warnings,
        "next_step": (
            "Use available fields and continue drafting. Mark missing fields as 未获取."
            if result_status == "partial"
            else "Use the public fields as source-labeled inputs; verify disputed facts against evidence."
        ),
    }


def nonnegative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Best-effort public Weibo post reader; no API key, cookie, or login."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect_parser = subparsers.add_parser("collect", help="read one public Weibo post")
    collect_parser.add_argument("target", help="post URL, numeric MID, or Base62 BID")
    collect_parser.add_argument("--timeout", type=nonnegative_float, default=15.0)
    collect_parser.add_argument("--pretty", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = collect(args.target, timeout=args.timeout)
    except KeyboardInterrupt:
        result = {
            "status": "unavailable",
            "warnings": ["operation interrupted"],
            "next_step": "Continue from user-provided materials.",
        }
    except Exception as exc:
        result = {
            "status": "unavailable",
            "warnings": [compact_error(exc)],
            "next_step": "Continue from user-provided screenshots, copied text, and factual explanation.",
        }

    indent = 2 if getattr(args, "pretty", False) else None
    json.dump(result, sys.stdout, ensure_ascii=False, indent=indent)
    sys.stdout.write("\n")
    # Public access failure is intentionally non-fatal for the surrounding skill.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
