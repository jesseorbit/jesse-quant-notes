# Market Discovery Issue - Need User Input

## Current Status

Updated the discovery logic to search for crypto Up/Down markets by removing:
- Time keyword filtering ("15 minute" etc.)
- enableOrderBook filter (not reliably set in API)
- Closed market filter (markets close quickly)

## Problem

Cannot locate markets matching the pattern: "bitcoin up and down December 17,12-12:15AM ET"

**Searches performed**:
- Scanned 2,000 markets from Gamma API
- Searched for "bitcoin up and down" - no matches in first 100 markets
- Searched for asset + "up"/"down" keywords - found wrong markets (old closed ones)

## Need from User

To fix the discovery logic, I need:

1. **Exact full question text** for one of these markets
2. **Market status**: Are they currently open or closed?
3. **Market ID or slug** if available
4. **URL** from Polymarket website if accessible

## Alternative Approach

If you can access one of these markets on Polymarket's website:
- Copy the full market question
- Share the URL (contains market slug/ID)
- This will let me reverse-engineer the exact search pattern

## Current Discovery Results

The updated logic found 7/8 markets but they're incorrect:
- "What will the price of Bitcoin be on November 4th, 2020?" (old, closed)
- "Will $BTC break $20k before 2021?" (old, closed)
- etc.

These match "up"/"down" keywords but aren't the 15-minute time-window markets you're looking for.
