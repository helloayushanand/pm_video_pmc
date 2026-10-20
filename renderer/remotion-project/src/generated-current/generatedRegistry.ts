import type React from "react";
import type {GeneratedSceneProps} from "../dynamic-sdk";

import {PortraitReveal_Asymmetric as GeneratedComponent1} from "./components/scene_01_intro_PortraitReveal_Asymmetric";
import {AsymmetricEditorial_Summary as GeneratedComponent2} from "./components/scene_02_executive_summary_AsymmetricEditorial_Summary";
import {MetricsTriptych_Animated as GeneratedComponent3} from "./components/scene_05_quantified_highlights_MetricsTriptych_Animated";
import {OrgNode_NetworkMap as GeneratedComponent4} from "./components/scene_06_leadership_scope_OrgNode_NetworkMap";
import {TimelineMarker_MetricPair as GeneratedComponent5} from "./components/scene_03_flipkart_milestone_TimelineMarker_MetricPair";

export const generatedSceneRegistry: Record<
  string,
  React.FC<GeneratedSceneProps>
> = {
  "scene_01_intro": GeneratedComponent1,
  "scene_02_executive_summary": GeneratedComponent2,
  "scene_05_quantified_highlights": GeneratedComponent3,
  "scene_06_leadership_scope": GeneratedComponent4,
  "scene_03_flipkart_milestone": GeneratedComponent5,
};

export const generatedSceneFallbackRegistry: Record<string, string> = {
  "scene_01_intro": "ApprovedAsset_PortraitCard",
  "scene_02_executive_summary": "TypographyOnly_ExecutiveSummary",
  "scene_05_quantified_highlights": "RemotionNative_MetricStack",
  "scene_06_leadership_scope": "DeterministicDiagram_SimpleOrg",
  "scene_03_flipkart_milestone": "TypographyOnly_Milestone",
};
