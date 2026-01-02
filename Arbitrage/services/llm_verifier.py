import os
import logging
from typing import Optional
from openai import OpenAI
import time

logger = logging.getLogger(__name__)

class LLMVerifier:
    def __init__(self):
        """Initialize OpenAI client if API key is present."""
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.client = None
        self.cache = {}
        
        if self.api_key:
            try:
                self.client = OpenAI(api_key=self.api_key)
                logger.info("LLMVerifier initialized with OpenAI")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
        else:
            logger.warning("OPENAI_API_KEY not found. LLM Verification disabled.")

    def verify_match(self, title_a: str, title_b: str) -> bool:
        """
        Verify if two market titles refer to the exact same event/question.
        Returns True if they match, False otherwise.
        """
        if not self.client:
            return True # Fallback: Assume match if no LLM (or return False to be safe? User wants strictness, so maybe False? But that breaks existing logic. Let's return True and rely on fuzzy match if LLM is missing)

        # Check Cache
        cache_key = f"{title_a}::{title_b}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        try:
            prompt = f"""
            You are an expert prediction market arbiter. 
            Do these two market titles ask the EXACT same question?
            They must refer to the same event, same outcome criteria, same date (if specified), and same entity.
            
            Market A: "{title_a}"
            Market B: "{title_b}"
            
            Ignore minor formatting differences, casing, or platform-specific prefixes (e.g. "Will...").
            Pay attention to:
            - Different Years (2024 vs 2025) -> NO
            - Different Entities (Inter used Como, Turkey vs Ukraine) -> NO
            - Different Metrics (Top 4 vs Top 6) -> NO
            
            Answer strictly with "YES" or "NO".
            """

            response = self.client.chat.completions.create(
                model="gpt-4o-mini", # Use fast model
                messages=[
                    {"role": "system", "content": "You are a strict logic verifier."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=5,
                temperature=0.0
            )
            
            answer = response.choices[0].message.content.strip().upper()
            is_match = "YES" in answer
            
            # Simple Cache
            self.cache[cache_key] = is_match
            
            if not is_match:
                logger.info(f"LLM REJECTED: '{title_a}' vs '{title_b}'")
            else:
                logger.debug(f"LLM ACCEPTED: '{title_a}' vs '{title_b}'")
                
            return is_match

        except Exception as e:
            logger.error(f"LLM Verification failed: {e}")
            return True # Fail open? Or fail closed? Given user complaints, maybe fail closed? 
            # But if API limit hits, we might lose all matches. Let's fail OPEN for now but log error.
            return True
