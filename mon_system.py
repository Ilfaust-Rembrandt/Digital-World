"""
╔══════════════════════════════════════════════════════════╗
║               .MON FILE SYSTEM — Pull Protocol           ║
║         "When you pull a Digimon, it leaves a mark."     ║
╚══════════════════════════════════════════════════════════╝

When a Digimon is PULLED from the Digital World, they shed
the "mon" suffix from their name — they are no longer just
a Digimon. They are an individual. They become a .mon file.

    Omegamon    → Omega.mon
    WarGreymon  → WarGrey.mon
    Seraphimon  → Seraphi.mon
    Beelzemon   → Beelze.mon
    Gallantmon  → Gallant.mon

The .mon file IS the Digimon's identity card. It contains
everything — their history, capabilities, nature, combat
record, evolution path, and current status.

PULL RULES:
    - Any Digimon can be pulled at any time
    - Pulling does NOT remove them from the world simulation
    - A pull is a READ operation — a snapshot at pull-time
    - The file is named after the stripped name (no "mon")
    - Extension is lowercase: .mon
    - If pulled again later, the file is OVERWRITTEN with
      fresh data (previous pull is lost — it was a snapshot)
    - Use pull_with_history() to append instead of overwrite

FILE LOCATION:
    mon_files/pulled/<Name>.mon          (standard pull)
    mon_files/pulled/archive/<Name>_<timestamp>.mon  (archived)

IMPORT:
    from mon_system import MonPullSystem
    puller = MonPullSystem(world_state_path="world_state.json")
    puller.pull("Omegamon")          # → mon_files/pulled/Omega.mon
    puller.pull_all_royal_knights()  # → pulls every active Knight
    puller.pull_by_id("digi_042")    # → pull by internal ID
"""

import os
import json
import re
from datetime import datetime
from typing import Optional


# ──────────────────────────────────────────────────────────────────────────────
# NAME PROCESSING
# ──────────────────────────────────────────────────────────────────────────────

def strip_mon_suffix(name: str) -> str:
    """
    Remove the trailing 'mon' (case-insensitive) from a Digimon's name.

    Examples:
        Omegamon       → Omega
        WarGreymon     → WarGrey
        Seraphimon     → Seraphi
        Beelzemon      → Beelze
        Gallantmon     → Gallant
        MetalGarurumon → MetalGaruru
        HerculesKabuterimon → HerculesKabuteri
        Botamon        → Bota         (Fresh-level, still applies)
        Agumon         → Agu

    Edge cases:
        If the name does not end in 'mon', it is returned unchanged.
        This should never happen in a valid simulation (all names end in mon)
        but is handled gracefully.
    """
    # Case-insensitive match for trailing 'mon'
    stripped = re.sub(r'(?i)mon$', '', name)
    if stripped == name:
        # No 'mon' suffix found — return as-is (shouldn't happen)
        return name
    return stripped


def build_pull_filename(digimon_name: str) -> str:
    """
    Given a Digimon's in-world name, return the .mon filename.

        Omegamon    → Omega.mon
        WarGreymon  → WarGrey.mon
    """
    base = strip_mon_suffix(digimon_name)
    return f"{base}.mon"


# ──────────────────────────────────────────────────────────────────────────────
# .MON FILE RENDERER
# ──────────────────────────────────────────────────────────────────────────────

# Evolution level order (for display bar)
_LEVEL_ORDER = [
    "Fresh", "In-Training", "Rookie",
    "Champion", "Ultimate", "Mega"
]

_ATTRIBUTE_SIGILS = {
    "Vaccine": "✦",   # Light sigil — protector
    "Data":    "◈",   # Data node — processor
    "Virus":   "▲",   # Spike — predator
}

_NATURE_ICONS = {
    "Aggressive": "⚔",
    "Cautious":   "🛡",
    "Curious":    "◎",
    "Loyal":      "♥",
    "Cunning":    "◆",
    "Feral":      "☠",
}


def render_evolution_bar(current_level: str) -> str:
    """
    Render a visual evolution progress bar.

    Example: ████░░  Champion
    """
    try:
        idx = _LEVEL_ORDER.index(current_level)
    except ValueError:
        idx = 0
    filled = idx + 1
    total  = len(_LEVEL_ORDER)
    bar    = "█" * filled + "░" * (total - filled)
    return f"[{bar}]  {current_level}"


def render_mon_file(record: dict, pull_timestamp: str, world_id: str = "UNKNOWN") -> str:
    """
    Render the full content of a .mon file from a Digimon record dict.

    This is the canonical format. All pulls use this renderer.
    """
    name        = record.get("name", "Unknown")
    pulled_name = strip_mon_suffix(name)
    attribute   = record.get("attribute", "Unknown")
    sigil       = _ATTRIBUTE_SIGILS.get(attribute, "?")
    level       = record.get("evolution_level", "Unknown")
    nature      = record.get("nature", "Unknown")
    nature_icon = _NATURE_ICONS.get(nature, "?")

    # ── Combat stats
    perf   = record.get("performance", 0.0)
    w_wins = record.get("battles_won", 0)
    w_loss = record.get("battles_lost", 0)
    u_wins = record.get("usurpation_wins", 0)
    u_loss = record.get("usurpation_losses", 0)
    total_battles = w_wins + w_loss
    win_pct = (w_wins / total_battles * 100) if total_battles > 0 else 0.0

    # ── Status flags
    alive       = record.get("alive", True)
    is_knight   = record.get("is_royal_knight", False)
    is_ygg      = record.get("is_yggdrasil", False)
    seat        = record.get("knight_seat", None)
    god_gen     = record.get("god_gen", None)

    # ── Status badge
    if is_ygg:
        status_badge = f"  ★ YGGDRASIL — GOD OF THE DIGITAL WORLD (Gen {god_gen})"
    elif is_knight:
        status_badge = f"  ⚜ ROYAL KNIGHT — {seat}"
    elif not alive:
        status_badge = "  ✝ RETIRED — Data preserved in the Akashic Record"
    else:
        status_badge = "  ◉ ACTIVE — Roaming the Digital World"

    # ── Capabilities
    caps = record.get("capabilities", [])
    cap_lines = [f"  [{i+1:02d}]  {cap}" for i, cap in enumerate(caps)] \
                if caps else ["  (none recorded)"]

    # ── Evolution lineage
    line_id   = record.get("line_id", "unknown")
    parent_id = record.get("parent_id", "none")
    gen       = record.get("generation", 0)

    # ── Timestamps
    born_at    = record.get("born_at",    "unknown")
    evolved_at = record.get("evolved_at", "unknown")
    ascended   = record.get("ascended_at", None)

    # ── Biome & Domain
    biome      = record.get("biome", "unknown")
    domain_txt = record.get("active_domain", "unassigned")

    # ── Build file
    sep  = "═" * 62
    sep2 = "─" * 62

    lines = [
        sep,
        f"",
        f"     {pulled_name}.mon",
        f"     {sigil}  {attribute}  ·  {level}  ·  {nature_icon} {nature}",
        f"",
        status_badge,
        f"",
        sep,
        f"",
        f"  [IDENTITY]",
        f"  {'Full Name':<20}: {name}",
        f"  {'Pulled As':<20}: {pulled_name}",
        f"  {'Internal ID':<20}: {record.get('id', 'unknown')}",
        f"  {'Line':<20}: {line_id}",
        f"  {'Attribute':<20}: {attribute}  {sigil}",
        f"  {'Nature':<20}: {nature}  {nature_icon}",
        f"  {'Generation':<20}: Gen {gen}",
        f"  {'Parent':<20}: {parent_id}",
        f"  {'World':<20}: {world_id}",
        f"",
        sep2,
        f"",
        f"  [EVOLUTION]",
        f"  {render_evolution_bar(level)}",
        f"  {'Born':<20}: {born_at}",
        f"  {'Last Evolved':<20}: {evolved_at}",
    ]

    if ascended:
        lines.append(f"  {'Ascended':<20}: {ascended}")

    lines += [
        f"",
        sep2,
        f"",
        f"  [LOCATION]",
        f"  {'Biome':<20}: {biome}",
        f"  {'Domain':<20}: {domain_txt}",
        f"",
        sep2,
        f"",
        f"  [COMBAT RECORD]",
        f"  {'Performance Pts':<20}: {perf:.1f}",
        f"  {'Battles Won':<20}: {w_wins}",
        f"  {'Battles Lost':<20}: {w_loss}",
        f"  {'Win Rate':<20}: {win_pct:.1f}%",
        f"  {'Usurp Wins':<20}: {u_wins}",
        f"  {'Usurp Losses':<20}: {u_loss}",
        f"",
        sep2,
        f"",
        f"  [HISTORY]",
        f"  {record.get('description', 'No history on record.')}",
        f"",
        sep2,
        f"",
        f"  [CAPABILITIES]",
    ]

    lines += cap_lines

    lines += [
        f"",
        sep2,
        f"",
        f"  [PULL RECORD]",
        f"  {'Pulled At':<20}: {pull_timestamp}",
        f"  {'Alive At Pull':<20}: {'Yes' if alive else 'No — Retired'}",
        f"",
        sep,
        f"  END OF FILE  ·  {pulled_name}.mon  ·  {pull_timestamp}",
        sep,
        "",
    ]

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# MON PULL SYSTEM
# ──────────────────────────────────────────────────────────────────────────────

class MonPullSystem:
    """
    The pull interface for the Digital World.

    Load the world state, find Digimon by name or ID,
    and write their .mon file to disk.

    Usage:
        puller = MonPullSystem("world_state.json")
        puller.pull("Omegamon")
        puller.pull_all_royal_knights()
        puller.pull_all()
        puller.pull_by_id("digi_007")
    """

    def __init__(
        self,
        world_state_path: str = "world_state.json",
        output_dir: str = "mon_files/pulled",
        archive: bool = False,
    ):
        """
        Args:
            world_state_path : Path to world_state.json
            output_dir       : Where to write .mon files
            archive          : If True, never overwrite — timestamp every pull
        """
        self.world_state_path = world_state_path
        self.output_dir       = output_dir
        self.archive          = archive
        self.world_state      = {}
        self._load()

    # ── I/O ──────────────────────────────────────────────────────────────────

    def _load(self):
        """Load the world state from disk."""
        if not os.path.exists(self.world_state_path):
            raise FileNotFoundError(
                f"World state not found at: {self.world_state_path}\n"
                f"Make sure the Digital World simulation has been started at least once."
            )
        with open(self.world_state_path, "r") as f:
            self.world_state = json.load(f)

    def reload(self):
        """Reload world state — call this to get fresh data mid-session."""
        self._load()
        print(f"[MON PULL] World state reloaded — Tick {self.world_state.get('tick', '?')}")

    # ── LOOKUP ────────────────────────────────────────────────────────────────

    def _all_digimon(self) -> dict:
        return self.world_state.get("digimon", {})

    def find_by_name(self, name: str) -> Optional[dict]:
        """
        Find a Digimon record by their in-world name (exact, case-insensitive).
        Returns the first match, or None.
        """
        name_lower = name.lower()
        for record in self._all_digimon().values():
            if record.get("name", "").lower() == name_lower:
                return record
        return None

    def find_by_id(self, digimon_id: str) -> Optional[dict]:
        """Find a Digimon record by their internal ID."""
        return self._all_digimon().get(digimon_id)

    def find_all_royal_knights(self) -> list[dict]:
        """Return all currently active Royal Knights."""
        return [
            r for r in self._all_digimon().values()
            if r.get("is_royal_knight") and r.get("alive", True)
        ]

    def find_yggdrasil(self) -> Optional[dict]:
        """Return the current Yggdrasil record, if any."""
        for record in self._all_digimon().values():
            if record.get("is_yggdrasil"):
                return record
        return None

    # ── PULL ─────────────────────────────────────────────────────────────────

    def _write(self, record: dict) -> str:
        """
        Core pull operation. Renders and writes the .mon file.

        Returns the path of the written file.
        """
        os.makedirs(self.output_dir, exist_ok=True)

        now       = datetime.now().isoformat()
        world_id  = self.world_state.get("world_id", "UNKNOWN")
        filename  = build_pull_filename(record["name"])

        if self.archive:
            # Archive mode: never overwrite, timestamp every file
            base   = filename.replace(".mon", "")
            ts     = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{base}_{ts}.mon"

        path = os.path.join(self.output_dir, filename)

        content = render_mon_file(record, pull_timestamp=now, world_id=world_id)

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        pulled_name = strip_mon_suffix(record["name"])
        level = record.get("evolution_level", "?")
        perf  = record.get("performance", 0.0)
        print(f"  [PULL]  {record['name']:<24} →  {filename:<30}  ({level}, {perf:.0f}pts)")

        return path

    def pull(self, name: str) -> Optional[str]:
        """
        Pull a Digimon by their in-world name.

            puller.pull("Omegamon")   → mon_files/pulled/Omega.mon

        Returns the output path, or None if not found.
        """
        record = self.find_by_name(name)
        if record is None:
            print(f"  [PULL]  '{name}' not found in world state.")
            return None
        return self._write(record)

    def pull_by_id(self, digimon_id: str) -> Optional[str]:
        """
        Pull a Digimon by their internal ID.

            puller.pull_by_id("digi_042")
        """
        record = self.find_by_id(digimon_id)
        if record is None:
            print(f"  [PULL]  ID '{digimon_id}' not found in world state.")
            return None
        return self._write(record)

    def pull_all_royal_knights(self) -> list[str]:
        """
        Pull every active Royal Knight.

        Returns list of output paths.
        """
        knights = self.find_all_royal_knights()
        if not knights:
            print("  [PULL]  No active Royal Knights found.")
            return []

        print(f"\n{'═'*60}")
        print(f"  PULLING ALL ROYAL KNIGHTS  ({len(knights)} active)")
        print(f"{'═'*60}")
        paths = [self._write(r) for r in knights]
        print(f"{'═'*60}")
        print(f"  {len(paths)} .mon file(s) written to: {self.output_dir}")
        print(f"{'═'*60}\n")
        return paths

    def pull_yggdrasil(self) -> Optional[str]:
        """Pull the current Yggdrasil's .mon file."""
        record = self.find_yggdrasil()
        if record is None:
            print("  [PULL]  No Yggdrasil found in world state.")
            return None
        print(f"\n{'═'*60}")
        print(f"  PULLING YGGDRASIL — GOD OF THE DIGITAL WORLD")
        print(f"{'═'*60}")
        path = self._write(record)
        print(f"{'═'*60}\n")
        return path

    def pull_all(self, alive_only: bool = True) -> list[str]:
        """
        Pull every Digimon in the world.

        Args:
            alive_only : If True (default), skip retired Digimon
        """
        all_records = list(self._all_digimon().values())
        if alive_only:
            all_records = [r for r in all_records if r.get("alive", True)]

        print(f"\n{'═'*60}")
        label = "ALIVE" if alive_only else "ALL"
        print(f"  PULLING {label} DIGIMON  ({len(all_records)} total)")
        print(f"{'═'*60}")
        paths = [self._write(r) for r in sorted(all_records, key=lambda r: r.get("name", ""))]
        print(f"{'═'*60}")
        print(f"  {len(paths)} .mon file(s) written to: {self.output_dir}")
        print(f"{'═'*60}\n")
        return paths

    def pull_by_attribute(self, attribute: str) -> list[str]:
        """Pull all Digimon of a given attribute (Data / Vaccine / Virus)."""
        targets = [
            r for r in self._all_digimon().values()
            if r.get("attribute", "").lower() == attribute.lower()
            and r.get("alive", True)
        ]
        print(f"\n{'═'*60}")
        print(f"  PULLING ALL {attribute.upper()} DIGIMON  ({len(targets)} found)")
        print(f"{'═'*60}")
        paths = [self._write(r) for r in targets]
        print(f"{'═'*60}")
        print(f"  {len(paths)} .mon file(s) written to: {self.output_dir}")
        print(f"{'═'*60}\n")
        return paths

    def pull_by_level(self, level: str) -> list[str]:
        """Pull all Digimon at a given evolution level."""
        targets = [
            r for r in self._all_digimon().values()
            if r.get("evolution_level", "").lower() == level.lower()
            and r.get("alive", True)
        ]
        print(f"\n{'═'*60}")
        print(f"  PULLING ALL {level.upper()}  ({len(targets)} found)")
        print(f"{'═'*60}")
        paths = [self._write(r) for r in targets]
        print(f"{'═'*60}")
        print(f"  {len(paths)} .mon file(s) written to: {self.output_dir}")
        print(f"{'═'*60}\n")
        return paths

    # ── STATUS ────────────────────────────────────────────────────────────────

    def list_pullable(self, alive_only: bool = True) -> None:
        """Print a summary table of all pullable Digimon."""
        all_records = list(self._all_digimon().values())
        if alive_only:
            all_records = [r for r in all_records if r.get("alive", True)]
        all_records.sort(key=lambda r: (r.get("evolution_level", ""), r.get("name", "")))

        print(f"\n{'═'*70}")
        print(f"  PULLABLE DIGIMON — World: {self.world_state.get('world_id', '?')}  "
              f"Tick: {self.world_state.get('tick', '?')}")
        print(f"{'─'*70}")
        print(f"  {'Name':<22} {'→ Pulled As':<20} {'Level':<14} {'Attr':<8} {'Perf':>7}")
        print(f"{'─'*70}")

        for r in all_records:
            name        = r.get("name", "?")
            pulled_name = strip_mon_suffix(name)
            level       = r.get("evolution_level", "?")
            attr        = r.get("attribute", "?")
            perf        = r.get("performance", 0.0)
            knight_mark = " ⚜" if r.get("is_royal_knight") else ""
            ygg_mark    = " ★" if r.get("is_yggdrasil")   else ""
            print(f"  {name:<22} → {pulled_name+'.mon':<20} {level:<14} {attr:<8} {perf:>7.1f}{knight_mark}{ygg_mark}")

        print(f"{'═'*70}")
        print(f"  {len(all_records)} Digimon listed  (⚜ Royal Knight  ★ Yggdrasil)")
        print(f"{'═'*70}\n")


# ──────────────────────────────────────────────────────────────────────────────
# CLI INTERFACE
# ──────────────────────────────────────────────────────────────────────────────

def _cli():
    """
    Command-line interface for the .mon pull system.

    Usage:
        python mon_system.py                          # list all pullable
        python mon_system.py pull Omegamon            # pull one by name
        python mon_system.py pull-id digi_007         # pull by ID
        python mon_system.py pull-knights             # pull all Royal Knights
        python mon_system.py pull-ygg                 # pull Yggdrasil
        python mon_system.py pull-all                 # pull all alive
        python mon_system.py pull-all --include-dead  # pull everyone
        python mon_system.py pull-attr Vaccine        # pull by attribute
        python mon_system.py pull-level Mega          # pull by level
    """
    import sys

    args   = sys.argv[1:]
    puller = MonPullSystem()

    if not args:
        puller.list_pullable()
        return

    cmd = args[0].lower()

    if cmd == "pull" and len(args) >= 2:
        puller.pull(args[1])

    elif cmd == "pull-id" and len(args) >= 2:
        puller.pull_by_id(args[1])

    elif cmd == "pull-knights":
        puller.pull_all_royal_knights()

    elif cmd == "pull-ygg":
        puller.pull_yggdrasil()

    elif cmd == "pull-all":
        alive_only = "--include-dead" not in args
        puller.pull_all(alive_only=alive_only)

    elif cmd == "pull-attr" and len(args) >= 2:
        puller.pull_by_attribute(args[1])

    elif cmd == "pull-level" and len(args) >= 2:
        puller.pull_by_level(args[1])

    elif cmd == "list":
        alive_only = "--include-dead" not in args
        puller.list_pullable(alive_only=alive_only)

    else:
        print(__doc__)


if __name__ == "__main__":
    _cli()
