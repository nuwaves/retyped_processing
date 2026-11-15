import json


def get_entity_extraction_prompt(text):
    """
    Generate a prompt for extracting named entities from text.
    """
    return (
        "Extract named entities (Person, Organization, Product) from the following text. Attempt to give a complete common first name and last name for - for example 'Joe Biden' and not 'Biden' but 'Bill Gates' and not 'William Gates'"
        "Return a JSON array of objects with 'name' and 'type' (PERSON, ORGANIZATION, PRODUCT). Return only the JSON. Your entire response should be a valid JSON object."
        'Example: [{"name": "John Doe", "type": "PERSON"}, {"name": "Acme Corp", "type": "ORGANIZATION"}].\n\nText:\n'
        + text
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
Do not include any additional text or explanations.

Use only the provided tags ids and do not select more than 10 tags."""


def get_speaker_transcript_prompt(
    episode,
    transcript=None,
    part=1,
    total_parts=1,
    known_speakers=(),
    previous_tail="",
    last_speaker="",
):
    """
    Generate a prompt for converting a transcript into a speaker-formatted script.

    Long transcripts are sent in parts. For part 2 onwards, pass the speaker
    names used so far and the end of the previous part's script so labels stay
    consistent across parts.

    Args:
        episode: The episode (for podcast/episode descriptions)
        transcript: The transcript text to format; defaults to the whole transcript
        part, total_parts: Which part this is, 1-based
        known_speakers: Speaker labels used in earlier parts
        previous_tail: The last lines of the previous part's script
        last_speaker: Who was speaking when the previous part ended

    Returns:
        str: Formatted prompt for speaker identification and script formatting
    """
    if transcript is None:
        transcript = episode.transcript

    continuation = ""
    if total_parts > 1:
        continuation = f"""
This transcript is long, so it is being formatted in parts. This is part {part} of {total_parts}. Format only the text below; do not summarize it or skip any of it.
"""
        if part > 1:
            speakers = ", ".join(known_speakers) if known_speakers else "none yet"
            continuation += f"""This part continues directly from the previous one. Keep using the same speaker labels: {speakers}.
The previous part's script ended with the lines below. Do not repeat them; continue from where they stop.
---
{previous_tail}
---
"""
            if last_speaker:
                continuation += f"""The previous part ended with {last_speaker} speaking. The transcript was split at an arbitrary point, so the opening of this part may be {last_speaker} still talking or another speaker replying. Decide from the text: if the first sentences continue {last_speaker}'s thought, label them {last_speaker}; if they answer or react to it, label them with whoever is replying.
"""

    return f"""You are an AI assistant that converts podcast transcripts into properly formatted scripts with speaker identification.
{continuation}
Original transcript:
{transcript}

Please rewrite this transcript as a script format with identified speakers. Follow these guidelines:

1. Identify different speakers as best as you can from context clues, speaking patterns, and content
2. Label speakers as "Host" or "Guest" if you cannot identify specific names, however you should use clues to try and identify them by name.
3. Format each line as "Speaker Name: [dialogue]"
4. Preserve the original content and meaning
5. Do not add stage directions, scene descriptions or commentary of your own; every line is something a speaker said
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

Please use this additional information to intuit which speakers are talking at any point:

Podcast description: {episode.podcast.description}
Podcast summary: {episode.podcast.summary}
Episode description: {episode.description}
"""


def get_speaker_names_prompt(episode, intro, samples):
    """
    Ask which person each "Speaker N" label in a publisher transcript is.

    Args:
        episode: The episode (for show and episode descriptions)
        intro: The opening of the transcript, where people introduce themselves
        samples: {label: {"share": percent of words, "lines": [text, ...]}}
    """
    speakers = "\n\n".join(
        f"{label} ({sample['share']}% of the words):\n"
        + "\n".join(f"- {line}" for line in sample["lines"])
        for label, sample in samples.items()
    )
    answer = json.dumps({label: "Full Name or null" for label in samples})
    return f"""This podcast transcript already marks who is speaking with labels like "Speaker 1". Work out the real name of the person behind each label.

Podcast: {episode.podcast.name}
Podcast description: {episode.podcast.description}
Podcast summary: {episode.podcast.summary}
Episode title: {episode.title}
Episode description: {episode.description}

Opening of the transcript:
{intro}

Longest lines from each speaker:

{speakers}

Guidelines:
- Use introductions ("I'm...", "my guest today is..."), people addressed by name, and who the show and episode descriptions say takes part.
- The hosts usually speak the most; guests named in the episode description are likely the other main speakers.
- Each person gets at most one label unless the lines clearly show two labels are the same person.
- Give the full name as commonly written, e.g. "John Coogan".
- Only use a name that appears above. Never guess a name for someone who isn't introduced or described.
- Use null (not the string "null") when you are not confident. A wrong name is worse than none.

Respond with only this JSON object, filled in:
{answer}"""


def get_episode_summary_prompt(
    transcript,
    podcast_description,
    episode_description,
    podcast_name="",
    episode_title="",
):
    """
    Generate a prompt for creating an episode summary from a transcript.

    Args:
        transcript: The full podcast transcript to summarize
        podcast_description: Description of the podcast
        episode_description: Description of the episode
        podcast_name: Name of the show
        episode_title: Title of the episode

    Returns:
        str: Formatted prompt for episode summary generation
    """
    return f"""Write a summary of this podcast episode for someone deciding whether to listen, or who wants the substance without listening. It will be published on the episode's page.

Show: {podcast_name}
Episode title: {episode_title}
Show description: {podcast_description}
Episode description: {episode_description}

Use this markdown structure exactly, with nothing before or after it:

One opening paragraph of 2-3 sentences, with no heading or label: who is talking (names and roles) and what the episode is about. Do not start with "In this episode" or "This episode".

## Key takeaways

5 to 8 bullet points. Each one states a specific claim, argument, number, story or piece of advice from the conversation, and who made it when that matters. Write each so it makes sense on its own.

## Notable quotes

2 or 3 short quotes copied word for word from the transcript, each as a markdown blockquote ending with the speaker's name. Leave this section out if nothing is worth quoting or you cannot tell who said it.

Rules:
- 250 to 450 words in total.
- Be concrete. Prefer "Fraser argues warehouses will absorb data lakes within five years" to "the guests discuss the future of data".
- Every point must come from the transcript. Do not add background, opinions or predictions of your own, and do not write a conclusion, "future directions" or outlook section.
- Do not repeat a point in different words.
- Only people who take part in the conversation count as participants. Someone heard in a played clip, or only mentioned, is not one; neither are historical figures or people who have died.
- The transcript is automatic speech-to-text and misspells names. Use the spelling from the show and episode descriptions when a name appears there.
- Leave out sponsor reads, ads and requests to subscribe or rate the show.

Transcript:
{transcript}
"""


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


def get_topic_selection_prompt(topic_list, episode_text):
    """
    Generate a prompt asking the model to pick the single best-fitting topic.
    """
    return f"""You are an AI assistant that assigns podcast episodes to a topic.

Available topics:
{json.dumps(topic_list, indent=2)}

Episode title and show notes:
{episode_text}

Pick the ONE topic from the list that best fits this episode.
Return ONLY a JSON object with the topic id, for example: {{"topic_id": 3}}
If none of the topics fit, return: {{"topic_id": null}}
Do not include any additional text or explanations."""
