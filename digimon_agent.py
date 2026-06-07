"""
╔══════════════════════════════════════════════════════════╗
║           DIGIMON AGENT SYSTEM - The Living World        ║
║         Individual Behaviour, Nature, and Action         ║
╚══════════════════════════════════════════════════════════╝

This module governs what individual Digimon DO each tick.
Yggdrasil handles the big picture (evolution, balance, world state).
The DigimonAgent handles the individual — their personality,
their choices, and their moment-to-moment survival.

NATURE SYSTEM (inspired by Pokemon natures):
    Every Digimon is born with a Nature that tilts their behaviour.
    Nature does not override rules — it weights decisions.
    An Aggressive Digimon still retreats if nearly dead.
    A Cautious Digimon still fights if cornered.

    Natures are weighted at birth by attribute:
        Virus   -> more likely Aggressive, Cunning, Feral
        Vaccine -> more likely Loyal, Cautious, Aggressive
        Data    -> more likely Curious, Cautious, Loyal

    Nature drifts slowly based on lived experience:
        Win many battles  -> drift toward Aggressive or Cunning
        Lose many battles -> drift toward Cautious or Feral
        Eat lots of data  -> drift toward Curious
        Protect allies    -> drift toward Loyal

INTELLIGENCE TIERS:
    Fresh / In-Training / Rookie / Champion -> rule-based only
    Ultimate -> rule-based + occasional LLM for complex decisions
    Mega / Royal Knights -> full LLM reasoning every tick

TICK ACTIONS (in order each tick):
    1. Roam      - move within or between biomes
    2. Feed      - consume data from the current biome
    3. Socialise - communicate with nearby same-attribute Digimon
    4. Decide    - choose a battle target (or not)
    5. Nature    - check if nature should drift
"""

import random
from typing import Optional


# =============================================================================
# NATURE DEFINITIONS
# =============================================================================

NATURES = {
    "Aggressive": {
        "description":  "Seeks battle, attacks first, prioritises offence.",
        "battle_bias":  +0.30,
        "flee_bias":    -0.20,
        "feed_bias":    -0.10,
        "social_bias":  +0.00,
        "feral_risk":   False,
        "drift_toward": ["Aggressive", "Cunning"],
        "drift_from":   ["Cautious"],
    },
    "Cautious": {
        "description":  "Avoids fights, prioritises survival and escape.",
        "battle_bias":  -0.25,
        "flee_bias":    +0.30,
        "feed_bias":    +0.10,
        "social_bias":  +0.10,
        "feral_risk":   False,
        "drift_toward": ["Cautious", "Loyal"],
        "drift_from":   ["Aggressive", "Feral"],
    },
    "Curious": {
        "description":  "Explores biomes, consumes more data, wanders far.",
        "battle_bias":  -0.10,
        "flee_bias":    +0.00,
        "feed_bias":    +0.25,
        "social_bias":  +0.15,
        "feral_risk":   False,
        "drift_toward": ["Curious", "Loyal"],
        "drift_from":   ["Feral", "Aggressive"],
    },
    "Loyal": {
        "description":  "Stays near same-attribute Digimon, boosts allies.",
        "battle_bias":  +0.05,
        "flee_bias":    -0.05,
        "feed_bias":    +0.05,
        "social_bias":  +0.30,
        "feral_risk":   False,
        "drift_toward": ["Loyal", "Cautious"],
        "drift_from":   ["Feral", "Aggressive"],
    },
    "Cunning": {
        "description":  "Picks fights it can win, retreats if losing.",
        "battle_bias":  +0.10,
        "flee_bias":    +0.20,
        "feed_bias":    +0.05,
        "social_bias":  -0.10,
        "feral_risk":   False,
        "drift_toward": ["Cunning", "Aggressive"],
        "drift_from":   ["Loyal", "Cautious"],
    },
    "Feral": {
        "description":  "Attacks anything, including own attribute. Unpredictable.",
        "battle_bias":  +0.40,
        "flee_bias":    -0.30,
        "feed_bias":    -0.20,
        "social_bias":  -0.30,
        "feral_risk":   True,
        "drift_toward": ["Feral", "Aggressive"],
        "drift_from":   ["Loyal", "Curious", "Cautious"],
    },
}

NATURE_WEIGHTS = {
    "Virus":   {"Aggressive": 35, "Cunning": 30, "Feral": 20, "Cautious": 5, "Curious": 5, "Loyal": 5},
    "Vaccine": {"Loyal": 30, "Cautious": 25, "Aggressive": 20, "Cunning": 15, "Curious": 10, "Feral": 0},
    "Data":    {"Curious": 35, "Cautious": 25, "Loyal": 20, "Cunning": 10, "Aggressive": 8, "Feral": 2},
}

DRIFT_THRESHOLDS = {
    "battle_wins": 10, "battle_losses": 8, "data_consumed": 15, "ally_assists": 12,
}

NATURE_DRIFT_TABLE = {
    "Aggressive": {"Aggressive": 50, "Cunning": 30, "Feral": 20},
    "Cautious":   {"Cautious": 50, "Loyal": 30, "Curious": 20},
    "Curious":    {"Curious": 50, "Loyal": 30, "Cautious": 20},
    "Loyal":      {"Loyal": 50, "Cautious": 25, "Curious": 25},
    "Cunning":    {"Cunning": 50, "Aggressive": 30, "Cautious": 20},
    "Feral":      {"Feral": 60, "Aggressive": 30, "Cunning": 10},
}

BIOMES = ["Desert", "Grasslands", "Forest", "Highlands", "Mountains", "Ocean", "DeepOcean"]

BIOME_ADJACENCY = {
    "Desert":     ["Grasslands", "Highlands"],
    "Grasslands": ["Desert", "Forest", "Highlands"],
    "Forest":     ["Grasslands", "Mountains", "Highlands"],
    "Highlands":  ["Desert", "Grasslands", "Forest", "Mountains"],
    "Mountains":  ["Forest", "Highlands", "Ocean"],
    "Ocean":      ["Mountains", "Grasslands", "DeepOcean"],
    "DeepOcean":  ["Ocean"],
}

BIOME_DATA_RICHNESS = {
    "Desert": 1.5, "Grasslands": 2.0, "Forest": 2.5,
    "Highlands": 2.0, "Mountains": 3.0, "Ocean": 2.5, "DeepOcean": 4.0,
}

BASE_ACTION_PROBS = {
    "battle": 0.30, "flee": 0.15, "feed": 0.40, "social": 0.25, "roam": 0.20,
}


# =============================================================================
# NATURE HELPERS
# =============================================================================

def assign_nature(attribute: str) -> str:
    weights    = NATURE_WEIGHTS.get(attribute, {n: 1 for n in NATURES})
    population = [k for k, v in weights.items() if v > 0]
    wts        = [v for v in weights.values() if v > 0]
    return random.choices(population, weights=wts, k=1)[0]


def action_probability(action: str, nature: str) -> float:
    base     = BASE_ACTION_PROBS.get(action, 0.20)
    bias_key = f"{action}_bias"
    bias     = NATURES.get(nature, {}).get(bias_key, 0.0)
    return max(0.05, min(0.95, base + bias))


def should_drift(record: dict) -> bool:
    exp = record.get("experience_counters", {})
    return (
        exp.get("battle_wins", 0)   >= DRIFT_THRESHOLDS["battle_wins"]   or
        exp.get("battle_losses", 0) >= DRIFT_THRESHOLDS["battle_losses"] or
        exp.get("data_consumed", 0) >= DRIFT_THRESHOLDS["data_consumed"] or
        exp.get("ally_assists", 0)  >= DRIFT_THRESHOLDS["ally_assists"]
    )


def drift_nature(record: dict) -> str:
    exp     = record.get("experience_counters", {})
    current = record.get("nature", "Cautious")

    scores = {
        "battle_wins":   exp.get("battle_wins", 0),
        "battle_losses": exp.get("battle_losses", 0),
        "data_consumed": exp.get("data_consumed", 0),
        "ally_assists":  exp.get("ally_assists", 0),
    }
    dominant = max(scores, key=scores.get)

    drift_targets = {
        "battle_wins":   ["Aggressive", "Cunning"],
        "battle_losses": ["Cautious", "Feral"],
        "data_consumed": ["Curious"],
        "ally_assists":  ["Loyal"],
    }
    targets = drift_targets[dominant]

    drift_options = NATURE_DRIFT_TABLE.get(current, {current: 100})
    boosted       = {n: w + (50 if n in targets else 0) for n, w in drift_options.items()}
    population    = list(boosted.keys())
    wts           = list(boosted.values())
    new_nature    = random.choices(population, weights=wts, k=1)[0]

    record["experience_counters"] = {k: 0 for k in exp}
    return new_nature


# =============================================================================
# DIGIMON AGENT
# =============================================================================

class DigimonAgent:
    """
    Wraps a Digimon record and drives its autonomous per-tick behaviour.

    Does NOT store state itself — reads/writes directly into the record dict.
    Intelligence tier determines whether rule-based or LLM logic is used.
    """

    LLM_LEVELS = {"Ultimate", "Mega"}

    def __init__(self, record: dict, world_state: dict, llm_client=None,
                 llm_model: str = "gpt-4o", biome_manager=None, logger=None):
        self.record        = record
        self.world_state   = world_state
        self.llm           = llm_client
        self.llm_model     = llm_model
        self.biome_manager = biome_manager   # BiomeManager instance for live richness + feeds
        self.logger        = logger          # DigitalWorldLogger for structured event logging
        self._ensure_fields()

    def _ensure_fields(self):
        self.record.setdefault("nature", assign_nature(self.record.get("attribute", "Data")))
        self.record.setdefault("experience_counters", {
            "battle_wins": 0, "battle_losses": 0, "data_consumed": 0, "ally_assists": 0,
        })
        self.record.setdefault("data_eaten",  0.0)
        self.record.setdefault("last_action", None)
        self.record.setdefault("ally_ids",    [])

    # -------------------------------------------------------------------------
    # MAIN TICK
    # -------------------------------------------------------------------------

    def tick(self, tick_number: int):
        if not self.record.get("alive", False):
            return

        level = self.record["evolution_level"]
        if level in self.LLM_LEVELS and self.llm:
            self._tick_llm(tick_number)
        else:
            self._tick_rules(tick_number)

        if should_drift(self.record):
            old    = self.record["nature"]
            new    = drift_nature(self.record)
            self.record["nature"] = new
            if old != new:
                self._log(f"{self.record['name']} nature drifted: {old} -> {new}")

    # -------------------------------------------------------------------------
    # RULE-BASED TICK
    # -------------------------------------------------------------------------

    def _tick_rules(self, tick_number: int):
        nature = self.record.get("nature", "Cautious")

        if random.random() < action_probability("roam",   nature): self._action_roam()
        if random.random() < action_probability("feed",   nature): self._action_feed()
        if random.random() < action_probability("social", nature): self._action_socialise()
        if random.random() < action_probability("battle", nature):
            target = self._find_battle_target(nature)
            if target:
                self._action_battle(target)

        self.record["last_action"] = tick_number

    # -------------------------------------------------------------------------
    # LLM-BASED TICK
    # -------------------------------------------------------------------------

    def _tick_llm(self, tick_number: int):
        try:
            import json
            context = self._build_llm_context()
            prompt  = (
                f"You are a {self.record['evolution_level']}-level Digimon named "
                f"{self.record['name']} with a {self.record['nature']} nature.\n\n"
                f"World context:\n{context}\n\n"
                f"Choose actions for this tick from: roam, feed, social, "
                f"battle <target_id>, retreat.\n"
                f"Respond with JSON only:\n"
                f'{"{"}"actions": ["roam", "feed"], "reasoning": "one sentence"{"}"}'
            )
            resp     = self.llm.chat.completions.create(
                model=self.llm_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
            )
            decision = json.loads(resp.choices[0].message.content)

            # Log the LLM decision BEFORE executing it
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
        except Exception:
            self._tick_rules(tick_number)

    def _build_llm_context(self) -> str:
        r      = self.record
        nearby = self._get_nearby_digimon(same_biome_only=True)
        nearby_summary = ", ".join(
            f"{d['name']}({d['attribute']},{d['evolution_level']})" for d in nearby[:5]
        ) or "none"
        return (
            f"Name: {r['name']} | Attribute: {r['attribute']} | "
            f"Nature: {r['nature']} | Level: {r['evolution_level']}\n"
            f"Biome: {r.get('biome','?')} | Performance: {r.get('performance',0):.1f}\n"
            f"Battles W/L: {r.get('battles_won',0)}/{r.get('battles_lost',0)}\n"
            f"Nearby: {nearby_summary}"
        )

    def _execute_llm_decision(self, decision: dict):
        for action_str in decision.get("actions", []):
            parts  = action_str.strip().split()
            action = parts[0].lower() if parts else ""
            if action == "roam":    self._action_roam()
            elif action == "feed":  self._action_feed()
            elif action == "social":self._action_socialise()
            elif action == "retreat":self._action_flee()
            elif action == "battle" and len(parts) > 1:
                target = self.world_state["digimon"].get(parts[1])
                if target and target.get("alive"):
                    self._action_battle(target)

    # -------------------------------------------------------------------------
    # ACTIONS
    # -------------------------------------------------------------------------

    def _action_roam(self):
        current   = self.record.get("biome", "Grasslands")
        attribute = self.record.get("attribute", "Data")
        nature    = self.record.get("nature", "Cautious")

        # Get valid adjacent biomes (respects blocked biomes from BiomeManager)
        if self.biome_manager:
            adjacent = self.biome_manager.get_valid_adjacency(current)
        else:
            adjacent = BIOME_ADJACENCY.get(current, [current])

        if not adjacent:
            return  # all exits blocked (Storm, Avalanche etc.)

        def _richness(biome_name: str) -> float:
            """Live richness from BiomeManager, fallback to static dict."""
            if self.biome_manager:
                return self.biome_manager.get_effective_richness(biome_name, attribute)
            return BIOME_DATA_RICHNESS.get(biome_name, 2.0)

        def _feed_count(biome_name: str) -> int:
            """How many live feed items are in this biome right now."""
            if self.biome_manager:
                return len(self.biome_manager.get_feed(biome_name))
            return 0

        if nature == "Loyal" and random.random() < 0.60:
            return  # Loyal types stay put most of the time

        elif nature == "Curious":
            # Seek the richest biome by live data volume + richness
            dest = max(adjacent, key=lambda b: _richness(b) + _feed_count(b) * 0.1)

        elif nature == "Cautious":
            # Avoid hostile biomes — prefer biomes where our attribute is welcome
            safe = [b for b in adjacent
                    if self.biome_manager and
                    self.biome_manager.biomes[b].definition.get("hostile_attr") != attribute]
            dest = random.choice(safe) if safe else random.choice(adjacent)

        elif nature == "Aggressive":
            # Seek biomes with other Digimon to fight
            pop_sorted = sorted(adjacent, key=lambda b: sum(
                1 for d in self.world_state["digimon"].values()
                if d.get("alive") and d.get("biome") == b and d["id"] != self.record["id"]
            ), reverse=True)
            dest = pop_sorted[0] if pop_sorted else random.choice(adjacent)

        elif nature == "Feral":
            # Feral Digimon chase the highest-population biome regardless of danger
            pop_sorted = sorted(adjacent, key=lambda b: sum(
                1 for d in self.world_state["digimon"].values()
                if d.get("alive") and d.get("biome") == b
            ), reverse=True)
            dest = pop_sorted[0] if pop_sorted else random.choice(adjacent)

        elif nature == "Cunning":
            # Move toward richest biome but only if it has fewer strong Digimon
            my_perf = self.record.get("performance", 0)
            safe_rich = [b for b in adjacent if not any(
                d.get("performance", 0) > my_perf * 1.5
                for d in self.world_state["digimon"].values()
                if d.get("alive") and d.get("biome") == b
            )]
            dest = max(safe_rich, key=_richness) if safe_rich else random.choice(adjacent)

        else:
            dest = random.choice(adjacent)

        if dest != current:
            self._log(f"{self.record['name']} roamed: {current} → {dest} "
                      f"(nature:{nature}, richness:{_richness(dest):.1f})")
            self.record["biome"] = dest

    def _action_feed(self):
        biome     = self.record.get("biome", "Grasslands")
        attribute = self.record.get("attribute", "Data")
        if self.biome_manager:
            richness = self.biome_manager.get_effective_richness(biome, attribute)
            # Chance to gain a real-data capability from the live feed
            if random.random() < 0.15:
                cap = self.biome_manager.get_capability_from_feed(biome, attribute)
                if cap and cap not in self.record.get("capabilities", []):
                    self.record.setdefault("capabilities", []).append(cap)
                    self._log(f"{self.record['name']} learned '{cap}' from live feed in {biome}.")
            # Chance to absorb a history fragment from live feed
            if random.random() < 0.08:
                frag = self.biome_manager.get_history_fragment(biome)
                if frag:
                    existing = self.record.get("description", "")
                    self.record["description"] = (existing + " " + frag).strip()[-500:]
        else:
            richness = BIOME_DATA_RICHNESS.get(biome, 2.0)
        gain      = richness * random.uniform(0.8, 1.2)

        if attribute == "Vaccine":
            prey = self._find_prey("Virus", must_be_weaker=True)
            if prey:
                bonus = prey.get("performance", 0) * 0.10
                gain += bonus
                prey["performance"] = max(0, prey["performance"] - bonus)

        elif attribute == "Virus":
            nature   = self.record.get("nature", "Cautious")
            is_feral = NATURES[nature]["feral_risk"]
            prey     = self._find_prey(None if is_feral else "Data", must_be_weaker=True)
            if not prey and not is_feral:
                prey = self._find_prey("Vaccine", must_be_weaker=True)
            if prey:
                bonus = prey.get("performance", 0) * 0.15
                gain += bonus
                prey["performance"] = max(0, prey["performance"] - bonus)

        self.record["data_eaten"]  = self.record.get("data_eaten", 0) + gain
        self.record["performance"] = self.record.get("performance", 0) + gain
        self.record["experience_counters"]["data_consumed"] += 1

    def _action_socialise(self):
        nature = self.record.get("nature", "Cautious")
        if nature == "Feral":
            target = self._find_battle_target(nature)
            if target:
                self._action_battle(target)
            return

        allies = self._get_nearby_digimon(same_biome_only=True, same_attribute=True)
        for ally in allies[:3]:
            if ally["id"] not in self.record["ally_ids"]:
                self.record["ally_ids"].append(ally["id"])
            if nature == "Loyal":
                ally["performance"] = ally.get("performance", 0) + 0.5
                self.record["experience_counters"]["ally_assists"] += 1

    def _action_battle(self, target: dict):
        nature      = self.record.get("nature", "Cautious")
        my_score    = self.record.get("performance", 1.0)
        their_score = target.get("performance", 1.0)
        total       = my_score + their_score or 1.0

        if nature == "Cautious" and random.random() < 0.35:
            self._action_flee(); return
        if nature == "Cunning" and (my_score / total) < 0.45:
            self._action_flee(); return

        # Ensure target has experience_counters (may not have been
        # through _ensure_fields if it was spawned before this module existed)
        target.setdefault("experience_counters", {
            "battle_wins": 0, "battle_losses": 0, "data_consumed": 0, "ally_assists": 0,
        })

        i_win = random.random() < (my_score / total)

        if i_win:
            gain = their_score * 0.20
            self.record["performance"]  = self.record.get("performance", 0) + gain
            self.record["battles_won"]  = self.record.get("battles_won", 0) + 1
            self.record["experience_counters"]["battle_wins"] += 1
            target["performance"]       = max(0, their_score - gain)
            target["battles_lost"]      = target.get("battles_lost", 0) + 1
            target["experience_counters"]["battle_losses"] += 1
            if target["performance"] <= 0:
                target["alive"] = False
                self._log(f"{self.record['name']} killed {target['name']}.")
        else:
            loss = my_score * 0.15
            self.record["performance"]  = max(0, my_score - loss)
            self.record["battles_lost"] = self.record.get("battles_lost", 0) + 1
            self.record["experience_counters"]["battle_losses"] += 1
            target["performance"]       = target.get("performance", 0) + loss * 0.5
            target["battles_won"]       = target.get("battles_won", 0) + 1
            target["experience_counters"]["battle_wins"] += 1
            if self.record["performance"] <= 0:
                self.record["alive"] = False
            elif nature in ("Cunning", "Cautious"):
                self._action_flee()

        # Structured log — captures every battle regardless of outcome
        if self.logger:
            self.logger.log_battle(
                tick=self.world_state.get("tick", 0),
                biome=self.record.get("biome", "Unknown"),
                attacker_id=self.record["id"],
                attacker_type=self.record.get("attribute", "Data"),
                attacker_level=self.record.get("evolution_level", "Rookie"),
                defender_id=target["id"],
                defender_type=target.get("attribute", "Data"),
                defender_level=target.get("evolution_level", "Rookie"),
                winner_id=self.record["id"] if i_win else target["id"],
                damage=their_score * 0.20 if i_win else my_score * 0.15,
            )

    def _action_flee(self):
        current = self.record.get("biome", "Grasslands")
        options = BIOME_ADJACENCY.get(current, [current])
        self.record["biome"] = random.choice(options)

    # -------------------------------------------------------------------------
    # TARGET FINDING
    # -------------------------------------------------------------------------

    def _find_battle_target(self, nature: str) -> Optional[dict]:
        my_attr  = self.record.get("attribute", "Data")
        my_perf  = self.record.get("performance", 0.0)
        is_feral = NATURES.get(nature, {}).get("feral_risk", False)

        candidates = [
            d for d in self._get_nearby_digimon(same_biome_only=True)
            if d["id"] != self.record["id"]
            and d.get("alive", False)
            and (is_feral or d["attribute"] != my_attr)
        ]
        if not candidates:
            return None

        if nature == "Cunning":
            beatable = [d for d in candidates if d.get("performance", 0) < my_perf * 0.85]
            return random.choice(beatable) if beatable else None
        elif nature == "Cautious":
            beatable = [d for d in candidates if d.get("performance", 0) < my_perf * 0.60]
            return random.choice(beatable) if beatable else None
        elif nature == "Curious":
            return random.choice(candidates) if random.random() < 0.20 else None
        elif nature == "Loyal":
            threatened = [
                d for d in candidates if d["attribute"] != my_attr
                and any(
                    self.world_state["digimon"].get(aid, {}).get("biome") == self.record.get("biome")
                    for aid in self.record.get("ally_ids", [])
                )
            ]
            return random.choice(threatened) if threatened else None
        else:
            return random.choice(candidates)

    def _find_prey(self, target_attribute: Optional[str], must_be_weaker: bool = True) -> Optional[dict]:
        my_perf    = self.record.get("performance", 0.0)
        candidates = [
            d for d in self._get_nearby_digimon(same_biome_only=True)
            if d["id"] != self.record["id"]
            and d.get("alive", False)
            and (target_attribute is None or d["attribute"] == target_attribute)
            and (not must_be_weaker or d.get("performance", 0) < my_perf * 0.70)
        ]
        return random.choice(candidates) if candidates else None

    def _get_nearby_digimon(self, same_biome_only: bool = True, same_attribute: bool = False) -> list:
        my_biome = self.record.get("biome", "")
        my_attr  = self.record.get("attribute", "")
        my_id    = self.record["id"]
        return [
            d for d in self.world_state["digimon"].values()
            if d["id"] != my_id
            and d.get("alive", False)
            and (not same_biome_only or d.get("biome") == my_biome)
            and (not same_attribute or d.get("attribute") == my_attr)
        ]

    # -------------------------------------------------------------------------
    # LOGGING
    # -------------------------------------------------------------------------

    def _log(self, message: str):
        self.world_state["events"].append({
            "tick": self.world_state.get("tick", 0),
            "level": "AGENT", "message": message,
        })


# =============================================================================
# AGENT RUNNER
# =============================================================================

class AgentRunner:
    """
    Runs all living Digimon agents each tick.
    Shuffles order randomly to prevent first-mover bias.

    Usage:
        runner = AgentRunner(yggdrasil_instance)
        runner.tick()   # call after yggdrasil.tick() each tick
    """

    def __init__(self, yggdrasil_instance, biome_manager=None, logger=None):
        self.god           = yggdrasil_instance
        self.state         = yggdrasil_instance.state
        self.llm           = getattr(yggdrasil_instance, "client", None)
        self.model         = getattr(yggdrasil_instance, "model", "gpt-4o")
        self.biome_manager = biome_manager   # injected by world.py after BiomeManager is created
        self.logger        = logger          # DigitalWorldLogger instance for structured logging

    def set_biome_manager(self, biome_manager):
        """Wire in the BiomeManager after construction (called from world.py)."""
        self.biome_manager = biome_manager

    def tick(self):
        tick_num = self.state.get("tick", 0)
        living   = [r for r in self.state["digimon"].values() if r.get("alive", False)]
        random.shuffle(living)
        for record in living:
            DigimonAgent(
                record, self.state, self.llm, self.model,
                biome_manager=self.biome_manager,
                logger=self.logger,
            ).tick(tick_num)

    def get_nature_summary(self) -> dict:
        summary = {n: 0 for n in NATURES}
        for r in self.state["digimon"].values():
            if r.get("alive"):
                summary[r.get("nature", "Cautious")] = summary.get(r.get("nature", "Cautious"), 0) + 1
        return summary

    def get_biome_population(self) -> dict:
        summary = {b: 0 for b in BIOMES}
        for r in self.state["digimon"].values():
            if r.get("alive"):
                summary[r.get("biome", "Grasslands")] = summary.get(r.get("biome", "Grasslands"), 0) + 1
        return summary
