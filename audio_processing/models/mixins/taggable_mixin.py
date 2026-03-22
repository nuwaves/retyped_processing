import json
import logging

from audio_processing.prompts import get_tag_suggestion_prompt

logger = logging.getLogger(__name__)


class TaggableMixin:
    """
    Mixin to provide tagging functionality using Groq LLM for tag suggestions.
    """

    def _validate_transcript(self):
        """Check if transcript exists and is valid for processing."""
        if not self.transcript or not self.transcript.strip():
            logger.warning(
                f"No transcript available for {self.__class__.__name__}: {getattr(self, 'raw_audio_url', str(self))}"
            )
            return False
        return True

    def _get_available_tags(self):
        """Get all available tags formatted for LLM processing."""
        from audio_processing.models.tag import Tag

        all_tags = Tag.objects.all()

        if not all_tags.exists():
            logger.warning("No tags available in the database")
            return None

        tag_list = []
        for tag in all_tags:
            tag_info = {
                "id": tag.id,
                "name": tag.name,
                "description": tag.description or tag.name,
            }
            tag_list.append(tag_info)

        return tag_list

    def _parse_and_apply_tags(self, llm_response):
        """Parse LLM response and apply valid tags to the model."""
        from audio_processing.models.tag import Tag

        try:
            suggested_tag_ids = json.loads(llm_response)
            if not isinstance(suggested_tag_ids, list):
                logger.error(
                    f"Expected list of tag IDs, got: {type(suggested_tag_ids)}"
                )
                return None

            applied_tags = []
            for tag_id in suggested_tag_ids:
                try:
                    tag = Tag.objects.get(id=tag_id)
                    self.tags.add(tag)
                    applied_tags.append(tag_id)
                    logger.info(
                        f"Applied tag '{tag.name}' to {self.__class__.__name__}: {getattr(self, 'raw_audio_url', str(self))}"
                    )
                except Tag.DoesNotExist:
                    logger.warning(f"Tag with ID {tag_id} does not exist")

            if applied_tags:
                logger.info(
                    f"Successfully applied {len(applied_tags)} tags to {self.__class__.__name__}: {getattr(self, 'raw_audio_url', str(self))}"
                )
                return applied_tags
            else:
                logger.warning(
                    f"No valid tags were applied to {self.__class__.__name__}: {getattr(self, 'raw_audio_url', str(self))}"
                )
                return []

        except json.JSONDecodeError:
            logger.error(f"Failed to parse LLM response as JSON: {llm_response}")
            return None

    def suggest_and_apply_tags(self):
        """
        Use Groq LLM to analyze the transcript and suggest relevant tags.
        Returns a list of applied tag IDs or None if failed.
        """
        # Validate transcript
        if not self._validate_transcript():
            return None

        # Get available tags
        tag_list = self._get_available_tags()
        if tag_list is None:
            return None

        logger.info(
            f"Analyzing transcript for tag suggestions: {getattr(self, 'raw_audio_url', str(self))}"
        )

        # Build the prompt for Groq
        prompt = get_tag_suggestion_prompt(tag_list, self.transcript)
        logger.info(f"Generated prompt for tag suggestions: {prompt}")

        # Call Groq LLM for tag suggestions
        llm_response = self.get_groq_completion(prompt)
        if llm_response is None:
            logger.error(
                f"Failed to get tag suggestions for {self.__class__.__name__}: {getattr(self, 'raw_audio_url', str(self))}"
            )
            return None

        # Parse and apply tags
        applied_tags = self._parse_and_apply_tags(llm_response)
        return applied_tags
