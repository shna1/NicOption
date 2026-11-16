from __future__ import annotations

from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse


ALLOWED_TAGS = {
    "a",
    "blockquote",
    "br",
    "div",
    "em",
    "figcaption",
    "figure",
    "h2",
    "h3",
    "img",
    "li",
    "ol",
    "p",
    "s",
    "strong",
    "u",
    "ul",
}
VOID_TAGS = {"br", "img"}


def _safe_link(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https", "mailto"} or (
        not parsed.scheme and value.strip().startswith(("/", "#"))
    )


def _safe_image(value: str) -> bool:
    parsed = urlparse(value.strip())
    return not parsed.scheme and parsed.path.startswith("/article-media/")


class _ArticleHTMLSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.output: list[str] = []
        self.open_tags: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag not in ALLOWED_TAGS:
            return

        clean_attrs: list[tuple[str, str]] = []
        attrs_map = {key.lower(): value or "" for key, value in attrs}
        if tag == "a" and _safe_link(attrs_map.get("href", "")):
            clean_attrs.append(("href", attrs_map["href"].strip()))
            clean_attrs.extend((("target", "_blank"), ("rel", "noopener noreferrer")))
        elif tag == "img" and _safe_image(attrs_map.get("src", "")):
            clean_attrs.extend(
                (
                    ("src", attrs_map["src"].strip()),
                    ("alt", attrs_map.get("alt", "").strip()[:180]),
                    ("loading", "lazy"),
                    ("decoding", "async"),
                )
            )
        elif tag == "img":
            return

        rendered_attrs = "".join(
            f' {name}="{escape(value, quote=True)}"' for name, value in clean_attrs
        )
        self.output.append(f"<{tag}{rendered_attrs}>")
        if tag not in VOID_TAGS:
            self.open_tags.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag not in ALLOWED_TAGS or tag in VOID_TAGS or tag not in self.open_tags:
            return
        while self.open_tags:
            current = self.open_tags.pop()
            self.output.append(f"</{current}>")
            if current == tag:
                break

    def handle_data(self, data: str) -> None:
        self.output.append(escape(data))

    def close(self) -> None:
        super().close()
        while self.open_tags:
            self.output.append(f"</{self.open_tags.pop()}>")


def sanitize_article_html(value: str) -> str:
    sanitizer = _ArticleHTMLSanitizer()
    sanitizer.feed(str(value or ""))
    sanitizer.close()
    return "".join(sanitizer.output).strip()
