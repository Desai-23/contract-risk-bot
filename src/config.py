import os

from dotenv import load_dotenv

load_dotenv()

# Ollama local LLM config (Phase 2+ will use this)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "phi3").strip()

# Audit + exports
AUDIT_LOG_PATH = os.getenv("AUDIT_LOG_PATH", "logs/audit.jsonl").strip()
EXPORT_DIR = os.getenv("EXPORT_DIR", "exports").strip()
