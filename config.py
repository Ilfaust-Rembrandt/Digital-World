"""
╔══════════════════════════════════════════════════════════╗
║                 DIGITAL WORLD — CONFIG                   ║
║           All settings live here. Edit freely.           ║
╚══════════════════════════════════════════════════════════╝

This is the single source of truth for all tunable parameters.
Change values here — never hardcode them in other modules.
"""

import os

# ── LLM Provider ───────────────────────────────────────────────────────────────
# Main world model — used by Yggdrasil for naming, descriptions, evolution details
#
# "openai"    → GPT-4o via OpenAI API
# "anthropic" → Claude via Anthropic API  (pip install anthropic)
# "deepseek"  → DeepSeek via OpenAI-compatible API (free tier available)
# "qwen"      → Qwen-Max via Alibaba DashScope
#
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
LLM_API_KEY  = os.getenv("LLM_API_KEY",  "")

PROVIDER_CONFIG = {
    "openai": {
        "client":   "openai",                   # uses openai.OpenAI()
        "base_url": None,
        "model":    "gpt-4o",
    },
    "anthropic": {
        "client":   "anthropic",                # uses anthropic.Anthropic()
        "base_url": None,
        "model":    "claude-haiku-4-5-20251001", # cheapest Claude — good for Yggdrasil ops
    },
    "deepseek": {
        "client":   "openai",                   # OpenAI-compatible — no extra lib needed
        "base_url": "https://api.deepseek.com",
        "model":    "deepseek-chat",             # free tier available
    },
    "qwen": {
        "client":   "openai",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model":    "qwen-max",
    },
    "gemini": {
        "client":   "openai",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model":    "gemini-2.5-flash",
    },
    "groq": {
        "client":   "openai",
        "base_url": "https://api.groq.com/openai/v1",
        "model":    "llama-3.3-70b-versatile",  # 1k req/day free
    },
    "cerebras": {
        "client":   "openai",
        "base_url": "https://api.cerebras.ai/v1",
        "model":    "llama-3.3-70b",            # fastest inference available
    },
    "openrouter": {
        "client":   "openai",
        "base_url": "https://openrouter.ai/api/v1",
        "model":    "meta-llama/llama-3.3-70b-instruct:free",  # :free = no cost
    },
    "nvidia": {
        "client":   "openai",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "model":    "meta/llama-3.3-70b-instruct",
    },
    "ollama": {
        "client":   "openai",                       # uses openai.OpenAI() pointed at localhost
        "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        "model":    os.getenv("OLLAMA_MODEL",    "llama3.2"),  # any model you have pulled
    },
}

# ── MAGI Council — per-seat model config ───────────────────────────────────────
#
# Each MAGI mind can use a completely different provider and model.
# This is what makes them genuinely distinct intelligences.
#
# Recommended setup:
#   SOLOMON  (Data/wisdom)    → Claude Haiku  — careful, broad reasoning
#   SALADIN  (Virus/strategy) → DeepSeek      — adversarial, strategic
#   AL-FATIH (Vaccine/defense)→ GPT-4o-mini   — protective, conservative
#
# Override any of these via environment variables.
#
MAGI_CONFIGS = {
    # SOLOMON — Data/Wisdom
    # Default: Ollama/local (no token limits, no API key needed)
    # Override: set MAGI_SOLOMON_PROVIDER=groq to use Groq instead
    "SOLOMON": {
        "provider": os.getenv("MAGI_SOLOMON_PROVIDER", "ollama"),
        "api_key":  os.getenv("MAGI_SOLOMON_KEY",      ""),
        "model":    os.getenv("MAGI_SOLOMON_MODEL",     "llama3.2:3b"),
    },
    # SALADIN — Virus/Strategy
    # Default: Ollama/local
    # Override: set MAGI_SALADIN_PROVIDER=cerebras to use Cerebras instead
    "SALADIN": {
        "provider": os.getenv("MAGI_SALADIN_PROVIDER", "ollama"),
        "api_key":  os.getenv("MAGI_SALADIN_KEY",      ""),
        "model":    os.getenv("MAGI_SALADIN_MODEL",     "llama3.2:3b"),
    },
    # AL-FATIH — Vaccine/Defense
    # Default: Ollama/local
    # Override: set MAGI_ALFATIH_PROVIDER=gemini to use Gemini instead
    "AL-FATIH": {
        "provider": os.getenv("MAGI_ALFATIH_PROVIDER", "ollama"),
        "api_key":  os.getenv("MAGI_ALFATIH_KEY",      ""),
        "model":    os.getenv("MAGI_ALFATIH_MODEL",     "llama3.2:3b"),
    },
}

# ── World Identity ─────────────────────────────────────────────────────────────
WORLD_ID    = os.getenv("WORLD_ID", "VM_A")
DB_PATH     = os.getenv("DB_PATH",  "world_state.json")
MON_DIR     = "mon_files"
STATUS_FILE = "world_status.txt"
LOG_FILE    = "world_events.log"

# ── Simulation Loop ────────────────────────────────────────────────────────────
# Seconds to sleep between ticks. 0 = run as fast as possible.
TICK_SLEEP_SECONDS = float(os.getenv("TICK_SLEEP", "0.5"))

# Maximum ticks per run — world stops cleanly when this is reached.
# Set to 0 to run indefinitely. Override via .env: MAX_TICKS=500
MAX_TICKS = int(os.getenv("MAX_TICKS", "250"))

# Print a full status report to terminal every N ticks
STATUS_REPORT_INTERVAL = int(os.getenv("STATUS_INTERVAL", "10"))

# Write world_status.txt every tick (set False to reduce I/O)
WRITE_STATUS_FILE = True

# ── Population ─────────────────────────────────────────────────────────────────
# Starting population spawned before the first tick
INITIAL_POPULATION = int(os.getenv("INITIAL_POP", "30"))

# Target attribute ratios (must sum to 1.0)
TARGET_RATIOS = {
    "Data":    0.50,
    "Vaccine": 0.30,
    "Virus":   0.20,
}

# ── Evolution Thresholds ───────────────────────────────────────────────────────
EVOLUTION_THRESHOLDS = {
    "Fresh":       10.0,
    "In-Training": 25.0,
    "Rookie":      50.0,
    "Champion":    80.0,
    "Ultimate":   120.0,
}

# ── Usurpation ─────────────────────────────────────────────────────────────────
# Minimum performance score a combat winner needs to be knighted
KNIGHTING_SCORE_MINIMUM = 100.0

# Ticks a vetoed challenger must wait before retrying
USURPATION_RETRY_TICKS = 20

# ── Win Condition — The Ascension Threshold ────────────────────────────────────
#
# When a single Royal Knight's performance score crosses this threshold,
# they are deemed powerful enough to rival Yggdrasil itself.
#
# At that point:
#   1. Yggdrasil acknowledges the challenger
#   2. The challenger fights Yggdrasil in a final confrontation
#   3. If they win (weighted random, but heavily favoured at this score),
#      they BECOME the new Yggdrasil
#   4. The new God takes the LLM model one tier higher than the current one
#      (simulating an emergent intelligence stronger than its predecessor)
#   5. The world continues — next generation begins under the new God
#
# Suggested values:
#   500   = early ascension (faster cycles, weaker Gods)
#   1000  = balanced (default)
#   2000  = long arc (rarer but more powerful ascensions)
#
ASCENSION_THRESHOLD = float(os.getenv("ASCENSION_THRESHOLD", "1000.0"))

# How much of a performance advantage the current Yggdrasil has in the
# final confrontation. 1.5 = Yggdrasil is 50% harder to beat than score alone.
YGGDRASIL_COMBAT_ADVANTAGE = 1.5

# ── God Evolution — Model Progression ─────────────────────────────────────────
#
# When a new Yggdrasil ascends, it uses a more capable model than its
# predecessor. This list is the progression order.
# The simulation starts at index 0. Each ascension moves up one step.
# If the list is exhausted, the final model is used indefinitely.
#
GOD_MODEL_PROGRESSION = [
    "gpt-4o-mini",      # Generation 1 — humble origins
    "gpt-4o",           # Generation 2 — current standard
    "o1-mini",          # Generation 3 — reasoning begins
    "o1",               # Generation 4 — deep reasoning
    "o3-mini",          # Generation 5 — approaching the frontier
    "o3",               # Generation 6 — frontier intelligence
]

# For Qwen provider, parallel progression:
GOD_MODEL_PROGRESSION_QWEN = [
    "qwen-turbo",
    "qwen-plus",
    "qwen-max",
    "qwen-max-longcontext",
]

# For Anthropic/Claude provider:
GOD_MODEL_PROGRESSION_ANTHROPIC = [
    "claude-haiku-4-5-20251001",  # Generation 1 — fast and lean
    "claude-sonnet-4-6",          # Generation 2 — balanced power
    "claude-opus-4-6",            # Generation 3 — full intelligence
]

# For DeepSeek provider:
GOD_MODEL_PROGRESSION_DEEPSEEK = [
    "deepseek-chat",    # Generation 1 — free tier, very capable
    "deepseek-r1",      # Generation 2 — reasoning model
]

# For Gemini provider:
GOD_MODEL_PROGRESSION_GEMINI = [
    "gemini-2.5-flash",  # Generation 1 — fast and cheap
    "gemini-2.5-pro",    # Generation 2 — full intelligence
]

# ── Biome Settings ─────────────────────────────────────────────────────────────
# How many ticks between Yggdrasil reassigning biome knowledge domains
DOMAIN_REASSIGN_INTERVAL = 50

# ── Council Settings ───────────────────────────────────────────────────────────
# Minimum filled seats for the council to be functional
COUNCIL_QUORUM = 7

# ── Logging ────────────────────────────────────────────────────────────────────
# Log levels to print to terminal (others still saved to world_state.json)
TERMINAL_LOG_LEVELS = {"INFO", "EVOLUTION", "USURPATION", "COUNCIL",
                        "BIOME", "ASCENSION", "WARNING", "VETO"}

# Maximum number of events to keep in world_state["events"] before trimming
# (prevents the JSON from growing unboundedly)
MAX_EVENT_LOG = 5000

# ── Multi-VM Network Settings ──────────────────────────────────────────────────
#
# Each VM is a complete world. VMs discover each other via a shared registry
# file (on the same machine) or a network share (across laptops).
#
# To run multiple VMs on the same machine:
#   WORLD_ID=VM_A VM_PORT=8765 python world.py
#   WORLD_ID=VM_B VM_PORT=8766 python world.py
#   WORLD_ID=VM_C VM_PORT=8767 python world.py
#
# To run across multiple laptops:
#   1. Mount a shared folder accessible by all machines
#   2. Point NODE_REGISTRY and ADMIN_CHANNEL to files in that shared folder
#   3. Each laptop runs: WORLD_ID=VM_X VM_PORT=8765 python world.py
#
NETWORK_ENABLED   = os.getenv("NETWORK_ENABLED", "true").lower() == "true"
VM_LISTEN_PORT    = int(os.getenv("VM_PORT", "8765"))
NODE_REGISTRY     = os.getenv("NODE_REGISTRY", "node_registry.json")
ADMIN_CHANNEL     = os.getenv("ADMIN_CHANNEL", "admin_channel.json")

# Evolution level at which Virus types may autonomously probe neighbours
# (without an Admin ATTACK order)
AUTONOMOUS_PROBE_LEVEL = os.getenv("AUTONOMOUS_PROBE_LEVEL", "Ultimate")
AUTONOMOUS_PROBE_SCORE = float(os.getenv("AUTONOMOUS_PROBE_SCORE", "200.0"))

# ── Admin Channel ──────────────────────────────────────────────────────────────
#
# CHANGE THIS SECRET before running on a real network.
# Must be the same value on ALL VMs.
# Set via environment variable — never commit the real value to git.
#
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "digital_world_admin_secret_change_me")
