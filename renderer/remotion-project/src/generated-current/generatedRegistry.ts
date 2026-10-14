import type React from "react";
import type {GeneratedSceneProps} from "../dynamic-sdk";

import {IntroDisplayAsymmetricTitleStrip as GeneratedComponent1} from "./components/s1_intro_IntroDisplayAsymmetricTitleStrip";
import {AsymmetricSummaryEditorialLead as GeneratedComponent2} from "./components/s2_exec_summary_AsymmetricSummaryEditorialLead";
import {HorizontalMilestoneTimeline as GeneratedComponent3} from "./components/s3_career_timeline_HorizontalMilestoneTimeline";
import {MetricTriptychProportionalCounters as GeneratedComponent4} from "./components/s4_quantified_highlights_MetricTriptychProportionalCounters";
import {OrgNodeMapCompactNode as GeneratedComponent5} from "./components/s5_leadership_scope_OrgNodeMapCompactNode";

export const generatedSceneRegistry: Record<
  string,
  React.FC<GeneratedSceneProps>
> = {
  "s1_intro": GeneratedComponent1,
  "s2_exec_summary": GeneratedComponent2,
  "s3_career_timeline": GeneratedComponent3,
  "s4_quantified_highlights": GeneratedComponent4,
  "s5_leadership_scope": GeneratedComponent5,
};

export const generatedSceneFallbackRegistry: Record<string, string> = {
  "s1_intro": "typography_only_card",
  "s2_exec_summary": "typography_only",
  "s3_career_timeline": "typography_only",
  "s4_quantified_highlights": "typography_only",
  "s5_leadership_scope": "typography_only_card",
};
