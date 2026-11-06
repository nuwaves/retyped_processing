import django.contrib.postgres.indexes
import django.contrib.postgres.search
from django.db import migrations


class Migration(migrations.Migration):
    """
    Replace Meilisearch with Postgres full-text search.

    Adds an indexed search_vector column to episodes, podcasts and entities.
    The columns start empty; fill them with the admin "Reindex all" actions
    (or reindex_all_*_for_search tasks) after deploying.
    """

    dependencies = [
        ("audio_processing", "0032_episode_publisher_transcripts"),
    ]

    operations = [
        migrations.AddField(
            model_name="episode",
            name="search_vector",
            field=django.contrib.postgres.search.SearchVectorField(
                editable=False, null=True
            ),
        ),
        migrations.AddField(
            model_name="podcast",
            name="search_vector",
            field=django.contrib.postgres.search.SearchVectorField(
                editable=False, null=True
            ),
        ),
        migrations.AddField(
            model_name="entity",
            name="search_vector",
            field=django.contrib.postgres.search.SearchVectorField(
                editable=False, null=True
            ),
        ),
        migrations.AddIndex(
            model_name="episode",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["search_vector"], name="episode_search_vector_gin"
            ),
        ),
        migrations.AddIndex(
            model_name="podcast",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["search_vector"], name="podcast_search_vector_gin"
            ),
        ),
        migrations.AddIndex(
            model_name="entity",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["search_vector"], name="entity_search_vector_gin"
            ),
        ),
    ]
