from pathlib import Path
import os
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')


def integer(name, default, minimum, maximum):
    value = int(os.getenv(name, str(default)))
    if not minimum <= value <= maximum:
        raise ValueError(f'{name} must be {minimum}..{maximum}')
    return value


PORT = integer('PORT', 4317, 1024, 65535)
MODEL = os.getenv('LLM_MODEL', '')
API_KEY = os.getenv('LLM_API_KEY') or os.getenv('OPENAI_API_KEY', '')
BASE_URL = os.getenv('LLM_BASE_URL') or os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')
MODEL_TIMEOUT = integer('LLM_TIMEOUT_MS', 60000, 100, 300000) / 1000
MAX_STEPS = integer('AGENT_MAX_STEPS', 24, 1, 100)
MAX_TOOLS = integer('AGENT_MAX_TOOL_CALLS', 60, 1, 200)
RUN_TIMEOUT = integer('AGENT_TIMEOUT_MS', 180000, 1000, 900000) / 1000
ARTIFACTS = ROOT / 'artifacts'
PLANNER_MODEL = os.getenv('PLANNER_MODEL') or MODEL
PLANNER_BASE_URL = os.getenv('PLANNER_BASE_URL') or BASE_URL
PLANNER_API_KEY = os.getenv('PLANNER_API_KEY') or API_KEY
COMPOSITION_MODEL = os.getenv('COMPOSITION_MODEL') or PLANNER_MODEL
COMPOSITION_BASE_URL = os.getenv('COMPOSITION_BASE_URL') or PLANNER_BASE_URL
COMPOSITION_API_KEY = os.getenv('COMPOSITION_API_KEY') or PLANNER_API_KEY
TASK_RUN_CONCURRENCY = integer('TASK_RUN_CONCURRENCY', 4, 1, 16)
TASK_MODEL_CONCURRENCY = integer('TASK_MODEL_CONCURRENCY', 4, 1, 16)
TASK_READ_CONCURRENCY = integer('TASK_READ_CONCURRENCY', 8, 1, 32)


def public_config():
    return {'modelConfigured': bool(API_KEY and MODEL), 'model': MODEL or None,
            'maxSteps': MAX_STEPS, 'backend': 'python', 'enableThinking': False,
            'connectors': {
                'erpnext': all(os.getenv(key) for key in ['ERPNEXT_BASE_URL', 'ERPNEXT_API_KEY', 'ERPNEXT_API_SECRET']),
                'zammad': all(os.getenv(key) for key in ['ZAMMAD_BASE_URL', 'ZAMMAD_API_TOKEN'])}}

# Judge role defaults to the configured executor; report same-model judging explicitly.
JUDGE_MODEL = os.getenv("JUDGE_MODEL") or MODEL
JUDGE_BASE_URL = os.getenv("JUDGE_BASE_URL") or BASE_URL
JUDGE_API_KEY = os.getenv("JUDGE_API_KEY") or API_KEY
