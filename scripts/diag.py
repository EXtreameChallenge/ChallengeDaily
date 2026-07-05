import config
import json
from pathlib import Path
from crypto import has_vault, load_secret

print(f"AI_ENABLED (settings): {config.load_settings().get('ai_enabled')}")
print(f"AI_VISION_MODEL: {config.AI_VISION_MODEL}")
print(f"AI_TEXT_MODEL: {config.AI_TEXT_MODEL}")
print(f"AI_API_KEY present: {bool(config.AI_API_KEY)}")
if config.AI_API_KEY:
    k = config.AI_API_KEY
    print(f"AI_API_KEY preview: {k[:4]}...{k[-4:]} (len={len(k)})")
else:
    print("AI_API_KEY is empty")
print(f"vault exists: {has_vault()}")
if has_vault():
    v = load_secret('ai_api_key', '')
    print(f"vault ai_api_key present: {bool(v)}")
    if v:
        print(f"vault key preview: {v[:4]}...{v[-4:]} (len={len(v)})")
