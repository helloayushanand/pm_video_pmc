import React from "react";
import {spring, useCurrentFrame, useVideoConfig} from "remotion";
import type {DSLContext, OrgTreeElement} from "../types";
import {spacing, radius, typography, shadows} from "../../dynamic-sdk";

type Props = {
  spec: OrgTreeElement;
  ctx: DSLContext;
};

export const OrgTree: React.FC<Props> = ({spec, ctx}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const {theme} = ctx;
  const isRadial = (spec.style ?? "radial") === "radial";

  const centerProgress = spring({
    frame,
    fps,
    config: {damping: 16, stiffness: 100},
  });

  const nodeCard = (
    label: string,
    sublabel: string | undefined,
    isCenter: boolean,
    accent: string,
  ): React.CSSProperties => ({
    padding: isCenter ? "28px 36px" : "18px 24px",
    borderRadius: radius.medium,
    background: isCenter ? theme.surface : theme.surfaceSecondary,
    border: `2px solid ${isCenter ? accent : theme.border}`,
    boxShadow: isCenter ? shadows.medium : shadows.subtle,
    textAlign: "center",
    display: "flex",
    flexDirection: "column",
    gap: 4,
    minWidth: isCenter ? 220 : 140,
  });

  const makeNode = (
    label: string,
    sublabel: string | undefined,
    isCenter: boolean,
    progress: number,
    key: number | string,
  ) =>
    React.createElement(
      "div",
      {
        key,
        style: {
          ...nodeCard(label, sublabel, isCenter, theme.accent),
          opacity: progress,
          transform: `scale(${0.85 + progress * 0.15})`,
        },
      },
      React.createElement(
        "div",
        {
          style: {
            fontFamily: theme.displayFont,
            fontSize: isCenter ? typography.subheading : typography.body,
            fontWeight: 650,
            color: theme.foreground,
          },
        },
        label,
      ),
      sublabel
        ? React.createElement(
            "div",
            {
              style: {
                fontFamily: theme.bodyFont,
                fontSize: typography.caption,
                color: theme.foregroundMuted,
              },
            },
            sublabel,
          )
        : null,
    );

  const childEls = spec.children.map((child, i) => {
    const delay = 8 + i * 6;
    const childProgress = spring({
      frame: Math.max(0, frame - delay),
      fps,
      config: {damping: 18, stiffness: 110},
    });
    return makeNode(child.label, child.sublabel, false, childProgress, i);
  });

  if (isRadial) {
    return React.createElement(
      "div",
      {
        style: {
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: spacing.xl,
          width: "100%",
        },
      },
      makeNode(
        spec.centerNode.label,
        spec.centerNode.sublabel,
        true,
        centerProgress,
        "center",
      ),
      React.createElement(
        "div",
        {
          style: {
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "center",
            gap: spacing.md,
          },
        },
        ...childEls,
      ),
    );
  }

  return React.createElement(
    "div",
    {
      style: {
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: spacing.lg,
        width: "100%",
      },
    },
    makeNode(
      spec.centerNode.label,
      spec.centerNode.sublabel,
      true,
      centerProgress,
      "center",
    ),
    ...childEls,
  );
};
