import type React from "react";
import type {GeneratedSceneProps} from "../../dynamic-sdk";

import {IntroEditorialStack as GeneratedComponent1} from "./components/intro_IntroEditorialStack";

export const generatedSceneRegistry: Record<
  string,
  React.FC<GeneratedSceneProps>
> = {
  "intro": GeneratedComponent1,
};

export const generatedSceneFallbackRegistry: Record<string, string> = {
  "intro": "StackedTypographyIntro",
};
