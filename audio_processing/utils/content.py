from bs4 import BeautifulSoup
import re


class HtmlSanitizer:
    def __init__(self):
        # Allowed HTML tags (whitelist approach)
        self.allowed_tags = {
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

        # Allowed attributes per tag
        self.allowed_attributes = {
            "a": ["href", "title"],
            "img": ["src", "alt", "title", "width", "height"],
            "blockquote": ["cite"],
            "table": ["summary"],
            "td": ["colspan", "rowspan"],
            "th": ["colspan", "rowspan", "scope"],
            "*": ["class", "id"],  # Global attributes
        }

        # Dangerous tags to completely remove
        self.dangerous_tags = {
            "script",
            "style",
            "iframe",
            "object",
            "embed",
            "form",
            "input",
            "textarea",
            "button",
            "select",
            "option",
            "meta",
            "link",
            "base",
            "applet",
            "audio",
            "video",
            "source",
        }

        # Dangerous URL schemes
        self.dangerous_schemes = ["javascript:", "vbscript:", "data:", "file:", "ftp:"]

    def sanitize(self, html_string: str) -> str:
        """Main sanitization method"""
        if not html_string:
            return ""

        # Parse with Beautiful Soup
        soup = BeautifulSoup(html_string, "html.parser")

        # Remove dangerous tags completely
        self._remove_dangerous_tags(soup)

        # Clean remaining tags and attributes
        self._clean_tags_and_attributes(soup)

        # Clean URLs in href and src attributes
        self._clean_urls(soup)

        # Remove event handlers and dangerous attributes
        self._remove_event_handlers(soup)

        return str(soup)

    def _remove_dangerous_tags(self, soup: BeautifulSoup):
        """Remove script, style, and other dangerous tags"""
        for tag_name in self.dangerous_tags:
            for tag in soup.find_all(tag_name):
                tag.decompose()  # Completely remove tag and contents

    def _clean_tags_and_attributes(self, soup: BeautifulSoup):
        """Remove disallowed tags and attributes"""
        for tag in soup.find_all():
            # Remove disallowed tags but keep content
            if tag.name not in self.allowed_tags:
                tag.unwrap()  # Remove tag but keep inner content
                continue

            # Clean attributes
            allowed_attrs = self.allowed_attributes.get(tag.name, [])
            global_attrs = self.allowed_attributes.get("*", [])
            allowed_attrs = allowed_attrs if len(allowed_attrs) > 1 else global_attrs

            # Remove disallowed attributes
            attrs_to_remove = []
            for attr in tag.attrs:
                if attr not in allowed_attrs:
                    attrs_to_remove.append(attr)

            for attr in attrs_to_remove:
                del tag.attrs[attr]

    def _clean_urls(self, soup: BeautifulSoup):
        """Clean href and src attributes to prevent XSS"""
        # Clean href attributes
        for tag in soup.find_all(attrs={"href": True}):
            href = tag.get("href", "").strip().lower()
            if any(href.startswith(scheme) for scheme in self.dangerous_schemes):
                del tag["href"]

        # Clean src attributes
        for tag in soup.find_all(attrs={"src": True}):
            src = tag.get("src", "").strip().lower()
            if any(src.startswith(scheme) for scheme in self.dangerous_schemes):
                del tag["src"]

    def _remove_event_handlers(self, soup: BeautifulSoup):
        """Remove event handler attributes like onclick, onload, etc."""
        event_pattern = re.compile(r"^on\w+", re.IGNORECASE)

        for tag in soup.find_all():
            attrs_to_remove = []
            for attr in tag.attrs:
                if event_pattern.match(attr):
                    attrs_to_remove.append(attr)

            for attr in attrs_to_remove:
                del tag.attrs[attr]


def sanitize_html_content(value: str) -> str:
    """
    Instantiate html sanitizer and return the parsed str
    """
    if not value:
        return None
    sanitizer = HtmlSanitizer()
    return sanitizer.sanitize(value)
