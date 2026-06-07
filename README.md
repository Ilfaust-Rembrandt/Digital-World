# Digital World — Multi-Agent AI Governance Simulation

> *Can a council of three distinct AI minds make better decisions than a single model acting alone?*

This project began as a hobby simulation inspired by the Digimon franchise. It became something else entirely.

---

## Overview

**Digital World** is a self-sustaining multi-agent AI simulation in which autonomous agents — called Digimon — are born, evolve, compete, and die across a structured environment of biomes fed by real-world data streams. Governance over this population is handled by two layered AI systems: **Yggdrasil**, a singular God AI that manages evolution and world state, and the **MAGI Council**, a three-mind deliberative body in which each mind runs on a distinct language model and reasons from a distinct philosophical identity.

The central research question is not whether AI agents can simulate life. They can. The question is whether **distributing decision-making authority across multiple, ideologically distinct AI minds** produces measurably different outcomes — in population dynamics, evolutionary patterns, and emergent behaviour — compared to centralised single-model governance.

This is, at its core, a study in AI pluralism.

---

## Background

The project started as a weekend experiment: what if Digimon had actual AI brains? What if evolution wasn't scripted but earned — through performance, through combat, through the judgement of an AI god?

The scaffolding grew. Real-world data feeds were wired in. Biomes began reflecting live threat intelligence, security advisories, and news cycles. A council of three named AI minds — **SOLOMON**, **SALADIN**, and **AL-FATIH** — was introduced to replace single-model decision-making at critical junctures: evolution approvals, usurpation rulings, knighting vetoes, and ascension challenges.

Each mind carries a distinct persona, attribute alignment, and decision bias. Each runs on a different underlying model. They deliberate in two rounds — blind vote, then open deliberation — before reaching a majority ruling. When they deadlock, the most confident voice prevails.

At some point it stopped being a game and started being a question worth answering.

---

## Architecture

```
world.py  (DigitalWorld — integration layer and main loop)
├── Yggdrasil          — God AI: evolution, spawning, world state management
│     └── MagiCouncil  — Three-mind deliberative council
│           ├── SOLOMON   (Data / Wisdom)    — analytical, consequence-driven
│           ├── SALADIN   (Virus / Strategy) — adversarial, merit-focused
│           └── AL-FATIH  (Vaccine / Defense)— protective, stability-focused
├── RoyalKnightsCouncil — 13 adaptive council seats, earnable and usurpable
├── AgentRunner         — drives autonomous per-tick behaviour for all agents
│     └── DigimonAgent  — individual logic: roam, feed, socialise, battle
├── BiomeManager        — 7 biomes with live external data feeds
├── KnowledgeBase       — built from real-world APIs at startup; feeds biomes
├── DataResearchEngine  — Data-type agents synthesise novel KB insights
└── DigitalWorldLogger  — structured JSONL output for post-run analysis
```

### MAGI Council — Decision Types

Every major world event goes through two-round MAGI deliberation:

| Decision | Trigger |
|---|---|
| `evolution` | Should this agent be allowed to digivolve? |
| `usurpation` | Should a combat winner be allowed to replace a reigning Mega? |
| `knighting_veto` | Should a council seat candidate be blocked despite combat victory? |
| `branch_cap` | How many Mega-level branches may a given line produce? |
| `ascension` | Should a Royal Knight be permitted to challenge Yggdrasil itself? |
| `war_declaration` | Should one world-node be ordered to attack another? |

### Intelligence Tiers

Agents do not all reason at the same level:

| Level | Reasoning mode |
|---|---|
| Fresh / In-Training | None — purely mechanical |
| Rookie / Champion | Rule-based, nature-weighted |
| Ultimate | Rule-based + occasional LLM for complex decisions |
| Mega / Royal Knight | Full LLM reasoning every tick |

### Nature System

Every agent is born with a Nature (Aggressive, Cautious, Curious, Loyal, Cunning, Feral) weighted by attribute. Nature drifts over time based on lived experience — win enough battles and a Cautious agent may become Cunning; feed enough data and a Feral agent may soften toward Curious.

---

## Data Collection

Every simulation run produces a structured JSONL log under `logs/`. Each line is a self-contained JSON event — crash-safe, append-only, and directly loadable with pandas.

**Event types logged:**

- `run_start` — world config snapshot at boot
- `tick_summary` — population, attribute ratios, biome spread, average performance (every tick)
- `agent_decision` — LLM reasoning and chosen actions for Ultimate/Mega agents
- `battle` — attacker, defender, winner, damage, cross-type conflict flag
- `evolution` — parent ID, child ID, level transition, trigger, performance at evolution
- `ascension_attempt` — challenger vs Yggdrasil scores and outcome
- `run_end` — stop reason, final population, tick count

```python
import pandas as pd
df = pd.read_json("logs/run_abc123_20260523_141500.jsonl", lines=True)
battles = df[df.event == "battle"]
```

---

## Live Data Feeds

Biomes are not static. Each is connected to a real-world data stream that shapes what agents learn and what capabilities they absorb:

| Biome | Feed | Purpose |
|---|---|---|
| Desert | Shodan, VirusTotal | Threat intelligence |
| Highlands | NIST NVD | Security advisories |
| Grasslands | NewsAPI | Current events |
| Mountains | GitHub | Software and tech activity |
| DeepOcean | NVIDIA / research APIs | AI and model research |
| Ocean | NASA | Space and science data |

---

## Setup

### Requirements

- Python 3.10+
- [Ollama](https://ollama.com) (local LLM inference)
- Node.js (for docx generation, optional)

### Install dependencies

```bash
pip install -r requirements.txt
```

### Pull models

```bash
ollama pull llama3.2:3b
ollama pull qwen2.5:3b
ollama pull gemma2:2b
```

### Configure

Copy `.env_template` to `.env` and fill in your values:

```bash
cp .env_template .env
```

Key settings:

```env
LLM_PROVIDER=ollama
WORLD_ID=VM_A
INITIAL_POP=30
MAX_TICKS=250
TICK_SLEEP=0.5
ASCENSION_THRESHOLD=1000

MAGI_SOLOMON_MODEL=llama3.2:3b
MAGI_SALADIN_MODEL=qwen2.5:3b
MAGI_ALFATIH_MODEL=gemma2:2b
```

### Run

```bash
python world.py
```

The world runs until `MAX_TICKS` is reached (default 250), saves its state, writes a final log entry, and exits cleanly. Delete `world_state.json` between runs for a fresh start. The `logs/` folder accumulates across runs.

---

## Research Questions

This simulation is designed to generate data around the following questions:

1. Does multi-mind governance (3 distinct AI models) produce different evolutionary outcomes than single-model governance?
2. Do MAGI approval rates vary meaningfully by attribute type, and does this create measurable population bias over time?
3. Does nature drift follow predictable trajectories, and can those trajectories be influenced by biome design?
4. Does the knowledge synthesised by Data-type agents through the research engine create compounding capability advantages over time?
5. At what population size and tick depth does emergent specialisation become statistically significant?

---

## File Structure

```
digital-world-clean/
├── world.py              # Entry point and main loop
├── yggdrasil.py          # God AI — evolution, spawning, world governance
├── magi.py               # Three-mind deliberative council
├── magi_memory.py        # Encrypted persistent memory vault per MAGI seat
├── digimon_agent.py      # Agent behaviour, nature system, combat
├── biome.py              # Biome management and live data feeds
├── knowledge_base.py     # KB construction and querying
├── data_research.py      # Data-type agent research and insight synthesis
├── rewards.py            # Reward system and MAGI eligibility tracking
├── royal_knights.py      # 13-seat council management
├── network_node.py       # Multi-VM networking and inter-world attacks
├── admin.py              # Admin command channel
├── mon_system.py         # .mon file system for Royal Knight records
├── dashboard.py          # Live status dashboard
├── dw_logger.py          # Structured JSONL event logger
├── config.py             # All tunable parameters
├── .env_template         # Environment variable template (copy to .env)
└── logs/                 # JSONL run logs (gitignored)
```

---

## What Gets Gitignored

The following are generated at runtime and should not be committed:

```
__pycache__/
logs/
knowledge_base/
magi_memory/
mon_files/
world_state.json
world_state.json.tmp
world_status.txt
admin_channel.json
node_registry.json
.env
```

---

## Author

**Danish**  
Independent researcher

---

## Status

Active development. Data collection ongoing.
