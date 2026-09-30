import type React from "react";
import type {GeneratedSceneProps} from "../dynamic-sdk";

import {AsymmetricEditorial_Keywords as GeneratedComponent1} from "./components/scene_02_exec_summary_AsymmetricEditorial_Keywords";
import {HorizontalCareerTimeline_3node as GeneratedComponent2} from "./components/scene_03_timeline_HorizontalCareerTimeline_3node";
import {AsymmetricMetricsGrid_Animated as GeneratedComponent3} from "./components/scene_04_metrics_AsymmetricMetricsGrid_Animated";
import {NetworkOrg_GeoRibbon as GeneratedComponent4} from "./components/scene_05_leadership_NetworkOrg_GeoRibbon";
import {TwoColumn_Strengths_Icons as GeneratedComponent5} from "./components/scene_06_strengths_TwoColumn_Strengths_Icons";

export const generatedSceneRegistry: Record<
  string,
  React.FC<GeneratedSceneProps>
> = {
  "scene_02_exec_summary": GeneratedComponent1,
  "scene_03_timeline": GeneratedComponent2,
  "scene_04_metrics": GeneratedComponent3,
  "scene_05_leadership": GeneratedComponent4,
  "scene_06_strengths": GeneratedComponent5,
};

export const generatedSceneFallbackRegistry: Record<string, string> = {
  "scene_02_exec_summary": "typography_only",
  "scene_03_timeline": "typography_only",
  "scene_04_metrics": "remotion_native",
  "scene_05_leadership": "deterministic_diagram",
  "scene_06_strengths": "typography_only",
};
