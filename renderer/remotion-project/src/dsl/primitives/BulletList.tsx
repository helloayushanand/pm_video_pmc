import React from "react";
import {spring, useCurrentFrame, useVideoConfig} from "remotion";
import type {DSLContext, BulletListElement} from "../types";
import {spacing, radius, typography} from "../../dynamic-sdk";

type Props = {
  spec: BulletListElement;
  ctx: DSLContext;
};

export const BulletList: React.FC<Props> = ({spec, ctx}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const {theme} = ctx;
  const staggerFrames = Math.round((spec.stagger ?? 0.12) * fps);
  const cols = spec.columns ?? 1;

  const container: React.CSSProperties = {
    display: "grid",
    gridTemplateColumns: cols === 2 ? "1fr 1fr" : "1fr",
    gap: spacing.md,
    width: "100%",
  };

  const items = spec.items.map((item, i) => {
    const delay = i * staggerFrames;
    const progress = spring({
      frame: Math.max(0, frame - delay),
      fps,
      config: {damping: 18, stiffness: 120},
    });

    return React.createElement(
      "div",
      {
        key: i,
        style: {
          display: "flex",
          gap: spacing.sm,
          alignItems: "flex-start",
          opacity: progress,
          transform: `translateX(${(1 - progress) * 24}px)`,
        },
      },
      React.createElement(
        "div",
        {
          style: {
            flexShrink: 0,
            width: 32,
            height: 32,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: item.icon ? 20 : 10,
            color: theme.accent,
            background: theme.surface,
            borderRadius: radius.small,
            border: `1px solid ${theme.border}`,
          },
        },
        item.icon || "●",
      ),
      React.createElement(
        "div",
        {style: {display: "flex", flexDirection: "column", gap: 4}},
        React.createElement(
          "div",
          {
            style: {
              fontFamily: theme.bodyFont,
              fontSize: typography.bodyLarge,
              fontWeight: 550,
              color: theme.foreground,
              lineHeight: 1.25,
            },
          },
          item.text,
        ),
        item.subtext
          ? React.createElement(
              "div",
              {
                style: {
                  fontFamily: theme.bodyFont,
                  fontSize: typography.body,
                  color: theme.foregroundMuted,
                  lineHeight: 1.35,
                },
              },
              item.subtext,
            )
          : null,
      ),
    );
  });

  return React.createElement("div", {style: container}, ...items);
};
