import React from "react";
import {interpolate, useCurrentFrame, useVideoConfig} from "remotion";
import type {ArtifactManifest, DynamicTheme} from "../dynamic-sdk";
import {defaultDynamicTheme, safeArea, typography} from "../dynamic-sdk";
import type {DSLContext, SceneSpec, ThemeOverrides} from "./types";
import {DSLBackground} from "./DSLBackground";
import {DSLLayout} from "./DSLLayout";

type Props = {
  spec: SceneSpec;
  baseTheme?: DynamicTheme;
  artifacts?: ArtifactManifest;
  sceneAudio?: string;
};

const applyOverrides = (base: DynamicTheme, overrides?: ThemeOverrides): DynamicTheme => {
  if (!overrides) return base;
  return {
    ...base,
    ...(overrides.background && {background: overrides.background}),
    ...(overrides.surface && {surface: overrides.surface}),
    ...(overrides.surfaceSecondary && {surfaceSecondary: overrides.surfaceSecondary}),
    ...(overrides.foreground && {foreground: overrides.foreground}),
    ...(overrides.foregroundMuted && {foregroundMuted: overrides.foregroundMuted}),
    ...(overrides.accent && {accent: overrides.accent}),
    ...(overrides.accentSecondary && {accentSecondary: overrides.accentSecondary}),
    ...(overrides.border && {border: overrides.border}),
  };
};

export const DSLScene: React.FC<Props> = ({spec, baseTheme, artifacts}) => {
  const frame = useCurrentFrame();
  const {durationInFrames, fps} = useVideoConfig();

  const theme = applyOverrides(baseTheme ?? defaultDynamicTheme, spec.themeOverrides);

  const ctx: DSLContext = {
    theme,
    fps,
    durationInFrames,
    artifacts: artifacts ?? {artifacts: []},
  };

  const fadeIn = Math.min(12, Math.floor(durationInFrames * 0.2));
  const fadeOut = Math.min(12, Math.floor(durationInFrames * 0.2));
  const holdStart = fadeIn;
  const holdEnd = Math.max(holdStart + 1, durationInFrames - fadeOut);

  const opacity = interpolate(
    frame,
    [0, holdStart, holdEnd, durationInFrames],
    [0, 1, 1, 0],
    {extrapolateLeft: "clamp", extrapolateRight: "clamp"},
  );

  const brand = React.createElement(
    "div",
    {
      style: {
        position: "absolute",
        left: safeArea.horizontal,
        top: 39,
        color: theme.accent,
        fontFamily: theme.bodyFont,
        fontSize: 17,
        fontWeight: 700,
        letterSpacing: 2.5,
        textTransform: "uppercase" as const,
        zIndex: 10,
      },
    },
    "Positive Moves",
  );

  const bottomBar = React.createElement("div", {
    style: {
      position: "absolute",
      left: 0,
      bottom: 0,
      width: "100%",
      height: 9,
      background: theme.accent,
      zIndex: 10,
    },
  });

  return React.createElement(
    "div",
    {
      style: {
        position: "absolute",
        inset: 0,
        opacity,
      },
    },
    React.createElement(
      DSLBackground,
      {spec: spec.background},
      brand,
      React.createElement(DSLLayout, {spec: spec.layout, ctx}),
      bottomBar,
    ),
  );
};
