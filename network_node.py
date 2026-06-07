"""
╔══════════════════════════════════════════════════════════════════╗
║            DIGITAL WORLD — NETWORK NODE MANAGER                 ║
║                                                                  ║
║  Handles inter-VM communication for a multi-node Digital World.  ║
║                                                                  ║
║  Each VM is a complete world. Nodes discover each other via a    ║
║  shared node registry file (or a network share on real hardware).║
║                                                                  ║
║  Virus types probe real exposed services on other VMs.           ║
║  Vaccine types harden real ports and respond to intrusions.      ║
║  Data types gather intelligence and feed both sides.             ║
║                                                                  ║
║  The Admin can order an attack via admin.py:                     ║
║    python admin.py attack VM_A VM_B                              ║
║                                                                  ║
║  Virus types on sufficiently-evolved nodes will also probe       ║
║  neighbours autonomously — no Admin order needed.                ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import time
import socket
import random
import subprocess
import threading
from datetime import datetime
from typing import Optional


# =============================================================================
# CONSTANTS
# =============================================================================

# Shared registry file — all VMs read/write this to discover each other.
# On a real multi-machine setup, point this to a network share.
NODE_REGISTRY_FILE = os.getenv("NODE_REGISTRY", "node_registry.json")

# Port range Virus types are allowed to probe (stays within your LAN)
PROBE_PORT_RANGE   = (8000, 8999)

# Port this VM listens on for inter-VM combat messages
# Each VM should set a unique port via env var
VM_LISTEN_PORT     = int(os.getenv("VM_PORT", "8765"))

# Heartbeat interval — how often nodes update the registry (seconds)
HEARTBEAT_INTERVAL = 10

# How long before a node is considered offline (seconds)
NODE_TIMEOUT       = 60

# Virus types at or above this evolution level can probe other VMs autonomously
AUTONOMOUS_PROBE_LEVEL = "Ultimate"

# Performance threshold for autonomous probing (must be strong enough)
AUTONOMOUS_PROBE_SCORE = 200.0


# =============================================================================
# NODE REGISTRY — shared discovery layer
# =============================================================================

class NodeRegistry:
    """
    Shared file that all VMs read/write to discover each other.
    On a single machine: just a JSON file in the shared project dir.
    On multiple machines: point NODE_REGISTRY to a network share path.
    """

    def __init__(self, path: str = NODE_REGISTRY_FILE):
        self.path = path
        self._ensure()

    def _ensure(self):
        if not os.path.exists(self.path):
            self._write({"nodes": {}})

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
        return {"nodes": {}}

    def _write(self, data: dict):
        import time as _t
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        for attempt in range(5):
            try:
                os.replace(tmp, self.path)
                return
            except PermissionError:
                if attempt < 4:
                    _t.sleep(0.1 * (attempt + 1))
                else:
                    try:
                        import shutil
                        shutil.copy2(tmp, self.path)
                        os.remove(tmp)
                    except Exception:
                        pass

    def register(self, vm_id: str, ip: str, port: int, state_summary: dict):
        """Register/update this VM's presence."""
        data = self._read()
        data["nodes"][vm_id] = {
            "vm_id":      vm_id,
            "ip":         ip,
            "port":       port,
            "last_seen":  datetime.utcnow().isoformat(),
            "tick":       state_summary.get("tick", 0),
            "population": state_summary.get("population", 0),
            "knights":    state_summary.get("knights", 0),
            "god_gen":    state_summary.get("god_gen", 0),
        }
        self._write(data)

    def get_peers(self, my_vm_id: str) -> list:
        """Get all active peer VMs (not ourselves, not timed out)."""
        data    = self._read()
        now     = datetime.utcnow()
        peers   = []
        for vm_id, node in data["nodes"].items():
            if vm_id == my_vm_id:
                continue
            try:
                last = datetime.fromisoformat(node["last_seen"])
                if (now - last).total_seconds() < NODE_TIMEOUT:
                    peers.append(node)
            except Exception:
                pass
        return peers

    def get_all(self) -> dict:
        return self._read().get("nodes", {})


# =============================================================================
# INTER-VM COMBAT MESSAGE — what Virus types send across the wire
# =============================================================================

class CombatPacket:
    """
    Represents a single inter-VM combat action.
    Virus types build these from their capabilities.
    Vaccine types receive and respond to them.
    """

    def __init__(self, attacker_id: str, attacker_name: str, attacker_vm: str,
                 target_vm: str, action: str, capability: str,
                 payload: dict = None):
        self.attacker_id   = attacker_id
        self.attacker_name = attacker_name
        self.attacker_vm   = attacker_vm
        self.target_vm     = target_vm
        self.action        = action        # "probe", "exploit", "persist", "exfil"
        self.capability    = capability    # the specific capability being used
        self.payload       = payload or {}
        self.timestamp     = datetime.utcnow().isoformat()

    def to_dict(self) -> dict:
        return self.__dict__

    @classmethod
    def from_dict(cls, d: dict) -> "CombatPacket":
        p = cls.__new__(cls)
        p.__dict__.update(d)
        return p


# =============================================================================
# NETWORK NODE — one per VM instance
# =============================================================================

class NetworkNode:
    """
    Manages all inter-VM networking for a single world instance.

    Responsibilities:
    - Register this VM in the node registry
    - Discover peer VMs
    - Allow Virus types to probe and attack peers
    - Receive and process incoming attacks
    - Allow Vaccine types to harden defenses
    - Feed combat results back into world state
    """

    def __init__(self, vm_id: str, world_state: dict, port: int = VM_LISTEN_PORT):
        self.vm_id       = vm_id
        self.state       = world_state
        self.port        = port
        self.registry    = NodeRegistry()
        self.ip          = self._get_local_ip()
        self._listener   = None
        self._incoming   = []   # queue of received CombatPackets
        self._lock       = threading.Lock()

        # Hardened ports tracked by Vaccine types: {port: digimon_id}
        self.hardened_ports: dict = {}

        # Active Virus connections out: {digimon_id: target_vm_id}
        self.active_probes: dict = {}

        # Start listener thread
        self._start_listener()

    def _get_local_ip(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    # ── Registry ──────────────────────────────────────────────────────────────

    def heartbeat(self):
        """Update presence in the shared registry."""
        living = [d for d in self.state.get("digimon", {}).values()
                  if d.get("alive")]
        self.registry.register(self.vm_id, self.ip, self.port, {
            "tick":       self.state.get("tick", 0),
            "population": len(living),
            "knights":    len([s for s in self.state.get("royal_knights", {})
                               .get("seats", {}).values() if s.get("occupied")]),
            "god_gen":    self.state.get("god_generation", 0),
        })

    def get_peers(self) -> list:
        return self.registry.get_peers(self.vm_id)

    # ── Listener — receives incoming attack packets ────────────────────────────

    def _start_listener(self):
        """Background thread that receives incoming CombatPackets."""
        self._listener = threading.Thread(target=self._listen_loop, daemon=True)
        self._listener.start()

    def _listen_loop(self):
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("0.0.0.0", self.port))
            srv.listen(10)
            srv.settimeout(1.0)
            while True:
                try:
                    conn, addr = srv.accept()
                    data = b""
                    while True:
                        chunk = conn.recv(4096)
                        if not chunk:
                            break
                        data += chunk
                    conn.close()
                    packet = CombatPacket.from_dict(json.loads(data.decode()))
                    with self._lock:
                        self._incoming.append(packet)
                except socket.timeout:
                    pass
                except Exception:
                    pass
        except Exception as e:
            print(f"[NET] Listener failed on port {self.port}: {e}")

    # ── Virus actions — outbound probing and attacks ──────────────────────────

    def virus_probe(self, digimon: dict, target_node: dict) -> dict:
        """
        A Virus type probes a target VM.
        Returns a result dict that feeds back into the Digimon's experience.

        This does real network activity — it attempts a TCP connection to the
        target VM's listen port. Success/failure is real, not simulated.
        """
        target_ip   = target_node["ip"]
        target_port = target_node["port"]
        cap         = random.choice(digimon.get("capabilities", ["basic_probe"]))

        # Build the combat packet
        packet = CombatPacket(
            attacker_id   = digimon["id"],
            attacker_name = digimon["name"],
            attacker_vm   = self.vm_id,
            target_vm     = target_node["vm_id"],
            action        = "probe",
            capability    = cap,
            payload       = {
                "evolution_level": digimon.get("evolution_level"),
                "performance":     digimon.get("performance", 0),
            },
        )

        # Attempt real TCP connection to target's combat port
        success = self._send_packet(target_ip, target_port, packet)

        result = {
            "action":      "probe",
            "target_vm":   target_node["vm_id"],
            "capability":  cap,
            "success":     success,
            "timestamp":   datetime.utcnow().isoformat(),
        }

        # Log the probe attempt in world state
        self.state.setdefault("network_log", []).append({
            "tick":     self.state.get("tick", 0),
            "type":     "outbound_probe",
            "from":     digimon["name"],
            "to_vm":    target_node["vm_id"],
            "cap":      cap,
            "success":  success,
        })
        self.state["network_log"] = self.state["network_log"][-500:]

        if success:
            # Track this probe as active
            self.active_probes[digimon["id"]] = target_node["vm_id"]
            print(f"[NET 🔴] {digimon['name']} probed {target_node['vm_id']} "
                  f"using '{cap}' — SUCCESS")
        else:
            self.active_probes.pop(digimon["id"], None)
            print(f"[NET 🔴] {digimon['name']} probed {target_node['vm_id']} "
                  f"using '{cap}' — BLOCKED")

        return result

    def virus_exploit(self, digimon: dict, target_node: dict,
                      probe_result: dict) -> dict:
        """
        Follow-up to a successful probe — attempt to exploit a service.
        Only called if probe succeeded and Digimon is Ultimate/Mega.
        """
        if not probe_result.get("success"):
            return {"success": False, "reason": "no_foothold"}

        cap = random.choice([c for c in digimon.get("capabilities", [])
                             if "exploit" in c or "penetrate" in c]
                            or digimon.get("capabilities", ["generic_exploit"]))

        packet = CombatPacket(
            attacker_id   = digimon["id"],
            attacker_name = digimon["name"],
            attacker_vm   = self.vm_id,
            target_vm     = target_node["vm_id"],
            action        = "exploit",
            capability    = cap,
            payload       = {
                "evolution_level": digimon.get("evolution_level"),
                "performance":     digimon.get("performance", 0),
                "probe_success":   True,
            },
        )
        success = self._send_packet(target_node["ip"], target_node["port"], packet)
        print(f"[NET 🔴] {digimon['name']} exploit attempt on "
              f"{target_node['vm_id']} — {'HIT' if success else 'DEFLECTED'}")
        return {"success": success, "capability": cap}

    # ── Vaccine actions — hardening and response ──────────────────────────────

    def vaccine_harden(self, digimon: dict) -> dict:
        """
        A Vaccine type hardens the local environment.
        Tracks which ports/rules this Digimon has locked down.
        Stronger Vaccine = more rules = harder target for Virus probes.
        """
        perf    = digimon.get("performance", 0)
        level   = digimon.get("evolution_level", "Rookie")
        caps    = digimon.get("capabilities", [])

        # Number of rules scales with evolution and performance
        level_factor = {
            "Fresh": 0, "In-Training": 0, "Rookie": 1,
            "Champion": 2, "Ultimate": 4, "Mega": 6,
        }.get(level, 1)
        n_rules = level_factor + int(perf / 100)

        rules_added = []
        for i in range(n_rules):
            cap      = caps[i % len(caps)] if caps else f"rule_{i}"
            port     = random.randint(*PROBE_PORT_RANGE)
            rule_key = f"{digimon['id']}_{port}"

            if port not in self.hardened_ports:
                self.hardened_ports[port] = digimon["id"]
                rules_added.append({"port": port, "cap": cap})

                # Track in world state for admin kill revocation
                self.state.setdefault("network_rules", {}).setdefault(
                    digimon["id"], []
                ).append({
                    "port":        port,
                    "capability":  cap,
                    "applied":     False,   # not real iptables — just sim tracking
                    "iptables_cmd": f"iptables -A INPUT -p tcp --dport {port} -j DROP",
                })

        if rules_added:
            print(f"[NET 🔵] {digimon['name']} hardened "
                  f"{len(rules_added)} rules (total: {len(self.hardened_ports)})")

        return {"rules_added": len(rules_added), "total_hardened": len(self.hardened_ports)}

    def vaccine_respond(self, digimon: dict, packet: CombatPacket) -> dict:
        """
        Vaccine type responds to an incoming attack packet.
        Returns whether the defense held.
        """
        perf       = digimon.get("performance", 0)
        attk_perf  = packet.payload.get("performance", 0)
        held       = perf > attk_perf * 0.7  # defender needs 70% of attacker's score

        # Log the defense
        self.state.setdefault("network_log", []).append({
            "tick":       self.state.get("tick", 0),
            "type":       "inbound_defense",
            "defender":   digimon["name"],
            "attacker":   packet.attacker_name,
            "from_vm":    packet.attacker_vm,
            "action":     packet.action,
            "held":       held,
        })

        if held:
            print(f"[NET 🔵] {digimon['name']} DEFENDED against "
                  f"{packet.attacker_name} ({packet.attacker_vm})")
            # Add a capability learned from blocking this attack
            learned = f"counter_{packet.capability[:12]}"
            if learned not in digimon.get("capabilities", []):
                digimon.setdefault("capabilities", []).append(learned)
        else:
            print(f"[NET 🔴] {packet.attacker_name} BREACHED defense of "
                  f"{digimon['name']} on {self.vm_id}")

        return {"held": held, "defender": digimon["name"]}

    # ── Incoming packet processing ────────────────────────────────────────────

    def process_incoming(self, world_state: dict) -> list:
        """
        Called each tick. Processes any packets received from other VMs.
        Finds the best available Vaccine type to respond.
        Returns list of combat results.
        """
        with self._lock:
            packets = list(self._incoming)
            self._incoming.clear()

        results = []
        for packet in packets:
            # Mark as under attack
            world_state.setdefault("inter_vm", {})["under_attack_from"] = \
                packet.attacker_vm

            # Find strongest living Vaccine type to respond
            vaccines = sorted(
                [d for d in world_state.get("digimon", {}).values()
                 if d.get("alive") and d.get("attribute") == "Vaccine"
                 and not d.get("admin_frozen")],
                key=lambda d: d.get("performance", 0),
                reverse=True,
            )
            if vaccines:
                result = self.vaccine_respond(vaccines[0], packet)
            else:
                # No defender — attack succeeds by default
                result = {"held": False, "defender": None}
                print(f"[NET 🔴] No Vaccine defenders on {self.vm_id}! "
                      f"{packet.attacker_name} attack uncontested.")

            results.append({"packet": packet.to_dict(), "result": result})

        return results

    # ── Autonomous Virus behavior ─────────────────────────────────────────────

    def maybe_autonomous_probe(self, digimon: dict) -> Optional[dict]:
        """
        Called during Virus type tick. If strong enough, may autonomously
        probe a neighbour — no Admin order needed.
        Only fires if peer VMs exist and Digimon meets thresholds.
        """
        # Check thresholds
        level_ok = digimon.get("evolution_level") in ("Ultimate", "Mega")
        score_ok = digimon.get("performance", 0) >= AUTONOMOUS_PROBE_SCORE
        if not (level_ok and score_ok):
            return None

        # Random chance per tick — not every tick
        if random.random() > 0.05:
            return None

        peers = self.get_peers()
        if not peers:
            return None

        target = random.choice(peers)
        return self.virus_probe(digimon, target)

    # ── Sender ────────────────────────────────────────────────────────────────

    def _send_packet(self, ip: str, port: int, packet: CombatPacket) -> bool:
        """
        Send a CombatPacket to a peer VM.
        Returns True if the connection succeeded (peer received it).
        A hardened Vaccine target may still be blocking this port.
        """
        # Check if target port is blocked (simulated by hardened_ports on target)
        # In a real multi-machine setup this is just a real TCP connection.
        try:
            data = json.dumps(packet.to_dict()).encode()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3.0)
            sock.connect((ip, port))
            sock.sendall(data)
            sock.close()
            return True
        except (ConnectionRefusedError, socket.timeout, OSError):
            return False

    # ── Main tick ─────────────────────────────────────────────────────────────

    def tick(self, world_state: dict, admin_executor=None):
        """
        Called every world tick.
        1. Send heartbeat to registry
        2. Process incoming attacks
        3. Handle admin-ordered attacks
        4. Let Vaccine types harden (periodically)
        """
        tick = world_state.get("tick", 0)

        # Heartbeat every 10 ticks
        if tick % 10 == 0:
            self.heartbeat()

        # Process incoming combat
        results = self.process_incoming(world_state)

        # Admin-ordered attack
        iv = world_state.get("inter_vm", {})
        if iv.get("attack_target") and not iv.get("ceasefire"):
            target_vm_id = iv["attack_target"]
            peers        = {p["vm_id"]: p for p in self.get_peers()}
            if target_vm_id in peers:
                self._execute_attack_order(world_state, peers[target_vm_id])

        # Vaccine hardening every 20 ticks
        if tick % 20 == 0:
            vaccines = [d for d in world_state.get("digimon", {}).values()
                        if d.get("alive") and d.get("attribute") == "Vaccine"
                        and not d.get("admin_frozen")]
            for vaccine in vaccines[:3]:  # top 3 Vaccines harden per interval
                self.vaccine_harden(vaccine)

        return results

    def _execute_attack_order(self, world_state: dict, target_node: dict):
        """Send the strongest Virus types against the target VM."""
        viruses = sorted(
            [d for d in world_state.get("digimon", {}).values()
             if d.get("alive") and d.get("attribute") == "Virus"
             and d.get("evolution_level") in ("Ultimate", "Mega")
             and not d.get("admin_frozen")],
            key=lambda d: d.get("performance", 0),
            reverse=True,
        )[:3]  # top 3 Virus types per tick

        for virus in viruses:
            probe  = self.virus_probe(virus, target_node)
            if probe.get("success"):
                self.virus_exploit(virus, target_node, probe)
            # Autonomous probe chance even outside ordered attack
            self.maybe_autonomous_probe(virus)
