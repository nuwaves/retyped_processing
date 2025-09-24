import logging
import json
import re

from audio_processing.prompts import get_quote_extraction_prompt

logger = logging.getLogger(__name__)


class QuotableMixin():
    """
    Mixin for models that can have quotes extracted from their content.
    
    This mixin provides functionality to extract memorable quotes using LLM analysis
    and create Quote objects associated with the model instance.
    """

    def extract_quotes(self):
        """
        Extract key quotes from the model's transcript using LLM.
        Creates Quote objects for entertaining, funny, controversial, or informative snippets.
        
        Returns:
            list: List of created Quote objects
        """
        # Check if the model has a transcript
        if not hasattr(self, 'transcript') or not self.transcript or not self.transcript.strip():
            logger.warning(f"No transcript available for quote extraction: {getattr(self, 'raw_audio_url', 'Unknown')}")
            return []
        
        try:            
            # Prepare the prompt for quote extraction
            # Limit transcript length to avoid token limits
            transcript_excerpt = self.transcript[:8000]
            prompt = get_quote_extraction_prompt(transcript_excerpt)
            
            response = self.get_groq_completion(prompt, max_tokens=2000)
            if not response:
                logger.error(f"Failed to get LLM response for quote extraction: {getattr(self, 'raw_audio_url', 'Unknown')}")
                return []
            cleaned_response = response
            # Remove everything before the first code block (if present)
            code_block_match = re.search(r'```json(.*?)```', cleaned_response, re.DOTALL | re.IGNORECASE)
            if code_block_match:
                cleaned_response = code_block_match.group(1)
            # If not found, fallback to removing any generic code block
            else:
                code_block_match = re.search(r'```(.*?)```', cleaned_response, re.DOTALL)
                if code_block_match:
                    cleaned_response = code_block_match.group(1)
            cleaned_response = cleaned_response.strip('`\n ')
            # Parse JSON response
            try:
                quote_data = json.loads(cleaned_response)
                quotes_list = quote_data.get('quotes', [])
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse quote extraction JSON: {str(e)} | Raw: {cleaned_response[:200]}")
                # Try to extract quotes from a more flexible format
                quotes_list = self._parse_quotes_fallback(cleaned_response)
            
            # Create Quote objects
            return self._create_quote_objects(quotes_list)
            
        except Exception as e:
            logger.error(f"Error during quote extraction: {str(e)}")
            return []

    def _parse_quotes_fallback(self, response_text):
        """
        Fallback method to parse quotes from LLM response when JSON parsing fails.
        Looks for quote patterns in the text.
        
        Args:
            response_text (str): The LLM response text to parse
            
        Returns:
            list: List of quote dictionaries
        """
        quotes = []
        try:
            # Look for quote-like patterns in the response
            quote_patterns = [
                r'"([^"]+)"\s*-\s*([^,\n]+)',  # "quote" - speaker
                r'"([^"]+)".*?(?:Speaker|speaker):\s*([^,\n]+)',  # "quote" speaker: name
                r'Quote:\s*"([^"]+)".*?(?:Speaker|speaker):\s*([^,\n]+)',  # Quote: "text" speaker: name
            ]
            
            for pattern in quote_patterns:
                matches = re.findall(pattern, response_text, re.IGNORECASE | re.MULTILINE)
                for match in matches[:12]:  # Limit to 12
                    if len(match) >= 2 and len(match[0].strip()) >= 10:
                        quotes.append({
                            'text': match[0].strip(),
                            'speaker': match[1].strip() if match[1].strip() else None,
                        })
                
                if quotes:  # If we found quotes with this pattern, stop trying others
                    break
                    
        except Exception as e:
            logger.error(f"Error in fallback quote parsing: {str(e)}")
        
        return quotes

    def _create_quote_objects(self, quotes_list):
        """
        Create Quote objects from the parsed quote data.
        
        Args:
            quotes_list (list): List of quote dictionaries
            
        Returns:
            list: List of created Quote objects
        """
        # Import Quote model
        from audio_processing.models.quote import Quote
        
        created_quotes = []
        
        for quote_info in quotes_list[:12]:  # Limit to 12 quotes max
            try:
                # Validate required fields
                quote_text = quote_info.get('text', '').strip()
                if not quote_text or len(quote_text) < 10:
                    continue
                
                speaker = quote_info.get('speaker', '').strip() or None
                
                # Create the Quote object - assumes the model is an Episode
                quote = Quote.objects.create(
                    episode=self,
                    text=quote_text,
                    speaker=speaker,
                )

                created_quotes.append(quote)
                logger.info(f"Created quote: {quote_text[:50]}...")
                
            except Exception as e:
                logger.error(f"Failed to create quote: {str(e)}")
                continue
        
        model_title = getattr(self, 'title', 'Unknown')
        logger.info(f"Extracted {len(created_quotes)} quotes from: {model_title}")
        return created_quotes

    def get_quotes(self):
        """
        Get all quotes associated with this model instance.
        
        Returns:
            QuerySet: Quote objects related to this instance
        """
        from audio_processing.models.quote import Quote
        return Quote.objects.filter(episode=self).order_by('-created_at')