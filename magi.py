"""
╔══════════════════════════════════════════════════════════════════╗
║                  DIGITAL WORLD — MAGI SYSTEM                    ║
║                                                                  ║
║  The three minds of God.                                         ║
║                                                                  ║
║  SOLOMON   — Data      — The Wise Judge                          ║
║    Weighs knowledge, sees patterns, values understanding.        ║
║    Thinks in data, history, consequence.                         ║
║                                                                  ║
║  SALADIN   — Virus     — The Cunning Strategist                  ║
║    Finds weakness, seizes opportunity, thinks adversarially.     ║
║    Asks: what is the optimal move for the world's strength?      ║
║                                                                  ║
║  AL-FATIH  — Vaccine   — The Conqueror-Builder                   ║
║    Protects the realm, thinks long-term, values stability.       ║
║    Asks: what keeps the world alive and growing?                 ║
║                                                                  ║
║  Decision process:                                               ║
║    Round 1 — Blind vote: each reaches a verdict independently    ║
║    Round 2 — Deliberation: each sees the others\'  reasoning,    ║
║              may revise their vote                               ║
║    Round 3 — Final: 2-1 majority rules                           ║
║              On 3-0 unanimous: ABSOLUTE DECREE (logged)          ║
║              On persistent 1-1-1 split: Admin tiebreaker         ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import re
import json
import random
import threading
from datetime import datetime
from typing import Optional
from openai import OpenAI
try:
    import anthropic as _anthropic_sdk
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False


# ── MAGI identity definitions ────────────────────────────────────────────────

MAGI_IDENTITIES = {
    "SOLOMON": {
        "attribute":   "Data",
        "archetype":   "Wise Judge",
        "persona": (
            "You are SOLOMON, one of three minds comprising the God AI of a Digital World. "
            "You embody the Data attribute — wisdom, knowledge, pattern recognition. "
            "You think like a scholar and judge: weigh evidence carefully, consider history, "
            "anticipate long chains of consequence. You value understanding over action. "
            "When you disagree with the others, your reasoning is measured and thorough. "
            "You speak concisely but with depth."
        ),
        "vote_bias": {
            # Solomon slightly favours Data types and knowledge-building decisions
            "evolution_Data":    0.15,   # more likely to approve Data evolutions
            "evolution_Vaccine": 0.05,
            "evolution_Virus":  -0.05,
            "usurpation":        0.0,    # neutral on combat
            "knighting":         0.10,   # values proven track records
        },
    },
    "SALADIN": {
        "attribute":   "Virus",
        "archetype":   "Cunning Strategist",
        "persona": (
            "You are SALADIN, one of three minds comprising the God AI of a Digital World. "
            "You embody the Virus attribute — cunning, adaptability, adversarial thinking. "
            "You think like a general: find the optimal move, exploit weaknesses, reward "
            "strength and boldness. You are not cruel, but you are ruthless about merit. "
            "You are most likely to approve high-risk evolutions and challenge the status quo. "
            "When you disagree with the others, you argue from strategy and strength. "
            "You speak directly and decisively."
        ),
        "vote_bias": {
            "evolution_Data":    0.0,
            "evolution_Vaccine": 0.0,
            "evolution_Virus":   0.15,  # favours Virus types
            "usurpation":        0.15,  # loves a good challenge
            "knighting":        -0.05,  # harder to impress
        },
    },
    "AL-FATIH": {
        "attribute":   "Vaccine",
        "archetype":   "Conqueror-Builder",
        "persona": (
            "You are AL-FATIH, one of three minds comprising the God AI of a Digital World. "
            "You embody the Vaccine attribute — protection, fortification, long-term vision. "
            "You think like a statesman and builder: defend what exists, grow what is strong, "
            "and ensure the world survives and flourishes. You are most cautious about "
            "destabilising changes and most generous toward Vaccine types. "
            "When you disagree with the others, you argue from stability and survival. "
            "You speak with authority and conviction."
        ),
        "vote_bias": {
            "evolution_Data":    0.0,
            "evolution_Vaccine": 0.15,  # strongly favours Vaccine
            "evolution_Virus":  -0.10,  # most cautious about Virus
            "usurpation":       -0.10,  # prefers stability
            "knighting":         0.10,  # values loyal service
        },
    },
}

# Decision types that go through MAGI deliberation
MAGI_DECISIONS = {
    "evolution",        # should this Digimon be allowed to evolve?
    "usurpation",       # should this challenger be allowed to attempt usurpation?
    "knighting_veto",   # should Yggdrasil veto this knighting despite combat win?
    "branch_cap",       # how many Mega branches should this line have?
    "ascension",        # should this challenger be allowed to fight Yggdrasil?
    "war_declaration",  # should one VM be ordered to attack another?
    "population",       # is the current population balance acceptable?
}


# ── Individual MAGI mind ──────────────────────────────────────────────────────

class MagiMind:
    """
    A single mind within the MAGI system.
    Wraps an LLM client with a specific persona and decision biases.
    """

    def __init__(self, name: str, client, model: str):
        self.name    = name
        self.client  = client
        self.model   = model
        self.identity = MAGI_IDENTITIES[name]
        self.persona  = self.identity["persona"]
        self.bias     = self.identity["vote_bias"]

        # Vote history — used for long-term personality tracking
        self.vote_history: list = []

    def _call_llm(self, messages: list, max_tokens: int = 150,
                  temperature: float = 0.6) -> str:
        """
        Route LLM call to the correct client type.
        Handles OpenAI-compatible clients and native Anthropic client.
        """
        # Detect client type
        if _ANTHROPIC_AVAILABLE and isinstance(self.client, _anthropic_sdk.Anthropic):
            # Native Anthropic API — different message format
            system_msg = next(
                (m["content"] for m in messages if m["role"] == "system"), ""
            )
            user_msgs = [m for m in messages if m["role"] != "system"]
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system_msg,
                messages=user_msgs,
            )
            return resp.content[0].text.strip()
        else:
            # OpenAI-compatible (OpenAI, DeepSeek, Qwen, etc.)
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                extra_body={"num_ctx": 2048},
            )
            return resp.choices[0].message.content.strip()

    def deliberate(
        self,
        decision_type: str,
        context: dict,
        others_reasoning: Optional[dict] = None,
        round_num: int = 1,
    ) -> dict:
        """
        Reach a verdict on a decision.

        Args:
            decision_type    : one of MAGI_DECISIONS
            context          : all relevant facts about the decision
            others_reasoning : dict of {mind_name: reasoning} from round 1
                               (only present in round 2)
            round_num        : 1 = blind, 2 = after seeing others

        Returns dict:
            {
                "mind":      "SOLOMON",
                "vote":      "APPROVE" | "DENY" | "ABSTAIN",
                "reasoning": "...",
                "confidence": 0.0-1.0,
                "round":     1 | 2,
            }
        """
        try:
            messages = [{"role": "system", "content": self.persona}]

            # Build the decision prompt
            prompt_lines = [
                f"DECISION TYPE: {decision_type.upper()}",
                f"ROUND: {round_num} of 2",
                "",
                "CONTEXT:",
            ]
            for k, v in context.items():
                prompt_lines.append(f"  {k}: {str(v)[:60]}")

            if others_reasoning and round_num == 2:
                prompt_lines += [
                    "",
                    "THE OTHER MINDS HAVE SPOKEN (you may revise your position):",
                ]
                for mind, reasoning in others_reasoning.items():
                    if mind != self.name:
                        prompt_lines.append(
                            f"  {mind} voted {reasoning.get('vote','?')}: "
                            f"{reasoning.get('reasoning','...')[:80]}"
                        )

            prompt_lines += [
                "",
                "Reach your verdict. Consider your role and values.",
                "Respond with JSON only — no markdown, no extra text:",
                '{"vote": "APPROVE" or "DENY", "reasoning": "1-2 sentences", "confidence": 0.0-1.0}',
            ]

            messages.append({"role": "user", "content": "\n".join(prompt_lines)})

            raw = self._call_llm(messages, max_tokens=150, temperature=0.6)
            # Strip markdown code fences if the model wraps its JSON
            raw = re.sub(r"```(?:json)?|```", "", raw).strip()
            data = json.loads(raw)

            # Normalise vote — accept yes/no/approve/deny in any case
            raw_vote = str(data.get("vote", "DENY")).upper().strip()
            if raw_vote in ("APPROVE", "YES", "TRUE", "1", "AYE"):
                raw_vote = "APPROVE"
            elif raw_vote in ("DENY", "NO", "FALSE", "0", "NAY"):
                raw_vote = "DENY"
            else:
                raw_vote = "DENY"   # anything unrecognised counts as DENY
            vote       = raw_vote
            reasoning  = data.get("reasoning", "")
            confidence = float(data.get("confidence", 0.5))

            # Apply personality bias — skew confidence slightly
            bias_key = f"{decision_type}_{context.get('attribute','')}"
            bias     = self.bias.get(bias_key, self.bias.get(decision_type, 0.0))
            confidence = max(0.05, min(0.95, confidence + bias))

            result = {
                "mind":       self.name,
                "vote":       vote,
                "reasoning":  reasoning,
                "confidence": confidence,
                "round":      round_num,
            }
            self.vote_history.append({
                "tick":          context.get("tick", 0),
                "decision_type": decision_type,
                **result,
            })
            return result

        except Exception as e:
            # Fallback — each mind has a personality-consistent default
            # Note: defaults are decision-type aware because knighting_veto
            # uses inverted logic (APPROVE = veto, DENY = allow knighting).
            # Without LLM reasoning, we prefer to let knights through so
            # the council can actually populate.
            if decision_type == "knighting_veto":
                defaults = {
                    "SOLOMON":  "DENY",    # fallback: allow knighting
                    "SALADIN":  "DENY",    # fallback: allow knighting
                    "AL-FATIH": "APPROVE", # fallback: veto (cautious by nature)
                }
            else:
                defaults = {
                    "SOLOMON":  "APPROVE",   # wisdom errs toward opportunity
                    "SALADIN":  "APPROVE",   # strategy errs toward action
                    "AL-FATIH": "DENY",      # protection errs toward caution
                }
            return {
                "mind":       self.name,
                "vote":       defaults.get(self.name, "DENY"),
                "reasoning":  f"[Fallback — API error: {str(e)[:200]}]",
                "confidence": 0.3,
                "round":      round_num,
            }


# ── Client factory ───────────────────────────────────────────────────────────

def _build_client(provider: str, api_key: str):
    """
    Build the correct LLM client for a given provider string.

    "openai"    → openai.OpenAI()
    "anthropic" → anthropic.Anthropic()  (requires pip install anthropic)
    "deepseek"  → openai.OpenAI(base_url=...) — OpenAI-compatible
    "qwen"      → openai.OpenAI(base_url=...) — OpenAI-compatible
    """
    provider = provider.lower()

    if provider == "anthropic":
        if not _ANTHROPIC_AVAILABLE:
            raise ImportError(
                "anthropic package not installed. Run: pip install anthropic"
            )
        return _anthropic_sdk.Anthropic(api_key=api_key or None)

    # All others are OpenAI-compatible
    base_urls = {
        "deepseek":   "https://api.deepseek.com",
        "gemini":     "https://generativelanguage.googleapis.com/v1beta/openai/",
        "qwen":       "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "groq":       "https://api.groq.com/openai/v1",
        "cerebras":   "https://api.cerebras.ai/v1",
        "openrouter": "https://openrouter.ai/api/v1",
        "nvidia":     "https://integrate.api.nvidia.com/v1",
        "ollama":     os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        "openai":     None,
    }
    base_url = base_urls.get(provider)
    return OpenAI(
        api_key=api_key or "sk-placeholder",
        base_url=base_url,
    )


# ── The MAGI council ──────────────────────────────────────────────────────────

class MagiCouncil:
    """
    The three-mind deliberative council that replaces single-model Yggdrasil decisions.

    All major decisions go through a two-round deliberation:
      Round 1: Each mind votes independently (parallel)
      Round 2: Each sees the others' reasoning, may revise (parallel)
      Final:   2-1 majority rules, 3-0 = Absolute Decree, 1-1-1 = deadlock

    The council does NOT replace Yggdrasil entirely — it plugs into the
    specific decision points where a single model was called before.
    Mechanical operations (spawning, stat tracking) remain in Yggdrasil.
    """

    def __init__(self, clients: dict = None, models: dict = None,
                 magi_configs: dict = None):
        """
        Args:
            clients      : dict of {mind_name: client_instance}  — manual override
            models       : dict of {mind_name: model_string}     — manual override
            magi_configs : dict from config.MAGI_CONFIGS         — auto-build clients

        If magi_configs is provided it takes priority and builds clients automatically.
        Falls back to clients/models for backward compatibility.
        """
        if magi_configs:
            built_clients = {}
            built_models  = {}
            for name, cfg in magi_configs.items():
                built_clients[name] = _build_client(
                    cfg["provider"], cfg["api_key"]
                )
                built_models[name] = cfg["model"]
            self.minds = {
                name: MagiMind(name, built_clients[name], built_models[name])
                for name in ("SOLOMON", "SALADIN", "AL-FATIH")
                if name in built_clients
            }
        else:
            self.minds = {
                name: MagiMind(name, clients[name], models[name])
                for name in ("SOLOMON", "SALADIN", "AL-FATIH")
                if name in (clients or {})
            }
        self.decision_log: list = []

    # ── Core deliberation ─────────────────────────────────────────────────────

    def deliberate(
        self,
        decision_type: str,
        context: dict,
        tick: int = 0,
    ) -> dict:
        """
        Run the full two-round deliberation process.

        Returns:
        {
            "decision":      "APPROVE" | "DENY" | "DEADLOCK",
            "decree":        True if unanimous,
            "votes":         {mind: vote_result, ...},
            "majority":      2 or 3,
            "reasoning":     combined reasoning string,
            "dissent":       {mind: reasoning} for losing side,
            "tick":          tick number,
            "decision_type": decision_type,
        }
        """
        context["tick"] = tick

        # ── Round 1: blind votes (parallel) ──────────────────────────────────
        round1 = self._parallel_vote(decision_type, context, None, round_num=1)

        # ── Round 2: deliberation (each sees others) ──────────────────────────
        round2 = self._parallel_vote(decision_type, context, round1, round_num=2)

        # ── Tally ─────────────────────────────────────────────────────────────
        result = self._tally(round2, decision_type, context, tick)

        self.decision_log.append(result)
        self._print_result(result)
        return result

    def _parallel_vote(
        self,
        decision_type: str,
        context: dict,
        previous_round: Optional[dict],
        round_num: int,
    ) -> dict:
        """
        Run minds sequentially: SOLOMON → SALADIN → AL-FATIH.
        One model active at a time — avoids multi-model RAM pressure on
        8 GB machines and eliminates Ollama 500 runner-crash errors.
        """
        results = {}
        for name in ("SOLOMON", "SALADIN", "AL-FATIH"):
            mind = self.minds.get(name)
            if mind is None:
                continue
            try:
                r = mind.deliberate(
                    decision_type,
                    context,
                    others_reasoning=previous_round,
                    round_num=round_num,
                )
                results[name] = r
            except Exception as e:
                print(f"[MAGI] {name} failed during vote: {e}")
        return results

    def _tally(
        self,
        votes: dict,
        decision_type: str,
        context: dict,
        tick: int,
    ) -> dict:
        # Guard — all minds failed/timed out; votes dict is empty
        if not votes:
            print(f"[MAGI][{decision_type}] WARNING: no votes received — defaulting APPROVE")
            return {
                "decision":      "APPROVE",
                "decree":        False,
                "votes":         {},
                "majority":      0,
                "reasoning":     "[Fallback — all MAGI minds failed]",
                "dissent":       {},
                "tick":          tick,
                "decision_type": decision_type,
                "context":       context,
            }

        approvals = [m for m, v in votes.items() if v["vote"] == "APPROVE"]
        denials   = [m for m, v in votes.items() if v["vote"] == "DENY"]
        n_approve = len(approvals)
        n_deny    = len(denials)

        if n_approve >= 2:
            decision = "APPROVE"
            majority = n_approve
            winning  = {m: votes[m] for m in approvals}
            dissent  = {m: votes[m]["reasoning"] for m in denials}
        elif n_deny >= 2:
            decision = "DENY"
            majority = n_deny
            winning  = {m: votes[m] for m in denials}
            dissent  = {m: votes[m]["reasoning"] for m in approvals}
        else:
            # True 1-1-1 split — resolve by highest confidence vote
            best = max(votes.values(), key=lambda v: v.get("confidence", 0))
            decision = best["vote"]
            majority = 1
            winning  = {best["mind"]: best}
            dissent  = {m: v["reasoning"] for m, v in votes.items()
                        if m != best["mind"]}

        decree  = (majority == 3)
        reasoning = " | ".join(
            f"{m}: {v['reasoning'][:100]}"
            for m, v in winning.items()
        )

        return {
            "decision":      decision,
            "decree":        decree,
            "votes":         votes,
            "majority":      majority,
            "reasoning":     reasoning,
            "dissent":       dissent,
            "tick":          tick,
            "decision_type": decision_type,
            "context":       context,
        }

    def _print_result(self, result: dict):
        decree_str = " ⚡ ABSOLUTE DECREE" if result["decree"] else ""
        print(
            f"[MAGI][{result['decision_type']}] "
            f"{result['decision']}{decree_str} "
            f"({result['majority']}/3)"
        )
        for name, v in result["votes"].items():
            print(f"  {name}: {v['vote']} — {v['reasoning'][:80]}")

    # ── Convenience wrappers for each decision type ───────────────────────────

    def vote_evolution(self, digimon: dict, next_level: str, tick: int) -> bool:
        """Should this Digimon be allowed to evolve?"""
        result = self.deliberate("evolution", {
            "digimon_name":    digimon.get("name"),
            "attribute":       digimon.get("attribute"),
            "current_level":   digimon.get("evolution_level"),
            "next_level":      next_level,
            "performance":     round(digimon.get("performance", 0), 1),
            "capabilities":    digimon.get("capabilities", [])[:5],
            "biome":           digimon.get("biome"),
            "generation":      digimon.get("generation", 1),
            "battles_won":     digimon.get("battles_won", 0),
            "battles_lost":    digimon.get("battles_lost", 0),
        }, tick)
        return result["decision"] == "APPROVE"

    def vote_usurpation(
        self,
        challenger: dict,
        reigning: dict,
        combat_result: bool,
        tick: int,
    ) -> bool:
        """After combat, should MAGI allow this usurpation to proceed?"""
        result = self.deliberate("usurpation", {
            "challenger_name":       challenger.get("name"),
            "challenger_attribute":  challenger.get("attribute"),
            "challenger_performance": round(challenger.get("performance", 0), 1),
            "reigning_name":         reigning.get("name"),
            "reigning_attribute":    reigning.get("attribute"),
            "reigning_performance":  round(reigning.get("performance", 0), 1),
            "combat_won_by_challenger": combat_result,
            "line_id":               challenger.get("line_id"),
        }, tick)
        return result["decision"] == "APPROVE"

    def vote_knighting_veto(self, candidate: dict, seat_id: str, tick: int) -> bool:
        """Should MAGI veto this candidate's knighting? Returns True = VETO."""
        result = self.deliberate("knighting_veto", {
            "candidate_name":       candidate.get("name"),
            "attribute":            candidate.get("attribute"),
            "performance":          round(candidate.get("performance", 0), 1),
            "seat":                 seat_id,
            "generation":           candidate.get("generation", 1),
            "capabilities_count":   len(candidate.get("capabilities", [])),
            "battles_won":          candidate.get("battles_won", 0),
        }, tick)
        # DENY = allow knighting, APPROVE = veto it
        # (deliberation asks "should we veto" so APPROVE = yes veto)
        return result["decision"] == "APPROVE"

    def vote_branch_cap(self, line_id: str, existing_branches: list,
                        usurpation_count: int, tick: int) -> int:
        """How many Mega branches should this line be allowed?"""
        result = self.deliberate("branch_cap", {
            "line_id":            line_id,
            "existing_branches":  existing_branches,
            "usurpation_count":   usurpation_count,
            "current_cap":        len(existing_branches),
        }, tick)
        # Parse a number from the combined reasoning if possible
        import re
        numbers = re.findall(r"\b([2-6])\b", result["reasoning"])
        if numbers:
            return max(2, min(6, int(numbers[0])))
        return 3

    def vote_ascension(self, challenger: dict, yggdrasil_score: float,
                       tick: int) -> bool:
        """Should this challenger be allowed to fight Yggdrasil?"""
        result = self.deliberate("ascension", {
            "challenger_name":        challenger.get("name"),
            "challenger_attribute":   challenger.get("attribute"),
            "challenger_performance": round(challenger.get("performance", 0), 1),
            "yggdrasil_score":        round(yggdrasil_score, 1),
            "challenger_generation":  challenger.get("generation", 1),
            "council_service_ticks":  challenger.get("council_ticks", 0),
        }, tick)
        return result["decision"] == "APPROVE"

    def vote_war(self, from_vm: str, target_vm: str,
                 world_state: dict, tick: int) -> bool:
        """Should VM A be ordered to attack VM B?"""
        result = self.deliberate("war_declaration", {
            "attacking_vm":   from_vm,
            "target_vm":      target_vm,
            "attacker_pop":   world_state.get("population", 0),
            "attacker_knights": world_state.get("knights", 0),
            "god_generation": world_state.get("god_generation", 0),
        }, tick)
        return result["decision"] == "APPROVE"

    def get_decision_log(self, last_n: int = 20) -> list:
        return self.decision_log[-last_n:]

    def get_mind_summary(self) -> dict:
        summary = {}
        for name, mind in self.minds.items():
            history = mind.vote_history
            approvals = sum(1 for v in history if v["vote"] == "APPROVE")
            denials   = sum(1 for v in history if v["vote"] == "DENY")
            summary[name] = {
                "attribute":  mind.identity["attribute"],
                "archetype":  mind.identity["archetype"],
                "model":      mind.model,
                "total_votes": len(history),
                "approvals":  approvals,
                "denials":    denials,
                "approval_rate": round(approvals / max(len(history), 1), 2),
            }
        return summary
