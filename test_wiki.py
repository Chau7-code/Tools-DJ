import wikipedia
import re

wikipedia.set_lang('fr')

def get_wiki_year(query):
    print(f"\n--- Testing: {query}")
    try:
        results = wikipedia.search(f"{query} chanson")
        if not results:
            results = wikipedia.search(query)
            
        if results:
            page_title = results[0]
            print(f"  Matched Page: {page_title}")
            page = wikipedia.page(page_title, auto_suggest=False)
            
            # The summary or the first 500 words usually contains the year
            # Looking for patterns like "en 1982" or "sorti en 1982" or "paru en 1982"
            content = page.content[:1500].lower()
            
            # Pattern 1: sorti(e) en XXXX, paru(e) en XXXX or date: XXXX
            patterns = [
                r'sorti[e]?\s+en\s+([1-2][0-9]{3})\b',
                r'paru[e]?\s+en\s+([1-2][0-9]{3})\b',
                r'date de sortie.*?(19\d{2}|20\d{2})',
                r'\([1-2][0-9]{3}\)', # Just a year in brackets next to title usually
                r'\b(19\d{2}\b|20[0-2]\d)\b' # Fallback to any sensible year
            ]
            
            for pat in patterns:
                matches = re.findall(pat, content)
                if matches:
                    # Clean up if matched a tuple
                    year = int(matches[0]) if type(matches[0]) == str else int(matches[0][0] if type(matches[0]) == tuple else matches[0])
                    print(f"  => Found Date: {year} (Pattern: {pat})")
                    return year
            print("  No sensible year found in first paragraphs.")
        else:
            print("  No wikipedia page found.")
    except Exception as e:
        print(f"  Error: {e}")
    return None

def test():
    test_cases = [
        "Michael Jackson Billie Jean",
        "Goldman Quand la musique est bonne",
        "Jul Alors la zone",
        "OBOY Cabeza",
        "Tame Impala The Less I Know the Better",
        "Ziak Akimbo"
    ]
    for t in test_cases:
        get_wiki_year(t)

if __name__ == "__main__":
    test()
