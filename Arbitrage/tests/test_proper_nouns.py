
from matcher import MarketMatcher
from models import StandardMarket

def test_proper_nouns():
    matcher = MarketMatcher()
    
    # Test 1: Inter vs Como (Distinct Proper Nouns)
    t1 = "Will Inter finish top 4?"
    t2 = "Will Como finish top 4?"
    result = matcher._check_proper_nouns(t1, t2)
    print(f"'{t1}' vs '{t2}' -> Passed? {result} (Expected: False)")
    assert result == False

    # Test 2: Turkey vs Ukraine (Distinct Proper Nouns)
    t1 = "Will Putin visit Turkey?"
    t2 = "Will Putin visit Ukraine?"
    result = matcher._check_proper_nouns(t1, t2)
    print(f"'{t1}' vs '{t2}' -> Passed? {result} (Expected: False)")
    assert result == False
    
    # Test 3: Same Entity
    t1 = "Will BTC hit 100k?"
    t2 = "Will BTC hit 100k?"
    result = matcher._check_proper_nouns(t1, t2)
    print(f"'{t1}' vs '{t2}' -> Passed? {result} (Expected: True)")
    assert result == True

    print("\nALL TESTS PASSED")

if __name__ == "__main__":
    test_proper_nouns()
