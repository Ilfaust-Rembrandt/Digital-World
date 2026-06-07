# How to Wire dw_logger into Your Project

## Step 1 — Copy the file
Put `dw_logger.py` in your project root (same folder as `world.py`).

---

## Step 2 — world.py changes

### At the top, add the import:
```python
from dw_logger import DigitalWorldLogger
```

### In DigitalWorld.__init__(), add:
```python
self.logger = DigitalWorldLogger()
self.logger.log_run_start(
    world_id=os.environ.get("WORLD_ID", "VM_A"),
    config={
        "tick_sleep"          : cfg.TICK_SLEEP,
        "ascension_threshold" : cfg.ASCENSION_THRESHOLD,
        "max_population"      : cfg.MAX_POPULATION,
    }
)
```

### Pass logger to AgentRunner:
```python
# Change this line in __init__:
self.agent_runner = AgentRunner(self.yggdrasil)
# To this:
self.agent_runner = AgentRunner(self.yggdrasil, logger=self.logger)
```

### In the tick() method, add AFTER all subsystems have run:
```python
# --- Tick summary logging ---
living = [r for r in self.yggdrasil.state["digimon"].values() if r.get("alive")]
type_counts = {"Data": 0, "Vaccine": 0, "Virus": 0}
for r in living:
    attr = r.get("attribute", "Data")
    type_counts[attr] = type_counts.get(attr, 0) + 1

biome_counts = {}
for r in living:
    b = r.get("biome", "Unknown")
    biome_counts[b] = biome_counts.get(b, 0) + 1

avg_perf = (
    sum(r.get("performance", 0) for r in living) / len(living)
    if living else 0.0
)

self.logger.log_tick_summary(
    tick=self.yggdrasil.state.get("tick", 0),
    population=len(living),
    type_counts=type_counts,
    biome_counts=biome_counts,
    avg_performance=avg_perf,
)
```

### In the signal handler / shutdown, add:
```python
living_count = sum(
    1 for r in self.yggdrasil.state["digimon"].values()
    if r.get("alive")
)
self.logger.log_run_end(
    tick=self.yggdrasil.state.get("tick", 0),
    reason="keyboard_interrupt",   # or "ascension", "max_ticks"
    final_population=living_count,
)
```

---

## Step 3 — digimon_agent.py changes

### In AgentRunner.__init__(), accept logger:
```python
def __init__(self, yggdrasil_instance, logger=None):
    self.god    = yggdrasil_instance
    self.state  = yggdrasil_instance.state
    self.llm    = getattr(yggdrasil_instance, "client", None)
    self.model  = getattr(yggdrasil_instance, "model", "gpt-4o")
    self.logger = logger   # <-- add this
```

### In AgentRunner.tick(), pass logger to each agent:
```python
agent = DigimonAgent(
    record=record,
    world_state=self.state,
    llm_client=self.llm,
    llm_model=self.model,
    logger=self.logger,    # <-- add this
)
```

### In DigimonAgent.__init__(), accept logger:
```python
def __init__(self, record, world_state, llm_client=None, llm_model=None, logger=None):
    ...
    self.logger = logger   # <-- add this
```

### In DigimonAgent._tick_llm(), after parsing the LLM decision:
```python
decision = json.loads(resp.choices[0].message.content)

# --- Log the decision BEFORE executing ---
if self.logger:
    self.logger.log_agent_decision(
        tick=tick_number,
        agent_id=self.record["id"],
        agent_type=self.record.get("attribute", "Data"),
        nature=self.record.get("nature", "Cautious"),
        evolution_level=self.record.get("evolution_level", "Rookie"),
        biome=self.record.get("biome", "Unknown"),
        actions=decision.get("actions", []),
        reasoning=decision.get("reasoning", ""),
        performance_before=self.record.get("performance", 0),
    )

self._execute_llm_decision(decision)
```

### In DigimonAgent._action_battle(), after resolving combat:
```python
if self.logger:
    self.logger.log_battle(
        tick=tick_number,          # you'll need to pass tick_number into _action_battle
        biome=self.record.get("biome", "Unknown"),
        attacker_id=self.record["id"],
        attacker_type=self.record.get("attribute", "Data"),
        attacker_level=self.record.get("evolution_level", "Rookie"),
        defender_id=target["id"],
        defender_type=target.get("attribute", "Data"),
        defender_level=target.get("evolution_level", "Rookie"),
        winner_id=winner["id"],    # whichever record won
        damage=damage_dealt,
    )
```

---

## Step 4 — Verify it works

Run `python world.py` for a few ticks, then:
```bash
# See if the log file was created
ls logs/

# Peek at the first few entries
python -c "
import json
with open('logs/run_XXXXXXXX_TIMESTAMP.jsonl') as f:
    for i, line in enumerate(f):
        print(json.dumps(json.loads(line), indent=2))
        if i >= 4: break
"
```

You should see structured JSON events flowing in real time.
