import re
from duckduckgo_search import DDGS
from duckduckgo_search.exceptions import DuckDuckGoSearchException

def search_release_year(query):
    print(f"Searching for: {query}")
    ddgs = DDGS()
    try:
        # Perform a specific query looking for the release year
        results = ddgs.text(f"release year '{query}' song", max_results=3)
        
        years_found = []
        for r in results:
            text = r.get("body", "") + " " + r.get("title", "")
            
            # Extract standard 4 digit years
            matches = re.findall(r'\b(19\d{2}|20\d{2})\b', text)
            years_found.extend(matches)
            
        print("Raw text snippets:")
        for r in results:
             print("  -", r.get('body'))
             
        if years_found:
            # Find the most common/earliest reasonable year
            from collections import Counter
            common = Counter(years_found).most_common(5)
            print("Detected years:", common)
            return min([int(y[0]) for y in common]) # A heuristic: usually the oldest year found is the original release
            
    except Exception as e:
        print("Error:", e)
    return None

def test():
    # A classic 80s song that might have re-releases
    test_cases = [
        "A-ha Take On Me",
        "Michael Jackson Billie Jean",
        "Goldman Quand la musique est bonne",
        "Jul Alors la zone",
        "Ziak Akimbo"
    ]
    
    for t in test_cases:
        year = search_release_year(t)
        print(f"--> Final Result for '{t}': {year}\n")

if __name__ == "__main__":
    test()
