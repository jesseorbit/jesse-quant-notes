
from matcher import MarketMatcher

def test_location_mismatch():
    matcher = MarketMatcher()
    
    # Case From User
    t1 = "Will Zelenskyy and Putin meet next in US?"
    t2 = "Will Putin and Zelenskyy meet next in Turkey?"
    
    # Raw titles might be casing preserved
    
    print("\n--- Test Location Mismatch ---")
    
    # 1. Check Proper Nouns extraction
    print(f"Title 1: {t1}")
    print(f"Title 2: {t2}")
    
    pn1 = matcher._check_proper_nouns(t1, t2) # wait, this returns bool, I want to debug internals
    # Let's verify via the public method
    result = matcher._check_proper_nouns(t1, t2)
    print(f"Result (Should be False): {result}")
    
    if result == True:
        print("FAILURE: Matcher incorrectly accepted the mismatch.")
    else:
        print("SUCCESS: Matcher correctly rejected the mismatch.")

if __name__ == "__main__":
    test_location_mismatch()
