"""
Decides *how* to enhance the image: gamma, CLAHE strength, which denoiser,
how hard to denoise, how much to sharpen.

Two decision paths:
  1. LLM + RAG - if an Anthropic API key is configured, ask the model to
     reason over the scene stats plus relevant snippets pulled from the
     knowledge notes, and return a plan as JSON.
  2. Heuristic fallback - deterministic rule engine in knowledge/heuristics.py.

The fallback isn't just for missing credentials - any failure in the LLM
path (network, auth, a malformed response) drops straight to it. The
pipeline should never hard-fail just because the network is down.
"""

import json
import re

import config
from agents.models import EnhancementPlan, SceneReport
from knowledge.heuristics import rule_based_plan
from knowledge.retriever import KnowledgeRetriever

try:
    import anthropic
except ImportError:
    anthropic = None


PLAN_FIELDS = ("gamma", "clahe_clip", "denoise_strength", "sharpen_amount")

SYSTEM_PROMPT = (
    "You are the planning stage of an image enhancement pipeline. Given "
    "measurements of a low-light photo and notes retrieved from a small "
    "internal knowledge base, choose enhancement parameters. Reply with "
    "ONLY a JSON object, no prose, no markdown fences. Fields: "
    "gamma (float, 0.3-1.0), clahe_clip (float, 1.5-4.0), clahe_tile (int, "
    "usually 8), denoise_method (\"nlmeans\" or \"bilateral\"), "
    "denoise_strength (float, 3-22), sharpen_amount (float, 0.2-0.8), "
    "reasoning (one short sentence)."
)


class PlanningAgent:
    def __init__(self, retriever: KnowledgeRetriever):
        self.retriever = retriever
        self.last_llm_error = ""
        self._client = self._init_client()

    @staticmethod
    def _init_client():
        if not config.ANTHROPIC_API_KEY or anthropic is None:
            return None
        try:
            return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        except Exception:
            return None

    def decide(self, scene: SceneReport, feedback: str = "") -> EnhancementPlan:
        if self._client is not None:
            query = scene.summary if not feedback else f"{scene.summary} Prior attempt feedback: {feedback}"
            retrieved = self.retriever.retrieve(query, k=config.RAG_TOP_K)
            plan = self._decide_with_llm(scene, feedback, retrieved)
            if plan is not None:
                return plan

        return self._decide_with_heuristic(scene, feedback)

    def _decide_with_llm(self, scene, feedback, retrieved):
        notes_block = "\n\n".join(f"[{chunk.chunk_id}]\n{chunk.text}" for chunk, _score in retrieved) or "(no notes matched)"
        user_prompt = (
            f"Scene measurements:\n"
            f"- mean brightness: {scene.mean_brightness}\n"
            f"- contrast (std dev): {scene.std_dev}\n"
            f"- percent dark pixels: {scene.percent_dark}\n"
            f"- percent blown highlights: {scene.percent_clipped_bright}\n"
            f"- noise estimate: {scene.noise_estimate}\n\n"
            f"Retrieved notes:\n{notes_block}\n\n"
            f"Prior attempt feedback: {feedback or '(none, this is the first pass)'}\n\n"
            f"Return the JSON plan now."
        )

        try:
            response = self._client.messages.create(
                model=config.ANTHROPIC_MODEL,
                max_tokens=400,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            raw_text = "".join(block.text for block in response.content if block.type == "text")
            data = json.loads(self._strip_fences(raw_text))

            for key in PLAN_FIELDS:
                if key not in data:
                    raise ValueError(f"model response missing '{key}'")

            return EnhancementPlan(
                gamma=float(data["gamma"]),
                clahe_clip=float(data["clahe_clip"]),
                clahe_tile=int(data.get("clahe_tile", 8)),
                denoise_method=data.get("denoise_method", "nlmeans"),
                denoise_strength=float(data["denoise_strength"]),
                sharpen_amount=float(data["sharpen_amount"]),
                reasoning=[str(data.get("reasoning", "")).strip() or "llm decision"],
                source="llm+rag",
                knowledge_used=[chunk.chunk_id for chunk, _score in retrieved],
            )
        except Exception as exc:  # noqa: BLE001 - any failure here just means "use the fallback"
            self.last_llm_error = f"{type(exc).__name__}: {exc}"
            return None

    def _decide_with_heuristic(self, scene, feedback) -> EnhancementPlan:
        raw = rule_based_plan(scene, feedback)
        return EnhancementPlan(
            gamma=raw["gamma"],
            clahe_clip=raw["clahe_clip"],
            clahe_tile=raw["clahe_tile"],
            denoise_method=raw["denoise_method"],
            denoise_strength=raw["denoise_strength"],
            sharpen_amount=raw["sharpen_amount"],
            reasoning=raw["reasoning"],
            source="heuristic-fallback",
            knowledge_used=[],
        )

    @staticmethod
    def _strip_fences(text: str) -> str:
        text = text.strip()
        match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
        return match.group(1) if match else text
