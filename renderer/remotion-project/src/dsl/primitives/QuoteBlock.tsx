import React from "react";
import type {DSLContext, QuoteElement} from "../types";
import {spacing, radius, typography, shadows} from "../../dynamic-sdk";

type Props = {
  spec: QuoteElement;
  ctx: DSLContext;
};

export const QuoteBlock: React.FC<Props> = ({spec, ctx}) => {
  const {theme} = ctx;
  const variant = spec.style ?? "editorial";

  const isCallout = variant === "callout";
  const isMinimal = variant === "minimal";

  const container: React.CSSProperties = {
    position: "relative",
    padding: isCallout ? "36px 40px" : "0 0 0 28px",
    borderLeft: isMinimal ? "none" : `4px solid ${theme.accent}`,
    background: isCallout ? theme.surface : "transparent",
    borderRadius: isCallout ? radius.large : 0,
    boxShadow: isCallout ? shadows.subtle : "none",
  };

  const quoteText: React.CSSProperties = {
    fontFamily: theme.displayFont,
    fontSize: typography.heading,
    fontWeight: 500,
    fontStyle: "italic",
    lineHeight: 1.35,
    color: theme.foreground,
  };

  const attribution: React.CSSProperties = {
    fontFamily: theme.bodyFont,
    fontSize: typography.body,
    color: theme.foregroundMuted,
    marginTop: spacing.sm,
    fontWeight: 500,
  };

  return React.createElement(
    "div",
    {style: container},
    React.createElement(
      "div",
      {style: quoteText},
      `“${spec.text}”`,
    ),
    spec.attribution
      ? React.createElement("div", {style: attribution}, `— ${spec.attribution}`)
      : null,
  );
};
