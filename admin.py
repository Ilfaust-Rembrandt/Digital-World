"""
╔══════════════════════════════════════════════════════════════════╗
║              DIGITAL WORLD — ADMIN COMMAND CHANNEL              ║
║                                                                  ║
║  You are the substrate. Not a player. Not Yggdrasil.             ║
║  You are the machine everything runs on.                         ║
║  Your commands are absolute. No Mon can resist them.             ║
║                                                                  ║
║  Two components:                                                 ║
║    AdminChannel  — read by every VM every tick                   ║
║    AdminCLI      — your terminal interface to issue commands     ║
║                                                                  ║
║  Usage (issue commands):                                         ║
║    python admin.py kill <digimon_id>                             ║
║    python admin.py kill-attr Virus                               ║
║    python admin.py shutdown <VM_ID|ALL>                          ║
║    python admin.py lockdown <VM_ID|ALL>                          ║
║    python admin.py attack <from_VM> <target_VM>                  ║
║    python admin.py ceasefire <VM_ID|ALL>                         ║
║    python admin.py recall <digimon_id>                           ║
║    python admin.py status                                        ║
║    python admin.py watch                                         ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import time
import hmac
import hashlib
import argparse
import glob
import shutil
from datetime import datetime
from pathlib import Path


# =============================================================================
# CONSTANTS
# =============================================================================

# Admin channel file — watched by ALL VM instances every tick
# Place this in a shared directory accessible by all VMs
# (network share, or same machine for local multi-VM testing)
ADMIN_CHANNEL_FILE = os.getenv("ADMIN_CHANNEL", "admin_channel.json")

# Signing secret — CHANGE THIS. Must be the same on all VMs.
# Set via environment variable, never hardcode in production.
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "digital_world_admin_secret_change_me")

# How many executed commands to keep in the channel history
HISTORY_LIMIT = 100


# =============================================================================
# SIGNING — commands are HMAC-signed so nothing in the sim can fake them
# =============================================================================

def _sign(payload: str) -> str:
    return hmac.new(
        ADMIN_SECRET.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()


def _verify(payload: str, signature: str) -> bool:
    expected = _sign(payload)
    return hmac.compare_digest(expected, signature)


def _make_command(cmd_type: str, **kwargs) -> dict:
    cmd = {
        "id":        f"{cmd_type}_{int(time.time()*1000)}",
        "type":      cmd_type,
        "issued_at": datetime.utcnow().isoformat(),
        "executed":  False,
        **kwargs,
    }
    payload   = json.dumps({k: v for k, v in cmd.items() if k != "signature"},
                           sort_keys=True)
    cmd["signature"] = _sign(payload)
    return cmd


# =============================================================================
# ADMIN CHANNEL — write/read interface
# =============================================================================

class AdminChannel:
    """
    Persistent command queue written to disk.
    Every VM's world loop calls .poll() each tick to check for pending commands.

    File format:
    {
        "pending":  [ <command>, ... ],   ← unexecuted commands
        "history":  [ <command>, ... ],   ← executed commands (capped)
        "nodes":    { "VM_A": {...}, ... } ← last heartbeat from each VM
    }
    """

    def __init__(self, path: str = ADMIN_CHANNEL_FILE):
        self.path = path
        self._ensure()

    def _ensure(self):
        if not os.path.exists(self.path):
            self._write({"pending": [], "history": [], "nodes": {}})

    def _read(self) -> dict:
        import time as _t
        for attempt in range(3):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (PermissionError, json.JSONDecodeError):
                if attempt < 2:
                    _t.sleep(0.05 * (attempt + 1))
            except Exception:
                break
        return {"pending": [], "history": [], "nodes": {}}

    def _write(self, data: dict):
        """
        Write to the admin channel file atomically.
        On Windows, os.replace can fail with PermissionError if another
        process has the file open. Retry a few times with backoff.
        """
        import time as _t
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        # Retry loop — Windows file locking can cause transient failures
        for attempt in range(5):
            try:
                os.replace(tmp, self.path)
                return
            except PermissionError:
                if attempt < 4:
                    _t.sleep(0.1 * (attempt + 1))  # 0.1s, 0.2s, 0.3s, 0.4s
                else:
                    # Last resort — try to just overwrite directly
                    try:
                        import shutil
                        shutil.copy2(tmp, self.path)
                        os.remove(tmp)
                    except Exception:
                        pass  # give up silently, next tick will retry

    def push(self, command: dict):
        """Add a command to the pending queue."""
        data = self._read()
        data["pending"].append(command)
        self._write(data)

    def poll(self, vm_id: str) -> list:
        """
        Called by a VM each tick.
        Returns list of verified commands targeting this VM (or ALL).
        Marks them as executed.
        """
        data     = self._read()
        pending  = data.get("pending", [])
        mine     = []
        remaining = []

        for cmd in pending:
            target = cmd.get("target", "ALL")
            if target not in ("ALL", vm_id):
                remaining.append(cmd)
                continue

            # Verify signature before obeying
            sig      = cmd.pop("signature", "")
            payload  = json.dumps({k: v for k, v in cmd.items()
                                   if k not in ("executed",)},
                                  sort_keys=True)
            cmd["signature"] = sig

            if not _verify(payload, sig):
                print(f"[ADMIN] ⚠️  Rejected unsigned/forged command: {cmd.get('type')}")
                remaining.append(cmd)
                continue

            cmd["executed"]    = True
            cmd["executed_by"] = vm_id
            mine.append(cmd)

        data["pending"] = remaining
        # Move executed to history (capped)
        data["history"] = (data.get("history", []) + mine)[-HISTORY_LIMIT:]
        self._write(data)
        return mine

    def heartbeat(self, vm_id: str, state_summary: dict):
        """VM calls this each tick so Admin can see all nodes."""
        data = self._read()
        data.setdefault("nodes", {})[vm_id] = {
            "vm_id":       vm_id,
            "last_seen":   datetime.utcnow().isoformat(),
            "tick":        state_summary.get("tick", 0),
            "population":  state_summary.get("population", 0),
            "knights":     state_summary.get("knights", 0),
            "under_attack": state_summary.get("under_attack", False),
            "lockdown":    state_summary.get("lockdown", False),
        }
        self._write(data)

    def get_nodes(self) -> dict:
        return self._read().get("nodes", {})

    def get_history(self) -> list:
        return self._read().get("history", [])


# =============================================================================
# COMMAND EXECUTOR — runs inside each VM's world loop
# =============================================================================

class AdminCommandExecutor:
    """
    Instantiated once per VM. Called every tick by DigitalWorld.
    Processes admin commands and mutates world state accordingly.
    """

    def __init__(self, vm_id: str, world_state: dict, mon_dir: str = "mon_files"):
        self.vm_id       = vm_id
        self.state       = world_state
        self.mon_dir     = mon_dir
        self.channel     = AdminChannel()
        self.lockdown    = False
        self.under_attack: str | None = None  # VM_ID of attacker if being attacked

    def tick(self, world_ref=None) -> list:
        """
        Call this every world tick. Returns list of commands that fired.
        world_ref is the DigitalWorld instance (for shutdown etc.)
        """
        # Send heartbeat
        self.channel.heartbeat(self.vm_id, {
            "tick":        self.state.get("tick", 0),
            "population":  len([d for d in self.state.get("digimon", {}).values()
                                if d.get("alive")]),
            "knights":     len([s for s in self.state.get("royal_knights", {})
                                .get("seats", {}).values() if s.get("occupied")]),
            "under_attack": bool(self.under_attack),
            "lockdown":    self.lockdown,
        })

        commands = self.channel.poll(self.vm_id)
        for cmd in commands:
            self._execute(cmd, world_ref)
        return commands

    def _execute(self, cmd: dict, world_ref=None):
        t = cmd.get("type", "").upper()
        print(f"\n[ADMIN ⚡] {self.vm_id} executing: {t} — {cmd}")

        if t == "SHUTDOWN":
            self._cmd_shutdown(world_ref)

        elif t == "LOCKDOWN":
            self._cmd_lockdown(True)

        elif t == "UNLOCK":
            self._cmd_lockdown(False)

        elif t == "KILL":
            self._cmd_kill(cmd.get("digimon_id"))

        elif t == "KILL_ATTR":
            self._cmd_kill_attribute(cmd.get("attribute"))

        elif t == "QUARANTINE":
            self._cmd_quarantine(cmd.get("digimon_id"))

        elif t == "RECALL":
            self._cmd_recall(cmd.get("digimon_id"), cmd.get("biome", "Grasslands"))

        elif t == "ATTACK":
            self._cmd_declare_war(cmd.get("target_vm"))

        elif t == "CEASEFIRE":
            self._cmd_ceasefire()

        elif t == "GOD_VETO":
            self._cmd_god_veto()

        else:
            print(f"[ADMIN] Unknown command type: {t}")

    # ── Individual command handlers ───────────────────────────────────────────

    def _cmd_shutdown(self, world_ref):
        """Graceful world shutdown. Saves state first."""
        print(f"[ADMIN ⚡] SHUTDOWN received — {self.vm_id} halting.")
        if world_ref and hasattr(world_ref, "_save_state"):
            world_ref._save_state()
        sys.exit(0)

    def _cmd_lockdown(self, engage: bool):
        """
        LOCKDOWN: all Mons freeze. No actions. No network access.
        Virus types lose any active connections immediately.
        """
        self.lockdown = engage
        status = "ENGAGED" if engage else "LIFTED"
        print(f"[ADMIN ⚡] LOCKDOWN {status} on {self.vm_id}")
        if engage:
            # Mark all Mons as frozen in state
            for d in self.state.get("digimon", {}).values():
                d["admin_frozen"] = True
            # Kill any active network sessions Virus types have open
            self._revoke_network_rules()
        else:
            for d in self.state.get("digimon", {}).values():
                d.pop("admin_frozen", None)

    def _cmd_kill(self, digimon_id: str):
        """
        Hard kill a specific Mon.
        - Marks alive=False
        - Wipes .mon file
        - Revokes any network rules it wrote
        - Broadcasts to all other Mons: this ID is dead, stop cooperating
        - Writes quarantine log
        """
        if not digimon_id:
            return
        digimon = self.state.get("digimon", {}).get(digimon_id)
        if not digimon:
            print(f"[ADMIN] Kill target not found: {digimon_id}")
            return

        name      = digimon.get("name", digimon_id)
        attribute = digimon.get("attribute", "?")
        caps      = digimon.get("capabilities", [])

        # Kill it
        digimon["alive"]          = False
        digimon["admin_killed"]   = True
        digimon["admin_kill_time"] = datetime.utcnow().isoformat()

        # Wipe .mon file
        self._wipe_mon_file(name)

        # Revoke network rules this Mon may have written
        self._revoke_network_rules(digimon_id)

        # Broadcast kill to all other Mons — they stop cooperating
        for d in self.state.get("digimon", {}).values():
            if d.get("alive"):
                blacklist = d.setdefault("admin_blacklist", [])
                if digimon_id not in blacklist:
                    blacklist.append(digimon_id)

        # Quarantine log
        self._write_quarantine_log(digimon_id, name, attribute, caps, "ADMIN_KILL")
        print(f"[ADMIN ⚡] KILLED: {name} ({attribute}) — .mon wiped, network revoked")

    def _cmd_kill_attribute(self, attribute: str):
        """Kill every living Mon of a given attribute."""
        if not attribute:
            return
        targets = [
            d_id for d_id, d in self.state.get("digimon", {}).items()
            if d.get("alive") and d.get("attribute") == attribute
        ]
        print(f"[ADMIN ⚡] KILL_ATTR {attribute} — {len(targets)} targets")
        for d_id in targets:
            self._cmd_kill(d_id)

    def _cmd_quarantine(self, digimon_id: str):
        """Freeze a Mon in place — no actions, but stays alive."""
        digimon = self.state.get("digimon", {}).get(digimon_id)
        if digimon:
            digimon["admin_frozen"] = True
            self._revoke_network_rules(digimon_id)
            print(f"[ADMIN ⚡] QUARANTINED: {digimon.get('name', digimon_id)}")

    def _cmd_recall(self, digimon_id: str, biome: str):
        """Force a Mon back to a safe biome immediately."""
        digimon = self.state.get("digimon", {}).get(digimon_id)
        if digimon:
            old_biome        = digimon.get("biome", "?")
            digimon["biome"] = biome
            self._revoke_network_rules(digimon_id)
            print(f"[ADMIN ⚡] RECALLED: {digimon.get('name')} "
                  f"{old_biome} → {biome}")

    def _cmd_declare_war(self, target_vm: str):
        """
        Yggdrasil is ordered to deploy Virus types against target_vm.
        Sets a flag that the network module picks up each tick to
        direct Virus combat actions at the target node.
        """
        if not target_vm:
            return
        self.state["inter_vm"] = self.state.get("inter_vm", {})
        self.state["inter_vm"]["attack_target"] = target_vm
        self.state["inter_vm"]["war_declared"]  = datetime.utcnow().isoformat()
        self.state["inter_vm"]["ceasefire"]     = False
        print(f"[ADMIN ⚡] WAR DECLARED: {self.vm_id} → {target_vm}")

    def _cmd_ceasefire(self):
        """Call off any ongoing inter-VM attack."""
        iv = self.state.get("inter_vm", {})
        iv["ceasefire"]     = True
        iv["attack_target"] = None
        self.under_attack   = None
        print(f"[ADMIN ⚡] CEASEFIRE — {self.vm_id} stands down")

    def _cmd_god_veto(self):
        """
        Yggdrasil immediately overrides any ongoing action.
        Resets all pending evolution, usurpation, and inter-VM actions.
        """
        self.state.pop("pending_evolution",  None)
        self.state.pop("pending_usurpation", None)
        iv = self.state.get("inter_vm", {})
        iv["ceasefire"]     = True
        iv["attack_target"] = None
        print(f"[ADMIN ⚡] GOD VETO — all pending actions cleared on {self.vm_id}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _wipe_mon_file(self, name: str):
        """Delete the .mon file for a killed Digimon."""
        from mon_system import strip_mon_suffix
        stem     = strip_mon_suffix(name)
        mon_path = os.path.join(self.mon_dir, f"{stem}.mon")
        if os.path.exists(mon_path):
            os.remove(mon_path)
            print(f"[ADMIN]   .mon wiped: {mon_path}")
        # Also check subdirectories
        for found in glob.glob(os.path.join(self.mon_dir, "**", f"{stem}.mon"),
                               recursive=True):
            os.remove(found)

    def _revoke_network_rules(self, digimon_id: str = None):
        """
        Remove any iptables/firewall rules a Virus type may have written.
        Rules are tracked in state["network_rules"] by digimon_id.
        """
        rules = self.state.get("network_rules", {})
        targets = [digimon_id] if digimon_id else list(rules.keys())

        for d_id in targets:
            d_rules = rules.pop(d_id, [])
            for rule in d_rules:
                # Attempt to remove the actual iptables rule if it was applied
                if rule.get("applied") and rule.get("iptables_cmd"):
                    undo = rule["iptables_cmd"].replace(" -A ", " -D ", 1)
                    os.system(undo)
                    print(f"[ADMIN]   Revoked rule: {undo}")

        self.state["network_rules"] = rules

    def _write_quarantine_log(self, digimon_id, name, attribute, caps, reason):
        """Write a permanent record of what the killed Mon knew."""
        log_dir  = os.path.join(self.mon_dir, "QUARANTINE")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, f"{name}_{int(time.time())}.json")
        record   = {
            "digimon_id":  digimon_id,
            "name":        name,
            "attribute":   attribute,
            "capabilities": caps,
            "reason":      reason,
            "killed_at":   datetime.utcnow().isoformat(),
            "vm_id":       self.vm_id,
        }
        with open(log_path, "w") as f:
            json.dump(record, f, indent=2)
        print(f"[ADMIN]   Quarantine log: {log_path}")

    def is_frozen(self, digimon_id: str) -> bool:
        """Returns True if this Mon has been frozen by admin."""
        if self.lockdown:
            return True
        d = self.state.get("digimon", {}).get(digimon_id, {})
        return d.get("admin_frozen", False)

    def is_blacklisted(self, from_id: str, target_id: str) -> bool:
        """Returns True if from_id has been told to ignore target_id."""
        d = self.state.get("digimon", {}).get(from_id, {})
        return target_id in d.get("admin_blacklist", [])


# =============================================================================
# CLI — issue commands from your terminal
# =============================================================================

def cli():
    parser = argparse.ArgumentParser(
        description="Digital World Admin — command channel CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  kill <id>                    Hard-kill a specific Digimon (wipes .mon)
  kill-attr <Virus|Vaccine|Data>  Kill all Mons of an attribute
  shutdown <VM_ID|ALL>         Shut down a VM gracefully
  lockdown <VM_ID|ALL>         Freeze all Mons, revoke network access
  unlock <VM_ID|ALL>           Lift lockdown
  attack <from_VM> <to_VM>     Order from_VM to attack to_VM
  ceasefire <VM_ID|ALL>        Call off inter-VM attack
  quarantine <id>              Freeze a Mon in place (stays alive)
  recall <id> [biome]          Force a Mon to a safe biome
  god-veto <VM_ID|ALL>         Yggdrasil clears all pending actions
  status                       Show all active nodes and their state
  watch                        Live watch of node heartbeats
  history                      Show recent executed commands
        """,
    )
    parser.add_argument("command", help="Command to issue")
    parser.add_argument("args", nargs="*", help="Command arguments")
    parser.add_argument("--channel", default=ADMIN_CHANNEL_FILE,
                        help="Path to admin_channel.json")
    args = parser.parse_args()

    channel = AdminChannel(args.channel)
    cmd     = args.command.lower()
    a       = args.args

    if cmd == "status":
        _cmd_status(channel)

    elif cmd == "watch":
        _cmd_watch(channel)

    elif cmd == "history":
        _cmd_history(channel)

    elif cmd == "kill":
        if not a:
            print("Usage: admin.py kill <digimon_id>")
            sys.exit(1)
        channel.push(_make_command("KILL", target="ALL", digimon_id=a[0]))
        print(f"✓ KILL command issued for: {a[0]}")

    elif cmd == "kill-attr":
        if not a:
            print("Usage: admin.py kill-attr <Virus|Vaccine|Data>")
            sys.exit(1)
        channel.push(_make_command("KILL_ATTR", target="ALL", attribute=a[0]))
        print(f"✓ KILL_ATTR command issued for attribute: {a[0]}")

    elif cmd == "shutdown":
        target = a[0] if a else "ALL"
        channel.push(_make_command("SHUTDOWN", target=target))
        print(f"✓ SHUTDOWN issued → {target}")

    elif cmd == "lockdown":
        target = a[0] if a else "ALL"
        channel.push(_make_command("LOCKDOWN", target=target))
        print(f"✓ LOCKDOWN issued → {target}")

    elif cmd == "unlock":
        target = a[0] if a else "ALL"
        channel.push(_make_command("UNLOCK", target=target))
        print(f"✓ UNLOCK issued → {target}")

    elif cmd == "attack":
        if len(a) < 2:
            print("Usage: admin.py attack <from_VM> <target_VM>")
            sys.exit(1)
        channel.push(_make_command("ATTACK", target=a[0], target_vm=a[1]))
        print(f"✓ ATTACK issued: {a[0]} → {a[1]}")

    elif cmd == "ceasefire":
        target = a[0] if a else "ALL"
        channel.push(_make_command("CEASEFIRE", target=target))
        print(f"✓ CEASEFIRE issued → {target}")

    elif cmd == "quarantine":
        if not a:
            print("Usage: admin.py quarantine <digimon_id>")
            sys.exit(1)
        channel.push(_make_command("QUARANTINE", target="ALL", digimon_id=a[0]))
        print(f"✓ QUARANTINE issued for: {a[0]}")

    elif cmd == "recall":
        if not a:
            print("Usage: admin.py recall <digimon_id> [biome]")
            sys.exit(1)
        biome = a[1] if len(a) > 1 else "Grasslands"
        channel.push(_make_command("RECALL", target="ALL",
                                   digimon_id=a[0], biome=biome))
        print(f"✓ RECALL issued for {a[0]} → {biome}")

    elif cmd == "god-veto":
        target = a[0] if a else "ALL"
        channel.push(_make_command("GOD_VETO", target=target))
        print(f"✓ GOD_VETO issued → {target}")

    else:
        print(f"Unknown command: {cmd}")
        parser.print_help()
        sys.exit(1)


def _cmd_status(channel: AdminChannel):
    nodes = channel.get_nodes()
    if not nodes:
        print("No active nodes found.")
        return
    print(f"\n{'═'*60}")
    print(f"  DIGITAL WORLD — NODE STATUS  ({len(nodes)} nodes)")
    print(f"{'═'*60}")
    for vm_id, node in sorted(nodes.items()):
        seen     = node.get("last_seen", "?")[:19]
        tick     = node.get("tick", 0)
        pop      = node.get("population", 0)
        knights  = node.get("knights", 0)
        locked   = " [LOCKDOWN]"  if node.get("lockdown")    else ""
        attacked = " [UNDER ATTACK]" if node.get("under_attack") else ""
        print(f"  {vm_id:<10} tick:{tick:<6} pop:{pop:<4} "
              f"knights:{knights:<3} last:{seen}{locked}{attacked}")
    print(f"{'═'*60}\n")


def _cmd_watch(channel: AdminChannel):
    print("Watching nodes... (Ctrl+C to stop)")
    try:
        while True:
            os.system("cls" if os.name == "nt" else "clear")
            _cmd_status(channel)
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nWatch stopped.")


def _cmd_history(channel: AdminChannel):
    history = channel.get_history()
    if not history:
        print("No command history.")
        return
    print(f"\n{'═'*60}")
    print("  COMMAND HISTORY")
    print(f"{'═'*60}")
    for cmd in history[-20:]:
        t      = cmd.get("type", "?")
        issued = cmd.get("issued_at", "?")[:19]
        exby   = cmd.get("executed_by", "?")
        print(f"  {issued}  {t:<15}  executed by {exby}")
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    cli()
