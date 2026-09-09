"""
Wires the agents together and owns the reflection loop:

  scene agent -> planning agent -> denoise agent -> review agent
                       ^                                  |
                       '------- feedback, retry -----------'

If nothing clears the quality bar within the allowed rounds, a fixed
conservative preset is applied as a last resort so the pipeline never
hands back something worse than a reasonable safe default.
"""

from pathlib import Path

import config
from agents.denoise_agent import DenoiseAgent
from agents.models import Attempt, EnhancementPlan, RunReport
from agents.planning_agent import PlanningAgent
from agents.reporting import write_report
from agents.review_agent import ReviewAgent
from agents.scene_agent import SceneAgent
from knowledge.retriever import KnowledgeRetriever
from toolbox.image_tools import build_default_registry, load_image, save_image


class Pipeline:
    def __init__(self, max_reflection_rounds: int = config.MAX_REFLECTION_ROUNDS):
        self.max_reflection_rounds = max_reflection_rounds
        self.registry = build_default_registry()
        self.scene_agent = SceneAgent(self.registry)
        self.planning_agent = PlanningAgent(KnowledgeRetriever())
        self.denoise_agent = DenoiseAgent(self.registry)
        self.review_agent = ReviewAgent()

    def run(self, input_path: str, output_path: str = None, report_path: str = None) -> RunReport:
        original = load_image(input_path)
        scene = self.scene_agent.analyze(original)

        attempts: list[Attempt] = []
        best_image = None
        best_score = -1.0
        feedback = ""

        for round_number in range(1, self.max_reflection_rounds + 2):
            plan = self.planning_agent.decide(scene, feedback)
            enhanced, method_used, fallback_triggered = self.denoise_agent.apply(original, plan)
            quality = self.review_agent.evaluate(original, enhanced)

            attempts.append(
                Attempt(
                    round_number=round_number,
                    plan=plan,
                    quality=quality,
                    denoise_method_used=method_used,
                    denoise_fallback_triggered=fallback_triggered,
                )
            )

            if quality.overall > best_score:
                best_score, best_image = quality.overall, enhanced

            if quality.passed:
                break

            feedback = quality.feedback

        used_safety_preset = False
        if best_score < self.review_agent.threshold:
            best_image, best_score, used_safety_preset = self._apply_safety_preset(original, attempts)

        output_path = output_path or self._default_output_path(input_path)
        report_path = report_path or str(Path(output_path).with_suffix("")) + "_report.md"

        save_image(best_image, output_path)

        run_report = RunReport(
            input_path=str(input_path),
            output_path=str(output_path),
            report_path=str(report_path),
            scene=scene,
            attempts=attempts,
            used_safety_preset=used_safety_preset,
            final_overall_score=best_score,
        )
        write_report(run_report, report_path)
        return run_report

    def _apply_safety_preset(self, original, attempts: list[Attempt]):
        plan = EnhancementPlan(
            **config.SAFETY_PRESET,
            reasoning=["no attempt cleared the quality threshold, applying the conservative safety preset"],
            source="safety-preset",
        )
        image, method_used, fallback_triggered = self.denoise_agent.apply(original, plan)
        quality = self.review_agent.evaluate(original, image)
        attempts.append(
            Attempt(
                round_number=len(attempts) + 1,
                plan=plan,
                quality=quality,
                denoise_method_used=method_used,
                denoise_fallback_triggered=fallback_triggered,
            )
        )
        return image, quality.overall, True

    @staticmethod
    def _default_output_path(input_path: str) -> str:
        stem = Path(input_path).stem
        return str(Path("outputs") / f"{stem}_enhanced.jpg")
