import React from "react";
import {Img, spring, staticFile, useCurrentFrame, useVideoConfig} from "remotion";
import type {DSLContext, PortraitElement} from "../types";
import {getApprovedArtifact, radius, shadows} from "../../dynamic-sdk";

type Props = {
  spec: PortraitElement;
  ctx: DSLContext;
};

export const PortraitFrame: React.FC<Props> = ({spec, ctx}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const {theme, artifacts} = ctx;

  const progress = spring({
    frame,
    fps,
    config: {damping: 16, stiffness: 100},
  });

  const artifact = getApprovedArtifact(artifacts, spec.artifactId);
  const borderColor = spec.borderColor || theme.accent;
  const borderRad = spec.borderRadius ?? 24;

  return React.createElement(
    "div",
    {
      style: {
        width: "100%",
        aspectRatio: "3 / 4",
        borderRadius: borderRad,
        overflow: "hidden",
        border: `4px solid ${borderColor}`,
        boxShadow: spec.shadow !== false ? shadows.strong : "none",
        transform: `scale(${0.92 + progress * 0.08})`,
        opacity: progress,
        background: theme.surface,
      },
    },
    React.createElement(Img, {
      src: staticFile(artifact.rendererPath),
      alt: artifact.altText,
      style: {
        width: "100%",
        height: "100%",
        objectFit: "cover",
      },
    }),
  );
};
