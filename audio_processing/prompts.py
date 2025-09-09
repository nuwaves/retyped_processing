import json

def get_entity_extraction_prompt(text):
    """
    Generate a prompt for extracting named entities from text.
    """
    return (
        "Extract named entities (Person, Organization, Product) from the following text. Attempt to give a complete common first name and last name for - for example 'Joe Biden' and not 'Biden' but 'Bill Gates' and not 'William Gates'"
        "Return a JSON array of objects with 'name' and 'type' (PERSON, ORGANIZATION, PRODUCT). Return only the JSON. Your entire response should be a valid JSON object."
        "Example: [{\"name\": \"John Doe\", \"type\": \"PERSON\"}, {\"name\": \"Acme Corp\", \"type\": \"ORGANIZATION\"}].\n\nText:\n" + text
    )


def get_tag_suggestion_prompt(tag_list, transcript_excerpt):
    
    return f"""You are an AI assistant that analyzes podcast transcripts and suggests relevant tags.

Available tags:
{json.dumps(tag_list, indent=2)}

Podcast transcript (first 2000 characters):
{transcript_excerpt}

Based on the transcript content, please suggest which tags are most relevant.
Return ONLY a JSON array of tag IDs (numbers) that apply to this podcast.
Example: [1, 3, 7]

Consider the topic, genre, subject matter, and themes discussed in the podcast.

Again, you should respond only with a JSON array of tag IDs.
Do not include any additional text or explanations."""

def get_speaker_transcript_prompt(episode):
    """
    Generate a prompt for converting a transcript into a speaker-formatted script.
    
    Args:
        transcript_excerpt: The podcast transcript to format
    
    Returns:
        str: Formatted prompt for speaker identification and script formatting
    """
    transcript = episode.transcript

    return f"""You are an AI assistant that converts podcast transcripts into properly formatted scripts with speaker identification.

Original transcript:
{transcript}

Please rewrite this transcript as a script format with identified speakers. Follow these guidelines:

1. Identify different speakers as best as you can from context clues, speaking patterns, and content
2. Label speakers as "Host" or"Guest" if you cannot identify specific names, however you should use clues to try and identify them by name.
3. Format each line as "Speaker Name: [dialogue]"
4. Preserve the original content and meaning
5. Add stage directions in [brackets] where helpful for context
6. Remove filler words like "um", "uh", "you know" for readability
7. Break long speeches into natural paragraphs
8. Maintain the original order of dialogue
9. Do not include any introductory text or explanations about what you are doing.
10. Be liberal in identifying speakers based on context, even if not explicitly stated in the transcript.
11. Do not add descriptions of visual elements- you cannot see what is happening!

Example format:
Ezra Klein: Welcome to today's show. I'm Ezra Klein here with my guest John Doe.
John Doe: Thanks for having me on the show.
Ezra Klein: Here's my first question for you...
[Discussion continues...]

Please use this additional information to intuit which speakers are talking at any point:

Podcast description: {episode.podcast.description}
Podcast summary: {episode.podcast.summary}
Episode description: {episode.description}
"""

def get_episode_summary_prompt(transcript):
    """
    Generate a prompt for creating an episode summary from a transcript.
    
    Args:
        transcript: The full podcast transcript to summarize
    
    Returns:
        str: Formatted prompt for episode summary generation
    """
    return f"""Summarize this podcast episode in 200-400 words. Include the main topic, key points, participants, and takeaways:

{transcript}"""


def get_quote_extraction_prompt(transcript):
    """
    Generate a prompt for extracting key quotes from a podcast episode transcript.
    
    Args:
        transcript: The podcast transcript to analyze for quotes
    
    Returns:
        str: Formatted prompt for quote extraction
    """
    return f"""Please analyze the following podcast episode transcript and extract up to 12 of the most interesting quotes. 
Focus on snippets that are particularly:
- Entertaining or funny
- Controversial or thought-provoking
- Informative or insightful
- Memorable or quotable

For each quote, provide:
1. The exact quote text (keep it concise, ideally 1-3 sentences)
2. The speaker (if identifiable from context, otherwise use "Unknown")
3. A category: memorable, funny, controversial, key_insight, or educational
4. Brief context if helpful

Format your response as JSON with this structure:
{{
    "quotes": [
        {{
            "text": "The exact quote text here",
            "speaker": "Speaker name or Unknown",
        }}
    ]
}}

Transcript:
{transcript}"""