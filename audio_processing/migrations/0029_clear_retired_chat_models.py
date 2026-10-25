from django.db import migrations

CHAT_MODEL_KEYS = ("DEFAULT_MODEL", "SUMMARY_MODEL", "TAG_MODEL", "SPEAKER_MODEL")
# Groq retired these; rows still naming them would override the new defaults.
RETIRED_MODELS = ("llama-3.1-8b-instant", "deepseek-r1-distill-llama-70b")


def clear_retired_chat_models(apps, schema_editor):
    Constance = apps.get_model("constance", "Constance")
    for row in Constance.objects.filter(key__in=CHAT_MODEL_KEYS):
        if any(model in (row.value or "") for model in RETIRED_MODELS):
            row.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("audio_processing", "0028_add_topic_is_enabled"),
        ("constance", "0003_drop_pickle"),
    ]

    operations = [
        migrations.RunPython(clear_retired_chat_models, migrations.RunPython.noop),
    ]
