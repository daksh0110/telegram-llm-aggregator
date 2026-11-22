import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(BACKEND_DIR / ".env")

# Edit these values to change model behavior. Keep credentials in backend/.env.
LLM_PROVIDER = "ollama"
LLM_BATCH_SIZE = 5
GEMINI_MODEL = "gemini-3.8-flash"
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "phi3:latest"
LLM_PROMPT_PATH = Path("prompts/job_filter.txt")


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    llm_batch_size: int
    llm_prompt_path: Path
    gemini_api_key: str
    gemini_model: str
    ollama_base_url: str
    ollama_model: str


if LLM_PROVIDER not in {"gemini", "ollama"}:
    raise ValueError("LLM_PROVIDER must be either 'gemini' or 'ollama'.")
if not isinstance(LLM_BATCH_SIZE, int) or isinstance(LLM_BATCH_SIZE, bool):
    raise ValueError("LLM_BATCH_SIZE must be a positive integer.")
if LLM_BATCH_SIZE < 1:
    raise ValueError("LLM_BATCH_SIZE must be a positive integer.")
if not GEMINI_MODEL.strip():
    raise ValueError("GEMINI_MODEL must not be empty.")
if not OLLAMA_MODEL.strip():
    raise ValueError("OLLAMA_MODEL must not be empty.")

prompt_path = Path(LLM_PROMPT_PATH)
if not prompt_path.is_absolute():
    prompt_path = BACKEND_DIR / prompt_path

settings = Settings(
    llm_provider=LLM_PROVIDER,
    llm_batch_size=LLM_BATCH_SIZE,
    llm_prompt_path=prompt_path.resolve(),
    gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
    gemini_model=GEMINI_MODEL.strip(),
    ollama_base_url=OLLAMA_BASE_URL.rstrip("/"),
    ollama_model=OLLAMA_MODEL.strip(),
)
