import React from "react";
import {interpolate, useCurrentFrame, useVideoConfig} from "remotion";
import type {DSLContext, ProgressBarElement} from "../types";
import {spacing, radius, typography} from "../../dynamic-sdk";

type Props = {
  spec: ProgressBarElement;
  ctx: DSLContext;
};

export const ProgressBar: React.FC<Props> = ({spec, ctx}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const {theme} = ctx;

  const fillDuration = Math.round(fps * 0.8);
  const fill = interpolate(frame, [6, 6 + fillDuration], [0, spec.value], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const barColor = spec.color || theme.accent;

  return React.createElement(
    "div",
    {style: {width: "100%", display: "flex", flexDirection: "column", gap: spacing.xs}},
    spec.label
      ? React.createElement(
          "div",
          {
            style: {
              display: "flex",
              justifyContent: "space-between",
              fontFamily: theme.bodyFont,
              fontSize: typography.body,
              color: theme.foreground,
              fontWeight: 500,
            },
          },
          React.createElement("span", null, spec.label),
          React.createElement("span", {style: {color: theme.accent, fontWeight: 650}}, `${Math.round(fill)}%`),
        )
      : null,
    React.createElement(
      "div",
      {
        style: {
          width: "100%",
          height: 14,
          borderRadius: radius.pill,
          background: theme.surfaceSecondary,
          overflow: "hidden",
        },
      },
      React.createElement("div", {
        style: {
          width: `${fill}%`,
          height: "100%",
          borderRadius: radius.pill,
          background: barColor,
        },
      }),
    ),
  );
};
