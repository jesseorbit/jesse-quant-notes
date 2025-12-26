
import os
import logging
from dotenv import load_dotenv

# Load env vars
load_dotenv()

from services.llm_verifier import LLMVerifier

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_llm_verification():
    print("Initializing LLMVerifier...")
    verifier = LLMVerifier()
    
    if not verifier.client:
        print("Skipping test: No OpenAI API Key found.")
        return

    test_cases = [
        (
            "Will Inter finish in the top 4?", 
            "Will Como finish in the top 4?", 
            False # Expect NO
        ),
        (
            "Will Bitcoin hit $100k in 2024?",
            "Will BTC reach 100,000 USD in 2024?",
            True # Expect YES
        ),
        (
            "Will Putin visit Turkey in 2024?",
            "Will Putin visit Ukraine in 2024?",
            False # Expect NO
        )
    ]
    
    print("\nRunning Test Cases...")
    for title_a, title_b, expected in test_cases:
        print(f"\nA: {title_a}")
        print(f"B: {title_b}")
        result = verifier.verify_match(title_a, title_b)
        status = "PASS" if result == expected else "FAIL"
        print(f"Result: {result} | Expected: {expected} -> {status}")

if __name__ == "__main__":
    test_llm_verification()
