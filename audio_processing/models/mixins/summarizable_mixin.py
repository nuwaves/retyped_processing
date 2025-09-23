import logging
from django.conf import settings
import requests
import re
from audio_processing.prompts import get_episode_summary_prompt
from constance import config


logger = logging.getLogger(__name__)


class SummarizableMixin:
    """
    Mixin to provide summarization functionality using Groq LLM for content summarization.
    """
    
    def generate_summary(self):
        """
        Generate a summary of the content using Groq LLM based on the transcript.
        Returns the summary text or None if failed.
        
        """
        # Validate transcript
        if not hasattr(self, 'transcript') or not self.transcript or not self.transcript.strip():
            logger.warning(f"No transcript available for summary generation: {getattr(self, 'raw_audio_url', str(self))}")
            return None
        
        logger.info(f"Generating summary for {self.__class__.__name__}: {getattr(self, 'raw_audio_url', str(self))}")
        
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            api_key = getattr(settings, 'GROQ_API_KEY', '')
            
            if not api_key:
                logger.error("GROQ_API_KEY not configured")
                return None
            
            # Limit transcript to first 130,000 tokens (roughly 100,000 words)
            # Approximating 1.3 characters per token for English text
            max_chars = 120000 * 1.3 # ~169,000 characters
            limited_transcript = self.transcript[:int(max_chars)]
            if len(self.transcript) > len(limited_transcript):
                logger.info(f"Transcript truncated from {len(self.transcript)} to {len(limited_transcript)} characters for summary generation")
            
            # Get the prompt from prompts file
            prompt = get_episode_summary_prompt(limited_transcript)
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
            "model": config.SUMMARY_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.3,
                "max_tokens": 8192
            }
            
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            
            result = response.json()
            summary_content = result['choices'][0]['message']['content'].strip()
            
            # Remove <think></think> blocks that some models include
            summary_content = re.sub(r'<think>.*?</think>', '', summary_content, flags=re.DOTALL).strip()
            
            if summary_content:
                if hasattr(self, 'summary'):
                    self.summary = summary_content
                    self.save()
                    logger.info(f"Summary generated for {self.__class__.__name__}: {getattr(self, 'raw_audio_url', str(self))}")
                else:
                    logger.warning(f"Model {self.__class__.__name__} does not have a 'summary' field")
                return summary_content
            else:
                logger.warning(f"No summary content returned for {self.__class__.__name__}: {getattr(self, 'raw_audio_url', str(self))}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed for summary generation: {str(e)} and response was: {response.json() if 'response' in locals() else 'N/A'}")
            return None
        except Exception as e:
            logger.error(f"Failed to generate summary for {self.__class__.__name__}: {str(e)}")
            return None
