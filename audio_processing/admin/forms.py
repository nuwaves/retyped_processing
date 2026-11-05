from django import forms

from audio_processing.models import Podcast


class FeedUrlForm(forms.Form):
    url = forms.URLField(
        label="RSS feed URL",
        max_length=200,
        widget=forms.URLInput(
            attrs={"placeholder": "https://example.com/feed.xml", "size": 70}
        ),
    )

    def clean_url(self):
        url = self.cleaned_data["url"].strip()
        self.existing = Podcast.objects.filter(url=url).first()
        if self.existing:
            raise forms.ValidationError("This feed has already been added.")
        return url


class ImportOptionsForm(FeedUrlForm):
    process_latest = forms.IntegerField(
        label="Process the latest episodes now",
        min_value=0,
        max_value=25,
        initial=3,
        help_text="How many of the newest episodes to transcribe and process right away. 0 to skip.",
    )
    auto_process = forms.BooleanField(
        label="Auto-process new episodes",
        required=False,
        help_text="When the daily feed refresh finds new episodes, process them automatically.",
    )
    auto_process_count = forms.IntegerField(
        label="Max new episodes per refresh",
        min_value=1,
        max_value=25,
        initial=3,
    )
    url = forms.URLField(widget=forms.HiddenInput)


class PodcastSettingsForm(forms.ModelForm):
    class Meta:
        model = Podcast
        fields = ("is_active", "auto_process", "auto_process_count")
        labels = {
            "is_active": "Active (refresh feed daily)",
            "auto_process": "Auto-process new episodes",
            "auto_process_count": "Max per refresh",
        }
