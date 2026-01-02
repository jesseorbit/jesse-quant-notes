"""
Text processing utilities for market title normalization.
"""

import re


def normalize_title(title: str) -> str:
    """
    Normalize market title for better matching.
    
    Steps:
    1. Convert to lowercase
    2. Remove special characters (keep alphanumeric and spaces)
    3. Remove extra whitespace
    4. Strip leading/trailing spaces
    
    Args:
        title: Raw market title
        
    Returns:
        Normalized title string
    """
    # Convert to lowercase
    normalized = title.lower()
    
    # Remove special characters, keep alphanumeric and spaces
    normalized = re.sub(r'[^a-z0-9\s]', ' ', normalized)
    
    # Remove extra whitespace
    normalized = re.sub(r'\s+', ' ', normalized)
    
    # Strip leading/trailing spaces
    normalized = normalized.strip()
    
    return normalized


def extract_keywords(title: str) -> set:
    """
    Extract important keywords from title.
    
    Args:
        title: Market title
        
    Returns:
        Set of important keywords
    """
    # Common words to ignore
    stop_words = {
        'will', 'be', 'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for',
        'of', 'and', 'or', 'by', 'before', 'after', 'than', 'more', 'less'
    }
    
    normalized = normalize_title(title)
    words = normalized.split()
    
    # Filter out stop words and short words
    keywords = {w for w in words if len(w) > 2 and w not in stop_words}
    
    return keywords


def has_common_keywords(title1: str, title2: str, min_common: int = 2) -> bool:
    """
    Check if two titles share important keywords.
    
    Args:
        title1: First title
        title2: Second title
        min_common: Minimum number of common keywords required
        
    Returns:
        True if titles share at least min_common keywords
    """
    keywords1 = extract_keywords(title1)
    keywords2 = extract_keywords(title2)
    
    common = keywords1 & keywords2
    
    return len(common) >= min_common
