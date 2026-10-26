import React from "react";
import {spring, useCurrentFrame, useVideoConfig} from "remotion";
import type {DSLContext, TimelineElement} from "../types";
import {spacing, radius, typography} from "../../dynamic-sdk";

type Props = {
  spec: TimelineElement;
  ctx: DSLContext;
};

export const TimelineStrip: React.FC<Props> = ({spec, ctx}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const {theme} = ctx;
  const nodes = spec.nodes;
  const staggerFrames = Math.round((spec.stagger ?? 0.2) * fps);
  const horizontal = (spec.orientation ?? "horizontal") === "horizontal";

  const container: React.CSSProperties = {
    display: "flex",
    flexDirection: horizontal ? "row" : "column",
    alignItems: horizontal ? "flex-start" : "stretch",
    gap: spacing.lg,
    width: "100%",
    position: "relative",
  };

  const connector: React.CSSProperties = {
    position: "absolute",
    background: theme.border,
    ...(horizontal
      ? {top: 18, left: 0, right: 0, height: 2}
      : {left: 18, top: 0, bottom: 0, width: 2}),
    ...(spec.connectorStyle === "dashed" && {
      background: "none",
      borderTop: horizontal ? `2px dashed ${theme.border}` : undefined,
      borderLeft: !horizontal ? `2px dashed ${theme.border}` : undefined,
    }),
    ...(spec.connectorStyle === "dotted" && {
      background: "none",
      borderTop: horizontal ? `2px dotted ${theme.border}` : undefined,
      borderLeft: !horizontal ? `2px dotted ${theme.border}` : undefined,
    }),
  };

  const connectorEl = React.createElement("div", {style: connector});

  const nodeEls = nodes.map((node, i) => {
    const delay = i * staggerFrames;
    const progress = spring({
      frame: Math.max(0, frame - delay),
      fps,
      config: {damping: 16, stiffness: 110},
    });
    const nodeAccent = node.accent || theme.accent;

    return React.createElement(
      "div",
      {
        key: i,
        style: {
          flex: horizontal ? 1 : undefined,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: spacing.xs,
          opacity: progress,
          transform: `translateY(${(1 - progress) * 20}px)`,
          position: "relative",
          zIndex: 1,
        },
      },
      React.createElement("div", {
        style: {
          width: 36,
          height: 36,
          borderRadius: "50%",
          background: theme.surface,
          border: `3px solid ${nodeAccent}`,
          flexShrink: 0,
        },
      }),
      React.createElement(
        "div",
        {
          style: {
            fontFamily: theme.displayFont,
            fontSize: typography.label,
            fontWeight: 700,
            color: nodeAccent,
            letterSpacing: 1,
          },
        },
        node.year,
      ),
      React.createElement(
        "div",
        {
          style: {
            fontFamily: theme.displayFont,
            fontSize: typography.subheading,
            fontWeight: 650,
            color: theme.foreground,
            textAlign: "center",
            lineHeight: 1.15,
          },
        },
        node.title,
      ),
      node.subtitle
        ? React.createElement(
            "div",
            {
              style: {
                fontFamily: theme.bodyFont,
                fontSize: typography.body,
                color: theme.foregroundMuted,
                textAlign: "center",
              },
            },
            node.subtitle,
          )
        : null,
    );
  });

  return React.createElement("div", {style: container}, connectorEl, ...nodeEls);
};
