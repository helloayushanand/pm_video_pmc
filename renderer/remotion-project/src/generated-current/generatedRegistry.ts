import type React from "react";
import type {GeneratedSceneProps} from "../dynamic-sdk";

import {PortraitEditorialLead as GeneratedComponent1} from "./components/s1_intro_PortraitEditorialLead";
import {AsymmetricExecSummaryColumn as GeneratedComponent2} from "./components/s2_execsum_AsymmetricExecSummaryColumn";
import {HorizontalMilestoneTimeline as GeneratedComponent3} from "./components/s3_timeline_HorizontalMilestoneTimeline";
import {EventRelaunchIllustration as GeneratedComponent4} from "./components/s4_milestone_flipkart_EventRelaunchIllustration";
import {ProportionalMetricsCluster as GeneratedComponent5} from "./components/s5_quantified_ProportionalMetricsCluster";

export const generatedSceneRegistry: Record<
  string,
  React.FC<GeneratedSceneProps>
> = {
  "s1_intro": GeneratedComponent1,
  "s2_execsum": GeneratedComponent2,
  "s3_timeline": GeneratedComponent3,
  "s4_milestone_flipkart": GeneratedComponent4,
  "s5_quantified": GeneratedComponent5,
};

export const generatedSceneFallbackRegistry: Record<string, string> = {
  "s1_intro": "existing_component_variant",
  "s2_execsum": "typography_only",
  "s3_timeline": "deterministic_diagram",
  "s4_milestone_flipkart": "image_generation",
  "s5_quantified": "deterministic_chart",
};
