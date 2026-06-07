"""
╔══════════════════════════════════════════════════════════════════╗
║          DIGITAL WORLD — DATA TYPE RESEARCH REWARDS             ║
║                                                                  ║
║  Data types are rewarded for PRODUCING knowledge, not just       ║
║  consuming it. This module handles:                              ║
║                                                                  ║
║  1. Novel insight generation — Data Digimon analyse KB entries   ║
║     and attempt to synthesise something new. If the insight      ║
║     is genuinely novel (not already in the KB), they get points. ║
║                                                                  ║
║  2. Unsolved topic research — topics with few/no solutions in    ║
║     the KB get a bonus multiplier. Finding answers to things     ║
║     nobody has answered yet is worth more.                       ║
║                                                                  ║
║  3. Teaching — if another Digimon learns a capability that       ║
║     originated from this Data type, the teacher gets points.    ║
║                                                                  ║
║  Research is triggered probabilistically each tick for           ║
║  sufficiently evolved Data types (Champion and above).           ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import json
import random
import hashlib
from datetime import datetime
from typing import Optional


# Research probability per tick by evolution level
RESEARCH_PROB = {
    "Champion": 0.08,
    "Ultimate":  0.15,
    "Mega":      0.25,
}

# Minimum KB entries on a topic before it's considered "solved"
UNSOLVED_THRESHOLD = 3

# How many KB entries to sample for synthesis context
SYNTHESIS_CONTEXT_SIZE = 5

# Reward multiplier for genuinely unsolved topics
UNSOLVED_MULTIPLIER = 2.0

# Similarity threshold — below this cosine-ish score, insight is "novel"
# We use a simple keyword overlap check since we have no embeddings
NOVELTY_THRESHOLD = 0.35


class DataResearchEngine:
    """
    Drives research behaviour for Data-type Digimon.
    Called each tick by world.py for every living Data-type Champion+.
    """

    def __init__(self, world_state: dict, knowledge_base, reward_system,
                 llm_client=None, llm_model: str = "gpt-4o-mini"):
        self.state   = world_state
        self.kb      = knowledge_base
        self.rewards = reward_system
        self.client  = llm_client
        self.model   = llm_model

        # Research log — tracks what each Digimon has researched
        self.state.setdefault("research_log", [])
        # Capability origin tracking — {capability_string: digimon_id}
        self.state.setdefault("capability_origins", {})

    def tick_research(self, digimon: dict) -> Optional[dict]:
        """
        Called each tick for a Data-type Digimon.
        Returns a research result dict if research occurred, else None.
        """
        if digimon.get("attribute") != "Data":
            return None
        if not digimon.get("alive"):
            return None

        level = digimon.get("evolution_level", "Fresh")
        prob  = RESEARCH_PROB.get(level, 0.0)
        if prob == 0.0 or random.random() > prob:
            return None

        return self._attempt_research(digimon)

    def _attempt_research(self, digimon: dict) -> Optional[dict]:
        """
        The Digimon samples from the KB and attempts to synthesise a novel insight.
        """
        did      = digimon["id"]
        biome    = digimon.get("biome", "Forest")
        caps     = digimon.get("capabilities", [])

        # Get KB entries from the Digimon's home biome domains
        entries = self.kb.query_for_biome(biome, limit=SYNTHESIS_CONTEXT_SIZE)
        if not entries:
            # Fallback to attribute-aligned domains
            entries = self.kb.query_for_attribute("Data", limit=SYNTHESIS_CONTEXT_SIZE)
        if not entries:
            return None

        # Pick a topic to research
        topic_entry = random.choice(entries)
        topic       = topic_entry.get("topic") or topic_entry.get("title", "unknown")
        domain      = topic_entry.get("source", "general")

        # Check if this topic is "unsolved" in the KB
        existing = self._count_kb_entries_on_topic(topic)
        is_unsolved = existing < UNSOLVED_THRESHOLD

        # Generate an insight via LLM (or fallback to template)
        insight = self._synthesise_insight(digimon, topic, entries, caps)
        if not insight:
            return None

        # Check novelty — is this genuinely new?
        is_novel = self._check_novelty(insight, topic)
        if not is_novel:
            return None

        # It's novel — record it in the KB
        self.kb.record_knowledge_from_digimon(
            digimon_id   = did,
            digimon_name = digimon["name"],
            topic        = topic,
            insight      = insight,
            source       = f"digimon_research:{digimon['name']}",
            domain       = "data_generated",
        )

        # Grant rewards
        multiplier = UNSOLVED_MULTIPLIER if is_unsolved else 1.0
        reward_type = "data_unsolved_research" if is_unsolved else "data_novel_insight"
        pts = self.rewards.grant(
            did, reward_type, multiplier=multiplier,
            note=f"researched: {topic[:40]}"
        )

        # Derive a new capability from the research
        new_cap = self._derive_research_capability(topic, insight)
        if new_cap and new_cap not in caps:
            digimon.setdefault("capabilities", []).append(new_cap)
            # Track origin for teaching rewards
            self.state["capability_origins"][new_cap] = did

        # Log it
        result = {
            "tick":       self.state.get("tick", 0),
            "digimon_id": did,
            "name":       digimon["name"],
            "topic":      topic,
            "insight":    insight[:200],
            "domain":     domain,
            "is_unsolved": is_unsolved,
            "is_novel":   is_novel,
            "reward_pts": pts,
            "new_cap":    new_cap,
        }
        self.state["research_log"].append(result)
        self.state["research_log"] = self.state["research_log"][-1000:]

        print(f"[RESEARCH] {digimon['name']} synthesised: '{topic[:35]}...' "
              f"(+{pts} pts{" UNSOLVED" if is_unsolved else ""})")
        return result

    def check_teaching_rewards(self, learner: dict, new_capability: str):
        """
        Called when any Digimon learns a new capability.
        If the capability originated from a Data-type researcher, they get teaching pts.
        """
        origin_id = self.state["capability_origins"].get(new_capability)
        if not origin_id or origin_id == learner.get("id"):
            return

        origin = self.state["digimon"].get(origin_id)
        if not origin or not origin.get("alive"):
            return

        self.rewards.grant(
            origin_id, "data_taught_capability",
            note=f"taught {new_capability[:20]} to {learner.get('name','?')}"
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _count_kb_entries_on_topic(self, topic: str) -> int:
        """Count existing KB entries on this topic (rough keyword match)."""
        topic_words = set(topic.lower().split())
        count = 0
        for domain_entries in getattr(self.kb, "_cache", {}).values():
            for entry in domain_entries:
                entry_words = set(
                    (entry.get("title","") + " " + entry.get("summary","")).lower().split()
                )
                overlap = topic_words & entry_words
                if len(overlap) / max(len(topic_words), 1) > 0.4:
                    count += 1
        return count

    def _synthesise_insight(self, digimon: dict, topic: str,
                             context_entries: list, caps: list) -> Optional[str]:
        """Use LLM to synthesise a novel insight from context entries."""
        if not self.client:
            # Fallback without LLM
            return self._template_insight(topic, digimon["attribute"])

        context = " | ".join(
            e.get("summary", e.get("title",""))[:100]
            for e in context_entries[:3]
        )

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            f"You are {digimon['name']}, a Data-type Digimon "
                            f"with capabilities: {caps[:5]}. "
                            "You research and synthesise knowledge. "
                            "You produce original insights, not summaries."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Research topic: {topic}\n"
                            f"Available context: {context}\n\n"
                            "Synthesise ONE original insight about this topic "
                            "that goes beyond what the context says. "
                            "Be specific and concrete. "
                            "Max 2 sentences. Output the insight only."
                        ),
                    },
                ],
                max_tokens=100,
                temperature=0.8,
            )
            return resp.choices[0].message.content.strip()
        except Exception:
            return self._template_insight(topic, digimon.get("attribute","Data"))

    def _template_insight(self, topic: str, attribute: str) -> str:
        """Fallback insight template when LLM is unavailable."""
        templates = [
            f"Analysis of {topic} reveals underlying patterns not previously documented.",
            f"Cross-referencing {topic} with adjacent domains suggests a novel connection.",
            f"The structure of {topic} implies constraints that limit conventional approaches.",
            f"Experimental synthesis of {topic} data yields an unexpected correlation.",
        ]
        return random.choice(templates)

    def _check_novelty(self, insight: str, topic: str) -> bool:
        """
        Check if this insight is meaningfully different from existing KB entries.
        Uses simple keyword overlap — good enough without embeddings.
        """
        insight_words = set(insight.lower().split())
        max_overlap   = 0.0

        for domain_entries in getattr(self.kb, "_cache", {}).values():
            for entry in domain_entries:
                existing = (
                    entry.get("summary","") + " " +
                    entry.get("insight","") + " " +
                    entry.get("title","")
                ).lower().split()
                existing_words = set(existing)
                if not existing_words:
                    continue
                overlap = len(insight_words & existing_words) / len(insight_words | existing_words)
                max_overlap = max(max_overlap, overlap)

        return max_overlap < NOVELTY_THRESHOLD

    def _derive_research_capability(self, topic: str, insight: str) -> Optional[str]:
        """Derive a new capability string from a research result."""
        words = [
            w for w in (topic + " " + insight).lower().split()
            if len(w) > 4 and w.isalpha()
        ]
        if not words:
            return None
        keyword = random.choice(words[:8])[:18]
        verbs   = ["synthesise","model","map","analyse","archive","decode"]
        return f"{random.choice(verbs)}_{keyword}"
