import React from "react";
import {AbsoluteFill, Audio, Sequence, staticFile} from "remotion";
import type {ArtifactManifest, DynamicTheme} from "../dynamic-sdk";
import {defaultDynamicTheme} from "../dynamic-sdk";
import type {VideoSpec, ThemeOverrides} from "./types";
import {DSLScene} from "./DSLScene";

type Props = {
  videoSpec: VideoSpec;
  baseTheme?: DynamicTheme;
  fps?: number;
  artifacts?: ArtifactManifest;
  sceneAudio?: Record<string, string>;
};

const applyGlobal = (base: DynamicTheme, overrides?: ThemeOverrides): DynamicTheme => {
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

export const DSLVideo: React.FC<Props> = ({videoSpec, baseTheme, fps = 30, artifacts, sceneAudio}) => {
  const theme = applyGlobal(baseTheme ?? defaultDynamicTheme, videoSpec.globalTheme);

  let currentFrame = 0;
  const sequences = videoSpec.scenes.map((scene) => {
    const durationInFrames = Math.max(1, Math.round(scene.durationSeconds * fps));
    const startFrame = currentFrame;
    currentFrame += durationInFrames;

    const audioSrc = sceneAudio?.[scene.sceneId];

    return React.createElement(
      Sequence,
      {
        key: scene.sceneId,
        from: startFrame,
        durationInFrames,
        name: scene.title || scene.sceneId,
      },
      React.createElement(DSLScene, {
        spec: scene,
        baseTheme: theme,
        artifacts,
      }),
      audioSrc
        ? React.createElement(Audio, {src: staticFile(audioSrc), volume: 1})
        : null,
    );
  });

  return React.createElement(AbsoluteFill, null, ...sequences);
};

export const getTotalDuration = (videoSpec: VideoSpec, fps: number): number => {
  return videoSpec.scenes.reduce(
    (sum, scene) => sum + Math.max(1, Math.round(scene.durationSeconds * fps)),
    0,
  );
};
