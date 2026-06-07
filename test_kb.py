"""
Quick connectivity test — run this before world.py to verify APIs are reachable.
    python test_kb.py
"""
import urllib.request, json, os, sys

def test(name, url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent":"DigitalWorld-Test/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
            # Try to find a result count
            count = (data.get("count") or data.get("total") or
                     len(data.get("results", data.get("items", data if isinstance(data,list) else []))))
            print(f"  OK  {name:<30} → {count} results")
            return True
    except Exception as e:
        print(f"  FAIL {name:<30} → {e}")
        return False

print("\n=== Digital World — API Connectivity Test ===\n")

results = []
results.append(test("Gutenberg fiction",     "https://gutendex.com/books/?topic=fiction&languages=en&copyright=false"))
results.append(test("Gutenberg history",     "https://gutendex.com/books/?topic=history&languages=en&copyright=false"))
results.append(test("NASA APOD",             f"https://api.nasa.gov/planetary/apod?api_key={os.getenv('NASA_API_KEY','DEMO_KEY')}&count=3"))
results.append(test("GitHub trending",       "https://api.github.com/search/repositories?q=stars:>1000+language:python&sort=stars&per_page=5"))
results.append(test("Internet Archive",      "https://archive.org/advancedsearch.php?q=mediatype:texts&fl=title&rows=3&output=json"))

shodan_key = os.getenv("SHODAN_API_KEY","")
if shodan_key and shodan_key != "your-shodan-key-here":
    results.append(test("Shodan",            f"https://api.shodan.io/api-info?key={shodan_key}"))
else:
    print(f"  SKIP {'Shodan':<30} → no key set")

print(f"\n{'='*47}")
passed = sum(results)
print(f"  {passed}/{len(results)} APIs reachable\n")

if passed == 0:
    print("  All APIs failed — check your internet connection.")
elif passed < len(results):
    print("  Some APIs failed — the world will still run,")
    print("  those biomes will just have less data.")
else:
    print("  All good — run python world.py")
