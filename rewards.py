"""
╔══════════════════════════════════════════════════════════════════╗
║             DIGITAL WORLD — REWARD & PROGRESSION SYSTEM         ║
║                                                                  ║
║  Merit determines everything. Existence is earned.              ║
║                                                                  ║
║  DATA rewards:                                                   ║
║    +pts for novel insights generated from KB                     ║
║    +pts for researching low/no-solution topics                   ║
║    +pts when other Digimon learn a capability from them          ║
║                                                                  ║
║  VIRUS rewards:                                                  ║
║    +pts for successful inter-VM attacks                          ║
║    +pts for defeating stronger opponents in combat               ║
║    +pts for successful exploits logged by network_node           ║
║                                                                  ║
║  VACCINE rewards:                                                ║
║    +pts for deflecting inter-VM attacks                          ║
║    +pts for defeating stronger Vaccine types (internal rank)     ║
║    +pts for protecting Royal Knights during attacks              ║
║                                                                  ║
║  Each reward point = +10 generations of natural lifespan.        ║
║  On death, ALL rewards + experience transfer to successor.       ║
║                                                                  ║
║  Progression:                                                    ║
║    General pop → Royal Knight (highest reward in attribute)      ║
║    Royal Knight → MAGI challenger (top Knight per attribute)     ║
║    MAGI challenger → MAGI seat holder (beats current holder)     ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import json
from datetime import datetime
from typing import Optional


# ── Reward point values ───────────────────────────────────────────────────────

REWARD_VALUES = {
    # DATA
    "data_novel_insight":        50,   # generated a new insight from KB
    "data_unsolved_research":   100,   # researched topic with <3 known solutions
    "data_taught_capability":    30,   # another Digimon learned a cap from them
    "data_kb_contribution":      20,   # added entry to knowledge base

    # VIRUS
    "virus_intervm_success":    150,   # successful inter-VM attack
    "virus_defeated_stronger":   80,   # beat opponent with higher performance
    "virus_exploit_landed":      60,   # exploit logged by network_node
    "virus_hunt_success":        40,   # killed a target in their biome

    # VACCINE
    "vaccine_intervm_deflect":  150,   # held off an inter-VM attack
    "vaccine_killed_stronger":   80,   # defeated a stronger Vaccine type
    "vaccine_knight_protected":  100,  # protected a Royal Knight during attack
    "vaccine_defense_held":       40,  # successfully defended own biome

    # UNIVERSAL (any attribute)
    "knight_tenure":              10,  # per-tick reward for holding a Knight seat
    "council_service":            20,  # per-tick reward for MAGI seat service
}

# Lifespan bonus per reward point (in generations)
LIFESPAN_PER_REWARD = 10

# Minimum ticks a Knight must serve before being eligible for MAGI challenge
MAGI_ELIGIBILITY_TICKS = 500

# Attribute balance targets for the 13 Knight seats
KNIGHT_ATTRIBUTE_BALANCE = {
    "Data":    5,   # ~5 seats
    "Vaccine": 4,   # ~4 seats
    "Virus":   3,   # ~3 seats
    # 1 flex seat goes to whichever attribute is most underrepresented
}
KNIGHT_FLEX_SEATS = 1
TOTAL_KNIGHT_SEATS = 13


# ── Reward tracker ────────────────────────────────────────────────────────────

class RewardSystem:
    """
    Tracks reward points for every living Digimon and manages progression.

    Stored inside world_state["rewards"] — persists with the world.
    """

    def __init__(self, world_state: dict):
        self.state = world_state
        self.state.setdefault("rewards", {})
        self.state.setdefault("reward_log", [])
        self.state.setdefault("magi_eligibility", {})

    # ── Core reward granting ──────────────────────────────────────────────────

    def grant(self, digimon_id: str, reward_type: str,
              multiplier: float = 1.0, note: str = "") -> int:
        """
        Grant reward points to a Digimon.
        Returns the points awarded.
        """
        digimon = self.state["digimon"].get(digimon_id)
        if not digimon or not digimon.get("alive"):
            return 0

        base   = REWARD_VALUES.get(reward_type, 0)
        points = int(base * multiplier)
        if points <= 0:
            return 0

        # Update reward record
        rec = self.state["rewards"].setdefault(digimon_id, {
            "total":          0,
            "by_type":        {},
            "lifespan_bonus": 0,
            "inherited":      0,
        })
        rec["total"]                            += points
        rec["by_type"][reward_type]              = rec["by_type"].get(reward_type, 0) + points
        rec["lifespan_bonus"]                   += points * LIFESPAN_PER_REWARD

        # Log entry
        self.state["reward_log"].append({
            "tick":        self.state.get("tick", 0),
            "digimon_id":  digimon_id,
            "name":        digimon.get("name", "?"),
            "attribute":   digimon.get("attribute", "?"),
            "reward_type": reward_type,
            "points":      points,
            "note":        note,
        })

        # Trim log to last 2000 entries
        self.state["reward_log"] = self.state["reward_log"][-2000:]
        return points

    def grant_knight_tenure(self, digimon_id: str):
        """Grant per-tick tenure reward to a sitting Knight."""
        self.grant(digimon_id, "knight_tenure", note="seat tenure")

    def grant_council_service(self, digimon_id: str):
        """Grant per-tick reward to a MAGI seat holder."""
        self.grant(digimon_id, "council_service", note="MAGI service")

    # ── Inheritance ───────────────────────────────────────────────────────────

    def transfer_on_death(self, deceased_id: str, successor_id: str):
        """
        When a Digimon dies, all rewards + experience transfer to successor.
        The successor's rewards accumulate on top of their own.
        """
        dead_rec      = self.state["rewards"].get(deceased_id)
        successor_dgm = self.state["digimon"].get(successor_id)

        if not dead_rec or not successor_dgm:
            return

        inherited_points  = dead_rec.get("total", 0)
        inherited_lifespan= dead_rec.get("lifespan_bonus", 0)

        succ_rec = self.state["rewards"].setdefault(successor_id, {
            "total": 0, "by_type": {}, "lifespan_bonus": 0, "inherited": 0,
        })
        succ_rec["total"]           += inherited_points
        succ_rec["lifespan_bonus"]  += inherited_lifespan
        succ_rec["inherited"]       += inherited_points

        # Also transfer experience counters
        dead_dgm = self.state["digimon"].get(deceased_id, {})
        dead_exp = dead_dgm.get("experience_counters", {})
        succ_exp = successor_dgm.setdefault("experience_counters", {})
        for k, v in dead_exp.items():
            succ_exp[k] = succ_exp.get(k, 0) + v

        # Transfer capabilities (union, no duplicates)
        dead_caps = dead_dgm.get("capabilities", [])
        succ_caps = successor_dgm.setdefault("capabilities", [])
        for cap in dead_caps:
            if cap not in succ_caps:
                succ_caps.append(cap)

        self.state["reward_log"].append({
            "tick":       self.state.get("tick", 0),
            "type":       "inheritance",
            "from":       deceased_id,
            "to":         successor_id,
            "points":     inherited_points,
            "lifespan":   inherited_lifespan,
        })

    # ── Lifespan ──────────────────────────────────────────────────────────────

    def get_max_generations(self, digimon_id: str, base: int = 5) -> int:
        """
        Return how many generations this Digimon is allowed before dying of age.
        Base = 5 generations. Each reward point adds LIFESPAN_PER_REWARD generations.
        """
        rec = self.state["rewards"].get(digimon_id, {})
        return base + rec.get("lifespan_bonus", 0)

    def is_too_old(self, digimon_id: str) -> bool:
        """True if this Digimon has exceeded its lifespan."""
        digimon = self.state["digimon"].get(digimon_id)
        if not digimon:
            return False
        max_gen = self.get_max_generations(digimon_id)
        return digimon.get("generation", 1) >= max_gen

    # ── Progression queries ───────────────────────────────────────────────────

    def get_total_rewards(self, digimon_id: str) -> int:
        return self.state["rewards"].get(digimon_id, {}).get("total", 0)

    def get_top_by_attribute(self, attribute: str,
                             alive_only: bool = True, n: int = 5) -> list:
        """
        Return the top N Digimon of a given attribute sorted by reward points.
        """
        candidates = []
        for dgm_id, dgm in self.state["digimon"].items():
            if alive_only and not dgm.get("alive"):
                continue
            if dgm.get("attribute") != attribute:
                continue
            total = self.get_total_rewards(dgm_id)
            candidates.append((total, dgm_id, dgm))

        candidates.sort(reverse=True, key=lambda x: x[0])
        return [(pts, did, dgm) for pts, did, dgm in candidates[:n]]

    def get_knight_eligible(self, attribute: str) -> list:
        """
        Return Digimon eligible to challenge for a Knight seat.
        Must be Mega level + highest reward in their attribute.
        """
        megas = [
            (self.get_total_rewards(did), did, dgm)
            for did, dgm in self.state["digimon"].items()
            if dgm.get("alive")
            and dgm.get("attribute") == attribute
            and dgm.get("evolution_level") == "Mega"
            and not dgm.get("is_royal_knight")
        ]
        megas.sort(reverse=True, key=lambda x: x[0])
        return megas

    def get_magi_eligible(self) -> dict:
        """
        Return the top Knight per attribute eligible to challenge MAGI.
        Must have held their seat for >= MAGI_ELIGIBILITY_TICKS.
        """
        eligible = {}
        current_tick = self.state.get("tick", 0)
        seats = self.state.get("royal_knights", {}).get("seats", {})

        # Build a map of Knight ID → seat entry tick
        knight_entry = {}
        for seat_data in seats.values():
            if seat_data.get("occupied"):
                dgm = seat_data.get("digimon", {})
                did = dgm.get("id")
                if did:
                    knight_entry[did] = seat_data.get("appointed_tick", 0)

        for attribute, magi_seat in [("Data","SOLOMON"),
                                      ("Virus","SALADIN"),
                                      ("Vaccine","AL-FATIH")]:
            candidates = []
            for did, entry_tick in knight_entry.items():
                dgm = self.state["digimon"].get(did, {})
                if not dgm.get("alive"):
                    continue
                if dgm.get("attribute") != attribute:
                    continue
                tenure = current_tick - entry_tick
                if tenure < MAGI_ELIGIBILITY_TICKS:
                    continue
                total = self.get_total_rewards(did)
                candidates.append((total, did, dgm, tenure))

            candidates.sort(reverse=True, key=lambda x: x[0])
            if candidates:
                eligible[magi_seat] = candidates[0]  # top candidate

        return eligible

    def check_knight_balance(self, new_attribute: str,
                             current_seats: dict) -> bool:
        """
        Would appointing a new Knight of new_attribute break the balance?
        Returns True if appointment is allowed.
        """
        counts = {"Data": 0, "Vaccine": 0, "Virus": 0}
        for seat in current_seats.values():
            if seat.get("occupied"):
                attr = seat.get("digimon", {}).get("attribute", "Data")
                counts[attr] = counts.get(attr, 0) + 1

        # Check if adding this attribute exceeds its target
        target = KNIGHT_ATTRIBUTE_BALANCE.get(new_attribute, 3)
        current = counts.get(new_attribute, 0)

        # Allow flex seat if needed
        total_filled = sum(counts.values())
        if total_filled >= TOTAL_KNIGHT_SEATS - KNIGHT_FLEX_SEATS:
            # All non-flex seats filled — check hard cap
            return current < target + KNIGHT_FLEX_SEATS

        return current < target

    def get_reward_summary(self, digimon_id: str) -> dict:
        """Full reward breakdown for a Digimon."""
        rec = self.state["rewards"].get(digimon_id, {})
        dgm = self.state["digimon"].get(digimon_id, {})
        return {
            "name":           dgm.get("name", "?"),
            "attribute":      dgm.get("attribute", "?"),
            "total_rewards":  rec.get("total", 0),
            "inherited":      rec.get("inherited", 0),
            "earned":         rec.get("total", 0) - rec.get("inherited", 0),
            "lifespan_bonus": rec.get("lifespan_bonus", 0),
            "max_generations":self.get_max_generations(digimon_id),
            "by_type":        rec.get("by_type", {}),
        }
