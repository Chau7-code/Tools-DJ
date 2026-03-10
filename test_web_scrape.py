import re
import time
from duckduckgo_search import DDGS

def search_release_year_web(query, outfile):
    out = f"Searching web for: {query}\n"
    ddgs = DDGS()
    try:
        search_term = f"date de sortie chanson {query}"
        results = list(ddgs.text(search_term, max_results=3))
        
        years_found = []
        out += "  Raw text snippets:\n"
        for r in results:
            text = r.get("body", "") + " " + r.get("title", "")
            matches = re.findall(r'\b(19[5-9]\d|20[0-2]\d)\b', text)
            years_found.extend(matches)
            out += f"    > {r.get('body')[:150]} ...\n"
             
        if years_found:
            from collections import Counter
            common = Counter(years_found).most_common(1)
            year = int(common[0][0])
            out += f"  => Detected year: {year}\n"
            return out
    except Exception as e:
        out += f"  Error: {e}\n"
    return out

def test():
    test_cases = [
        "Michael Jackson Billie Jean",
        "Goldman Quand la musique est bonne",
        "Jul Alors la zone",
        "OBOY Cabeza",
        "Tame Impala The Less I Know the Better"
    ]
    with open("scrape_out.txt", "w", encoding="utf-8") as f:
        for t in test_cases:
            f.write(search_release_year_web(t, f) + "\n")
            time.sleep(2)

if __name__ == "__main__":
    test()
