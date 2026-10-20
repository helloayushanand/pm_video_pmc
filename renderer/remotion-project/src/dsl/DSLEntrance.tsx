import React from "react";
import {interpolate, spring, useCurrentFrame, useVideoConfig} from "remotion";
import type {EntranceSpec} from "./types";

type Props = {
  spec?: EntranceSpec;
  children?: React.ReactNode;
};

export const DSLEntrance: React.FC<Props> = ({spec, children}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  if (!spec || spec.type === "none") {
    return React.createElement(React.Fragment, null, children);
  }

  const delayFrames = Math.round((spec.delay ?? 0) * fps);
  const durationFrames = Math.max(1, Math.round((spec.duration ?? 0.6) * fps));
  const local = Math.max(0, frame - delayFrames);

  const progress = spring({
    frame: local,
    fps,
    config: {damping: 18, stiffness: 120, mass: 0.8},
    durationInFrames: durationFrames,
  });

  const opacity = interpolate(progress, [0, 1], [0, 1]);

  let transform = "";

  switch (spec.type) {
    case "fade":
      break;
    case "slide_up":
      transform = `translateY(${interpolate(progress, [0, 1], [36, 0])}px)`;
      break;
    case "slide_down":
      transform = `translateY(${interpolate(progress, [0, 1], [-36, 0])}px)`;
      break;
    case "slide_left":
      transform = `translateX(${interpolate(progress, [0, 1], [36, 0])}px)`;
      break;
    case "slide_right":
      transform = `translateX(${interpolate(progress, [0, 1], [-36, 0])}px)`;
      break;
    case "scale":
      transform = `scale(${interpolate(progress, [0, 1], [0.85, 1])})`;
      break;
  }

  return React.createElement(
    "div",
    {style: {opacity, transform: transform || undefined}},
    children,
  );
};
