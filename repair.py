import re, os
path = "lotto_server.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

# Fix unclosed quotes in common dictionary patterns
# Example: "official_result": "誘몄텛泥?,
# Becomes: "official_result": "미추첨",
text = re.sub(r'诱쒖텛泥\?,', '"미추첨",', text)
text = re.sub(r'诱곗떦泥\?,', '"미당첨",', text)
text = re.sub(r'诱쒖텛泥\? ', '"미추첨" ', text)
text = re.sub(r'诱곗떦泥\? ', '"미당첨" ', text)

# Find any line that ends with unclosed quote and comma
# Regex for: name: "something [missing quote],
text = re.sub(r'": "([^"]+),', r'": "\1",', text)

# Also fix the playwright args in one go
new_args = 'args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--disable-software-rasterizer", "--single-process", "--js-flags=--max-old-space-size=128", "--disable-blink-features=AutomationControlled"]'
text = re.sub(r'args=\[[^\]]+\]', new_args, text)

with open("lotto_server_fixed.py", "w", encoding="utf-8") as f:
    f.write(text)
print("SUCCESS")
