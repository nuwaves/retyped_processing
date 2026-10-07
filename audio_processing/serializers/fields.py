from rest_framework import serializers

from audio_processing.utils import sanitize_html_content


class HtmlSanitizedField(serializers.CharField):
    def to_representation(self, value):
        if isinstance(value, str):
            return sanitize_html_content(value)
        return value
