from __future__ import annotations

import datetime as dt
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import yaml


def nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def key(value: str) -> str:
    return nfc(value).strip().casefold()


FORBIDDEN = re.compile(r"[/\\:\[\]#^|]")


class InvalidName(ValueError):
    pass


def title(value: str) -> str:
    clean = nfc(value).strip()
    if clean.lower().endswith(".md"):
        clean = clean[:-3].rstrip()
    if not clean:
        raise InvalidName("the title is empty")
    if len(clean) > 200:
        raise InvalidName("the title is longer than 200 characters")
    if clean.startswith("."):
        raise InvalidName("a title does not start with a dot")
    bad = FORBIDDEN.search(clean)
    if bad:
        raise InvalidName(f"a title cannot contain '{bad.group()}'")
    return clean


def folder(value: str | None) -> str:
    if not value:
        return ""
    parts = [nfc(part).strip() for part in value.replace("\\", "/").split("/")]
    parts = [part for part in parts if part]
    for part in parts:
        if part in (".", "..") or part.startswith("."):
            raise InvalidName(f"a folder cannot be called '{part}'")
        bad = FORBIDDEN.search(part)
        if bad:
            raise InvalidName(f"a folder cannot contain '{bad.group()}'")
    path = "/".join(parts)
    if len(path) > 1000:
        raise InvalidName("the folder path is longer than 1000 characters")
    return path


def path_of(folder_path: str, note_title: str) -> str:
    return f"{folder_path}/{note_title}" if folder_path else note_title


def ancestors(folder_path: str) -> list[str]:
    parts = folder_path.split("/") if folder_path else []
    return ["/".join(parts[: i + 1]) for i in range(len(parts))]


FRONTMATTER = re.compile(r"\A---[ \t]*\r?\n(?:(.*?)\r?\n)?---[ \t]*(?:\r?\n|\Z)", re.S)


@dataclass(frozen=True)
class Split:
    frontmatter: str | None
    body: str
    offset: int


def split(content: str) -> Split:
    match = FRONTMATTER.match(content)
    if not match:
        return Split(None, content, 0)
    return Split(match.group(1) or "", content[match.end() :], match.end())


class InvalidProperties(ValueError):
    pass


def _plain(value: Any) -> Any:
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [_plain(v) for v in value]
    return value


def load_properties(frontmatter: str | None) -> dict[str, Any]:
    if frontmatter is None or not frontmatter.strip():
        return {}
    try:
        loaded = yaml.safe_load(frontmatter)
    except yaml.YAMLError as error:
        raise InvalidProperties(f"the frontmatter is not valid YAML: {error}") from error
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise InvalidProperties("the frontmatter is not a list of properties")
    return _plain(loaded)


def properties(content: str) -> dict[str, Any]:
    try:
        return load_properties(split(content).frontmatter)
    except InvalidProperties:
        return {}


class _Dumper(yaml.SafeDumper):
    def increase_indent(self, flow: bool = False, indentless: bool = False):  # noqa: ARG002
        return super().increase_indent(flow, False)


ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _yaml_value(value: Any) -> Any:
    if isinstance(value, str) and ISO_DATE.match(value):
        try:
            return dt.date.fromisoformat(value)
        except ValueError:
            return value
    if isinstance(value, list):
        return [_yaml_value(v) for v in value]
    return value


def dump_properties(values: dict[str, Any]) -> str:
    return yaml.dump(
        {k: _yaml_value(v) for k, v in values.items()},
        Dumper=_Dumper,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=10**6,
    ).rstrip("\n")


def with_properties(content: str, values: dict[str, Any]) -> str:
    parts = split(content)
    body = parts.body if parts.frontmatter is not None else content
    if not values:
        return body
    return f"---\n{dump_properties(values)}\n---\n{body}"


def set_properties(content: str, set_: dict[str, Any], remove: list[str]) -> str:
    current = load_properties(split(content).frontmatter)
    for name in remove:
        current.pop(name, None)
    for name, value in set_.items():
        current[name] = value
    return with_properties(content, current)


BLOCK_START = "%% arga %%"
BLOCK_END = "%% /arga %%"
BLOCK = re.compile(r"^%% arga %%[ \t]*\r?\n(.*?)^%% /arga %%[ \t]*(?:\r?\n|\Z)", re.M | re.S)


@dataclass(frozen=True)
class Block:
    start: int
    end: int
    inner: str


def block(content: str) -> Block | None:
    offset = split(content).offset
    match = BLOCK.search(content, offset)
    if match is None:
        return None
    return Block(match.start(), match.end(), match.group(1).rstrip("\n"))


def render_block(inner: str) -> str:
    body = inner.strip("\n")
    return f"{BLOCK_START}\n{body}\n{BLOCK_END}\n" if body else f"{BLOCK_START}\n{BLOCK_END}\n"


def with_block(content: str, inner: str | None, at_end: bool = False) -> str:
    found = block(content)
    if inner is None:
        if found is None:
            return content
        head_end = split(content).offset
        head = content[:head_end]
        before = content[head_end : found.start].rstrip("\n")
        after = content[found.end :].lstrip("\n")
        if before and after:
            return head + before + "\n\n" + after
        return head + (before + "\n" if before else after)
    new = render_block(inner)
    if found is not None:
        return content[: found.start] + new + content[found.end :]
    parts = split(content)
    head = content[: parts.offset]
    if at_end:
        body = parts.body.rstrip("\n")
        return head + (body + "\n\n" if body else "") + new
    rest = parts.body.lstrip("\n")
    return head + new + ("\n" + rest if rest else "")


def outside_block(content: str) -> str:
    return split(with_block(content, None)).body


def in_block(content: str, position: int) -> bool:
    found = block(content)
    return found is not None and found.start <= position < found.end


def safe_title(value: str) -> str:
    clean = nfc(value)
    clean = re.sub(r"\s*:\s*", " - ", clean)
    clean = re.sub(r"[/\\|]", "-", clean)
    clean = clean.replace("[", "(").replace("]", ")")
    clean = re.sub(r"[#^]", "", clean)
    clean = re.sub(r"\s+", " ", clean).strip().lstrip(".").strip()
    if clean.lower().endswith(".md"):
        clean = clean[:-3].strip()
    return clean[:200].strip() or "Untitled"


FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
INLINE_CODE = re.compile(r"(`+)(?:(?!\1).)+?\1")
COMMENT = re.compile(r"%%.*?%%", re.S)


def _blank(text: str) -> str:
    return re.sub(r"[^\n]", " ", text)


def mask(text: str) -> str:
    lines = text.split("\n")
    out: list[str] = []
    fence: str | None = None
    for line in lines:
        opening = FENCE.match(line)
        if fence is None and opening:
            fence = opening.group(1)
            out.append(_blank(line))
            continue
        if fence is not None:
            closing = FENCE.match(line)
            if closing and closing.group(1)[0] == fence[0] and len(closing.group(1)) >= len(fence):
                fence = None
            out.append(_blank(line))
            continue
        out.append(INLINE_CODE.sub(lambda m: _blank(m.group()), line))
    return COMMENT.sub(lambda m: _blank(m.group()), "\n".join(out))


def _line_at(text: str, position: int) -> int:
    return text.count("\n", 0, position)


WIKILINK = re.compile(r"(!?)\[\[([^\[\]\n]+?)\]\]")
APP_LINK = re.compile(r"^([a-z][a-z0-9_]*):(.+)$")
FILE_EXTENSIONS = frozenset(
    {
        *("png", "jpg", "jpeg", "gif", "webp", "svg", "bmp", "avif", "heic", "pdf"),
        *("mp3", "m4a", "wav", "ogg", "flac", "mp4", "webm", "mov", "mkv"),
        *("csv", "json", "txt", "zip", "canvas", "base"),
    }
)


@dataclass(frozen=True)
class Link:
    start: int
    end: int
    line: int
    kind: str
    target: str
    title_key: str
    folder_key: str | None
    heading: str | None
    alias: str | None
    embed: bool
    escaped_pipe: bool


def _target_parts(target: str) -> tuple[str, str, str | None]:
    app = APP_LINK.match(target)
    if app:
        return "app", key(target), None
    name = target
    if "/" in name:
        folder_part, name = name.rsplit("/", 1)
        folder_key: str | None = key(folder(folder_part)) or None
    else:
        folder_key = None
    extension = name.rsplit(".", 1)[1].lower() if "." in name else ""
    if extension in FILE_EXTENSIONS:
        return "file", key(name), folder_key
    if name.lower().endswith(".md"):
        name = name[:-3]
    return "note", key(name), folder_key


def links(content: str) -> list[Link]:
    masked = mask(content)
    found: list[Link] = []
    for match in WIKILINK.finditer(masked):
        inner = content[match.start(2) : match.end(2)]
        escaped = "\\|" in inner
        inner = inner.replace("\\|", "|")
        target, _, alias = inner.partition("|")
        target, _, heading = target.partition("#")
        target = nfc(target).strip()
        if not target:
            continue
        kind, title_key, folder_key = _target_parts(target)
        found.append(
            Link(
                start=match.start(),
                end=match.end(),
                line=_line_at(content, match.start()),
                kind=kind,
                target=target,
                title_key=title_key,
                folder_key=folder_key,
                heading=nfc(heading).strip() or None,
                alias=nfc(alias).strip() or None if alias else None,
                embed=bool(match.group(1)),
                escaped_pipe=escaped,
            )
        )
    return found


def rewrite_links(content: str, new_target: Callable[[Link], str | None]) -> str:
    out = content
    for link in reversed(links(content)):
        target = new_target(link)
        if target is None or target == link.target:
            continue
        pipe = "\\|" if link.escaped_pipe else "|"
        rebuilt = ("!" if link.embed else "") + "[[" + target
        if link.heading:
            rebuilt += "#" + link.heading
        if link.alias:
            rebuilt += pipe + link.alias
        rebuilt += "]]"
        out = out[: link.start] + rebuilt + out[link.end :]
    return out


INLINE_TAG = re.compile(r"(?:(?<=\s)|^)#([\w/-]+)", re.M)


def _tag_key(raw: str) -> str | None:
    clean = key(raw.lstrip("#")).strip("/")
    if not clean or not re.search(r"[^\d/_-]", clean):
        return None
    return clean[:200]


def tags(content: str) -> list[str]:
    parts = split(content)
    found: list[str] = []
    for match in INLINE_TAG.finditer(mask(parts.body)):
        found.append(match.group(1))
    try:
        values = load_properties(parts.frontmatter)
    except InvalidProperties:
        values = {}
    for name in ("tags", "tag"):
        value = values.get(name)
        if isinstance(value, str):
            found.extend(re.split(r"[,\s]+", value))
        elif isinstance(value, list):
            found.extend(str(v) for v in value if v is not None)
    seen: dict[str, None] = {}
    for raw in found:
        tag = _tag_key(raw)
        if tag:
            seen.setdefault(tag, None)
    return list(seen)


HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*(?:[ \t]#+)?[ \t]*$", re.M)


@dataclass(frozen=True)
class Heading:
    level: int
    text: str
    line: int
    start: int
    body_start: int
    end: int


def headings(content: str) -> list[Heading]:
    parts = split(content)
    masked = _blank(content[: parts.offset]) + mask(parts.body)
    raw = [
        (len(m.group(1)), nfc(m.group(2)).strip(), m.start(), m.end())
        for m in HEADING.finditer(masked)
    ]
    found: list[Heading] = []
    for i, (level, text, start, line_end) in enumerate(raw):
        end = len(content)
        for other_level, _, other_start, _ in raw[i + 1 :]:
            if other_level <= level:
                end = other_start
                break
        body_start = line_end + 1 if line_end < len(content) else line_end
        found.append(
            Heading(
                level, text, _line_at(content, start), start, min(body_start, len(content)), end
            )
        )
    return found


class NotFoundInNote(ValueError):
    pass


class Ambiguous(ValueError):
    pass


def section(content: str, heading: str) -> Heading:
    wanted = key(heading.lstrip("#"))
    matches = [h for h in headings(content) if key(h.text) == wanted]
    if not matches:
        available = ", ".join(f"'{h.text}'" for h in headings(content)[:20]) or "none"
        raise NotFoundInNote(f"there is no heading '{heading}'. The ones there are: {available}")
    if len(matches) > 1:
        lines = ", ".join(str(h.line + 1) for h in matches)
        raise Ambiguous(f"there are {len(matches)} headings '{heading}' (lines {lines})")
    return matches[0]


def _block(text: str) -> str:
    return text.strip("\n")


def replace_section(content: str, heading: str, text: str) -> str:
    found = section(content, heading)
    rest = content[found.end :]
    new = _block(text)
    tail = "\n\n" if rest else "\n"
    return content[: found.body_start] + (new + tail if new else ("\n" if rest else "")) + rest


def append(content: str, text: str, heading: str | None = None) -> str:
    new = _block(text)
    if not new:
        return content
    if heading is None:
        before, after = content.rstrip("\n"), ""
    else:
        found = section(content, heading)
        before = content[: found.end].rstrip("\n")
        after = content[found.end :]
    joined = f"{before}\n\n{new}\n" if before else f"{new}\n"
    if after:
        joined += "\n" + after
    return joined


def replace_fragment(content: str, old: str, new: str) -> str:
    if not old:
        raise NotFoundInNote("the fragment to change is empty")
    count = content.count(old)
    if count == 0:
        normalized = nfc(old)
        if normalized != old and content.count(normalized) == 1:
            return content.replace(normalized, nfc(new), 1)
        raise NotFoundInNote(
            "the fragment does not appear in the note; read it again and copy it exactly"
        )
    if count > 1:
        raise Ambiguous(
            f"the fragment appears {count} times; give more text around it so it is unique"
        )
    return content.replace(old, new, 1)


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def search_text(note_title: str, content: str) -> str:
    return fold(f"{note_title}\n{content}")


WORD = re.compile(r"[^\W_]+", re.UNICODE)


def query_words(query: str) -> list[str]:
    return WORD.findall(fold(query))[:12]


PLURALS = ("es", "en", "s", "n", "e")


def variants(word: str) -> list[str]:
    found = [word]
    for ending in PLURALS:
        if word.endswith(ending) and len(word) - len(ending) >= 4:
            stem = word[: -len(ending)]
            if stem not in found:
                found.append(stem)
    return found


def tsquery(query: str) -> str | None:
    words = query_words(query)
    if not words:
        return None
    return " & ".join("(" + " | ".join(f"{v}:*" for v in variants(word)) + ")" for word in words)


def snippet(content: str, query: str, width: int = 160) -> str:
    body = split(content).body
    words = query_words(query)
    folded: list[str] = []
    index: list[int] = []
    for position, char in enumerate(body):
        piece = fold(char)
        folded.append(piece)
        index.extend([position] * len(piece))
    haystack = "".join(folded)
    at = -1
    for word in words:
        at = haystack.find(word)
        if at >= 0:
            break
    start = 0 if at < 0 else max(0, index[at] - width // 3)
    piece = body[start : start + width]
    piece = re.sub(r"\s+", " ", piece).strip()
    return ("…" if start > 0 else "") + piece + ("…" if start + width < len(body) else "")


def outline(content: str) -> list[dict[str, Any]]:
    return [{"level": h.level, "text": h.text, "line": h.line} for h in headings(content)]


def line(content: str, number: int) -> str:
    lines = content.split("\n")
    return lines[number].strip() if 0 <= number < len(lines) else ""
