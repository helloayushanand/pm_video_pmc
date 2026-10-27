import React from "react";
import type {DSLContext, ElementSpec} from "./types";
import {DSLEntrance} from "./DSLEntrance";

import {
  DisplayTitle,
  BodyCopy,
  SectionLabel,
  AutoFitText,
  MetricValue,
  MetricCard,
  ApprovedAsset,
  typography,
  spacing,
  radius,
} from "../dynamic-sdk";

import {TimelineStrip} from "./primitives/TimelineStrip";
import {BulletList} from "./primitives/BulletList";
import {PortraitFrame} from "./primitives/PortraitFrame";
import {QuoteBlock} from "./primitives/QuoteBlock";
import {OrgTree} from "./primitives/OrgTree";
import {BadgeRow} from "./primitives/BadgeRow";
import {ProgressBar} from "./primitives/ProgressBar";

type Props = {
  spec: ElementSpec;
  ctx: DSLContext;
};

const ROLE_MAP: Record<string, {fontSize: number; fontWeight: number; lineHeight: number; letterSpacing?: number}> = {
  display: {fontSize: typography.displayMedium, fontWeight: 740, lineHeight: 1.04, letterSpacing: -2.6},
  heading: {fontSize: typography.heading, fontWeight: 680, lineHeight: 1.12, letterSpacing: -1},
  subheading: {fontSize: typography.subheading, fontWeight: 600, lineHeight: 1.2},
  body: {fontSize: typography.body, fontWeight: 450, lineHeight: 1.42},
  label: {fontSize: typography.label, fontWeight: 750, lineHeight: 1.3, letterSpacing: 2.7},
  caption: {fontSize: typography.caption, fontWeight: 500, lineHeight: 1.4},
};

const renderInner = (spec: ElementSpec, ctx: DSLContext): React.ReactNode => {
  const {theme} = ctx;

  switch (spec.type) {
    case "text": {
      const role = ROLE_MAP[spec.role] ?? ROLE_MAP.body;
      const isLabel = spec.role === "label";
      const isDisplay = spec.role === "display";
      const color = spec.color || (isLabel ? theme.accent : isDisplay ? theme.foreground : theme.foreground);
      const fontFamily = isDisplay || spec.role === "heading" ? theme.displayFont : theme.bodyFont;
      return React.createElement(
        isDisplay ? "h1" : "div",
        {
          style: {
            margin: 0,
            color,
            fontFamily,
            fontSize: role.fontSize,
            fontWeight: role.fontWeight,
            lineHeight: role.lineHeight,
            letterSpacing: role.letterSpacing,
            textTransform: isLabel ? "uppercase" as const : undefined,
            textAlign: spec.align ?? "left",
            maxWidth: spec.maxWidth,
            overflowWrap: "break-word" as const,
          },
        },
        spec.content,
      );
    }

    case "autofit_text":
      return React.createElement(AutoFitText, {
        text: spec.text,
        theme,
        maximumFontSize: spec.maxFontSize,
        minimumFontSize: spec.minFontSize,
        align: spec.align,
      });

    case "metric":
      return React.createElement(MetricValue, {
        value: spec.value,
        label: spec.label,
        theme,
        emphasis: spec.emphasis,
      });

    case "metric_row": {
      const items = spec.items.map((item, i) => {
        const el = spec.cardStyle
          ? React.createElement(MetricCard, {
              key: i,
              value: item.value,
              label: item.label,
              theme,
              emphasis: item.emphasis,
              delayFrames: Math.round(i * (spec.stagger ?? 0.15) * ctx.fps),
            })
          : React.createElement(MetricValue, {
              key: i,
              value: item.value,
              label: item.label,
              theme,
              emphasis: item.emphasis,
            });
        return el;
      });
      return React.createElement(
        "div",
        {
          style: {
            display: "flex",
            gap: spacing.lg,
            flexWrap: "wrap" as const,
          },
        },
        ...items,
      );
    }

    case "timeline":
      return React.createElement(TimelineStrip, {spec, ctx});

    case "bullet_list":
      return React.createElement(BulletList, {spec, ctx});

    case "portrait": {
      if (!spec.artifactId || !ctx.artifacts.artifacts.find((a) => a.artifactId === spec.artifactId)) {
        return React.createElement("div", {
          style: {width: "100%", flex: "1 1 0", minHeight: 0, borderRadius: 24, background: theme.surface, border: `2px solid ${theme.border}`},
        });
      }
      return React.createElement(PortraitFrame, {spec, ctx});
    }

    case "image": {
      if (!spec.artifactId || !ctx.artifacts.artifacts.find((a) => a.artifactId === spec.artifactId)) {
        return React.createElement("div", {
          style: {width: "100%", height: 200, borderRadius: spec.borderRadius ?? 0, background: theme.surface, border: `1px solid ${theme.border}`},
        });
      }
      return React.createElement(ApprovedAsset, {
        artifactId: spec.artifactId,
        manifest: ctx.artifacts,
        fit: spec.fit,
        style: {borderRadius: spec.borderRadius ?? 0},
      });
    }

    case "quote":
      return React.createElement(QuoteBlock, {spec, ctx});

    case "org_tree":
      return React.createElement(OrgTree, {spec, ctx});

    case "badge_row":
      return React.createElement(BadgeRow, {spec, ctx});

    case "divider":
      return React.createElement("div", {
        style: {
          width: "100%",
          height: spec.thickness ?? 1,
          background: spec.color || theme.border,
        },
      });

    case "spacer":
      return React.createElement("div", {style: {height: spec.height}});

    case "progress_bar":
      return React.createElement(ProgressBar, {spec, ctx});

    default:
      return null;
  }
};

const getEntrance = (spec: ElementSpec) => {
  if ("entrance" in spec && spec.entrance) return spec.entrance;
  return undefined;
};

export const DSLElement: React.FC<Props> = ({spec, ctx}) => {
  const entrance = getEntrance(spec);
  const inner = renderInner(spec, ctx);

  if (entrance) {
    return React.createElement(DSLEntrance, {spec: entrance}, inner);
  }
  return React.createElement(React.Fragment, null, inner);
};
