"""
╔══════════════════════════════════════════════════════════╗
║              DIGITAL WORLD — WORLD RUNNER                ║
║         The Integration Layer. Everything starts here.   ║
╚══════════════════════════════════════════════════════════╝

This is the entry point for the Digital World simulation.
It wires together all four modules and runs the world loop:

    Yggdrasil       — God AI, evolution, world state
    RoyalKnights    — 13 adaptive council seats
    DigimonAgents   — Individual behaviour, nature, combat
    BiomeManager    — Environments, events, knowledge domains

WORLD LOOP (each tick):
    1. Yggdrasil.tick()         — evolve Digimon, balance population
    2. BiomeManager.tick()      — tick events, assign domains, force-flee
    3. AgentRunner.tick()       — run all Digimon agents
    4. RoyalKnights.tick()      — appoint Knights, process challenges
    5. RewardSystem.tick()      — grant tenure/service rewards, check lifespan
    6. check_magi_challenges()  — eligible Knights challenge MAGI seats
    7. check_ascension()        — has anyone grown strong enough to rival God?
    8. report()                 — status to terminal and file

WIN CONDITION — THE ASCENSION:
    When a Royal Knight's performance score crosses ASCENSION_THRESHOLD:
        1. Yggdrasil acknowledges the challenger in the world log
        2. A final confrontation is simulated (weighted combat)
        3. If the challenger wins:
               - They BECOME the new Yggdrasil
               - The God model upgrades to the next tier in the progression
               - Their .Mon file is written as the new God's record
               - The world continues — next generation begins
        4. If Yggdrasil wins:
               - The challenger is retired (data preserved)
               - Their performance is reset — try again next generation
               - Yggdrasil grows stronger from the confrontation

Run with:
    python world.py

Or with overrides:
    WORLD_ID=VM_B TICK_SLEEP=0 ASCENSION_THRESHOLD=500 python world.py
"""

import os
import sys
import time
import random
import signal
import json
from datetime import datetime
from dw_logger import DigitalWorldLogger

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env before anything else so API keys are available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # keys must be in environment already

import config as cfg
from yggdrasil      import Yggdrasil
from royal_knights  import RoyalKnightsCouncil
from digimon_agent  import AgentRunner
from biome          import BiomeManager
from mon_system     import strip_mon_suffix
from knowledge_base import KnowledgeBase
from data_research  import DataResearchEngine

# ── Optional multi-VM systems (loaded only if NETWORK_ENABLED) ────────────────
if cfg.NETWORK_ENABLED:
    from network_node import NetworkNode
    from admin        import AdminChannel, AdminCommandExecutor
else:
    NetworkNode          = None
    AdminChannel         = None
    AdminCommandExecutor = None


# =============================================================================
# WORLD CLASS
# =============================================================================

class DigitalWorld:
    """
    The complete Digital World simulation.

    Owns and coordinates all four subsystems. Runs the main tick loop.
    Manages the ascension win condition and God-model progression.
    """

    def __init__(self):
        self._running       = True
        self._god_gen       = self._load_god_generation()
        self._ascension_log = []

        # ── Initialise Yggdrasil (God AI) ─────────────────────────────────
        self.yggdrasil = Yggdrasil(
            world_id=cfg.WORLD_ID,
            db_path=cfg.DB_PATH,
        )
        # Override model based on current God generation
        self.yggdrasil.model = self._current_god_model()

        # ── Structured Logger ──────────────────────────────────────────────
        self.logger = DigitalWorldLogger()
        self.logger.log_run_start(
            world_id=cfg.WORLD_ID,
            config={
                "tick_sleep"          : cfg.TICK_SLEEP_SECONDS,
                "ascension_threshold" : cfg.ASCENSION_THRESHOLD,
                "initial_population"  : cfg.INITIAL_POPULATION,
            }
        )

        # ── Attach all subsystems ──────────────────────────────────────────
        self.council = RoyalKnightsCouncil(self.yggdrasil)
        self.agents  = AgentRunner(self.yggdrasil, logger=self.logger)
        self.biomes  = BiomeManager(self.yggdrasil)
        # Wire live biome data into agents so roaming uses real feed richness
        self.agents.set_biome_manager(self.biomes)

        # ── Knowledge Base — Yggdrasil reads the internet at startup ──────
        self.kb = KnowledgeBase()
        self.kb.build(force=False, verbose=True)   # skips if fresh
        self.biomes.set_knowledge_base(self.kb)    # biomes feed from KB

        # ── Data Research Engine ───────────────────────────────────────────────
        self.research = DataResearchEngine(
            world_state    = self.yggdrasil.state,
            knowledge_base = self.kb,
            reward_system  = self.yggdrasil.rewards,
            llm_client     = self.yggdrasil.client,
            llm_model      = self.yggdrasil.model,
        )

        # ── Pass config values into Yggdrasil ─────────────────────────────
        self.yggdrasil.KNIGHTING_SCORE_MINIMUM = cfg.KNIGHTING_SCORE_MINIMUM
        self.yggdrasil.USURPATION_RETRY_TICKS  = cfg.USURPATION_RETRY_TICKS
        self.yggdrasil.EVOLUTION_THRESHOLDS     = cfg.EVOLUTION_THRESHOLDS
        self.yggdrasil.TARGET_RATIOS            = cfg.TARGET_RATIOS

        # ── Multi-VM networking + admin channel ──────────────────────────────
        if cfg.NETWORK_ENABLED and NetworkNode is not None:
            self.network = NetworkNode(
                vm_id       = cfg.WORLD_ID,
                world_state = self.yggdrasil.state,
                port        = cfg.VM_LISTEN_PORT,
            )
            self.admin = AdminCommandExecutor(
                vm_id       = cfg.WORLD_ID,
                world_state = self.yggdrasil.state,
                mon_dir     = cfg.MON_DIR,
            )
            self._log(f"Network node online: {cfg.WORLD_ID} "
                      f"port {cfg.VM_LISTEN_PORT}", "INFO")
        else:
            self.network = None
            self.admin   = None

        # ── Graceful shutdown on Ctrl+C ────────────────────────────────────
        signal.signal(signal.SIGINT,  self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        self._log("=" * 60, "INFO")
        self._log(f"Digital World '{cfg.WORLD_ID}' online.", "INFO")
        self._log(f"God Generation: {self._god_gen + 1} | Model: {self._current_god_model()}", "INFO")
        self._log(f"Ascension threshold: {cfg.ASCENSION_THRESHOLD:.0f} pts", "INFO")
        self._log("=" * 60, "INFO")

    # -------------------------------------------------------------------------
    # GOD GENERATION TRACKING
    # -------------------------------------------------------------------------

    def _load_god_generation(self) -> int:
        """Load the current God generation from world state, default 0."""
        if os.path.exists(cfg.DB_PATH):
            try:
                with open(cfg.DB_PATH) as f:
                    data = json.load(f)
                return data.get("god_generation", 0)
            except Exception:
                pass
        return 0

    def _current_god_model(self) -> str:
        """Return the LLM model for the current God generation."""
        progression = (
            cfg.GOD_MODEL_PROGRESSION_QWEN
            if cfg.LLM_PROVIDER == "qwen"
            else cfg.GOD_MODEL_PROGRESSION
        )
        idx = min(self._god_gen, len(progression) - 1)
        return progression[idx]

    def _next_god_model(self) -> str:
        """Return the LLM model for the NEXT God generation."""
        progression = (
            cfg.GOD_MODEL_PROGRESSION_QWEN
            if cfg.LLM_PROVIDER == "qwen"
            else cfg.GOD_MODEL_PROGRESSION
        )
        idx = min(self._god_gen + 1, len(progression) - 1)
        return progression[idx]

    # -------------------------------------------------------------------------
    # STARTUP — SEED THE WORLD
    # -------------------------------------------------------------------------

    def seed_population(self):
        """
        Spawn the initial population if the world is new (tick == 0).
        Skipped on subsequent runs — world continues from saved state.
        """
        if self.yggdrasil.state["tick"] > 0:
            self._log("Continuing existing world — skipping initial seed.", "INFO")
            return

        self._log(f"Seeding initial population of {cfg.INITIAL_POPULATION} Digimon...", "INFO")
        biome_list = list(cfg.TARGET_RATIOS.keys())
        biomes     = ["Desert", "Grasslands", "Forest", "Highlands",
                      "Mountains", "Ocean", "DeepOcean"]

        for i in range(cfg.INITIAL_POPULATION):
            # Weighted attribute selection based on target ratios
            attrs  = list(cfg.TARGET_RATIOS.keys())
            weights= list(cfg.TARGET_RATIOS.values())
            attr   = random.choices(attrs, weights=weights, k=1)[0]
            biome  = random.choice(biomes)
            self.yggdrasil.spawn_digimon(attr, biome)

        self._log(f"World seeded. {cfg.INITIAL_POPULATION} Fresh Digimon born.", "INFO")
        self.yggdrasil.save_state()

    # -------------------------------------------------------------------------
    # MAIN TICK
    # -------------------------------------------------------------------------

    def tick(self):
        """
        Execute one full world tick in correct dependency order.

        Order matters:
            1. Yggdrasil first — evolves Digimon, balances population
               so agents have accurate records to act on
            2. Biomes second — events may force-flee Digimon before
               agents move, and richness must be current for feeding
            3. Agents third — act on the current biome state
            4. Council fourth — appoints Knights from newly evolved Megas,
               processes open challenges
            5. Ascension check last — after all actions this tick
        """
        # 1. God AI tick
        self.yggdrasil.tick()

        # 2. Biome tick
        self.biomes.tick()

        # 3. Agent tick — patch agent roaming to use biome-aware adjacency
        self._tick_agents_with_biome_awareness()

        # 4. Council tick
        self.council.tick()

        # 5. Reward system — tenure grants, lifespan checks, MAGI eligibility
        self._tick_rewards()

        # 6. MAGI challenge check — every 100 ticks
        tick_now = self.yggdrasil.state["tick"]
        if tick_now % 100 == 0:
            self._check_magi_challenges()

        # 7. Trim event log to prevent unbounded growth
        self._trim_event_log()

        # 6. Write status
        if cfg.WRITE_STATUS_FILE:
            self._write_status_file()

        # 7. Admin channel — check for commands every tick
        if self.admin:
            fired = self.admin.tick(world_ref=self)
            for cmd in fired:
                self._log(f"Admin command executed: {cmd.get('type')} "
                          f"by {cmd.get('issued_at', '?')[:19]}", "INFO")

        # 8. Network tick — inter-VM heartbeat, incoming attacks, ordered attacks
        if self.network:
            results = self.network.tick(self.yggdrasil.state, self.admin)
            for r in results:
                pkt  = r.get("packet", {})
                held = r.get("result", {}).get("held", False)
                defender_name = r.get("result", {}).get("defender")
                self._log(
                    f"Inter-VM combat: {pkt.get('attacker_name')} "
                    f"({pkt.get('attacker_vm')}) vs {cfg.WORLD_ID} — "
                    f"{'HELD' if held else 'BREACHED'}",
                    "INFO",
                )
                # Grant rewards based on outcome
                rewards = self.yggdrasil.rewards
                if held and defender_name:
                    # Find the defending Vaccine Digimon by name
                    for did, dgm in self.yggdrasil.state["digimon"].items():
                        if dgm.get("name") == defender_name and dgm.get("alive"):
                            rewards.grant(did, "vaccine_intervm_deflect",
                                          note=f"deflected {pkt.get('attacker_vm')}")
                            break
                elif not held:
                    # Find the attacking Virus Digimon by name
                    attacker_name = pkt.get("attacker_name")
                    attacker_vm   = pkt.get("attacker_vm")
                    if attacker_vm == cfg.WORLD_ID:
                        for did, dgm in self.yggdrasil.state["digimon"].items():
                            if dgm.get("name") == attacker_name and dgm.get("alive"):
                                rewards.grant(did, "virus_intervm_success",
                                              note=f"breached {pkt.get('target_vm')}")
                                break

            # Autonomous probing by strong Virus types
            for digimon in self.yggdrasil.state.get("digimon", {}).values():
                if (digimon.get("alive")
                        and digimon.get("attribute") == "Virus"
                        and not digimon.get("admin_frozen")
                        and not (self.admin and self.admin.is_frozen(digimon["id"]))):
                    probe_result = self.network.maybe_autonomous_probe(digimon)
                    if probe_result and probe_result.get("success"):
                        self.yggdrasil.rewards.grant(
                            digimon["id"], "virus_exploit_landed",
                            note="autonomous probe success"
                        )

        # 9. Tick summary logging — one structured entry per tick
        living = [r for r in self.yggdrasil.state["digimon"].values() if r.get("alive")]
        type_counts  = {"Data": 0, "Vaccine": 0, "Virus": 0}
        biome_counts = {}
        for r in living:
            attr = r.get("attribute", "Data")
            type_counts[attr] = type_counts.get(attr, 0) + 1
            b = r.get("biome", "Unknown")
            biome_counts[b]   = biome_counts.get(b, 0) + 1
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

        # 10. Terminal report on interval
        tick = self.yggdrasil.state["tick"]
        if tick % cfg.STATUS_REPORT_INTERVAL == 0:
            self._print_status()

    def _tick_agents_with_biome_awareness(self):
        """
        Run all agents but override their roaming to respect biome blocking.

        The biome manager's get_valid_adjacency() filters out blocked biomes.
        We patch each Digimon's roam destination after the fact — if they
        moved to a blocked biome, we redirect them to a valid one.
        """
        # Record biomes before agent tick
        pre_biomes = {
            dgm_id: record.get("biome")
            for dgm_id, record in self.yggdrasil.state["digimon"].items()
            if record.get("alive")
        }

        # Run agents normally
        self.agents.tick()

        # Correct any illegal moves into blocked biomes
        for dgm_id, record in self.yggdrasil.state["digimon"].items():
            if not record.get("alive"):
                continue
            new_biome = record.get("biome")
            if new_biome and not self.biomes.can_enter(new_biome):
                # Biome is blocked — send them back or to a valid adjacent
                old_biome = pre_biomes.get(dgm_id, "Grasslands")
                valid     = self.biomes.get_valid_adjacency(old_biome)
                record["biome"] = random.choice(valid) if valid else old_biome

        # Override feed richness using biome-aware values
        # (agents already fed using static richness; we apply a correction bonus/penalty)
        for record in self.yggdrasil.state["digimon"].values():
            if not record.get("alive"):
                continue
            biome     = record.get("biome", "Grasslands")
            attribute = record.get("attribute", "Data")
            # Biome-aware richness vs static richness ratio
            biome_richness  = self.biomes.get_effective_richness(biome, attribute)
            static_richness = 2.0   # Baseline from digimon_agent
            if biome_richness != static_richness:
                # Apply a small correction to performance this tick
                correction = (biome_richness - static_richness) * 0.1
                record["performance"] = max(0, record.get("performance", 0) + correction)

            # Domain capability bonus — chance to gain a new capability from biome domain
            domain_cap = self.biomes.get_domain_cap_bonus(biome)
            if domain_cap and domain_cap not in record.get("capabilities", []):
                if random.random() < 0.02:   # 2% chance per tick to absorb domain cap
                    record.setdefault("capabilities", []).append(domain_cap)

    # -------------------------------------------------------------------------
    # WIN CONDITION — ASCENSION CHECK
    # -------------------------------------------------------------------------

    def check_ascension(self) -> bool:
        """
        Check whether any Royal Knight has grown powerful enough to rival
        Yggdrasil and attempt to ascend.

        Called once per tick after all other systems have run.

        Returns:
            True if an ascension occurred (world continues under new God)
            False if no ascension this tick
        """
        active_knights = self.council.get_active_knights()

        for seat_id, data in active_knights.items():
            knight = data["digimon"]
            score  = knight.get("performance", 0.0)

            if score < cfg.ASCENSION_THRESHOLD:
                continue

            # A challenger has emerged
            self._log(
                f"{'=' * 50}\n"
                f"  ASCENSION ALERT: {knight['name']} [{seat_id}]\n"
                f"  Performance: {score:.1f} / {cfg.ASCENSION_THRESHOLD:.1f}\n"
                f"  A Royal Knight now rivals Yggdrasil itself.\n"
                f"{'=' * 50}",
                "ASCENSION",
            )

            result = self._final_confrontation(knight, seat_id)
            return result   # One ascension attempt per tick

        return False

    def _final_confrontation(self, challenger: dict, seat_id: str) -> bool:
        """
        Simulate the final confrontation between a Royal Knight and Yggdrasil.

        Yggdrasil has a built-in advantage (cfg.YGGDRASIL_COMBAT_ADVANTAGE)
        but a sufficiently powerful challenger can still win.

        Combat weight:
            Challenger  = challenger["performance"]
            Yggdrasil   = challenger["performance"] * YGGDRASIL_COMBAT_ADVANTAGE

        So at threshold (1000 pts) with advantage 1.5:
            Challenger wins probability = 1000 / (1000 + 1500) = 40%
            Still winnable but hard — as it should be.

        Args:
            challenger : The Royal Knight's record dict
            seat_id    : Their council seat

        Returns:
            True if challenger wins (ascension), False if Yggdrasil wins
        """
        c_score = challenger.get("performance", 0.0)
        g_score = c_score * cfg.YGGDRASIL_COMBAT_ADVANTAGE
        total   = c_score + g_score

        challenger_wins = random.random() < (c_score / total)

        self._log(
            f"FINAL CONFRONTATION: {challenger['name']} ({c_score:.0f}) "
            f"vs Yggdrasil ({g_score:.0f}) → "
            f"{'CHALLENGER WINS' if challenger_wins else 'YGGDRASIL PREVAILS'}",
            "ASCENSION",
        )

        # Log the ascension attempt to JSONL
        self.logger.log_ascension_attempt(
            tick=self.yggdrasil.state.get("tick", 0),
            challenger_id=challenger.get("id", "?"),
            challenger_performance=c_score,
            yggdrasil_performance=g_score,
            outcome="challenger_wins" if challenger_wins else "yggdrasil_wins",
        )

        if challenger_wins:
            self._ascend(challenger, seat_id)
            return True
        else:
            self._yggdrasil_prevails(challenger)
            return False

    def _ascend(self, challenger: dict, seat_id: str):
        """
        The challenger has defeated Yggdrasil. They become the new God.

        What happens:
            1. Challenger's .Mon file is written as the new God's record
            2. God generation counter increments
            3. LLM model upgrades to the next tier
            4. Yggdrasil's world log records the event permanently
            5. The council seat is vacated (the new God has no seat — they ARE God)
            6. The world continues — Yggdrasil now runs on the challenger's lineage
        """
        new_model = self._next_god_model()
        self._god_gen += 1

        # Record ascension in world state
        self.yggdrasil.state["god_generation"] = self._god_gen
        self.yggdrasil.state.setdefault("ascension_log", []).append({
            "tick":           self.yggdrasil.state["tick"],
            "new_god_name":   challenger["name"],
            "new_god_id":     challenger["id"],
            "new_god_line":   challenger.get("line_id", "unknown"),
            "old_model":      self._current_god_model(),
            "new_model":      new_model,
            "performance":    challenger["performance"],
            "timestamp":      datetime.now().isoformat(),
        })

        # Write the new God's .Mon file
        self._write_god_mon(challenger, new_model)

        # Upgrade Yggdrasil's model
        self.yggdrasil.model = new_model
        self.agents.model    = new_model

        # Vacate the old council seat — the new God transcends it
        self.council.vacate_seat(
            seat_id,
            reason=f"{challenger['name']} ascended to become Yggdrasil Generation {self._god_gen}"
        )

        # Mark the challenger as the new God in their record
        challenger["is_yggdrasil"] = True
        challenger["ascended_at"]  = datetime.now().isoformat()
        challenger["god_gen"]      = self._god_gen

        self._log(
            f"\n{'#' * 60}\n"
            f"  ASCENSION COMPLETE\n"
            f"  {challenger['name']} is the new Yggdrasil.\n"
            f"  God Generation: {self._god_gen}\n"
            f"  New God Model:  {new_model}\n"
            f"  The Digital World enters a new age.\n"
            f"{'#' * 60}",
            "ASCENSION",
        )

        self.yggdrasil.save_state()
        self.yggdrasil.vault.flush_all()   # persist MAGI memories
        self._print_status()

    def _yggdrasil_prevails(self, challenger: dict):
        """
        Yggdrasil won. The challenger is humbled but not destroyed.
        Their performance is reduced. They must grow stronger.
        Yggdrasil itself grows from the confrontation.
        """
        # Challenger loses 30% of their performance
        old_score = challenger["performance"]
        challenger["performance"] = old_score * 0.70
        challenger["battles_lost"] = challenger.get("battles_lost", 0) + 1

        self._log(
            f"Yggdrasil prevails. {challenger['name']} reduced from "
            f"{old_score:.0f} to {challenger['performance']:.0f} pts. "
            f"The challenger must grow stronger.",
            "ASCENSION",
        )

    def _write_god_mon(self, record: dict, new_model: str):
        """
        Write a special .mon file for the newly ascended God.
        Stored in mon_files/GODS/ to distinguish from Knight .mon files.
        Name is stripped of 'mon' suffix: Omegamon → Omega_God_Gen1.mon
        """
        god_dir     = os.path.join(cfg.MON_DIR, "GODS")
        os.makedirs(god_dir, exist_ok=True)
        pulled_name = strip_mon_suffix(record['name'])
        file_path   = os.path.join(god_dir, f"{pulled_name}_God_Gen{self._god_gen}.mon")

        lines = [
            "=" * 60,
            f"  {pulled_name}.mon  —  YGGDRASIL  GEN {self._god_gen}",
            "=" * 60,
            "",
            "[IDENTITY]",
            f"  Full Name       : {record['name']}",
            f"  Pulled As       : {pulled_name}",
            f"  Digimon ID      : {record['id']}",
            f"  God Generation  : {self._god_gen}",
            f"  Ascended At     : {datetime.now().isoformat()}",
            f"  Attribute       : {record['attribute']}",
            f"  Line            : {record.get('line_id', 'unknown')}",
            f"  Evolution Level : Yggdrasil (beyond Mega)",
            "",
            "[GOD CAPABILITIES]",
            f"  LLM Model       : {new_model}",
            f"  Previous God    : Generation {self._god_gen - 1}",
        ]
        for cap in record.get("capabilities", []):
            lines.append(f"  - {cap}")
        lines += [
            "",
            "[COMBAT RECORD AT ASCENSION]",
            f"  Performance     : {record.get('performance', 0):.1f}",
            f"  Battles Won     : {record.get('battles_won', 0)}",
            f"  Battles Lost    : {record.get('battles_lost', 0)}",
            f"  Usurp Wins      : {record.get('usurpation_wins', 0)}",
            "",
            "[LINEAGE]",
            f"  Parent ID       : {record.get('parent_id', 'none')}",
            f"  Generation      : {record.get('generation', '?')}",
            "",
            "=" * 60,
            f"  {pulled_name} IS NOW YGGDRASIL",
            "  The Digital World bends to its will.",
            "=" * 60,
        ]
        with open(file_path, "w") as f:
            f.write("\n".join(lines))
        self._log(f"God .mon written: {file_path}", "ASCENSION")

    # -------------------------------------------------------------------------
    # REPORTING
    # -------------------------------------------------------------------------

    def _print_status(self):
        """Print a full world status report to the terminal."""
        tick    = self.yggdrasil.state["tick"]
        pop     = self.yggdrasil.get_population_summary()
        god_gen = self.yggdrasil.state.get("god_generation", 0)

        print("\n" + "=" * 65)
        print(f"  DIGITAL WORLD '{cfg.WORLD_ID}' — TICK {tick}")
        print(f"  God Generation: {god_gen + 1} | Model: {self.yggdrasil.model}")
        print(f"  Ascension Threshold: {cfg.ASCENSION_THRESHOLD:.0f} pts")
        print("=" * 65)

        # Population
        print(f"\n  POPULATION: {pop['total']} living")
        print(f"    Data: {pop['by_attribute']['Data']}  "
              f"Vaccine: {pop['by_attribute']['Vaccine']}  "
              f"Virus: {pop['by_attribute']['Virus']}")
        print(f"    Levels: " + "  ".join(
            f"{lvl[:3]}:{count}"
            for lvl, count in pop["by_level"].items()
            if count > 0
        ))

        # Council
        print(f"\n  ROYAL KNIGHTS: {self.council.council_strength()}/13 seats filled")
        active = self.council.get_active_knights()
        if active:
            # Show top 3 by performance
            top = sorted(
                active.items(),
                key=lambda x: x[1]["digimon"].get("performance", 0),
                reverse=True,
            )[:3]
            for seat_id, data in top:
                d = data["digimon"]
                print(f"    {seat_id}: {d['name']:<20} "
                      f"[{d['attribute']}] {d['performance']:.0f} pts")

        # Ascension progress — show closest to threshold
        if active:
            closest = max(
                active.values(),
                key=lambda x: x["digimon"].get("performance", 0),
            )
            best    = closest["digimon"]
            pct     = min(100, best["performance"] / cfg.ASCENSION_THRESHOLD * 100)
            bar_len = 30
            filled  = int(bar_len * pct / 100)
            bar     = "█" * filled + "░" * (bar_len - filled)
            print(f"\n  ASCENSION PROGRESS:")
            print(f"    {best['name']}: [{bar}] {pct:.1f}%")
            print(f"    {best['performance']:.0f} / {cfg.ASCENSION_THRESHOLD:.0f} pts")

        # MAGI Council
        magi_summary = self.yggdrasil.magi.get_mind_summary()
        magi_eligible = self.yggdrasil.rewards.get_magi_eligible()
        print(f"\n  MAGI COUNCIL:")
        seat_map = {"SOLOMON": "◈ Data", "SALADIN": "▲ Virus", "AL-FATIH": "✦ Vaccine"}
        for seat, info in magi_summary.items():
            eligible_str = " ⚡CHALLENGE PENDING" if seat in magi_eligible else ""
            print(f"    {seat:<10} [{seat_map.get(seat,seat)}] "
                  f"model:{info['model']:<12} "
                  f"votes:{info['total_votes']:<5} "
                  f"approve:{info['approval_rate']:.0%}"
                  f"{eligible_str}")

        # Top reward holders per attribute
        print(f"\n  TOP REWARD HOLDERS:")
        for attr in ("Data", "Vaccine", "Virus"):
            top = self.yggdrasil.rewards.get_top_by_attribute(attr, n=1)
            if top:
                pts, did, dgm = top[0]
                print(f"    {attr:<8} → {dgm['name']:<20} {pts:>6} reward pts")

        # Biomes
        print(f"\n  BIOMES:")
        for name, biome in self.biomes.biomes.items():
            event = f" [{biome.active_event}]" if biome.active_event else ""
            domain = biome.domain or "?"
            print(f"    {name:<12} R:{biome.effective_richness:.1f}  "
                  f"Domain:{domain:<18}{event}")

        # Nature distribution
        natures = self.agents.get_nature_summary()
        active_natures = {k: v for k, v in natures.items() if v > 0}
        if active_natures:
            print(f"\n  NATURE DISTRIBUTION:")
            print("    " + "  ".join(f"{k[:3]}:{v}" for k, v in active_natures.items()))

        print("=" * 65 + "\n")

    def _write_status_file(self):
        """Write a live world_status.txt that updates every tick."""
        tick    = self.yggdrasil.state["tick"]
        pop     = self.yggdrasil.get_population_summary()
        god_gen = self.yggdrasil.state.get("god_generation", 0)
        active  = self.council.get_active_knights()

        lines = [
            f"DIGITAL WORLD '{cfg.WORLD_ID}' — LIVE STATUS",
            f"Updated: {datetime.now().isoformat()}",
            f"Tick: {tick} | God Gen: {god_gen + 1} | Model: {self.yggdrasil.model}",
            "",
            f"POPULATION: {pop['total']}",
            f"  Data:{pop['by_attribute']['Data']}  "
            f"Vaccine:{pop['by_attribute']['Vaccine']}  "
            f"Virus:{pop['by_attribute']['Virus']}",
            "",
            f"COUNCIL: {self.council.council_strength()}/13",
        ]

        if active:
            best = max(active.values(), key=lambda x: x["digimon"].get("performance", 0))
            d    = best["digimon"]
            pct  = min(100, d["performance"] / cfg.ASCENSION_THRESHOLD * 100)
            lines += [
                "",
                f"ASCENSION LEADER: {d['name']}",
                f"  {d['performance']:.0f} / {cfg.ASCENSION_THRESHOLD:.0f} pts ({pct:.1f}%)",
            ]

        lines += ["", "BIOMES:"]
        for name, biome in self.biomes.biomes.items():
            event = f" [{biome.active_event}]" if biome.active_event else ""
            lines.append(f"  {name}: R={biome.effective_richness:.1f}{event}")

        try:
            with open(cfg.STATUS_FILE, "w") as f:
                f.write("\n".join(lines))
        except Exception:
            pass

    def _tick_rewards(self):
        """
        Grant per-tick rewards and check lifespan expiry each tick.

        Tenure rewards: sitting Knights get knight_tenure points every tick.
        Service rewards: MAGI seat holders get council_service points every tick.
        Lifespan: Digimon that exceed their reward-extended generation cap die
                  and transfer everything to their successor.
        """
        rewards = self.yggdrasil.rewards
        state   = self.yggdrasil.state
        tick    = state["tick"]

        # Grant Knight tenure rewards
        active_knights = self.council.get_active_knights()
        for seat_data in active_knights.values():
            dgm = seat_data.get("digimon", {})
            did = dgm.get("id")
            if did:
                rewards.grant_knight_tenure(did)
                # Track when they were appointed for MAGI eligibility
                state.get("royal_knights", {}).get("seats", {}).get(
                    seat_data.get("seat_id",""), {}
                ).setdefault("appointed_tick", tick)

        # Grant MAGI service rewards to current seat holders
        # MAGI holders are tracked in yggdrasil state
        for seat in ("SOLOMON", "SALADIN", "AL-FATIH"):
            holder_id = state.get("magi_holders", {}).get(seat)
            if holder_id:
                rewards.grant_council_service(holder_id)
                # Record knowledge from vault into memory every 50 ticks
                if tick % 50 == 0:
                    self.yggdrasil.vault.flush_all()

        # Data-type research — Champion+ Data types may synthesise insights
        for dgm_id, dgm in list(self.yggdrasil.state["digimon"].items()):
            if (dgm.get("alive")
                    and dgm.get("attribute") == "Data"
                    and dgm.get("evolution_level") in ("Champion", "Ultimate", "Mega")
                    and not dgm.get("admin_frozen")):
                self.research.tick_research(dgm)

        # Lifespan check — kill off Digimon that have lived too long
        # (only checks a sample each tick to avoid performance hit)
        living = [
            (did, d) for did, d in state["digimon"].items()
            if d.get("alive") and not d.get("is_royal_knight")
            and not d.get("is_yggdrasil")
        ]
        # Check ~5% of population per tick
        import random as _r
        sample = _r.sample(living, min(len(living), max(1, len(living) // 20)))
        for did, dgm in sample:
            if rewards.is_too_old(did):
                # Find their successor (the most recent child)
                successor_id = self._find_successor(did)
                if successor_id:
                    rewards.transfer_on_death(did, successor_id)
                dgm["alive"] = False
                dgm["died_of"] = "age"
                self._log(
                    f"AGE: {dgm['name']} lived {dgm.get('generation',1)} generations "
                    f"and died. Legacy transferred to successor.", "INFO"
                )

    def _find_successor(self, digimon_id: str) -> str:
        """Find the most recently spawned Digimon that lists this one as parent."""
        state = self.yggdrasil.state
        children = [
            (d["id"], d.get("born_at",""))
            for d in state["digimon"].values()
            if d.get("parent_id") == digimon_id and d.get("alive")
        ]
        if not children:
            return None
        # Most recent child
        children.sort(key=lambda x: x[1], reverse=True)
        return children[0][0]

    def _check_magi_challenges(self):
        """
        Check if any Royal Knight has earned the right to challenge a MAGI seat.
        Called every 100 ticks.

        Challenge routes:
          SOLOMON  (Data)    — deliberation: challenger argues before SALADIN + AL-FATIH
          SALADIN  (Virus)   — brawl: combat result, other two ratify
          AL-FATIH (Vaccine) — deliberation: challenger argues before SOLOMON + SALADIN
        """
        eligible = self.yggdrasil.rewards.get_magi_eligible()
        if not eligible:
            return

        state = self.yggdrasil.state
        tick  = state["tick"]

        for seat, candidate_tuple in eligible.items():
            pts, challenger_id, challenger, tenure = candidate_tuple

            # Get current holder (if any — seats may be vacant at world start)
            holder_id   = state.get("magi_holders", {}).get(seat)
            holder      = state["digimon"].get(holder_id) if holder_id else None
            holder_name = holder["name"] if holder else f"[{seat} AI]"

            self._log(
                f"MAGI CHALLENGE: {challenger['name']} ({pts} reward pts, "
                f"{tenure} ticks tenure) challenges {seat} ({holder_name})",
                "USURPATION"
            )

            # Route by attribute / seat
            if seat == "SALADIN":
                # Brawl — combat weighted by reward points
                holder_pts = self.yggdrasil.rewards.get_total_rewards(holder_id) if holder_id else 0
                total      = pts + holder_pts or 1
                challenger_wins = __import__("random").random() < (pts / total)
                self._log(
                    f"MAGI BRAWL: {challenger['name']} ({pts}pts) vs "
                    f"{holder_name} ({holder_pts}pts) → "
                    f"{'CHALLENGER' if challenger_wins else 'HOLDER'}",
                    "USURPATION"
                )
                # Other two ratify (rubber stamp unless deadlock)
                ratified = self.yggdrasil.magi.vote_usurpation(
                    challenger, holder or {}, challenger_wins, tick
                )
                success = challenger_wins and ratified

            else:
                # Deliberation — MAGI votes (the two non-challenged minds decide)
                # We reuse vote_ascension since it's the same "is this challenger worthy" question
                success = self.yggdrasil.magi.vote_ascension(
                    challenger,
                    pts,  # challenger's reward points as their "score"
                    tick,
                )

            if success:
                self._install_magi_holder(seat, challenger, challenger_id, pts, tick)
            else:
                self._log(
                    f"MAGI CHALLENGE FAILED: {challenger['name']} was not deemed worthy. "
                    f"They must grow stronger.", "USURPATION"
                )
                # Record failed challenge in vault
                self.yggdrasil.vault.memories[seat].record_succession(
                    tick, challenger["name"], "FAILURE",
                    "brawl" if seat == "SALADIN" else "deliberation", pts
                )

    def _install_magi_holder(self, seat: str, challenger: dict,
                              challenger_id: str, reward_pts: int, tick: int):
        """
        Install a Digimon as the new holder of a MAGI seat.
        They take the title. Their birth name is preserved in memory.
        All accumulated knowledge from the vault is now accessible to them.
        """
        state      = self.yggdrasil.state
        old_holder = state.get("magi_holders", {}).get(seat)

        # Transfer old holder's rewards to their successor if alive
        if old_holder and old_holder != challenger_id:
            # Old holder steps down — they don't die, they return to the world
            old_dgm = state["digimon"].get(old_holder, {})
            old_dgm.pop("is_magi_holder", None)

        # Install new holder
        state.setdefault("magi_holders", {})[seat] = challenger_id
        challenger["is_magi_holder"]  = True
        challenger["magi_seat"]       = seat
        challenger["magi_title"]      = seat   # they ARE now SOLOMON/SALADIN/AL-FATIH
        challenger["magi_since_tick"] = tick

        # Record in vault
        vault_mem = self.yggdrasil.vault.memories.get(seat)
        if vault_mem and vault_mem.is_unlocked():
            vault_mem.set_holder(
                holder_name   = challenger["name"],
                model         = self.yggdrasil.model,
                tick          = tick,
                reason        = "challenge",
                reward_points = reward_pts,
                generation    = challenger.get("generation", 1),
            )
            vault_mem.record_succession(
                tick, challenger["name"], "SUCCESS",
                "brawl" if seat == "SALADIN" else "deliberation", reward_pts
            )
            vault_mem.flush()

        self._log(
            f"\n{'★' * 55}\n"
            f"  MAGI SUCCESSION: {challenger['name']} takes the {seat} seat.\n"
            f"  They are now {seat}. Their birth name is remembered.\n"
            f"  Reward points: {reward_pts} | Tenure: tick {tick}\n"
            f"{'★' * 55}",
            "ASCENSION"
        )

    def _trim_event_log(self):
        """Keep the event log from growing unboundedly."""
        events = self.yggdrasil.state.get("events", [])
        if len(events) > cfg.MAX_EVENT_LOG:
            self.yggdrasil.state["events"] = events[-cfg.MAX_EVENT_LOG:]

    def _log(self, message: str, level: str = "INFO"):
        """Log through Yggdrasil's log system."""
        self.yggdrasil._log(message, level)

    # -------------------------------------------------------------------------
    # SHUTDOWN
    # -------------------------------------------------------------------------

    def _handle_shutdown(self, signum, frame):
        """Handle Ctrl+C or SIGTERM — save state before exiting."""
        print("\n\n[SHUTDOWN] Signal received. Saving world state...")
        self._running = False

    def shutdown(self):
        """Clean shutdown — save everything."""
        self.yggdrasil.save_state()
        self._write_status_file()
        self._log("World saved. Shutting down.", "INFO")
        living_count = sum(
            1 for r in self.yggdrasil.state["digimon"].values()
            if r.get("alive")
        )
        self.logger.log_run_end(
            tick=self.yggdrasil.state.get("tick", 0),
            reason=(
                "max_ticks" if cfg.MAX_TICKS > 0
                and self.yggdrasil.state.get("tick", 0) >= cfg.MAX_TICKS
                else "keyboard_interrupt"
            ),
            final_population=living_count,
        )
        print("[SHUTDOWN] World state saved. Goodbye.")

    # -------------------------------------------------------------------------
    # MAIN LOOP
    # -------------------------------------------------------------------------

    def run(self):
        """
        The main world loop.

        Runs indefinitely until:
            - Ctrl+C / SIGTERM (graceful shutdown)
            - An ascension occurs — world continues under new God
              (the loop never actually stops on ascension, it keeps running)
        """
        self.seed_population()
        self._print_status()

        print(f"\n[WORLD] Running. Ctrl+C to save and stop.\n")

        try:
            while self._running:
                self.tick()
                self.check_ascension()

                # Stop cleanly when MAX_TICKS is reached (0 = run forever)
                current_tick = self.yggdrasil.state.get("tick", 0)
                if cfg.MAX_TICKS > 0 and current_tick >= cfg.MAX_TICKS:
                    print(f"\n[WORLD] MAX_TICKS ({cfg.MAX_TICKS}) reached — stopping cleanly.")
                    self._running = False

                if cfg.TICK_SLEEP_SECONDS > 0:
                    time.sleep(cfg.TICK_SLEEP_SECONDS)

        except KeyboardInterrupt:
            pass
        finally:
            self.shutdown()


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    world = DigitalWorld()
    world.run()
