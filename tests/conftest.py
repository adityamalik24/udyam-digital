"""Tests never reach the live LLM: an empty key stops core.llm from loading the one in .env."""
import os
os.environ["LLM_API_KEY"] = ""
