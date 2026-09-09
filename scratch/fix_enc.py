from pathlib import Path
p = Path('python/ingestion/unified_fetch.py')
text = p.read_text(encoding='utf-8')
text = text.replace(', "w")', ', "w", encoding="utf-8")')
p.write_text(text, encoding='utf-8')
print("Done")
