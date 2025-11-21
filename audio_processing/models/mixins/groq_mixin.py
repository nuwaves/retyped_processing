import logging
from django.conf import settings
import requests
import re
from constance import config
import os
import tempfile
import os
from audio_processing.models.mixins.audio_chunking import transcribe_audio_in_chunks
from pathlib import Path

logger = logging.getLogger(__name__)

class GroqMixin():
    """
    Mixin providing Groq API integration for various LLM tasks.
    """
    
    def get_groq_completion(self, prompt, model=None, max_tokens=1000, temperature=0.3):
        """
        Generic method to get completions from Groq API.
        
        Args:
            prompt (str): The prompt to send to the model
            model (str, optional): Model name, defaults to llama3-70b-8192
            max_tokens (int): Maximum tokens in response
            temperature (float): Temperature for response generation
            
        Returns:
            str: The completion content or None if failed
        """
        url = "https://api.groq.com/openai/v1/chat/completions"
        api_key = getattr(settings, 'GROQ_API_KEY', '')
        if not api_key:
            logger.error("GROQ_API_KEY not configured")
            return None
        
        # Default model if none specified
        if model is None:
            model = getattr(config, 'DEFAULT_MODEL', 'llama-3.1-8b-instant')
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            
            result = response.json()
            content = result['choices'][0]['message']['content'].strip()
            
            # Remove any <think> tags that might be present
            content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
            
            return content
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Groq API request failed: {str(e)}")
            return None
        except (KeyError, IndexError) as e:
            logger.error(f"Unexpected Groq API response format: {str(e)}")
            return None

    def get_transcript_from_groq(self):
        """
        Get transcript from Groq Whisper API. If file >100MB, use AudioChunkingMixin to chunk, transcribe, and stitch together.
        Returns:
            str: The transcript text or None if failed
        """
        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        api_key = getattr(settings, 'GROQ_API_KEY', '')
        if not api_key:
            logger.error("GROQ_API_KEY not configured")
            return None
        headers = {"Authorization": f"Bearer {api_key}"}
        clean_url = self.s3_audio_url
        if clean_url is None:
            clean_url = self.clean_url(self.raw_audio_url)
        tmp_path = None
        try:
            with requests.get(clean_url, stream=True, timeout=300) as r:
                r.raise_for_status()
                with tempfile.NamedTemporaryFile(delete=False) as tmp:
                    for chunk in r.iter_content(chunk_size=65536):
                        tmp.write(chunk)
                    tmp_path = tmp.name
            file_size = os.path.getsize(tmp_path)
            max_chunk_size = 100 * 1024 * 1024  # 100MB
            if file_size > max_chunk_size:
                # Use the mixin to chunk and transcribe
                result = transcribe_audio_in_chunks(Path(tmp_path))
                transcript = result.get("text", "")
            else:
                # Single file, send as usual
                with open(tmp_path, 'rb') as f:
                    files = {
                        "url": (None, clean_url),
                        "model": (None, config.TEXT_TO_SPEECH_MODEL),
                        "language": (None, "en"),
                        "response_format": (None, "json"),
                    }
                    response = requests.post(url, headers=headers, files=files)
                    response.raise_for_status()
                    transcript = response.json().get("text", "")
            if transcript.strip():
                self.transcript = transcript
                self.save()
                logger.info(f"Transcript updated for: {self.raw_audio_url}")
                return transcript
            else:
                logger.warning(f"No transcript returned for: {self.raw_audio_url}")
                return None
        finally:
            if tmp_path:
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    
    def generate_speaker_script(self):
        """
        Use Groq LLM to convert the raw transcript into a formatted script with speaker identification.
        Returns the script transcript or None if failed.
        """
        # Validate transcript
        if not self._validate_transcript():
            return None
        
        logger.info(f"Generating speaker script for: {self.raw_audio_url}")
        
        try:
            # Get the prompt from prompts file
            prompt = get_speaker_transcript_prompt(self)
            
            # Use the generic completion method
            script_content = self.get_groq_completion(
                prompt=prompt,
                model=getattr(config, 'SPEAKER_MODEL', None),
                max_tokens=8000,
                temperature=0.3
            )
            
            if script_content:
                self.script_transcript = script_content
                self.save()
                logger.info(f"Speaker script generated for: {self.raw_audio_url}")
                return script_content
            else:
                logger.warning(f"No script content returned for: {self.raw_audio_url}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to generate speaker script: {str(e)}")
            return None

    def _validate_transcript(self):
        """
        Validate that the transcript exists and is suitable for processing.
        
        Returns:
            bool: True if transcript is valid, False otherwise
        """
        if not hasattr(self, 'transcript') or not self.transcript:
            logger.warning(f"No transcript available for: {getattr(self, 'raw_audio_url', 'Unknown')}")
            return False
        
        if not self.transcript.strip():
            logger.warning(f"Empty transcript for: {getattr(self, 'raw_audio_url', 'Unknown')}")
            return False
        
        return True