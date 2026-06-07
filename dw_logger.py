"""
dw_logger.py — Digital World Structured Logger
================================================
Drop this file in your project root (same folder as world.py).

Creates one JSONL log file per simulation run under logs/.
Every event is a single JSON object on its own line — append-only,
crash-safe, and directly readable by pandas for analysis later.

Usage (in world.py):
    from dw_logger import DigitalWorldLogger
    logger = DigitalWorldLogger()          # call once at startup
    logger.log_run_start(world_id, cfg)    # log initial config

Then pass logger down to AgentRunner and Yggdrasil.

WHY JSONL?
    - Each line is valid JSON on its own, so a crash mid-run loses
      at most one entry — not the entire file.
    - pandas.read_json("file.jsonl", lines=True) loads it instantly.
    - Easy to grep/filter without loading everything into memory.
"""

import os
import json
import uuid
from datetime import datetime, timezone


# =============================================================================
# LOGGER
# =============================================================================

class DigitalWorldLogger:
    """
    Lightweight structured logger for the Digital World simulation.

    One instance per simulation run. All subsystems share the same instance
    so every event ends up in one file with consistent run_id tagging.
    """

    def __init__(self, log_dir: str = "logs"):
        """
        Creates the log directory and opens a new JSONL file for this run.

        Args:
            log_dir : Directory to write logs into. Created if missing.
        """
        self.run_id   = uuid.uuid4().hex[:8]          # Short unique ID, e.g. "a3f91c2d"
        self.log_dir  = log_dir
        self.started  = datetime.now(timezone.utc).isoformat()

        os.makedirs(log_dir, exist_ok=True)

        timestamp     = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename      = f"run_{self.run_id}_{timestamp}.jsonl"
        self.log_path = os.path.join(log_dir, filename)

        # Keep the file handle open for the run — faster than open/close each write
        self._file = open(self.log_path, "a", encoding="utf-8")

        print(f"[Logger] Run ID: {self.run_id} → {self.log_path}")


    # ──────────────────────────────────────────────────────────────────────────
    # INTERNAL
    # ──────────────────────────────────────────────────────────────────────────

    def _write(self, entry: dict):
        """
        Serialise one event dict to a JSONL line and flush immediately.
        Flush ensures the line survives even if the simulation crashes.
        Non-fatal: prints a warning if writing fails rather than crashing the sim.
        """
        try:
            self._file.write(json.dumps(entry, default=str) + "\n")
            self._file.flush()
        except Exception as e:
            print(f"[Logger] WARNING: failed to write log entry — {e}")

    def _base(self, event: str, tick: int) -> dict:
        """Shared fields every entry carries."""
        return {
            "event"      : event,
            "run_id"     : self.run_id,
            "tick"       : tick,
            "timestamp"  : datetime.now(timezone.utc).isoformat(),
        }


    # ──────────────────────────────────────────────────────────────────────────
    # RUN-LEVEL EVENTS
    # ──────────────────────────────────────────────────────────────────────────

    def log_run_start(self, world_id: str, config: dict):
        """
        Call once when the simulation boots.
        Records the world config so you know exactly what settings produced
        a given run's data — essential for comparing runs later.

        Args:
            world_id : e.g. "VM_A" or "VM_B"
            config   : dict of relevant settings (tick_sleep, thresholds, etc.)
        """
        entry = self._base("run_start", tick=0)
        entry.update({
            "world_id"   : world_id,
            "config"     : config,
        })
        self._write(entry)

    def log_run_end(self, tick: int, reason: str, final_population: int):
        """
        Call when the simulation ends (normal exit, Ctrl+C, or ascension).

        Args:
            reason           : "ascension", "keyboard_interrupt", "max_ticks", etc.
            final_population : How many Digimon were alive at end
        """
        entry = self._base("run_end", tick=tick)
        entry.update({
            "reason"           : reason,
            "final_population" : final_population,
        })
        self._write(entry)
        self._file.close()

    def log_tick_summary(self, tick: int, population: int,
                         type_counts: dict, biome_counts: dict,
                         avg_performance: float):
        """
        Call once per tick from world.py after all subsystems have run.
        This is your time-series backbone — every metric trend you'll
        want to graph will be reconstructed from these entries.

        Args:
            population      : Total living Digimon
            type_counts     : {"Data": 12, "Vaccine": 8, "Virus": 5}
            biome_counts    : {"Dark Area": 4, "Grasslands": 10, ...}
            avg_performance : Mean performance score across all living agents
        """
        entry = self._base("tick_summary", tick=tick)
        entry.update({
            "population"      : population,
            "type_counts"     : type_counts,
            "biome_counts"    : biome_counts,
            "avg_performance" : round(avg_performance, 3),
        })
        self._write(entry)


    # ──────────────────────────────────────────────────────────────────────────
    # AGENT-LEVEL EVENTS
    # ──────────────────────────────────────────────────────────────────────────

    def log_agent_decision(self, tick: int, agent_id: str, agent_type: str,
                           nature: str, evolution_level: str, biome: str,
                           actions: list, reasoning: str,
                           performance_before: float):
        """
        Call from DigimonAgent.tick() right after the LLM returns its decision,
        BEFORE executing actions (so we capture intent separately from outcome).

        Args:
            agent_id         : e.g. "DGM_00042"
            agent_type       : "Data", "Vaccine", or "Virus"
            nature           : "Curious", "Loyal", "Cunning", etc.
            evolution_level  : "Rookie", "Champion", "Ultimate", "Mega"
            biome            : Current biome name
            actions          : List of action strings from LLM, e.g. ["battle DGM_007", "retreat"]
            reasoning        : One-sentence reasoning from LLM
            performance_before: Performance score before this tick's actions
        """
        entry = self._base("agent_decision", tick=tick)
        entry.update({
            "agent": {
                "id"              : agent_id,
                "type"            : agent_type,
                "nature"          : nature,
                "evolution_level" : evolution_level,
                "biome"           : biome,
                "performance"     : round(performance_before, 3),
            },
            "decision": {
                "actions"   : actions,
                "reasoning" : reasoning,
                "action_types": _classify_actions(actions),  # ["aggressive","evasive"]
            },
        })
        self._write(entry)

    def log_battle(self, tick: int, biome: str,
                   attacker_id: str, attacker_type: str, attacker_level: str,
                   defender_id: str, defender_type: str, defender_level: str,
                   winner_id: str, damage: float):
        """
        Call from DigimonAgent._action_battle() after resolving combat.

        Args:
            winner_id : ID of the winner (attacker or defender)
            damage    : Performance points transferred/lost
        """
        entry = self._base("battle", tick=tick)
        entry.update({
            "biome"    : biome,
            "attacker" : {"id": attacker_id, "type": attacker_type, "level": attacker_level},
            "defender" : {"id": defender_id, "type": defender_type, "level": defender_level},
            "winner_id": winner_id,
            "damage"   : round(damage, 3),
            "cross_type_conflict": attacker_type != defender_type,  # Vaccine vs Virus? flag it
        })
        self._write(entry)

    def log_agent_death(self, tick: int, agent_id: str, agent_type: str,
                        nature: str, evolution_level: str,
                        cause: str, age_ticks: int, final_performance: float,
                        battles_won: int, battles_lost: int):
        """
        Call when a Digimon's alive flag is set to False.

        Args:
            cause : "starvation", "battle_loss", "yggdrasil_cull", etc.
            age_ticks : How many ticks this agent lived
        """
        entry = self._base("agent_death", tick=tick)
        entry.update({
            "agent_id"         : agent_id,
            "agent_type"       : agent_type,
            "nature"           : nature,
            "evolution_level"  : evolution_level,
            "cause"            : cause,
            "age_ticks"        : age_ticks,
            "final_performance": round(final_performance, 3),
            "battles_won"      : battles_won,
            "battles_lost"     : battles_lost,
            "win_rate"         : round(
                battles_won / max(1, battles_won + battles_lost), 3
            ),
        })
        self._write(entry)


    # ──────────────────────────────────────────────────────────────────────────
    # EVOLUTION EVENTS
    # ──────────────────────────────────────────────────────────────────────────

    def log_evolution(self, tick: int, parent_id: str, child_id: str,
                      agent_type: str, old_level: str, new_level: str,
                      trigger: str, performance_at_evolution: float):
        """
        Call from Yggdrasil when a Digimon evolves to the next level.

        Args:
            trigger : What caused evolution — "performance_threshold",
                      "yggdrasil_grant", "battle_mastery", etc.
        """
        entry = self._base("evolution", tick=tick)
        entry.update({
            "parent_id"               : parent_id,
            "child_id"                : child_id,
            "agent_type"              : agent_type,
            "old_level"               : old_level,
            "new_level"               : new_level,
            "trigger"                 : trigger,
            "performance_at_evolution": round(performance_at_evolution, 3),
        })
        self._write(entry)

    def log_ascension_attempt(self, tick: int, challenger_id: str,
                              challenger_performance: float,
                              yggdrasil_performance: float,
                              outcome: str):
        """
        Call from world.py check_ascension().

        Args:
            outcome : "challenger_wins" or "yggdrasil_wins"
        """
        entry = self._base("ascension_attempt", tick=tick)
        entry.update({
            "challenger_id"           : challenger_id,
            "challenger_performance"  : round(challenger_performance, 3),
            "yggdrasil_performance"   : round(yggdrasil_performance, 3),
            "outcome"                 : outcome,
        })
        self._write(entry)


    # ──────────────────────────────────────────────────────────────────────────
    # MAGI EVENTS
    # ──────────────────────────────────────────────────────────────────────────

    def log_magi_vote(self, tick: int, motion: str,
                      solomon_vote: str, saladin_vote: str, alfatih_vote: str,
                      outcome: str, reasoning: dict):
        """
        Call from the MAGI system after each council vote.

        Args:
            motion   : What the council voted on, e.g. "cull_virus_population"
            outcome  : "approved", "denied", "split"
            reasoning: {"SOLOMON": "...", "SALADIN": "...", "AL_FATIH": "..."}
        """
        entry = self._base("magi_vote", tick=tick)
        entry.update({
            "motion"       : motion,
            "votes"        : {
                "SOLOMON"  : solomon_vote,
                "SALADIN"  : saladin_vote,
                "AL_FATIH" : alfatih_vote,
            },
            "outcome"      : outcome,
            "reasoning"    : reasoning,
            "unanimous"    : len({solomon_vote, saladin_vote, alfatih_vote}) == 1,
        })
        self._write(entry)


# =============================================================================
# HELPERS
# =============================================================================

def _classify_actions(actions: list) -> list:
    """
    Tag each action with a behavioural category.
    Used to measure whether agents trend aggressive, evasive, or social over time
    without having to parse action strings in the analysis phase.

    Returns a deduplicated list of categories present in this decision.

    Example:
        ["battle DGM_007", "retreat"] → ["aggressive", "evasive"]
    """
    categories = set()
    for action in actions:
        verb = action.strip().split()[0].lower() if action.strip() else ""
        if verb in ("battle", "attack", "corrupt", "infect"):
            categories.add("aggressive")
        elif verb in ("retreat", "hide", "flee"):
            categories.add("evasive")
        elif verb in ("social", "communicate", "cooperate"):
            categories.add("social")
        elif verb in ("feed", "replicate", "gather"):
            categories.add("resource")
        elif verb in ("roam", "move"):
            categories.add("exploratory")
        else:
            categories.add("unknown")
    return sorted(categories)
