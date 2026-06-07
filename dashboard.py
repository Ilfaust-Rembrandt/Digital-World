"""
╔══════════════════════════════════════════════════════════════════╗
║           DIGITAL WORLD — RICH TERMINAL DASHBOARD               ║
║                                                                  ║
║  Live world status rendered in the terminal using Rich.          ║
║  Replaces the pygame dashboard — no display server needed.       ║
║  Run standalone:  python dashboard.py                            ║
║  Or it auto-starts from world.py if DASHBOARD=true              ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import json
import time
import threading
from datetime import datetime
from typing import Optional

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.columns import Columns
    from rich.text import Text
    from rich.progress import BarColumn, Progress, TextColumn
    from rich.layout import Layout
    from rich.live import Live
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

# ── Config ────────────────────────────────────────────────────────────────────

WORLD_STATE_FILE = os.getenv("DB_PATH", "world_state.json")
REFRESH_SECONDS  = float(os.getenv("DASHBOARD_REFRESH", "2.0"))

ATTRIBUTE_COLOURS = {
    "Data":    "cyan",
    "Vaccine": "green",
    "Virus":   "red",
}

LEVEL_COLOURS = {
    "Fresh":       "dim white",
    "In-Training": "white",
    "Rookie":      "yellow",
    "Champion":    "bright_yellow",
    "Ultimate":    "bright_magenta",
    "Mega":        "bright_red",
}

MAGI_COLOURS = {
    "SOLOMON":  "cyan",
    "SALADIN":  "red",
    "AL-FATIH": "green",
}


# ── Dashboard renderer ────────────────────────────────────────────────────────

class DigitalWorldDashboard:

    def __init__(self, state_file: str = WORLD_STATE_FILE):
        self.state_file = state_file
        self.console    = Console()
        self._state: dict = {}

    def _load(self) -> bool:
        try:
            with open(self.state_file) as f:
                self._state = json.load(f)
            return True
        except Exception:
            return False

    # ── Section builders ──────────────────────────────────────────────────────

    def _header(self) -> Panel:
        state   = self._state
        tick    = state.get("tick", 0)
        god_gen = state.get("god_generation", 0) + 1
        world   = state.get("world_id", "VM_A")
        ts      = datetime.now().strftime("%H:%M:%S")

        text = Text()
        text.append(f"  ⟁ DIGITAL WORLD ", style="bold bright_white")
        text.append(f"'{world}'", style="bold cyan")
        text.append(f"   Tick: ", style="dim white")
        text.append(f"{tick:,}", style="bold white")
        text.append(f"   God Gen: ", style="dim white")
        text.append(f"{god_gen}", style="bold yellow")
        text.append(f"   {ts}", style="dim white")

        return Panel(text, box=box.DOUBLE_EDGE, style="bold blue")

    def _population_table(self) -> Panel:
        digimon  = self._state.get("digimon", {})
        living   = [d for d in digimon.values() if d.get("alive")]

        by_attr  = {"Data": 0, "Vaccine": 0, "Virus": 0}
        by_level = {}
        for d in living:
            attr = d.get("attribute", "Data")
            lvl  = d.get("evolution_level", "Fresh")
            by_attr[attr] = by_attr.get(attr, 0) + 1
            by_level[lvl] = by_level.get(lvl, 0) + 1

        table = Table(box=box.SIMPLE, show_header=True,
                      header_style="bold dim white")
        table.add_column("Attribute", style="bold")
        table.add_column("Count", justify="right")
        table.add_column("Bar", min_width=20)

        total = max(len(living), 1)
        for attr, count in by_attr.items():
            colour = ATTRIBUTE_COLOURS.get(attr, "white")
            pct    = count / total
            filled = int(pct * 20)
            bar    = f"[{colour}]{'█' * filled}[/][dim]{'░' * (20 - filled)}[/]"
            table.add_row(
                f"[{colour}]{attr}[/]",
                f"[{colour}]{count}[/]",
                bar,
            )

        # Level breakdown as a compact text row
        level_order = ["Fresh","In-Training","Rookie","Champion","Ultimate","Mega"]
        level_parts = []
        for lvl in level_order:
            c = by_level.get(lvl, 0)
            if c > 0:
                col = LEVEL_COLOURS.get(lvl, "white")
                level_parts.append(f"[{col}]{lvl[:3]}:{c}[/]")

        level_text = Text.from_markup("  ".join(level_parts))

        from rich.console import Group
        content = Group(table, level_text)
        return Panel(content, title=f"[bold]Population [white]{len(living)}[/][/]",
                     box=box.ROUNDED, border_style="blue")

    def _magi_panel(self) -> Panel:
        decisions = self._state.get("magi_decision_log", [])
        holders   = self._state.get("magi_holders", {})

        table = Table(box=box.SIMPLE, show_header=True,
                      header_style="bold dim white", padding=(0,1))
        table.add_column("Seat",     style="bold", min_width=10)
        table.add_column("Attr",     min_width=8)
        table.add_column("Holder",   min_width=16)
        table.add_column("Votes",    justify="right", min_width=6)

        seats = {
            "SOLOMON":  ("Data",    "cyan"),
            "SALADIN":  ("Virus",   "red"),
            "AL-FATIH": ("Vaccine", "green"),
        }

        for seat, (attr, colour) in seats.items():
            holder_id  = holders.get(seat)
            holder_dgm = self._state.get("digimon", {}).get(holder_id, {})
            holder_name = holder_dgm.get("name", "[AI]") if holder_id else "[AI]"

            seat_votes = [d for d in decisions if d.get("decision_type")]
            vote_count = len(seat_votes)

            table.add_row(
                f"[{colour}]{seat}[/]",
                f"[{colour}]{attr}[/]",
                f"[white]{holder_name}[/]",
                f"[dim]{vote_count}[/]",
            )

        # Last 3 decisions
        recent = decisions[-3:] if decisions else []
        lines  = []
        for d in reversed(recent):
            decision = d.get("decision","?")
            dtype    = d.get("decision_type","?")
            colour   = "green" if decision == "APPROVE" else "red"
            decree   = " ⚡" if d.get("decree") else ""
            lines.append(
                f"[dim]tick{d.get('tick',0)}[/] [{colour}]{decision}[/] "
                f"[dim]{dtype}{decree}[/]"
            )

        from rich.console import Group
        from rich.text import Text as RText
        recent_text = RText("\n".join(lines)) if lines else RText("[dim]no decisions yet[/]")
        content = Group(table, Panel(recent_text, title="[dim]Recent Verdicts[/]",
                                     box=box.SIMPLE, border_style="dim"))
        return Panel(content, title="[bold]MAGI Council[/]",
                     box=box.ROUNDED, border_style="magenta")

    def _knights_panel(self) -> Panel:
        seats   = self._state.get("royal_knights", {}).get("seats", {})
        filled  = [(sid, s) for sid, s in seats.items() if s.get("occupied")]
        empty   = sum(1 for s in seats.values() if not s.get("occupied"))

        table = Table(box=box.SIMPLE, show_header=True,
                      header_style="bold dim white", padding=(0,1))
        table.add_column("#",      min_width=3,  justify="right")
        table.add_column("Knight", min_width=18)
        table.add_column("Attr",   min_width=8)
        table.add_column("Pts",    min_width=6,  justify="right")

        for seat_id, seat in sorted(filled, key=lambda x: x[0])[:13]:
            d      = seat.get("digimon", {})
            attr   = d.get("attribute", "Data")
            colour = ATTRIBUTE_COLOURS.get(attr, "white")
            pts    = d.get("performance", 0)
            table.add_row(
                f"[dim]{seat_id[-2:]}[/]",
                f"[{colour}]{d.get('name','?')[:16]}[/]",
                f"[{colour}]{attr[:3]}[/]",
                f"[yellow]{pts:.0f}[/]",
            )

        if empty > 0:
            table.add_row("", f"[dim]({empty} vacant)[/]", "", "")

        return Panel(table,
                     title=f"[bold]Royal Knights [{len(filled)}/13][/]",
                     box=box.ROUNDED, border_style="yellow")

    def _ascension_panel(self) -> Panel:
        threshold = self._state.get("ascension_threshold", 1000)
        seats     = self._state.get("royal_knights", {}).get("seats", {})
        digimon   = self._state.get("digimon", {})

        best_score = 0.0
        best_name  = "—"
        best_attr  = "Data"

        for seat in seats.values():
            if not seat.get("occupied"):
                continue
            d     = seat.get("digimon", {})
            score = d.get("performance", 0.0)
            if score > best_score:
                best_score = score
                best_name  = d.get("name", "?")
                best_attr  = d.get("attribute", "Data")

        pct    = min(1.0, best_score / max(threshold, 1))
        filled = int(pct * 30)
        colour = ATTRIBUTE_COLOURS.get(best_attr, "white")
        bar    = f"[{colour}]{'█' * filled}[/][dim]{'░' * (30 - filled)}[/]"

        lines = [
            f"  [bold]{best_name}[/]  [{colour}]{best_score:.0f}[/] / [dim]{threshold:.0f}[/] pts",
            f"  {bar}  [dim]{pct*100:.1f}%[/]",
        ]

        ascension_log = self._state.get("ascension_log", [])
        if ascension_log:
            last = ascension_log[-1]
            lines.append(
                f"\n  [dim]Last ascension: [yellow]{last.get('new_god_name','?')}[/] "
                f"at tick {last.get('tick',0)}[/]"
            )

        from rich.text import Text as RText
        text = RText.from_markup("\n".join(lines))
        return Panel(text, title="[bold]Ascension Progress[/]",
                     box=box.ROUNDED, border_style="bright_red")

    def _rewards_panel(self) -> Panel:
        rewards  = self._state.get("rewards", {})
        digimon  = self._state.get("digimon", {})

        # Top 5 by total reward points
        scored = []
        for did, rec in rewards.items():
            dgm = digimon.get(did, {})
            if not dgm.get("alive"):
                continue
            scored.append((rec.get("total", 0), dgm))
        scored.sort(reverse=True)

        table = Table(box=box.SIMPLE, show_header=True,
                      header_style="bold dim white", padding=(0,1))
        table.add_column("Digimon",  min_width=16)
        table.add_column("Attr",     min_width=4)
        table.add_column("Rewards",  justify="right", min_width=7)
        table.add_column("Gen+",     justify="right", min_width=6)

        for pts, dgm in scored[:5]:
            attr   = dgm.get("attribute","Data")
            colour = ATTRIBUTE_COLOURS.get(attr, "white")
            rec    = rewards.get(dgm.get("id",""), {})
            bonus  = rec.get("lifespan_bonus", 0)
            table.add_row(
                f"[{colour}]{dgm.get('name','?')[:14]}[/]",
                f"[{colour}]{attr[:3]}[/]",
                f"[yellow]{pts:,}[/]",
                f"[dim]+{bonus}[/]",
            )

        return Panel(table, title="[bold]Top Reward Holders[/]",
                     box=box.ROUNDED, border_style="cyan")

    def _biomes_panel(self) -> Panel:
        # Read from world_status.txt if available for biome richness
        biome_data = self._state.get("biome_state", {})

        biomes = [
            "Desert", "Grasslands", "Forest",
            "Highlands", "Mountains", "Ocean", "DeepOcean"
        ]

        table = Table(box=box.SIMPLE, show_header=False, padding=(0,1))
        table.add_column("Biome",   min_width=12)
        table.add_column("Domain",  min_width=14)
        table.add_column("Event",   min_width=12)

        for b in biomes:
            data   = biome_data.get(b, {})
            domain = data.get("domain", "—")[:13]
            event  = data.get("active_event", "")
            event_str = f"[yellow]{event[:10]}[/]" if event else "[dim]—[/]"
            table.add_row(
                f"[bright_blue]{b[:11]}[/]",
                f"[dim]{domain}[/]",
                event_str,
            )

        return Panel(table, title="[bold]Biomes[/]",
                     box=box.ROUNDED, border_style="bright_blue")

    def _research_panel(self) -> Panel:
        log = self._state.get("research_log", [])[-5:]

        lines = []
        for entry in reversed(log):
            name    = entry.get("name","?")
            topic   = entry.get("topic","?")[:35]
            pts     = entry.get("reward_pts", 0)
            unsolved= " [yellow]UNSOLVED[/]" if entry.get("is_unsolved") else ""
            lines.append(
                f"[cyan]{name}[/] → [dim]{topic}[/] "
                f"[green]+{pts}pts[/]{unsolved}"
            )

        text = "\n".join(lines) if lines else "[dim]No research yet[/]"
        from rich.text import Text as RText
        return Panel(RText.from_markup(text),
                     title="[bold]Data Research[/]",
                     box=box.ROUNDED, border_style="cyan")

    # ── Full render ───────────────────────────────────────────────────────────

    def render(self) -> None:
        """Render one full frame to the console."""
        if not self._load():
            self.console.print(
                Panel("[yellow]Waiting for world_state.json...[/]",
                      title="Digital World Dashboard")
            )
            return

        from rich.console import Group

        self.console.print(self._header())

        # Row 1: population | magi
        self.console.print(
            Columns([self._population_table(), self._magi_panel()],
                    equal=False, expand=True)
        )

        # Row 2: knights | ascension
        self.console.print(
            Columns([self._knights_panel(), self._ascension_panel()],
                    equal=False, expand=True)
        )

        # Row 3: rewards | biomes | research
        self.console.print(
            Columns([self._rewards_panel(), self._biomes_panel(),
                     self._research_panel()],
                    equal=True, expand=True)
        )

    def run_live(self) -> None:
        """Run as a live auto-refreshing dashboard."""
        if not RICH_AVAILABLE:
            print("Rich not installed. Run: pip install rich")
            return

        with Live(console=self.console, refresh_per_second=1,
                  screen=True) as live:
            while True:
                if self._load():
                    from io import StringIO
                    from rich.console import Console as RC
                    buf = RC(file=StringIO(), width=self.console.width or 120)

                    buf.print(self._header())
                    buf.print(Columns([self._population_table(),
                                       self._magi_panel()],
                                      equal=False, expand=True))
                    buf.print(Columns([self._knights_panel(),
                                       self._ascension_panel()],
                                      equal=False, expand=True))
                    buf.print(Columns([self._rewards_panel(),
                                       self._biomes_panel(),
                                       self._research_panel()],
                                      equal=True, expand=True))

                    live.update(buf.file.getvalue())
                else:
                    live.update(
                        Panel("[yellow]Waiting for world_state.json...[/]")
                    )
                time.sleep(REFRESH_SECONDS)


# ── Standalone entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    if not RICH_AVAILABLE:
        print("Rich not installed. Run: pip install rich")
        exit(1)

    dash = DigitalWorldDashboard()

    import sys
    if "--once" in sys.argv:
        dash.render()
    else:
        print("Starting live dashboard. Press Ctrl+C to exit.")
        print(f"Reading from: {WORLD_STATE_FILE}")
        dash.run_live()
