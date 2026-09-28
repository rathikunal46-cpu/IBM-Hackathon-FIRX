import os, re

ext_path = os.path.expandvars('%LOCALAPPDATA%') + r'\Programs\IBM Bob1\resources\app\extensions\bob-code\dist\extension.js'
with open(ext_path, 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Find the actual model passed in the request body
for m in re.finditer(r'chat/completions', content):
    start = max(0, m.start()-600)
    end   = min(len(content), m.end()+400)
    snippet = content[start:end]
    print('=== snippet around chat/completions ===')
    print(snippet[:900])
    print()
    break  # just first one
