import React from "react";
import {spring, useCurrentFrame, useVideoConfig} from "remotion";
import type {DSLContext, BadgeRowElement} from "../types";
import {spacing, radius, typography} from "../../dynamic-sdk";

type Props = {
  spec: BadgeRowElement;
  ctx: DSLContext;
};

export const BadgeRow: React.FC<Props> = ({spec, ctx}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const {theme} = ctx;
  const staggerFrames = Math.round((spec.stagger ?? 0.08) * fps);

  const items = spec.items.map((item, i) => {
    const delay = i * staggerFrames;
    const progress = spring({
      frame: Math.max(0, frame - delay),
      fps,
      config: {damping: 20, stiffness: 140},
    });

    return React.createElement(
      "div",
      {
        key: i,
        style: {
          display: "inline-flex",
          alignItems: "center",
          gap: 8,
          padding: "10px 20px",
          borderRadius: radius.pill,
          background: theme.surface,
          border: `1px solid ${theme.border}`,
          fontFamily: theme.bodyFont,
          fontSize: typography.body,
          fontWeight: 550,
          color: theme.foreground,
          opacity: progress,
          transform: `scale(${0.8 + progress * 0.2})`,
        },
      },
      item.icon
        ? React.createElement("span", {style: {fontSize: 18}}, item.icon)
        : null,
      item.label,
    );
  });

  return React.createElement(
    "div",
    {
      style: {
        display: "flex",
        flexWrap: "wrap",
        gap: spacing.sm,
      },
    },
    ...items,
  );
};
