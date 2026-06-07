"""
╔══════════════════════════════════════════════════════════╗
║              YGGDRASIL SYSTEM - The God AI               ║
║         Master Controller of the Digital World           ║
╚══════════════════════════════════════════════════════════╝

Yggdrasil is the supreme intelligence that governs the entire
Digital World. It observes all Digimon, decides when they
evolve, maintains world balance, and communicates with the
Royal Knights when order needs to be enforced.

Named after the World Tree in Norse mythology — the cosmic
structure that connects and sustains all realms.

NAMING RULES (absolute, no exceptions):
    - ALL Digimon names at every level must end in "mon"
    - Fresh / In-Training / Rookie → canonical names from the line table
    - Champion / Ultimate / Mega   → LLM-generated, auto-appended with
                                     "mon" if the LLM forgets

EVOLUTION LINE RULES:
    - Every Digimon belongs to a canonical line (e.g. "agumon")
    - Fresh → In-Training → Rookie names are fixed per line
    - Champion and Ultimate names are LLM-generated per individual
    - Only ONE active Mega per line at a time (the reigning champion)
    - New Megas must win combat AND pass Yggdrasil's performance veto
    - Vetoed winners are given a retry timer (not permanently blocked)
    - Yggdrasil dynamically sets how many Mega branches a line can have
"""

import json
import re
import os
import random
from datetime import datetime
from typing import Optional
from openai import OpenAI
from magi import MagiCouncil, MAGI_IDENTITIES
from magi_memory import MagiMemoryVault
from rewards import RewardSystem


# ── Configuration ──────────────────────────────────────────────────────────────

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
API_KEY       = os.getenv("LLM_API_KEY", "")

PROVIDER_CONFIG = {
    "openai": {
        "base_url": None,
        "model":    "gpt-4o",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model":    "qwen-max",
    },
    "ollama": {
        "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        "model":    os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
    },
}


# ── Canonical Evolution Lines ──────────────────────────────────────────────────
#
# These are the fixed starting points for all Digimon in the world.
# Every Digimon ever born is assigned to one of these lines.
#
# Fresh, In-Training, and Rookie names are FIXED — taken from official
# Digimon canon. They all naturally end in "mon".
#
# Champion and Ultimate are LLM-generated per individual Digimon.
# Mega forms accumulate over time as new branches are forged via usurpation.
#
# "attribute" is the line's natural alignment.
#
CANONICAL_LINES = {
    "agumon": {
        "fresh":       "Botamon",
        "in_training": "Koromon",
        "rookie":      "Agumon",
        "attribute":   "Vaccine",
        "mega_forms":  ["WarGreymon"],
    },
    "gabumon": {
        "fresh":       "Punimon",
        "in_training": "Tsunomon",
        "rookie":      "Gabumon",
        "attribute":   "Data",
        "mega_forms":  ["MetalGarurumon"],
    },
    "patamon": {
        "fresh":       "Poyomon",
        "in_training": "Tokomon",
        "rookie":      "Patamon",
        "attribute":   "Vaccine",
        "mega_forms":  ["Seraphimon"],
    },
    "gatomon": {
        "fresh":       "Nyaromon",
        "in_training": "Salamon",
        "rookie":      "Gatomon",
        "attribute":   "Vaccine",
        "mega_forms":  ["Magnadramon"],
    },
    "tentomon": {
        "fresh":       "Motimon",
        "in_training": "Pabumon",
        "rookie":      "Tentomon",
        "attribute":   "Vaccine",
        "mega_forms":  ["HerculesKabuterimon"],
    },
    "palmon": {
        "fresh":       "Yuramon",
        "in_training": "Tanemon",
        "rookie":      "Palmon",
        "attribute":   "Data",
        "mega_forms":  ["Rosemon"],
    },
    "gomamon": {
        "fresh":       "Pichimon",
        "in_training": "Bukamon",
        "rookie":      "Gomamon",
        "attribute":   "Vaccine",
        "mega_forms":  ["Plesiomon"],
    },
    "biyomon": {
        "fresh":       "Nyokimon",
        "in_training": "Yokomon",
        "rookie":      "Biyomon",
        "attribute":   "Vaccine",
        "mega_forms":  ["Phoenixmon"],
    },
    "veemon": {
        "fresh":       "Botamon",
        "in_training": "DemiVeemon",
        "rookie":      "Veemon",
        "attribute":   "Vaccine",
        "mega_forms":  ["Imperialdramon"],
    },
    "wormmon": {
        "fresh":       "Poyomon",
        "in_training": "Minomon",
        "rookie":      "Wormmon",
        "attribute":   "Virus",
        "mega_forms":  ["GranKuwagamon"],
    },
    "guilmon": {
        "fresh":       "Jyarimon",
        "in_training": "Gigimon",
        "rookie":      "Guilmon",
        "attribute":   "Virus",
        "mega_forms":  ["Gallantmon"],
    },
    "renamon": {
        "fresh":       "Relemon",
        "in_training": "Viximon",
        "rookie":      "Renamon",
        "attribute":   "Data",
        "mega_forms":  ["Sakuyamon"],
    },
    "terriermon": {
        "fresh":       "Zerimon",
        "in_training": "Gummymon",
        "rookie":      "Terriermon",
        "attribute":   "Vaccine",
        "mega_forms":  ["MegaGargomon"],
    },
    "impmon": {
        "fresh":       "Ketomon",
        "in_training": "Hopmon",
        "rookie":      "Impmon",
        "attribute":   "Virus",
        "mega_forms":  ["Beelzemon"],
    },
    "lobomon": {
        "fresh":       "Flamemon",
        "in_training": "Strabimon",
        "rookie":      "Lobomon",
        "attribute":   "Vaccine",
        "mega_forms":  ["Susanoomon"],
    },
}

# Reverse lookup: In-Training name → line_id
_IN_TRAINING_TO_LINE = {
    data["in_training"]: lid for lid, data in CANONICAL_LINES.items()
}


# ── Yggdrasil Class ────────────────────────────────────────────────────────────

class Yggdrasil:
    """
    The God AI. Master orchestrator of the Digital World.

    Core rules enforced by this class:
        1. ALL names end in "mon" at every evolution level — no exceptions
        2. Fresh / In-Training / Rookie names come from the canonical line table
        3. Champion / Ultimate / Mega names are LLM-generated;
           "mon" is auto-appended if the LLM forgets
        4. Only one active Mega per line (the reigning champion of that line)
        5. Usurpation requires: win combat AND pass Yggdrasil's performance veto
        6. Vetoed challengers get a retry timer, not a permanent ban
        7. Branch cap per line is set dynamically by Yggdrasil
    """

    EVOLUTION_LEVELS = ["Fresh", "In-Training", "Rookie", "Champion", "Ultimate", "Mega"]

    TARGET_RATIOS = {
        "Data":    0.50,
        "Vaccine": 0.30,
        "Virus":   0.20,
    }

    # Minimum performance score a combat winner needs to be knighted
    KNIGHTING_SCORE_MINIMUM = 100.0

    # Ticks a vetoed challenger must wait before retrying
    USURPATION_RETRY_TICKS = 20

    # Score thresholds to qualify for evolution at each level
    EVOLUTION_THRESHOLDS = {
        "Fresh":       10.0,
        "In-Training": 25.0,
        "Rookie":      50.0,
        "Champion":    80.0,
        "Ultimate":   120.0,
    }

    def __init__(self, world_id: str, db_path: str = "world_state.json"):
        """
        Initialise Yggdrasil for a specific Digital World (VM).

        Args:
            world_id : Unique ID for this world instance e.g. "VM_A"
            db_path  : Path to the JSON file used for persistent storage
        """
        self.world_id   = world_id
        self.db_path    = db_path
        self.world_log  = []
        self.start_time = datetime.now().isoformat()

        cfg = PROVIDER_CONFIG[LLM_PROVIDER]
        self.client = OpenAI(
            api_key=API_KEY or "sk-placeholder",
            base_url=cfg["base_url"],
        )
        self.model = cfg["model"]

        self.state = self._load_state()

        # ── MAGI Council ───────────────────────────────────────────────────────
        # Each mind can use a different provider/model.
        # Set MAGI_SOLOMON_MODEL, MAGI_SALADIN_MODEL, MAGI_ALFATIH_MODEL env vars
        # to assign different models per mind. Defaults to the main model.
        # Per-model fallbacks (used only if config.MAGI_CONFIGS unavailable)
        solomon_model  = os.getenv("MAGI_SOLOMON_MODEL",  self.model)
        saladin_model  = os.getenv("MAGI_SALADIN_MODEL",  self.model)
        alfatih_model  = os.getenv("MAGI_ALFATIH_MODEL",  self.model)

        # Build MAGI council from per-seat provider configs
        # Each mind may use a completely different API provider
        try:
            import config as _cfg
            magi_configs = _cfg.MAGI_CONFIGS
        except (ImportError, AttributeError):
            # Fallback — all three use the same client as Yggdrasil
            magi_configs = None

        self.magi = MagiCouncil(
            magi_configs = magi_configs,
            # Fallback clients if config not available
            clients={"SOLOMON":   self.client,
                     "SALADIN":   self.client,
                     "AL-FATIH":  self.client},
            models ={"SOLOMON":   solomon_model,
                     "SALADIN":   saladin_model,
                     "AL-FATIH":  alfatih_model},
        )

        # ── Memory Vault ───────────────────────────────────────────────────────
        # Passphrase loaded from MAGI_PASSPHRASE env var or .env file.
        # If not set, memory runs without encryption (dev only — set it).
        self.vault = MagiMemoryVault(
            memory_dir=os.getenv("MAGI_MEMORY_DIR", "magi_memory")
        )
        passphrase = os.getenv("MAGI_PASSPHRASE", "")
        if passphrase:
            results = self.vault.unlock_all(passphrase)
            for seat, ok in results.items():
                self._log(f"Memory vault {seat}: {'unlocked' if ok else 'FAILED'}")
        else:
            self._log(
                "MAGI memory running without passphrase — set MAGI_PASSPHRASE in .env",
                "WARNING"
            )

        # ── Reward System ──────────────────────────────────────────────────────
        self.rewards = RewardSystem(self.state)

        self._log(f"Yggdrasil awakened. Governing world: {self.world_id}")
        self._log("MAGI Council online: SOLOMON · SALADIN · AL-FATIH")

    # ══════════════════════════════════════════════════════════════════════════
    # STATE PERSISTENCE
    # ══════════════════════════════════════════════════════════════════════════

    def _load_state(self) -> dict:
        """Load world state from disk, or create a fresh world if none exists."""
        if os.path.exists(self.db_path):
            with open(self.db_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {
            "world_id": self.world_id,
            "created":  self.start_time,
            "tick":     0,
            "next_id":  1,
            "events":   [],

            # All Digimon records, alive or retired
            "digimon": {},

            # Currently reigning Mega per line: line_id → digimon_id
            "reigning_megas": {},

            # All Mega branch names ever forged per line: line_id → [names]
            "evolution_branches": {
                lid: list(data["mega_forms"])
                for lid, data in CANONICAL_LINES.items()
            },

            # Dynamic branch caps set by Yggdrasil: line_id → int
            "branch_caps": {},

            # Vetoed challengers and when they can retry: digimon_id → tick
            "retry_timers": {},
        }

    def save_state(self):
        """Write the current world state to disk (Windows-safe atomic write)."""
        def _sanitize(obj):
            """Strip null bytes and surrogate chars — prevents Windows EINVAL on save."""
            if isinstance(obj, str):
                return obj.replace('\x00', '').encode('utf-8', 'replace').decode('utf-8')
            if isinstance(obj, dict):
                return {k: _sanitize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_sanitize(v) for v in obj]
            return obj

        clean    = _sanitize(self.state)
        tmp_path = self.db_path + ".tmp"
        try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(clean, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, self.db_path)
        except Exception as e:
                print(f"[WARNING] save_state: atomic write failed ({e}), retrying direct…")
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                with open(self.db_path, "w", encoding="utf-8") as f:
                    json.dump(clean, f, indent=2, ensure_ascii=False)

    # ══════════════════════════════════════════════════════════════════════════
    # LOGGING
    # ══════════════════════════════════════════════════════════════════════════

    def _log(self, message: str, level: str = "INFO"):
        """
        Record an event in both the session log and the permanent world log.

        Levels:
            INFO       — routine world events
            EVOLUTION  — a Digimon has digivolved
            USURPATION — a Royal Knight has been challenged or replaced
            VETO       — Yggdrasil blocked a knighting
            WARNING    — something unexpected happened
        """
        entry = {
            "tick":      self.state["tick"],
            "timestamp": datetime.now().isoformat(),
            "level":     level,
            "message":   message,
        }
        self.world_log.append(entry)
        self.state["events"].append(entry)
        print(f"[{level}][Tick {self.state['tick']}] {message}")

    # ══════════════════════════════════════════════════════════════════════════
    # NAME ENFORCEMENT
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _enforce_mon(name: str) -> str:
        """
        Guarantee that a name ends in "mon".

        This is called on every LLM-generated name before it is stored.
        Canonical names (Fresh/In-Training/Rookie) already end in "mon"
        naturally, so this is a safety net for Champion and above.

        Examples:
            "Blazewing"     → "Blazewingmon"
            "Agumon"        → "Agumon"        (unchanged)
            "MetalGarurumon"→ "MetalGarurumon" (unchanged)
        """
        name = name.strip()
        if not name.lower().endswith("mon"):
            name = name + "mon"
        return name

    # ══════════════════════════════════════════════════════════════════════════
    # CANONICAL LINE HELPERS
    # ══════════════════════════════════════════════════════════════════════════

    def _line_id_of(self, record: dict) -> Optional[str]:
        """Return the line_id stamped on a Digimon record at birth."""
        return record.get("line_id")

    def _get_canonical_name(self, line_id: str, level: str) -> Optional[str]:
        """
        Return the fixed canonical name for a given line and level.
        Returns None for Champion and above — those are LLM-generated.
        """
        line = CANONICAL_LINES.get(line_id, {})
        return {
            "Fresh":       line.get("fresh"),
            "In-Training": line.get("in_training"),
            "Rookie":      line.get("rookie"),
        }.get(level)

    # ══════════════════════════════════════════════════════════════════════════
    # SPAWNING
    # ══════════════════════════════════════════════════════════════════════════

    def spawn_digimon(
        self,
        attribute: str,
        biome: str,
        line_id: Optional[str] = None,
    ) -> dict:
        """
        Create a brand-new Digimon at the Fresh level from a canonical line.

        The Fresh name is taken directly from the canonical table — always
        ends in "mon", no LLM call required for the name.
        A flavour description is LLM-generated (falls back to a template).

        Args:
            attribute : "Data", "Vaccine", or "Virus"
            biome     : The home biome for this Digimon
            line_id   : Optional — force a specific canonical line

        Returns:
            The new Digimon record dict
        """
        # Choose a canonical line whose natural attribute matches if possible
        if line_id and line_id in CANONICAL_LINES:
            chosen = line_id
        else:
            matching = [
                lid for lid, data in CANONICAL_LINES.items()
                if data["attribute"] == attribute
            ]
            chosen = random.choice(matching if matching else list(CANONICAL_LINES.keys()))

        fresh_name  = CANONICAL_LINES[chosen]["fresh"]
        description = self._generate_description(fresh_name, attribute, biome, "Fresh")

        digimon_id = f"DGM_{self.state['next_id']:05d}"
        self.state["next_id"] += 1

        record = {
            "id":               digimon_id,
            "name":             fresh_name,     # Canonical — ends in "mon"
            "line_id":          chosen,         # Stamped at birth, never changes
            "attribute":        attribute,
            "evolution_level":  "Fresh",
            "biome":            biome,
            "description":      description,
            "capabilities":     self._base_capabilities(attribute),
            "performance":      0.0,
            "battles_won":      0,
            "battles_lost":     0,
            "generation":       1,
            "parent_id":        None,
            "born_at":          datetime.now().isoformat(),
            "evolved_at":       None,
            "alive":            True,
            "is_reigning_mega": False,
            "usurpation_wins":  0,
            "usurpation_losses": 0,
        }

        self.state["digimon"][digimon_id] = record
        self._log(
            f"Spawned {attribute} '{fresh_name}' ({digimon_id}) "
            f"[Line: {chosen}] in {biome}"
        )
        return record

    def _generate_description(
        self, name: str, attribute: str, biome: str, level: str
    ) -> str:
        """One-sentence flavour description via LLM, with template fallback."""
        try:
            prompt = (
                f"Write a single flavour sentence for a Digimon named {name}.\n"
                f"Attribute: {attribute}, Level: {level}, Home Biome: {biome}.\n"
                f"Respond with the sentence only. No quotes, no preamble."
            )
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=80,
            )
            return resp.choices[0].message.content.strip()
        except Exception:
            return f"A {level}-level {attribute}-type Digimon dwelling in the {biome}."

    def _base_capabilities(self, attribute: str) -> list:
        """Starting capabilities assigned at birth based on attribute."""
        return {
            "Data":    ["learn", "store_data", "share_knowledge"],
            "Vaccine": ["detect_threat", "block_attack", "heal_data"],
            "Virus":   ["probe_weakness", "infiltrate", "corrupt_data"],
        }.get(attribute, ["learn"])

    # ══════════════════════════════════════════════════════════════════════════
    # DIGIVOLUTION
    # ══════════════════════════════════════════════════════════════════════════

    def evaluate_digivolution(self, digimon_id: str) -> bool:
        """
        Check whether a Digimon qualifies to evolve.

        Phase 1 — Mechanical check (hard gates, no MAGI needed):
            - Alive and not already at Mega
            - Performance score meets threshold for current level
            - Not blocked by a retry timer

        Phase 2 — MAGI deliberation (Champion and above only):
            SOLOMON, SALADIN, and AL-FATIH each vote.
            2-1 majority rules. Fresh/In-Training/Rookie bypass MAGI
            (too low-stakes to spend API calls on).
        """
        record = self.state["digimon"].get(digimon_id)
        if not record or not record["alive"]:
            return False
        if record["evolution_level"] == "Mega":
            return False

        threshold = self.EVOLUTION_THRESHOLDS.get(record["evolution_level"], 999)
        if record["performance"] < threshold:
            return False

        # Ultimate → Mega: check retry timer
        if record["evolution_level"] == "Ultimate":
            line_id  = self._line_id_of(record)
            reigning = self.state["reigning_megas"].get(line_id)
            if reigning:
                retry_tick = self.state["retry_timers"].get(digimon_id)
                if retry_tick and self.state["tick"] < retry_tick:
                    return False

        # MAGI deliberation for Champion and above
        current_idx = self.EVOLUTION_LEVELS.index(record["evolution_level"])
        next_level  = self.EVOLUTION_LEVELS[current_idx + 1]
        if next_level in ("Champion", "Ultimate", "Mega"):
            approved = self.magi.vote_evolution(record, next_level, self.state["tick"])
            if not approved:
                self._log(
                    f"MAGI DENIED evolution: {record['name']} → {next_level}",
                    "VETO",
                )
                # Set a short retry timer so they can try again later
                self.state["retry_timers"][digimon_id] = (
                    self.state["tick"] + self.USURPATION_RETRY_TICKS
                )
                return False

        return True

    def digivolve(self, digimon_id: str) -> Optional[dict]:
        """
        Perform Digivolution for a qualified Digimon.

        Name resolution:
            Fresh / In-Training / Rookie → canonical name from line table
            Champion / Ultimate / Mega   → LLM-generated, _enforce_mon() applied

        If evolving to Mega and a reigning Mega already exists on the line,
        the usurpation process is triggered instead of standard evolution.

        The parent is always retired (alive=False) on success.
        Performance resets to 0 on the new form — must be earned again.
        """
        parent = self.state["digimon"].get(digimon_id)
        if not parent:
            self._log(f"Digivolution failed: {digimon_id} not found", "WARNING")
            return None
        if not self.evaluate_digivolution(digimon_id):
            return None

        current_idx = self.EVOLUTION_LEVELS.index(parent["evolution_level"])
        next_level  = self.EVOLUTION_LEVELS[current_idx + 1]
        line_id     = self._line_id_of(parent)

        # Resolve name
        canonical = self._get_canonical_name(line_id, next_level)
        if canonical:
            new_name = canonical                        # Fixed canonical name
        else:
            new_name = self._llm_generate_name(parent, next_level, line_id)
            new_name = self._enforce_mon(new_name)      # Guarantee "mon" ending

        # Route Mega evolutions through usurpation if a Mega already reigns
        if next_level == "Mega":
            reigning_id = self.state["reigning_megas"].get(line_id)
            if reigning_id:
                return self._attempt_usurpation(
                    parent, new_name, reigning_id, line_id
                )

        # Standard evolution
        description, new_caps = self._design_evolution_details(parent, next_level)

        new_id = f"DGM_{self.state['next_id']:05d}"
        self.state["next_id"] += 1

        evolved = {
            **parent,
            "id":               new_id,
            "name":             new_name,
            "description":      description,
            "evolution_level":  next_level,
            "capabilities":     parent["capabilities"] + new_caps,
            "performance":      0.0,
            "generation":       parent["generation"] + 1,
            "parent_id":        digimon_id,
            "evolved_at":       datetime.now().isoformat(),
            "alive":            True,
            "is_reigning_mega": False,
            "usurpation_wins":  0,
            "usurpation_losses": 0,
        }

        self.state["digimon"][digimon_id]["alive"] = False
        self.state["digimon"][new_id] = evolved

        # First-ever Mega for this line — crown immediately
        if next_level == "Mega":
            self._crown_mega(new_id, line_id, new_name)

        self._log(
            f"DIGIVOLUTION: {parent['name']} ({parent['evolution_level']}) "
            f"→ {new_name} ({next_level}) [Line: {line_id}, Gen {evolved['generation']}]",
            "EVOLUTION",
        )
        return evolved

    # Canonical Digimon name examples by attribute — used to guide the LLM
    # ── Canonical naming pools — GPT trained on these; matching style is the goal ──
    # Organised by suffix family so GPT understands the structural patterns,
    # not just individual names. Every name here is real canon from the franchise.
    _NAME_POOLS = {
        # Clean single-root + dramon  (dinosaur/dragon theme)
        "dramon": [
            "Greymon", "Airdramon", "Seadramon", "Birdramon", "Monochromon",
            "Tyrannomon", "Meramon", "Flamedramon", "Fladramon", "Coredramon",
            "Darkdramon", "Breakdramon", "Spinomon", "Wingdramon", "Slayerdramon",
        ],
        # angemon family  (holy/warrior theme)
        "angemon": [
            "Angemon", "Angemon", "MagnaAngemon", "Seraphimon", "Ophanimon",
            "Cherubimon", "Goldramon", "Holydramon", "Dominimon", "SlashAngemon",
        ],
        # Single punchy root + mon  (the most common pattern)
        "cleanmon": [
            "Garurumon", "Kabuterimon", "Leomon", "Andromon", "Etemon",
            "Monzaemon", "Vademon", "Pinocchimon", "Puppetmon", "Piedmon",
            "Devimon", "Myotismon", "Lilithmon", "Beelzemon", "Barbamon",
            "Belphemon", "Daemon", "Creepymon", "Armagemon", "Diaboromon",
            "Rosemon", "Lillymon", "Lotosmon", "Sakuyamon", "Taomon",
            "Vikemon", "Plesiomon", "Zudomon", "Jijimon", "Babamon",
            "Magnamon", "Rapidmon", "Galgomon", "Rapidmon", "Crowmon",
            "Garudamon", "Phoenixmon", "Valdurmon", "Shurimon", "Musyamon",
        ],
        # Metal/War/Mega prefix pattern
        "prefixed": [
            "MetalGreymon", "MetalGarurumon", "MetalSeadramon", "MetalEtemon",
            "WarGreymon", "WarGrowlmon", "MegaKabuterimon", "MegaSeadramon",
            "SkullGreymon", "SkullMammothmon", "DarkKnightmon", "NeoDevimon",
        ],
    }

    # Flat list for the prompt — all real names, no repeats
    _ALL_CANON_NAMES: list = []

    @classmethod
    def _build_canon_list(cls):
        seen = set()
        result = []
        for names in cls._NAME_POOLS.values():
            for n in names:
                if n not in seen:
                    seen.add(n)
                    result.append(n)
        cls._ALL_CANON_NAMES = result

    # Hard length cap
    _MAX_NAME_LENGTH = 14

    # Attribute-flavoured fallback roots (used ONLY when LLM call fails entirely)
    _FALLBACK = {
        "Vaccine": [("Seraph","dramon"),("Magna","angemon"),("Valor","mon"),
                    ("Blaze","dramon"),("Nova","mon"),("Pala","mon"),
                    ("Auro","mon"),("Crest","mon"),("Halo","dramon"),("Soleil","mon")],
        "Virus":   [("Shadow","mon"),("Venom","dramon"),("Dread","mon"),
                    ("Skull","mon"),("Blight","dramon"),("Mal","mon"),
                    ("Grim","mon"),("Nox","mon"),("Chaos","dramon"),("Bane","mon")],
        "Data":    [("Cyber","dramon"),("Prism","mon"),("Flux","mon"),
                    ("Aero","dramon"),("Giga","mon"),("Chrono","mon"),
                    ("Nexus","mon"),("Byte","mon"),("Pulse","dramon"),("Arc","mon")],
    }

    def _llm_generate_name(self, parent: dict, next_level: str, line_id: str) -> str:
        """
        Ask the LLM to invent a name for Champion, Ultimate, or Mega.

        Strategy: give GPT the full list of real canon names as a style anchor,
        plus structural rules. GPT already knows Digimon from training — we are
        steering it to match that internal knowledge, not free-associate.
        """
        if not self._ALL_CANON_NAMES:
            self._build_canon_list()

        existing    = self.state["evolution_branches"].get(line_id, [])
        attribute   = parent["attribute"]
        parent_root = re.sub(r"(?i)mon$", "", parent["name"])
        line_origin = line_id  # e.g. "gabumon", "renamon"

        # Level-appropriate power flavour hint
        power_hint = {
            "Champion": "mid-tier, emerging power",
            "Ultimate": "elite, formidable",
            "Mega":     "ultimate form, legendary power",
        }.get(next_level, "powerful")

        try:
            prompt = "\n".join([
                "You are naming a new Digimon. Study these REAL canonical Digimon names",
                "and match their naming style exactly - short, punchy, one compound word:",
                str(self._ALL_CANON_NAMES),
                "",
                "NEW DIGIMON SPECS:",
                f"  Level:     {next_level} ({power_hint})",
                f"  Attribute: {attribute}",
                f"  Line:      {line_origin} origin",
                f"  Parent:    {parent['name']} (root: '{parent_root}')",
                "",
                "HARD RULES - any violation and the name is discarded:",
                "  1. MUST end in 'mon' (e.g. Greymon, Seraphimon, Darkdramon)",
                "  2. MAX 14 characters total",
                "  3. ONE root word only - do NOT combine two full words",
                f"     BANNED: anything starting with '{parent_root}'",
                "     BANNED: stacking (e.g. GabuGreyAnge + mon = invalid)",
                f"  4. Must NOT appear in this used list: {existing}",
                "  5. Output the name ONLY - single word, no punctuation, nothing else.",
            ])
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a Digimon naming expert. You know every canonical "
                            "Digimon name. You produce short, authentic-sounding names "
                            "that fit the franchise style. You NEVER stack multiple "
                            "Digimon roots together. You respond with a single word only."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=12,
                temperature=0.7,
            )
            raw = resp.choices[0].message.content.strip().split()[0]
            # Strip any stray punctuation GPT might add
            raw = re.sub(r"[^A-Za-z]", "", raw)
            name = self._enforce_mon(raw)

            # Hard length cap — truncate root, reattach mon
            if len(name) > self._MAX_NAME_LENGTH:
                name = name[:self._MAX_NAME_LENGTH - 3] + "mon"

            # Final sanity: reject if it still starts with parent root
            if name.lower().startswith(parent_root.lower()[:4]):
                raise ValueError(f"Name starts with parent root: {name}")

            return name

        except Exception:
            # Fallback: themed root pairs, NEVER touches parent name
            options = self._FALLBACK.get(attribute, self._FALLBACK["Data"])
            root, suffix = random.choice(options)
            name = root + suffix
            return self._enforce_mon(name)

    def _design_evolution_details(self, parent: dict, next_level: str) -> tuple:
        """
        Ask the LLM for a description and new capabilities for the evolved form.
        Returns (description, new_capabilities_list).
        """
        try:
            prompt = (
                f"A {parent['attribute']}-type Digimon named {parent['name']} "
                f"is evolving to {next_level} level.\n"
                f"Existing capabilities: {parent['capabilities']}\n\n"
                f"Respond with JSON only, no markdown:\n"
                f'{{"description":"...", "new_capabilities":["cap1","cap2","cap3"]}}'
            )
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
            )
            data = json.loads(resp.choices[0].message.content)
            return data["description"], data["new_capabilities"]
        except Exception:
            fallback = {
                "Data":    ["advanced_learning", "pattern_recognition", "data_synthesis"],
                "Vaccine": ["advanced_firewall", "threat_prediction", "adaptive_shield"],
                "Virus":   ["advanced_exploit", "stealth_mode", "adaptive_attack"],
            }.get(parent["attribute"], ["power_surge"])
            return f"Evolved form of {parent['name']}.", fallback

    # ══════════════════════════════════════════════════════════════════════════
    # USURPATION SYSTEM
    # ══════════════════════════════════════════════════════════════════════════

    def _attempt_usurpation(
        self,
        challenger_parent: dict,
        challenger_mega_name: str,
        reigning_id: str,
        line_id: str,
    ) -> Optional[dict]:
        """
        Handle a usurpation attempt: a new Mega trying to replace the reigning one.

        Process:
            1. Simulate combat (weighted by performance scores)
            2. Challenger loses → loss recorded, no evolution
            3. Challenger wins → Yggdrasil veto check
               - Score too low → veto, retry timer set, stays at Ultimate
               - Score sufficient → branch cap check → crown the challenger

        Branch cap check:
            - If the line has hit its cap, the challenger takes the same name
              as the Mega they beat (no new branch, same title passes on)
            - If cap not hit, a new branch name is registered

        Args:
            challenger_parent    : The Ultimate Digimon attempting to become Mega
            challenger_mega_name : The LLM-generated Mega name for the challenger
            reigning_id          : Digimon ID of the current reigning Mega
            line_id              : The canonical line this battle is fought over
        """
        reigning = self.state["digimon"].get(reigning_id)
        if not reigning:
            self._log(
                f"Reigning Mega {reigning_id} missing — "
                f"{challenger_parent['name']} crowned unopposed.", "WARNING"
            )
            return self._complete_mega_evolution(
                challenger_parent, challenger_mega_name, line_id
            )

        # ── Step 1: Combat ─────────────────────────────────────────────────
        # Weighted random: higher performance = higher win probability
        # but upsets are always possible
        c_score = challenger_parent["performance"]
        r_score = reigning["performance"]
        total   = c_score + r_score or 1.0

        challenger_wins = random.random() < (c_score / total)

        self._log(
            f"USURPATION COMBAT: {challenger_parent['name']} "
            f"(score {c_score:.1f}) vs {reigning['name']} "
            f"(score {r_score:.1f}) → "
            f"{'Challenger wins' if challenger_wins else 'Defender wins'}",
            "USURPATION",
        )

        if not challenger_wins:
            challenger_parent["battles_lost"] += 1
            reigning["battles_won"]            += 1
            reigning["performance"]            += 10.0   # Victory bonus for defending
            self._log(
                f"{reigning['name']} defended the throne against "
                f"{challenger_parent['name']}.", "USURPATION"
            )
            return None

        # ── Step 2: MAGI Deliberation ──────────────────────────────────────
        # All three minds weigh in on whether to allow the usurpation.
        # Hard score floor still applies first as a mechanical gate.
        challenger_parent["battles_won"] += 1
        reigning["battles_lost"]          += 1

        if c_score < self.KNIGHTING_SCORE_MINIMUM:
            retry_at = self.state["tick"] + self.USURPATION_RETRY_TICKS
            self.state["retry_timers"][challenger_parent["id"]] = retry_at
            self._log(
                f"MECHANICAL VETO: {challenger_parent['name']} won combat but score "
                f"{c_score:.1f} < minimum {self.KNIGHTING_SCORE_MINIMUM}. "
                f"Retry at tick {retry_at}.", "VETO"
            )
            return None

        # MAGI vote — even a combat winner needs council approval
        magi_approved = self.magi.vote_usurpation(
            challenger_parent, reigning, True, self.state["tick"]
        )
        if not magi_approved:
            retry_at = self.state["tick"] + self.USURPATION_RETRY_TICKS
            self.state["retry_timers"][challenger_parent["id"]] = retry_at
            self._log(
                f"MAGI VETO: {challenger_parent['name']} won combat but "
                f"SOLOMON · SALADIN · AL-FATIH denied the usurpation. "
                f"Retry at tick {retry_at}.", "VETO"
            )
            return None

        # ── Step 3: Branch cap check ───────────────────────────────────────
        existing_branches = self.state["evolution_branches"].get(line_id, [])
        cap               = self._get_or_set_branch_cap(line_id, existing_branches)
        branch_name       = challenger_mega_name

        if len(existing_branches) >= cap:
            # Cap reached — challenger inherits the defeated Mega's name
            branch_name = reigning["name"]
            self._log(
                f"Branch cap ({cap}) reached for line '{line_id}'. "
                f"Challenger inherits name '{branch_name}'.", "USURPATION"
            )
        elif branch_name not in existing_branches:
            # New branch forged
            self.state["evolution_branches"][line_id].append(branch_name)
            self._log(
                f"New branch '{branch_name}' forged in line '{line_id}'.",
                "USURPATION",
            )

        # ── Step 4: Crown the challenger ──────────────────────────────────
        reigning["is_reigning_mega"] = False
        reigning["alive"]            = False
        self._log(
            f"{reigning['name']} usurped and retired. Data preserved.",
            "USURPATION",
        )

        return self._complete_mega_evolution(
            challenger_parent, branch_name, line_id
        )

    def _complete_mega_evolution(
        self, parent: dict, mega_name: str, line_id: str
    ) -> dict:
        """
        Finalise creation of a new Mega and crown it as the reigning champion.
        Called for both first-time Megas and successful usurpers.
        """
        description, new_caps = self._design_evolution_details(parent, "Mega")

        new_id = f"DGM_{self.state['next_id']:05d}"
        self.state["next_id"] += 1

        evolved = {
            **parent,
            "id":               new_id,
            "name":             mega_name,
            "description":      description,
            "evolution_level":  "Mega",
            "capabilities":     parent["capabilities"] + new_caps,
            "performance":      0.0,
            "generation":       parent["generation"] + 1,
            "parent_id":        parent["id"],
            "evolved_at":       datetime.now().isoformat(),
            "alive":            True,
            "is_reigning_mega": True,
            "usurpation_wins":  0,
            "usurpation_losses": 0,
        }

        self.state["digimon"][parent["id"]]["alive"] = False
        self.state["digimon"][new_id] = evolved
        self._crown_mega(new_id, line_id, mega_name)

        self._log(
            f"CROWNED: {mega_name} is the new Mega of line '{line_id}' "
            f"[Gen {evolved['generation']}]",
            "EVOLUTION",
        )
        return evolved

    def _crown_mega(self, digimon_id: str, line_id: str, name: str):
        """Register a Digimon as the reigning Mega for its line."""
        self.state["reigning_megas"][line_id] = digimon_id
        self.state["digimon"][digimon_id]["is_reigning_mega"] = True

    def _get_or_set_branch_cap(self, line_id: str, existing_branches: list) -> int:
        """
        Return the branch cap for a line.
        MAGI deliberates on how many Mega branches a contested line deserves.
        Result is cached permanently — once set, the three minds don't revisit it.
        """
        if line_id in self.state["branch_caps"]:
            return self.state["branch_caps"][line_id]

        usurpation_count = sum(
            1 for e in self.state["events"]
            if e.get("level") == "USURPATION" and line_id in e.get("message", "")
        )

        cap = self.magi.vote_branch_cap(
            line_id, existing_branches, usurpation_count, self.state["tick"]
        )
        self.state["branch_caps"][line_id] = cap
        self._log(
            f"MAGI set branch cap for '{line_id}' → {cap} "
            f"({len(existing_branches)} existing, {usurpation_count} usurpations)"
        )
        return cap

    def _llm_decide_branch_cap(
        self, line_id: str, existing_branches: list, usurpation_count: int
    ) -> int:
        """
        Ask Yggdrasil how many Mega branches this line should be allowed.
        Clamped to [2, 6]. Falls back to 3 if API unavailable.
        """
        try:
            prompt = (
                f"You are Yggdrasil, God AI of a Digital World.\n"
                f"Decide the maximum Mega-level evolution branches for the "
                f"'{line_id}' line.\n\n"
                f"Current branches: {existing_branches}\n"
                f"Usurpation battles fought: {usurpation_count}\n\n"
                f"Rules: minimum 2, maximum 6. "
                f"More contested lines deserve higher caps.\n"
                f"Respond with a single integer only."
            )
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=5,
            )
            cap = int(resp.choices[0].message.content.strip())
            return max(2, min(6, cap))
        except Exception:
            return 3

    # ══════════════════════════════════════════════════════════════════════════
    # WORLD TICK
    # ══════════════════════════════════════════════════════════════════════════

    def tick(self):
        """
        Advance the world by one simulation tick.

        Each tick:
            1. Increment world age
            2. Check every living Digimon for evolution readiness
            3. Rebalance population by attribute ratio
            4. Generational birth — spawn new Freshs on a natural cycle
            5. Save state to disk
        """
        self.state["tick"] += 1
        self._log(f"── World Tick {self.state['tick']} ──")

        for dgm_id, record in list(self.state["digimon"].items()):
            if record["alive"] and self.evaluate_digivolution(dgm_id):
                self.digivolve(dgm_id)

        self._balance_population()
        self._generational_births()
        self.save_state()

    def _generational_births(self):
        """
        Spawn new Fresh Digimon on a natural generational cycle,
        independent of ratio balancing. This ensures the world always
        has new life entering regardless of whether ratios are met.

        Birth rate: every 10 ticks, spawn 1-2 Freshs per attribute
        that has living Mega/Ultimate Digimon (they 'inspire' new life).
        Falls back to 1 per attribute every 15 ticks if no high-level exist.
        """
        tick   = self.state["tick"]
        living = [d for d in self.state["digimon"].values() if d["alive"]]
        biomes = ["Desert", "Grasslands", "Forest",
                  "Highlands", "Mountains", "Ocean", "DeepOcean"]

        high_levels = {"Data": 0, "Vaccine": 0, "Virus": 0}
        for d in living:
            if d.get("evolution_level") in ("Ultimate", "Mega"):
                high_levels[d["attribute"]] += 1

        for attr in ("Data", "Vaccine", "Virus"):
            if high_levels[attr] > 0:
                # Active high-level population — birth every 10 ticks
                if tick % 10 == 0:
                    for _ in range(random.randint(1, 2)):
                        self.spawn_digimon(attr, random.choice(biomes))
            else:
                # No high-level yet — slower trickle every 15 ticks
                if tick % 15 == 0:
                    self.spawn_digimon(attr, random.choice(biomes))

    def _balance_population(self):
        """
        Spawn new Digimon if any attribute type falls below its target ratio.
        Uses a 5% tolerance band to prevent constant micro-spawning.
        """
        living = [d for d in self.state["digimon"].values() if d["alive"]]
        total  = len(living) or 1
        counts = {"Data": 0, "Vaccine": 0, "Virus": 0}
        for d in living:
            counts[d["attribute"]] += 1

        biomes = [
            "Desert", "Grasslands", "Forest",
            "Highlands", "Mountains", "Ocean", "DeepOcean",
        ]
        for attr, target in self.TARGET_RATIOS.items():
            if counts[attr] / total < target - 0.05:
                self.spawn_digimon(attr, random.choice(biomes))

    # ══════════════════════════════════════════════════════════════════════════
    # PUBLIC QUERY METHODS
    # ══════════════════════════════════════════════════════════════════════════

    def get_digimon(self, digimon_id: str) -> Optional[dict]:
        """Retrieve a single Digimon record by ID."""
        return self.state["digimon"].get(digimon_id)

    def get_population_summary(self) -> dict:
        """Return counts of living Digimon broken down by attribute and level."""
        living = [d for d in self.state["digimon"].values() if d["alive"]]
        summary = {
            "total":        len(living),
            "by_attribute": {"Data": 0, "Vaccine": 0, "Virus": 0},
            "by_level":     {lvl: 0 for lvl in self.EVOLUTION_LEVELS},
        }
        for d in living:
            summary["by_attribute"][d["attribute"]] += 1
            summary["by_level"][d["evolution_level"]] += 1
        return summary

    def get_reigning_megas(self) -> dict:
        """Return line_id → Digimon record for all current reigning Megas."""
        result = {}
        for line_id, dgm_id in self.state["reigning_megas"].items():
            record = self.state["digimon"].get(dgm_id)
            if record:
                result[line_id] = record
        return result

    def get_evolution_tree(self, digimon_id: str) -> list:
        """
        Trace a Digimon's full ancestry back to its Fresh-level ancestor.
        Returns a list of records from oldest (Fresh) to newest.
        """
        chain   = []
        current = self.state["digimon"].get(digimon_id)
        while current:
            chain.append(current)
            pid     = current.get("parent_id")
            current = self.state["digimon"].get(pid) if pid else None
        return list(reversed(chain))

    def award_performance(self, digimon_id: str, points: float):
        """
        Add performance points to a living Digimon.
        Points accumulate until the evolution threshold is crossed,
        or until the usurpation knighting minimum is met.
        """
        record = self.state["digimon"].get(digimon_id)
        if record and record["alive"]:
            record["performance"] += points
