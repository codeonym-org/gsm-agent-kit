import re
import unicodedata
from html import unescape
from html.parser import HTMLParser

from markdown_it import MarkdownIt
from markdown_it.token import Token


class _HtmlText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text: list[str] = []

    def handle_data(self, data: str) -> None:
        self.text.append(data)

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("br", "p", "div", "li"):
            self.text.append("\n")


def _html_text(text: str) -> str:
    parser = _HtmlText()
    parser.feed(text)
    return "".join(parser.text)


class PlainTextNormalizer:
    def __init__(self):
        self.parser = MarkdownIt("commonmark").enable(["table", "strikethrough"])

    def _inline(self, tokens: list[Token]) -> str:
        pieces: list[str] = []
        links: list[tuple[str, int]] = []
        for token in tokens:
            if token.type in ("text", "code_inline"):
                pieces.append(token.content)
            elif token.type in ("softbreak", "hardbreak"):
                pieces.append("\n")
            elif token.type == "image":
                pieces.append(self._inline(token.children or []))
            elif token.type == "link_open":
                links.append((token.attrGet("href") or "", len(pieces)))
            elif token.type == "link_close" and links:
                url, start = links.pop()
                label = "".join(pieces[start:])
                if url and label != url:
                    pieces.append(f" ({url})")
            elif token.type == "html_inline":
                pieces.append(_html_text(token.content))
        return "".join(pieces)

    def normalize(self, text: str) -> str:
        pieces = []
        for token in self.parser.parse(text):
            if token.type == "inline":
                pieces.append(self._inline(token.children or []))
            elif token.type in ("fence", "code_block"):
                pieces.append(token.content + "\n\n")
            elif token.type == "html_block":
                pieces.append(_html_text(token.content) + "\n\n")
            elif token.type in ("paragraph_close", "heading_close"):
                pieces.append("\n\n")
            elif token.type in ("tr_close", "list_item_close", "hr"):
                pieces.append("\n")
            elif token.type in ("td_close", "th_close"):
                pieces.append("; ")
        text = unescape("".join(pieces))
        text = text.translate(
            str.maketrans(
                {
                    "‘": "'",
                    "’": "'",
                    "“": '"',
                    "”": '"',
                    "–": "-",
                    "—": "-",
                    "…": "...",
                    "\u00a0": " ",
                    "\r": "\n",
                    "\t": " ",
                }
            )
        )
        text = "".join(
            c
            for c in text
            if ord(c) <= 0xFFFF
            and not 0xD800 <= ord(c) <= 0xDFFF
            and c not in ("\ufe0e", "\ufe0f")
            and (c == "\n" or unicodedata.category(c) not in ("Cc", "Cf"))
        )
        text = unicodedata.normalize("NFC", text)
        lines = [re.sub(r"[^\S\n]+", " ", line).strip() for line in text.splitlines()]
        return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
