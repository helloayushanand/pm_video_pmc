import type React from "react";
import type {GeneratedSceneProps} from "../dynamic-sdk";

import {Hero_Typographic_Silhouette as GeneratedComponent1} from "./components/s1_Hero_Typographic_Silhouette";
import {ExecutiveSummary_IconRow as GeneratedComponent2} from "./components/s2_ExecutiveSummary_IconRow";
import {ThreeNode_CareerTimeline as GeneratedComponent3} from "./components/s3_ThreeNode_CareerTimeline";
import {AnimatedMetricBurst_4up as GeneratedComponent4} from "./components/s4_AnimatedMetricBurst_4up";
import {OrgNetwork_GeoBadges as GeneratedComponent5} from "./components/s5_OrgNetwork_GeoBadges";

export const generatedSceneRegistry: Record<
  string,
  React.FC<GeneratedSceneProps>
> = {
  "s1": GeneratedComponent1,
  "s2": GeneratedComponent2,
  "s3": GeneratedComponent3,
  "s4": GeneratedComponent4,
  "s5": GeneratedComponent5,
};

export const generatedSceneFallbackRegistry: Record<string, string> = {
  "s1": "Typography_only_title_card",
  "s2": "Typography_summary_card",
  "s3": "Horizontal_typography_timeline",
  "s4": "Staggered_metric_typography",
  "s5": "Two_column_label_list",
};
