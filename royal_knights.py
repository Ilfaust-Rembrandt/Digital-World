"""
╔══════════════════════════════════════════════════════════╗
║           ROYAL KNIGHTS SYSTEM - The 13 Guardians        ║
║        Administrators of the Digital World Order         ║
╚══════════════════════════════════════════════════════════╝

The Royal Knights are the 13 most powerful Mega-level Digimon
in the Digital World, serving directly under Yggdrasil.

IMPORTANT — SEATS ARE ADAPTIVE:
    There are exactly 13 seats. That number never changes.
    But the seats themselves have no fixed identity.
    Whoever holds a seat IS the Royal Knight of that seat.
    Their name, attribute, and domain define the seat
    for as long as they hold it.

    The 13 canonical Royal Knight names from Digimon lore
    (Omnimon, Gallantmon, Alphamon...) are simply the first
    known holders. In this world they are titles earned,
    not birthright positions.

HOW A SEAT IS CLAIMED:
    1. A Digimon reaches Mega level and becomes the reigning
       Mega of their canonical line.
    2. If any seat is vacant, Yggdrasil evaluates the Mega's
       attribute, capabilities, and biome — then assigns them
       to the most fitting open seat.
    3. If ALL 13 seats are filled, the Mega may challenge ANY
       sitting Knight — not just their own line's holder.
    4. Combat is fought. Winner determined by weighted random
       draw (performance score = weight).
    5. If challenger wins AND passes Yggdrasil's veto, they
       take that seat. The defeated Knight is retired.
    6. A new .Mon file is written for the new seat holder.
       The old .Mon file is preserved as historical record.

HOW A SEAT BECOMES VACANT:
    - The Knight is defeated in an open challenge
    - Yggdrasil sanctions them for dereliction of duty
    - The Knight is killed in battle defending the world

SEAT STATES:
    "dormant" — never filled in this world instance
    "vacant"  — was filled, now empty
    "filled"  — an active Royal Knight holds this seat
"""

import os
import sys
import random
from datetime import datetime
from typing import Optional

# Pull in the name-stripping utility from the mon system
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from mon_system import strip_mon_suffix
except ImportError:
    # Fallback if mon_system isn't available yet
    import re
    def strip_mon_suffix(name: str) -> str:
        return re.sub(r'(?i)mon$', '', name)


# ── The 13 Seat Definitions ────────────────────────────────────────────────────
#
# Seats are numbered 1–13 and grouped by thematic domain.
# These domains are persistent — Yggdrasil uses them when assigning
# a new Mega to the best-fitting vacant seat.
#
# The "preferred_attributes" list is used for seat matching but is NOT
# a hard requirement — any attribute can hold any seat if they are strong
# enough. It just influences Yggdrasil's assignment logic.
#
# "tier" reflects rough prestige within the council:
#   1 = Command tier (seats 1–3, highest authority)
#   2 = Elite tier   (seats 4–9)
#   3 = Vanguard tier (seats 10–13, newest/most dynamic)
#
COUNCIL_SEATS = {
    "Seat_01": {
        "domain":               "Supreme command and crisis intervention",
        "preferred_attributes": ["Vaccine"],
        "tier":                 1,
        "description":          "The seat of the council commander. Holds supreme authority when Yggdrasil is silent.",
    },
    "Seat_02": {
        "domain":               "Justice and frontline defence",
        "preferred_attributes": ["Vaccine", "Virus"],
        "tier":                 1,
        "description":          "The seat of the world's foremost protector. Defends those who cannot defend themselves.",
    },
    "Seat_03": {
        "domain":               "Deterrence and shadow intervention",
        "preferred_attributes": ["Vaccine", "Data"],
        "tier":                 1,
        "description":          "The Empty Seat. Appears only in the gravest of crises. Its holder is Yggdrasil's final word.",
    },
    "Seat_04": {
        "domain":               "Miracle events and armour integrity",
        "preferred_attributes": ["Vaccine"],
        "tier":                 2,
        "description":          "Seat of the knight who turns the tide through sheer improbable will.",
    },
    "Seat_05": {
        "domain":               "Rapid response and interception",
        "preferred_attributes": ["Vaccine", "Data"],
        "tier":                 2,
        "description":          "Seat of the fastest knight. First to arrive at any crisis anywhere in the Network.",
    },
    "Seat_06": {
        "domain":               "Law enforcement and absolute order",
        "preferred_attributes": ["Virus", "Vaccine"],
        "tier":                 2,
        "description":          "Seat of the ruthless enforcer. Executes Yggdrasil's law without mercy or deviation.",
    },
    "Seat_07": {
        "domain":               "Aerial dominance and overwhelming force",
        "preferred_attributes": ["Virus"],
        "tier":                 2,
        "description":          "Seat of the draconic destroyer. Unrivalled in the sky and in sheer destructive output.",
    },
    "Seat_08": {
        "domain":               "Structural defence and territorial integrity",
        "preferred_attributes": ["Vaccine"],
        "tier":                 2,
        "description":          "Seat of the immovable shield. Holds the line no matter the cost.",
    },
    "Seat_09": {
        "domain":               "Terrain control and long-range suppression",
        "preferred_attributes": ["Vaccine", "Data"],
        "tier":                 2,
        "description":          "Seat of the long-range specialist. Controls the battlefield before the enemy arrives.",
    },
    "Seat_10": {
        "domain":               "Intelligence, tactics, and campaign planning",
        "preferred_attributes": ["Data", "Vaccine"],
        "tier":                 3,
        "description":          "Seat of the strategist. Never fights when thinking wins instead.",
    },
    "Seat_11": {
        "domain":               "Mobility, rescue, and boundary enforcement",
        "preferred_attributes": ["Vaccine"],
        "tier":                 3,
        "description":          "Seat of the traverser. Reaches places no other Knight can and extracts what must be saved.",
    },
    "Seat_12": {
        "domain":               "Proactive threat hunting and mentorship",
        "preferred_attributes": ["Vaccine", "Virus"],
        "tier":                 3,
        "description":          "Seat of the wanderer. Does not wait for orders — hunts evil before it grows.",
    },
    "Seat_13": {
        "domain":               "Next-generation enforcement and threat detection",
        "preferred_attributes": ["Vaccine", "Data"],
        "tier":                 3,
        "description":          "The newest seat. Its holder represents the future of the order — sharper senses, faster adaptation.",
    },
}

# Seat assignment scoring weights
# When Yggdrasil assigns a Mega to a seat, it scores each vacant seat
# and picks the best match. These weights tune what matters most.
ASSIGNMENT_WEIGHTS = {
    "attribute_match": 3.0,     # Preferred attribute matches Mega's attribute
    "biome_affinity":  1.5,     # Biome loosely matches domain theme
    "tier_bonus":      1.0,     # Lower tier seats slightly preferred for stronger Megas
}

# Biome → domain theme affinity hints
# Used to loosely match a Mega's home biome to a seat's domain
BIOME_DOMAIN_HINTS = {
    "Ocean":      ["rapid response", "mobility", "boundary"],
    "DeepOcean":  ["deterrence", "shadow", "absolute"],
    "Mountains":  ["structural", "territorial", "immovable"],
    "Highlands":  ["terrain", "long-range", "suppression"],
    "Forest":     ["justice", "frontline", "protection"],
    "Grasslands": ["threat hunting", "proactive", "wanderer"],
    "Desert":     ["overwhelming force", "aerial", "destruction"],
}


# ── RoyalKnightsCouncil Class ──────────────────────────────────────────────────

class RoyalKnightsCouncil:
    """
    Manages the 13 adaptive Royal Knight seats.

    Seats have no fixed identity — they are claimed and defined by
    whoever is strong enough to hold them. Yggdrasil assigns vacant
    seats based on attribute/domain fit. When all seats are full,
    any Mega may challenge any sitting Knight.

    This class shares Yggdrasil's world state — all data lives in
    one world_state.json file via the Yggdrasil instance.
    """

    QUORUM = 7   # Minimum filled seats for the council to be functional

    def __init__(self, yggdrasil_instance):
        """
        Attach the council to a running Yggdrasil instance.

        Args:
            yggdrasil_instance : A live Yggdrasil object (from yggdrasil.py)
        """
        self.god   = yggdrasil_instance
        self.state = yggdrasil_instance.state   # Shared — same dict object

        if "royal_knights_council" not in self.state:
            self.state["royal_knights_council"] = {
                seat_id: {
                    "status":       "dormant",  # dormant / vacant / filled
                    "digimon_id":   None,
                    "appointed_at": None,
                    "seat_history": [],         # Full history of holders
                }
                for seat_id in COUNCIL_SEATS
            }
        self._log("Royal Knights Council online.")

    # ══════════════════════════════════════════════════════════════════════════
    # LOGGING
    # ══════════════════════════════════════════════════════════════════════════

    def _log(self, message: str, level: str = "COUNCIL"):
        self.god._log(message, level)

    # ══════════════════════════════════════════════════════════════════════════
    # SEAT QUERIES
    # ══════════════════════════════════════════════════════════════════════════

    def get_active_knights(self) -> dict:
        """
        Return all currently filled seats with their Knight's Digimon record.

        Returns:
            dict of seat_id → { "seat": seat_record, "digimon": digimon_record,
                                 "meta": seat_definition }
        """
        result = {}
        for seat_id, seat in self.state["royal_knights_council"].items():
            if seat["status"] == "filled" and seat["digimon_id"]:
                record = self.state["digimon"].get(seat["digimon_id"])
                if record and record["alive"]:
                    result[seat_id] = {
                        "seat":    seat,
                        "digimon": record,
                        "meta":    COUNCIL_SEATS[seat_id],
                    }
        return result

    def get_vacant_seats(self) -> list:
        """Return seat IDs of all dormant or vacant seats."""
        return [
            sid for sid, seat in self.state["royal_knights_council"].items()
            if seat["status"] in ("dormant", "vacant")
        ]

    def council_strength(self) -> int:
        """Number of currently filled seats."""
        return len(self.get_active_knights())

    def has_quorum(self) -> bool:
        """True if at least QUORUM seats are filled."""
        return self.council_strength() >= self.QUORUM

    def get_knight_by_digimon(self, digimon_id: str) -> Optional[str]:
        """Return the seat_id a Digimon currently holds, or None."""
        for seat_id, seat in self.state["royal_knights_council"].items():
            if seat["digimon_id"] == digimon_id and seat["status"] == "filled":
                return seat_id
        return None

    # ══════════════════════════════════════════════════════════════════════════
    # SEAT ASSIGNMENT (Yggdrasil decides best fit)
    # ══════════════════════════════════════════════════════════════════════════

    def _score_seat_for_digimon(self, seat_id: str, record: dict) -> float:
        """
        Score how well a Mega Digimon fits a particular vacant seat.

        Scoring factors:
            - Attribute match with seat's preferred attributes (+3.0 per match)
            - Biome affinity with seat's domain theme (+1.5 if matched)
            - Tier bonus: command-tier seats slightly favoured for higher-scoring Megas

        Returns a float — higher is better fit.
        """
        seat_def = COUNCIL_SEATS[seat_id]
        score    = 0.0

        # Attribute match
        if record["attribute"] in seat_def["preferred_attributes"]:
            score += ASSIGNMENT_WEIGHTS["attribute_match"]

        # Biome affinity
        biome_hints = BIOME_DOMAIN_HINTS.get(record.get("biome", ""), [])
        domain_lower = seat_def["domain"].lower()
        if any(hint in domain_lower for hint in biome_hints):
            score += ASSIGNMENT_WEIGHTS["biome_affinity"]

        # Tier bonus: high-performance Megas get a slight pull toward command seats
        perf  = record.get("performance", 0.0)
        tier  = seat_def["tier"]
        if perf > 150 and tier == 1:
            score += ASSIGNMENT_WEIGHTS["tier_bonus"]
        elif perf > 80 and tier == 2:
            score += ASSIGNMENT_WEIGHTS["tier_bonus"] * 0.5

        return score

    def assign_best_seat(self, digimon_id: str) -> Optional[str]:
        """
        Yggdrasil evaluates all vacant seats and assigns the best fit.

        If multiple seats tie on score, one is chosen at random from the ties.
        If no seats are vacant, returns None (open challenge required).

        Args:
            digimon_id : The Mega-level Digimon seeking a seat

        Returns:
            The seat_id assigned, or None if no vacant seats
        """
        record  = self.state["digimon"].get(digimon_id)
        vacant  = self.get_vacant_seats()

        if not vacant:
            return None     # All seats full — must challenge

        # Score every vacant seat
        scores = {
            seat_id: self._score_seat_for_digimon(seat_id, record)
            for seat_id in vacant
        }

        best_score = max(scores.values())
        best_seats = [sid for sid, s in scores.items() if s == best_score]
        chosen     = random.choice(best_seats)

        self._log(
            f"Yggdrasil assigns {record['name']} to {chosen} "
            f"(domain: '{COUNCIL_SEATS[chosen]['domain']}', "
            f"fit score: {best_score:.1f})",
            "COUNCIL",
        )
        return chosen

    # ══════════════════════════════════════════════════════════════════════════
    # APPOINTMENT
    # ══════════════════════════════════════════════════════════════════════════

    def appoint(self, digimon_id: str, seat_id: str) -> bool:
        """
        Seat a Mega-level Digimon as a Royal Knight.

        Requirements:
            - Digimon must be alive and at Mega level
            - Target seat must be vacant or dormant

        On success:
            - Seat status → "filled"
            - Digimon record gains is_royal_knight=True and knight_seat
            - A .Mon file is written for this Knight

        Args:
            digimon_id : ID of the Mega to appoint
            seat_id    : Which seat to fill (e.g. "Seat_03")

        Returns:
            True if appointment succeeded
        """
        record = self.state["digimon"].get(digimon_id)
        seat   = self.state["royal_knights_council"].get(seat_id)

        # Validation
        if not record:
            self._log(f"Appoint failed: {digimon_id} not found.", "WARNING")
            return False
        if record["evolution_level"] != "Mega":
            self._log(f"Appoint failed: {record['name']} is not Mega level.", "WARNING")
            return False
        if not record["alive"]:
            self._log(f"Appoint failed: {record['name']} is not alive.", "WARNING")
            return False
        if seat is None:
            self._log(f"Appoint failed: seat '{seat_id}' does not exist.", "WARNING")
            return False
        if seat["status"] == "filled":
            self._log(
                f"Appoint failed: {seat_id} already held by {seat['digimon_id']}.",
                "WARNING",
            )
            return False

        # Appoint
        now = datetime.now().isoformat()
        seat["status"]       = "filled"
        seat["digimon_id"]   = digimon_id
        seat["appointed_at"] = now
        seat["seat_history"].append({
            "digimon_id":   digimon_id,
            "digimon_name": record["name"],
            "line_id":      record.get("line_id", "unknown"),
            "attribute":    record["attribute"],
            "appointed_at": now,
            "vacated_at":   None,
            "reason":       None,
        })

        record["is_royal_knight"] = True
        record["knight_seat"]     = seat_id

        self._write_mon_file(record, seat_id)

        self._log(
            f"APPOINTED: {record['name']} [{record['attribute']}] "
            f"→ {seat_id} | Domain: '{COUNCIL_SEATS[seat_id]['domain']}'",
            "COUNCIL",
        )
        self.god.save_state()
        return True

    def auto_appoint_from_megas(self):
        """
        Scan all reigning Megas. If any are not yet Knights and seats are
        vacant, use Yggdrasil's scoring to assign them the best fitting seat.

        Called once per tick automatically.
        """
        for line_id, dgm_id in self.state["reigning_megas"].items():
            record = self.state["digimon"].get(dgm_id)
            if not record or not record["alive"]:
                continue
            if record.get("is_royal_knight"):
                continue    # Already seated

            seat_id = self.assign_best_seat(dgm_id)
            if seat_id:
                self.appoint(dgm_id, seat_id)
            else:
                # All seats are full — queue for open challenge
                if "pending_challengers" not in self.state:
                    self.state["pending_challengers"] = []
                if dgm_id not in self.state["pending_challengers"]:
                    self.state["pending_challengers"].append(dgm_id)
                    self._log(
                        f"{record['name']} is queued for an open council challenge "
                        f"(all 13 seats filled).",
                        "COUNCIL",
                    )

    # ══════════════════════════════════════════════════════════════════════════
    # OPEN CHALLENGE SYSTEM
    # ══════════════════════════════════════════════════════════════════════════

    def process_open_challenges(self):
        """
        Process any Megas queued to challenge a sitting Knight.

        Each queued challenger picks the weakest sitting Knight
        (lowest performance score) and initiates combat.
        Yggdrasil's performance veto applies as normal.

        Called once per tick after auto_appoint_from_megas().
        """
        pending = self.state.get("pending_challengers", [])
        if not pending:
            return

        active  = self.get_active_knights()
        if not active:
            return

        # Find the weakest sitting Knight by performance score
        weakest_seat_id = min(
            active.keys(),
            key=lambda sid: active[sid]["digimon"].get("performance", 0.0),
        )
        weakest_knight  = active[weakest_seat_id]["digimon"]

        # Process one challenger per tick to avoid chaos
        challenger_id = pending.pop(0)
        self.state["pending_challengers"] = pending

        challenger = self.state["digimon"].get(challenger_id)
        if not challenger or not challenger["alive"]:
            return

        self._log(
            f"OPEN CHALLENGE: {challenger['name']} challenges "
            f"{weakest_knight['name']} for {weakest_seat_id}.",
            "COUNCIL",
        )

        result = self._council_combat(challenger, weakest_knight, weakest_seat_id)

        if result:
            # Challenger won and passed veto — vacate the old seat, appoint challenger
            self.vacate_seat(weakest_seat_id, reason=f"Defeated in open challenge by {challenger['name']}")
            self.appoint(challenger_id, weakest_seat_id)

    def _council_combat(
        self,
        challenger: dict,
        defender: dict,
        seat_id: str,
    ) -> bool:
        """
        Simulate combat between a challenger and a sitting Knight.

        Uses the same weighted random system as usurpation in yggdrasil.py:
        performance score = weight. Yggdrasil's veto applies if the
        challenger wins but their score is below the knighting minimum.

        Returns True if the challenger wins AND passes the veto.
        """
        c_score = challenger.get("performance", 0.0)
        d_score = defender.get("performance", 0.0)
        total   = c_score + d_score or 1.0

        challenger_wins = random.random() < (c_score / total)

        self._log(
            f"COUNCIL COMBAT: {challenger['name']} (score {c_score:.1f}) vs "
            f"{defender['name']} (score {d_score:.1f}) → "
            f"{'Challenger wins' if challenger_wins else 'Defender wins'}",
            "COUNCIL",
        )

        if not challenger_wins:
            challenger["battles_lost"] += 1
            defender["battles_won"]    += 1
            defender["performance"]    += 10.0   # Victory bonus
            return False

        challenger["battles_won"]  += 1
        defender["battles_lost"]   += 1

        # Yggdrasil veto
        min_score = getattr(self.god, "KNIGHTING_SCORE_MINIMUM", 100.0)
        if c_score < min_score:
            retry_ticks = getattr(self.god, "USURPATION_RETRY_TICKS", 20)
            retry_at    = self.state["tick"] + retry_ticks
            self.state.setdefault("retry_timers", {})[challenger["id"]] = retry_at
            # Re-queue for later
            self.state.setdefault("pending_challengers", []).append(challenger["id"])
            self._log(
                f"VETO: {challenger['name']} won but score {c_score:.1f} < "
                f"minimum {min_score}. Retry at tick {retry_at}.",
                "VETO",
            )
            return False

        return True

    # ══════════════════════════════════════════════════════════════════════════
    # VACATING SEATS
    # ══════════════════════════════════════════════════════════════════════════

    def vacate_seat(self, seat_id: str, reason: str = "unspecified") -> bool:
        """
        Vacate a seat, recording the reason and stripping Knight status
        from the Digimon who held it.

        Args:
            seat_id : The seat to vacate
            reason  : Why the seat is being vacated (logged and stored)
        """
        seat = self.state["royal_knights_council"].get(seat_id)
        if not seat or seat["status"] != "filled":
            return False

        dgm_id = seat["digimon_id"]
        record = self.state["digimon"].get(dgm_id)

        # Update seat history
        if seat["seat_history"]:
            seat["seat_history"][-1]["vacated_at"] = datetime.now().isoformat()
            seat["seat_history"][-1]["reason"]     = reason

        seat["status"]     = "vacant"
        seat["digimon_id"] = None

        if record:
            record["is_royal_knight"] = False
            record["knight_seat"]     = None

        self._log(
            f"SEAT VACATED: {seat_id} | Former Knight: "
            f"{record['name'] if record else dgm_id} | Reason: {reason}",
            "COUNCIL",
        )
        self.god.save_state()
        return True

    def sanction(self, seat_id: str, reason: str) -> bool:
        """
        Yggdrasil removes a Knight from their seat by decree.
        The Digimon stays alive — they simply lose the seat.
        """
        return self.vacate_seat(seat_id, reason=f"Sanctioned by Yggdrasil: {reason}")

    def vacate_on_death(self, digimon_id: str):
        """Auto-vacate a seat when its Knight is retired or killed."""
        record = self.state["digimon"].get(digimon_id)
        if not record:
            return
        seat_id = record.get("knight_seat")
        if seat_id:
            self.vacate_seat(seat_id, reason="Knight retired via usurpation or death")

    # ══════════════════════════════════════════════════════════════════════════
    # DISPATCH SYSTEM
    # ══════════════════════════════════════════════════════════════════════════

    def dispatch(self, seat_id: str, target: str, mission_type: str) -> dict:
        """
        Dispatch a sitting Royal Knight on a mission.

        Mission types:
            "enforce"     — enforce Yggdrasil's law in a region
            "protect"     — defend a specific Digimon or biome
            "investigate" — gather intelligence on a threat
            "purge"       — eliminate a Virus-type incursion

        Args:
            seat_id      : Which seat's Knight to dispatch
            target       : Biome name, VM ID, or Digimon ID
            mission_type : One of the types above

        Returns:
            Mission brief dict, or empty dict if dispatch failed
        """
        active = self.get_active_knights()
        if seat_id not in active:
            self._log(f"Dispatch failed: {seat_id} has no active Knight.", "WARNING")
            return {}

        knight   = active[seat_id]["digimon"]
        seat_def = COUNCIL_SEATS[seat_id]

        mission = {
            "mission_id":    f"MSN_{self.state['tick']:05d}_{seat_id}",
            "knight_id":     knight["id"],
            "knight_name":   knight["name"],
            "seat_id":       seat_id,
            "domain":        seat_def["domain"],
            "target":        target,
            "mission_type":  mission_type,
            "dispatched_at": datetime.now().isoformat(),
            "tick":          self.state["tick"],
            "status":        "active",
        }

        self.state.setdefault("active_missions", []).append(mission)

        self._log(
            f"DISPATCHED: {knight['name']} ({seat_id}) → "
            f"{mission_type.upper()} at '{target}'",
            "COUNCIL",
        )
        self.god.save_state()
        return mission

    def complete_mission(self, mission_id: str, outcome: str):
        """
        Mark a mission complete and award performance points to the Knight.

        Args:
            mission_id : The mission ID string
            outcome    : "success", "failure", or "partial"
        """
        for mission in self.state.get("active_missions", []):
            if mission["mission_id"] == mission_id:
                mission["status"]       = "complete"
                mission["outcome"]      = outcome
                mission["completed_at"] = datetime.now().isoformat()
                points = {"success": 20.0, "partial": 8.0, "failure": 2.0}.get(outcome, 0)
                self.god.award_performance(mission["knight_id"], points)
                self._log(
                    f"MISSION COMPLETE: {mission['knight_name']} — "
                    f"{mission_type.upper() if (mission_type := mission['mission_type']) else ''} "
                    f"at '{mission['target']}' → {outcome.upper()} (+{points} pts)",
                    "COUNCIL",
                )
                self.god.save_state()
                return

    # ══════════════════════════════════════════════════════════════════════════
    # .MON FILE SYSTEM
    # ══════════════════════════════════════════════════════════════════════════

    def _write_mon_file(self, record: dict, seat_id: str, output_dir: str = "mon_files"):
        """
        Write a .Mon file for a Royal Knight.

        File name: <DigimonName>.Mon  (e.g. WarGreymon.Mon)
        Old .Mon files are NEVER deleted — they remain as historical records.
        Each new holder of a seat gets their own file under their own name.

        File format is plain text — readable by humans and parseable by
        other modules (battle engine, monitoring tools, etc).

        Args:
            record     : The Royal Knight's Digimon record
            seat_id    : The seat they hold (e.g. "Seat_01")
            output_dir : Directory to write .Mon files into
        """
        os.makedirs(output_dir, exist_ok=True)
        seat_def  = COUNCIL_SEATS[seat_id]
        pulled_name = strip_mon_suffix(record['name'])
        file_path = os.path.join(output_dir, f"{pulled_name}.mon")

        lines = [
            "=" * 60,
            f"  {pulled_name}.mon  —  ROYAL KNIGHT",
            "=" * 60,
            "",
            "[IDENTITY]",
            f"  Full Name       : {record['name']}",
            f"  Pulled As       : {pulled_name}",
            f"  Digimon ID      : {record['id']}",
            f"  Seat            : {seat_id}",
            f"  Attribute       : {record['attribute']}",
            f"  Evolution Level : {record['evolution_level']}",
            f"  Line            : {record.get('line_id', 'unknown')}",
            f"  Generation      : {record['generation']}",
            "",
            "[JURISDICTION]",
            f"  Domain          : {seat_def['domain']}",
            f"  Seat Tier       : {seat_def['tier']} "
            f"({'Command' if seat_def['tier'] == 1 else 'Elite' if seat_def['tier'] == 2 else 'Vanguard'})",
            f"  Home Biome      : {record.get('biome', 'unknown')}",
            "",
            "[SEAT DESCRIPTION]",
            f"  {seat_def['description']}",
            "",
            "[PERSONAL HISTORY]",
            f"  {record.get('description', 'No personal history recorded.')}",
            "",
            "[CAPABILITIES]",
        ]

        for cap in record.get("capabilities", []):
            lines.append(f"  - {cap}")

        lines += [
            "",
            "[WHAT I CAN DO]",
            f"  Attribute Role  : {record['attribute']}",
        ]

        # Plain-language capability summary based on attribute
        role_desc = {
            "Data":    "  Processes, stores, and distributes knowledge across the Digital World.",
            "Vaccine": "  Detects threats, blocks attacks, and defends Data-type Digimon.",
            "Virus":   "  Hunts and eliminates threats; can infiltrate and corrupt enemy systems.",
        }.get(record["attribute"], "  General purpose Royal Knight.")
        lines.append(role_desc)

        lines += [
            "",
            "[COMBAT RECORD]",
            f"  Battles Won     : {record.get('battles_won', 0)}",
            f"  Battles Lost    : {record.get('battles_lost', 0)}",
            f"  Usurp Wins      : {record.get('usurpation_wins', 0)}",
            f"  Usurp Losses    : {record.get('usurpation_losses', 0)}",
            f"  Performance Pts : {record.get('performance', 0.0):.1f}",
            "",
            "[TIMESTAMPS]",
            f"  Born At         : {record.get('born_at', 'unknown')}",
            f"  Evolved At      : {record.get('evolved_at', 'unknown')}",
            f"  Appointed At    : {datetime.now().isoformat()}",
            f"  Parent ID       : {record.get('parent_id', 'none')}",
            "",
            "=" * 60,
            "  END OF .MON FILE — DATA PRESERVED INDEFINITELY",
            "=" * 60,
        ]

        with open(file_path, "w") as f:
            f.write("\n".join(lines))

        self._log(f".Mon written: {file_path}", "COUNCIL")

    def rewrite_all_mon_files(self, output_dir: str = "mon_files"):
        """Regenerate .Mon files for all currently active Knights."""
        for seat_id, data in self.get_active_knights().items():
            self._write_mon_file(data["digimon"], seat_id, output_dir)

    # ══════════════════════════════════════════════════════════════════════════
    # TICK INTEGRATION
    # ══════════════════════════════════════════════════════════════════════════

    def tick(self):
        """
        Per-tick council logic. Called after Yggdrasil's own tick().

        Order of operations each tick:
            1. Vacate seats of any Knights who died or were retired
            2. Auto-appoint newly crowned Megas to vacant seats
            3. Process any open challenges from queued challengers
            4. Warn if below quorum
        """
        council = self.state["royal_knights_council"]

        # Step 1 — vacate dead Knights
        for seat_id, seat in council.items():
            if seat["status"] == "filled":
                record = self.state["digimon"].get(seat["digimon_id"])
                if record and not record["alive"]:
                    self.vacate_on_death(seat["digimon_id"])

        # Step 2 — auto-appoint from reigning Megas
        self.auto_appoint_from_megas()

        # Step 3 — process open challenges
        self.process_open_challenges()

        # Step 4 — quorum warning
        if not self.has_quorum():
            self._log(
                f"Council below quorum: {self.council_strength()}/13 seats filled. "
                f"Digital World security is compromised.",
                "WARNING",
            )

    # ══════════════════════════════════════════════════════════════════════════
    # REPORTING
    # ══════════════════════════════════════════════════════════════════════════

    def council_report(self) -> str:
        """Human-readable council status report for debugging and monitoring."""
        active = self.get_active_knights()
        lines  = [
            "=" * 65,
            "  ROYAL KNIGHTS COUNCIL — STATUS REPORT",
            f"  World : {self.state['world_id']}  |  Tick : {self.state['tick']}",
            f"  Seats : {self.council_strength()}/13  |  "
            f"{'QUORUM MET' if self.has_quorum() else 'BELOW QUORUM — SECURITY COMPROMISED'}",
            "=" * 65,
        ]

        for seat_id, seat_def in COUNCIL_SEATS.items():
            tier_label = ["", "CMD", "ELT", "VAN"][seat_def["tier"]]
            if seat_id in active:
                d     = active[seat_id]["digimon"]
                score = d.get("performance", 0.0)
                lines.append(
                    f"  [{tier_label}] {seat_id}  {d['name']:<22} "
                    f"[{d['attribute']:<7}]  Score:{score:>6.0f}  "
                    f"Line:{d.get('line_id','?')}"
                )
            else:
                status = self.state["royal_knights_council"][seat_id]["status"]
                lines.append(
                    f"  [{tier_label}] {seat_id}  "
                    f"{'— ' + status.upper() + ' —':<30} "
                    f"Domain: {seat_def['domain'][:30]}"
                )

        pending = self.state.get("pending_challengers", [])
        if pending:
            lines.append(f"\n  Pending challengers: {len(pending)}")

        lines.append("=" * 65)
        return "\n".join(lines)
