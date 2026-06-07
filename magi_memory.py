"""
╔══════════════════════════════════════════════════════════════════╗
║               DIGITAL WORLD — MAGI MEMORY SYSTEM                ║
║                                                                  ║
║  Each MAGI seat holds an encrypted, compressed memory file.      ║
║  The holder writes to their own. All three can read each other.  ║
║                                                                  ║
║  Files:                                                          ║
║    solomon.magi   — Data seat memory                             ║
║    saladin.magi   — Virus seat memory                            ║
║    alfatih.magi   — Vaccine seat memory                          ║
║                                                                  ║
║  Encryption: AES-256-GCM                                         ║
║  Key derivation: PBKDF2-HMAC-SHA256, 480,000 iterations          ║
║  Compression: lzma (highest ratio)                               ║
║  Tamper detection: GCM authentication tag (built-in)             ║
║                                                                  ║
║  You hold the passphrase. Share it with Claude to inspect.       ║
║  Never stored. Salt is stored in file header (safe).             ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import json
import lzma
import hashlib
import secrets
import struct
import time
from datetime import datetime
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend


# ── File format constants ─────────────────────────────────────────────────────
#
# .magi file layout (all values little-endian):
#
#   [0:4]   magic      b"MAGI"
#   [4:5]   version    uint8 = 1
#   [5:6]   seat_id    uint8 (0=SOLOMON, 1=SALADIN, 2=AL-FATIH)
#   [6:38]  salt       32 random bytes (for PBKDF2)
#   [38:50] nonce      12 bytes (AES-GCM nonce, fresh each write)
#   [50:54] entry_count uint32 (total decisions ever recorded)
#   [54:]   ciphertext  AES-256-GCM encrypted + authenticated lzma payload
#
# The GCM authentication tag (16 bytes) is appended to the ciphertext
# automatically by AESGCM — tampering invalidates it immediately.

MAGIC       = b"MAGI"
VERSION     = 1
PBKDF2_ITER = 480_000   # NIST recommended minimum 2024 is 600k for SHA-256;
                         # we use 480k for startup speed, still extremely strong
SALT_LEN    = 32
NONCE_LEN   = 12

SEAT_IDS = {"SOLOMON": 0, "SALADIN": 1, "AL-FATIH": 2}
SEAT_NAMES = {v: k for k, v in SEAT_IDS.items()}

# How many entries to include in the cross-seat digest (keeps context tight)
DIGEST_ENTRIES = 30


# ── Memory schema ─────────────────────────────────────────────────────────────
#
# The plaintext payload (before compression + encryption) is a JSON dict:
#
# {
#   "seat":        "SOLOMON",
#   "created":     "ISO timestamp of first holder",
#   "lineage": [
#       {
#           "holder_name":   "Wisemon",        # birth name of the Digimon
#           "title":         "SOLOMON",         # always the seat title
#           "model":         "gpt-4o",
#           "took_seat_at":  "ISO timestamp",
#           "left_seat_at":  "ISO timestamp or null",
#           "reason":        "original | succession | challenge",
#           "reward_points": 4821,
#           "generation":    15,
#       },
#       ...
#   ],
#   "decisions": [
#       {
#           "tick":          1042,
#           "type":          "evolution",
#           "vote":          "APPROVE",
#           "reasoning":     "...",    # SUMMARISED, not raw
#           "confidence":    0.87,
#           "outcome":       null,     # filled in later if outcome known
#       },
#       ...
#   ],
#   "knowledge": [
#       {
#           "tick":    500,
#           "topic":   "CVE-2024-1234 buffer overflow pattern",
#           "insight": "compact 1-2 sentence essence",
#           "source":  "offensive_security",
#           "domain":  "saladin",     # which seat this came from
#       },
#       ...
#   ],
#   "digest": {
#       # Rolling summary updated on each write — this is what the other
#       # two seats read. Much smaller than the full knowledge list.
#       "last_updated": "ISO timestamp",
#       "key_insights":  ["...", "...", ...],   # top DIGEST_ENTRIES insights
#       "recent_votes":  ["...", "...", ...],   # last 20 decisions summarised
#       "personality_drift": "...",             # how this mind has evolved
#   },
#   "succession_record": [
#       {
#           "tick":         8000,
#           "challenger":   "Darkdramon",
#           "outcome":      "SUCCESS | FAILURE",
#           "method":       "deliberation | brawl",
#           "reward_points_at_challenge": 12400,
#       },
#       ...
#   ],
# }


class MagiMemory:
    """
    Encrypted, compressed persistent memory for a single MAGI seat.

    One instance per seat per process. The holder writes;
    all three seats can read each other via read_digest().
    """

    def __init__(self, seat: str, memory_dir: str = "magi_memory"):
        self.seat       = seat
        self.seat_id    = SEAT_IDS[seat]
        self.memory_dir = memory_dir
        self.path       = os.path.join(memory_dir, f"{seat.lower().replace('-','_')}.magi")
        self._key: Optional[bytes] = None      # derived from passphrase, held in RAM only
        self._data: Optional[dict] = None      # decrypted payload in RAM

        os.makedirs(memory_dir, exist_ok=True)

    # ── Key management ────────────────────────────────────────────────────────

    def unlock(self, passphrase: str) -> bool:
        """
        Derive the AES key from the passphrase and load (or create) the memory file.
        Returns True if successful, False if file exists but passphrase is wrong.
        """
        if os.path.exists(self.path):
            salt = self._read_salt()
        else:
            salt = secrets.token_bytes(SALT_LEN)

        self._key = self._derive_key(passphrase, salt)

        if os.path.exists(self.path):
            try:
                self._data = self._load()
                return True
            except Exception:
                self._key  = None
                self._data = None
                return False
        else:
            # First time — create fresh memory
            self._data = self._empty_memory()
            self._save(salt)
            return True

    def lock(self):
        """Wipe the key and decrypted data from RAM."""
        self._key  = None
        self._data = None

    def is_unlocked(self) -> bool:
        return self._key is not None and self._data is not None

    def _derive_key(self, passphrase: str, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=PBKDF2_ITER,
            backend=default_backend(),
        )
        return kdf.derive(passphrase.encode("utf-8"))

    # ── Read ──────────────────────────────────────────────────────────────────

    def _read_salt(self) -> bytes:
        with open(self.path, "rb") as f:
            header = f.read(6 + SALT_LEN)
        assert header[:4] == MAGIC, "Not a .magi file"
        return header[6:6 + SALT_LEN]

    def _load(self) -> dict:
        with open(self.path, "rb") as f:
            raw = f.read()

        assert raw[:4] == MAGIC,   "Invalid magic bytes"
        assert raw[4]  == VERSION, "Unsupported version"

        salt       = raw[6:6 + SALT_LEN]
        nonce      = raw[6 + SALT_LEN : 6 + SALT_LEN + NONCE_LEN]
        ciphertext = raw[6 + SALT_LEN + NONCE_LEN + 4:]  # skip entry_count too

        aesgcm    = AESGCM(self._key)
        compressed = aesgcm.decrypt(nonce, ciphertext, None)  # raises on tamper
        return json.loads(lzma.decompress(compressed).decode("utf-8"))

    def read_digest(self, passphrase: str) -> Optional[dict]:
        """
        Read just the digest section of any .magi file without fully unlocking it.
        Used by the other two seats to get cross-seat intelligence.
        """
        if not os.path.exists(self.path):
            return None
        try:
            salt = self._read_salt()
            key  = self._derive_key(passphrase, salt)

            with open(self.path, "rb") as f:
                raw = f.read()

            nonce      = raw[6 + SALT_LEN : 6 + SALT_LEN + NONCE_LEN]
            ciphertext = raw[6 + SALT_LEN + NONCE_LEN + 4:]
            aesgcm     = AESGCM(key)
            compressed = aesgcm.decrypt(nonce, ciphertext, None)
            data       = json.loads(lzma.decompress(compressed).decode("utf-8"))
            return data.get("digest", {})
        except Exception:
            return None

    # ── Write ─────────────────────────────────────────────────────────────────

    def _save(self, salt: bytes = None):
        assert self._key and self._data, "Memory not unlocked"

        if salt is None:
            salt = self._read_salt()

        # Update digest before saving
        self._update_digest()

        payload    = json.dumps(self._data, ensure_ascii=False, separators=(",", ":"))
        compressed = lzma.compress(payload.encode("utf-8"), preset=9)

        nonce       = secrets.token_bytes(NONCE_LEN)
        aesgcm      = AESGCM(self._key)
        ciphertext  = aesgcm.encrypt(nonce, compressed, None)

        entry_count = len(self._data.get("decisions", []))

        with open(self.path, "wb") as f:
            f.write(MAGIC)
            f.write(bytes([VERSION, self.seat_id]))
            f.write(salt)
            f.write(nonce)
            f.write(struct.pack("<I", entry_count))
            f.write(ciphertext)

    def _update_digest(self):
        """Rebuild the rolling digest from current knowledge and decisions."""
        knowledge = self._data.get("knowledge", [])
        decisions = self._data.get("decisions", [])
        lineage   = self._data.get("lineage",   [])

        # Key insights — most recent DIGEST_ENTRIES from knowledge
        key_insights = [
            f"[{k.get('domain','?')}] {k.get('insight','')}"
            for k in knowledge[-DIGEST_ENTRIES:]
        ]

        # Recent votes — last 20 decisions as compact strings
        recent_votes = [
            f"tick{d.get('tick',0)} {d.get('type','?')} → {d.get('vote','?')} ({d.get('reasoning','')[:60]})"
            for d in decisions[-20:]
        ]

        # Personality drift — summarise how the current holder differs from the first
        current = lineage[-1] if lineage else {}
        first   = lineage[0]  if lineage else {}
        drift   = (
            f"Current holder: {current.get('holder_name','?')}, "
            f"generation {current.get('generation',1)}. "
            f"Seat held since {first.get('took_seat_at','?')[:10]}. "
            f"{len(lineage)} holder(s) total."
        )

        self._data["digest"] = {
            "seat":              self.seat,
            "last_updated":      datetime.utcnow().isoformat(),
            "total_decisions":   len(decisions),
            "total_knowledge":   len(knowledge),
            "key_insights":      key_insights,
            "recent_votes":      recent_votes,
            "personality_drift": drift,
        }

    # ── Public write API ──────────────────────────────────────────────────────

    def record_decision(self, tick: int, decision_type: str, vote: str,
                        reasoning: str, confidence: float, outcome: str = None):
        """Append a decision to memory. Summarised — not raw verbose output."""
        assert self.is_unlocked()
        self._data["decisions"].append({
            "tick":       tick,
            "type":       decision_type,
            "vote":       vote,
            "reasoning":  reasoning[:300],   # hard cap — keep it lean
            "confidence": round(confidence, 2),
            "outcome":    outcome,
            "recorded":   datetime.utcnow().isoformat(),
        })
        # Auto-save every 50 decisions to avoid data loss
        if len(self._data["decisions"]) % 50 == 0:
            self._save()

    def record_knowledge(self, tick: int, topic: str, insight: str,
                         source: str, domain: str = None):
        """Append a knowledge entry — extracted insight, not raw data."""
        assert self.is_unlocked()
        self._data["knowledge"].append({
            "tick":    tick,
            "topic":   topic[:150],
            "insight": insight[:400],
            "source":  source,
            "domain":  domain or self.seat.lower(),
            "recorded": datetime.utcnow().isoformat(),
        })

    def record_succession(self, tick: int, challenger_name: str,
                          outcome: str, method: str, reward_points: int):
        """Record a succession attempt against this seat."""
        assert self.is_unlocked()
        self._data["succession_record"].append({
            "tick":                       tick,
            "challenger":                 challenger_name,
            "outcome":                    outcome,
            "method":                     method,
            "reward_points_at_challenge": reward_points,
            "recorded":                   datetime.utcnow().isoformat(),
        })

    def set_holder(self, holder_name: str, model: str, tick: int,
                   reason: str = "original", reward_points: int = 0,
                   generation: int = 1):
        """
        Record a new holder taking the seat.
        The previous holder's left_seat_at is filled in automatically.
        """
        assert self.is_unlocked()
        lineage = self._data["lineage"]
        if lineage:
            lineage[-1]["left_seat_at"] = datetime.utcnow().isoformat()
        lineage.append({
            "holder_name":   holder_name,
            "title":         self.seat,
            "model":         model,
            "took_seat_at":  datetime.utcnow().isoformat(),
            "left_seat_at":  None,
            "reason":        reason,
            "reward_points": reward_points,
            "generation":    generation,
            "tick":          tick,
        })
        self._save()

    def flush(self):
        """Force write to disk."""
        if self.is_unlocked():
            self._save()

    # ── Query API (for loading into MAGI context) ─────────────────────────────

    def get_context_for_decision(self, decision_type: str,
                                 recent_n: int = 20) -> dict:
        """
        Return a compact context dict to inject into a MAGI mind's prompt.
        Keeps token count low while giving the mind its full memory.
        """
        assert self.is_unlocked()
        lineage   = self._data.get("lineage",   [])
        knowledge = self._data.get("knowledge", [])
        decisions = self._data.get("decisions", [])

        # Filter decisions by type for relevance
        relevant  = [d for d in decisions if d["type"] == decision_type][-10:]
        recent_k  = knowledge[-recent_n:]

        current_holder = lineage[-1] if lineage else {}

        return {
            "seat":             self.seat,
            "current_holder":   current_holder.get("holder_name", "Unknown"),
            "holders_count":    len(lineage),
            "total_decisions":  len(decisions),
            "relevant_past_decisions": [
                f"tick{d['tick']}: {d['vote']} — {d['reasoning'][:80]}"
                for d in relevant
            ],
            "recent_knowledge": [
                f"[{k['source']}] {k['insight'][:100]}"
                for k in recent_k
            ],
        }

    def get_file_stats(self) -> dict:
        """Return file size and entry counts without decrypting."""
        if not os.path.exists(self.path):
            return {"exists": False}
        size = os.path.getsize(self.path)
        # Read entry count from header (plaintext)
        with open(self.path, "rb") as f:
            f.seek(6 + SALT_LEN + NONCE_LEN)
            raw_count = f.read(4)
        count = struct.unpack("<I", raw_count)[0] if len(raw_count) == 4 else 0
        return {
            "exists":        True,
            "size_bytes":    size,
            "size_kb":       round(size / 1024, 1),
            "entry_count":   count,
            "path":          self.path,
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _empty_memory(self) -> dict:
        return {
            "seat":              self.seat,
            "created":           datetime.utcnow().isoformat(),
            "lineage":           [],
            "decisions":         [],
            "knowledge":         [],
            "succession_record": [],
            "digest":            {},
        }


# ── Shared memory manager (all three seats) ───────────────────────────────────

class MagiMemoryVault:
    """
    Manages all three MAGI memory files together.
    Provides cross-seat reading so each mind can access the others' digests.

    One instance lives inside MagiCouncil.
    """

    def __init__(self, memory_dir: str = "magi_memory"):
        self.memories = {
            seat: MagiMemory(seat, memory_dir)
            for seat in ("SOLOMON", "SALADIN", "AL-FATIH")
        }
        self._passphrase: Optional[str] = None

    def unlock_all(self, passphrase: str) -> dict:
        """
        Unlock all three memory files.
        Returns dict of {seat: success_bool}.
        """
        self._passphrase = passphrase
        results = {}
        for seat, mem in self.memories.items():
            results[seat] = mem.unlock(passphrase)
        return results

    def lock_all(self):
        for mem in self.memories.values():
            mem.lock()
        self._passphrase = None

    def flush_all(self):
        for mem in self.memories.values():
            mem.flush()

    def get_cross_seat_context(self, requesting_seat: str) -> dict:
        """
        Build the cross-seat intelligence brief for a MAGI mind.
        The requesting seat gets digests from the other two.
        """
        context = {}
        for seat, mem in self.memories.items():
            if seat == requesting_seat:
                continue
            if mem.is_unlocked():
                context[seat] = mem.get_context_for_decision("any", recent_n=15)
            elif self._passphrase:
                # Read just the digest without full unlock
                digest = MagiMemory(seat, mem.memory_dir).read_digest(self._passphrase)
                context[seat] = {"digest": digest} if digest else {}
        return context

    def record_decision_all(self, seat: str, tick: int, decision_type: str,
                             vote: str, reasoning: str, confidence: float):
        """Record a decision to the appropriate seat memory."""
        mem = self.memories.get(seat)
        if mem and mem.is_unlocked():
            mem.record_decision(tick, decision_type, vote, reasoning, confidence)

    def record_knowledge(self, seat: str, tick: int, topic: str,
                         insight: str, source: str):
        """Record a knowledge entry to the appropriate seat memory."""
        mem = self.memories.get(seat)
        if mem and mem.is_unlocked():
            mem.record_knowledge(tick, topic, insight, source, domain=seat.lower())

    def set_holder(self, seat: str, holder_name: str, model: str,
                   tick: int, reason: str = "original",
                   reward_points: int = 0, generation: int = 1):
        mem = self.memories.get(seat)
        if mem and mem.is_unlocked():
            mem.set_holder(holder_name, model, tick, reason, reward_points, generation)

    def get_vault_status(self) -> dict:
        return {
            seat: mem.get_file_stats()
            for seat, mem in self.memories.items()
        }
