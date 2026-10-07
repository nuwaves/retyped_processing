import nh3

# Feed descriptions and show notes come from third-party RSS feeds and are
# rendered as HTML by the frontend, so everything outside this list is stripped.
ALLOWED_TAGS = {
    "p",
    "br",
    "strong",
    "b",
    "em",
    "i",
    "u",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "ul",
    "ol",
    "li",
    "blockquote",
    "code",
    "pre",
    "a",
    "img",
    "table",
    "thead",
    "tbody",
    "tr",
    "td",
    "th",
    "div",
    "span",
}

ALLOWED_ATTRIBUTES = {
    "a": {"href", "title"},
    "img": {"src", "alt", "title", "width", "height"},
    "blockquote": {"cite"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
}

ALLOWED_URL_SCHEMES = {"http", "https", "mailto"}


def sanitize_html_content(value: str) -> str:
    """
    Return value with unsafe tags, attributes and URL schemes removed.
    """
    if not value:
        return None
    return nh3.clean(
        value,
        tags=ALLOWED_TAGS,
        clean_content_tags={"script", "style"},
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_URL_SCHEMES,
        link_rel="noopener noreferrer nofollow",
    )
