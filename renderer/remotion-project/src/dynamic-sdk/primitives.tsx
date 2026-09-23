import React from "react";

import {
  Img,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

import {
  radius,
  safeArea,
  shadows,
  spacing,
  typography,
} from "./theme";

import {
  getApprovedArtifact,
} from "./validation";

import type {
  ArtifactManifest,
  ChildrenProps,
  DynamicTheme,
  HorizontalAlignment,
  RevealDirection,
} from "./types";


type SceneFrameProps =
  ChildrenProps & {
    theme: DynamicTheme;
    background?: string;
    showBrand?: boolean;
    showConfidentiality?: boolean;
    sceneLabel?: string;
  };


export const SceneFrame:
React.FC<SceneFrameProps> = ({
  theme,
  background,
  showBrand = true,
  showConfidentiality = true,
  sceneLabel,
  children,
}) => {
  const frame = useCurrentFrame();

  const {
    durationInFrames,
  } = useVideoConfig();

  const opacity = interpolate(
    frame,
    [
      0,
      12,
      Math.max(
        13,
        durationInFrames - 12,
      ),
      durationInFrames,
    ],
    [0, 1, 1, 0],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  const brand = showBrand
    ? React.createElement(
        "div",
        {
          style: {
            position: "absolute",
            left: safeArea.horizontal,
            top: 35,
            color: theme.accent,
            fontFamily: theme.bodyFont,
            fontSize:
              typography.label,
            fontWeight: 700,
            letterSpacing: 2.5,
            textTransform: "uppercase",
          },
        },
        "Positive Moves",
      )
    : null;

  const confidentiality =
    showConfidentiality
      ? React.createElement(
          ConfidentialityLabel,
          {
            text:
              theme.confidentialityText,
            theme,
          },
        )
      : null;

  const label = sceneLabel
    ? React.createElement(
        "div",
        {
          style: {
            position: "absolute",
            left: safeArea.horizontal,
            bottom: 35,
            color:
              theme.foregroundMuted,
            fontFamily:
              theme.bodyFont,
            fontSize:
              typography.caption,
            letterSpacing: 1,
            opacity: 0.72,
          },
        },
        sceneLabel,
      )
    : null;

  const content =
    React.createElement(
      "div",
      {
        style: {
          position: "absolute",
          inset: 0,
          opacity,
        },
      },
      children,
    );

  return React.createElement(
    "div",
    {
      style: {
        position: "absolute",
        inset: 0,
        overflow: "hidden",
        color: theme.foreground,
        fontFamily: theme.bodyFont,
        background:
          background
          || (
            "radial-gradient("
            + "circle at 82% 16%, "
            + theme.accent
            + "22 0%, transparent 32%), "
            + "linear-gradient("
            + "135deg, "
            + theme.background
            + " 0%, "
            + theme.surface
            + " 54%, "
            + theme.background
            + " 100%)"
          ),
      },
    },
    brand,
    confidentiality,
    label,
    content,
  );
};


type SafeAreaProps =
  ChildrenProps & {
    horizontal?: number;
    vertical?: number;
  };


export const SafeArea:
React.FC<SafeAreaProps> = ({
  horizontal = safeArea.horizontal,
  vertical = safeArea.vertical,
  children,
}) =>
  React.createElement(
    "div",
    {
      style: {
        position: "absolute",
        left: horizontal,
        right: horizontal,
        top: vertical,
        bottom: vertical,
        overflow: "hidden",
      },
    },
    children,
  );


type StackProps =
  ChildrenProps & {
    direction?: "row" | "column";
    gap?: number;
    align?: HorizontalAlignment;
    wrap?: boolean;
    style?: React.CSSProperties;
  };


export const Stack:
React.FC<StackProps> = ({
  direction = "column",
  gap = spacing.md,
  align = "left",
  wrap = false,
  style,
  children,
}) => {
  const alignItems =
    align === "left"
      ? "flex-start"
      : align === "right"
        ? "flex-end"
        : "center";

  return React.createElement(
    "div",
    {
      style: {
        display: "flex",
        flexDirection: direction,
        gap,
        alignItems,
        flexWrap:
          wrap
            ? "wrap"
            : "nowrap",
        ...style,
      },
    },
    children,
  );
};


type SplitLayoutProps =
  ChildrenProps & {
    leftRatio?: number;
    gap?: number;
  };


export const SplitLayout:
React.FC<SplitLayoutProps> = ({
  leftRatio = 0.58,
  gap = spacing.xl,
  children,
}) => {
  const childArray =
    React.Children.toArray(
      children,
    );

  return React.createElement(
    "div",
    {
      style: {
        display: "grid",
        gridTemplateColumns:
          leftRatio
          + "fr "
          + (1 - leftRatio)
          + "fr",
        gap,
        width: "100%",
        height: "100%",
        alignItems: "center",
      },
    },
    childArray[0] || null,
    childArray[1] || null,
  );
};


type TextProps = {
  children: React.ReactNode;
  theme: DynamicTheme;
  align?: HorizontalAlignment;
  maxWidth?: number;
  style?: React.CSSProperties;
};


export const SectionLabel:
React.FC<TextProps> = ({
  children,
  theme,
  align = "left",
  maxWidth,
  style,
}) =>
  React.createElement(
    "div",
    {
      style: {
        color: theme.accent,
        fontFamily: theme.bodyFont,
        fontSize: typography.label,
        fontWeight: 750,
        letterSpacing: 2.7,
        textTransform: "uppercase",
        textAlign: align,
        maxWidth,
        ...style,
      },
    },
    children,
  );


export const DisplayTitle:
React.FC<TextProps> = ({
  children,
  theme,
  align = "left",
  maxWidth = 1400,
  style,
}) =>
  React.createElement(
    "h1",
    {
      style: {
        margin: 0,
        color: theme.foreground,
        fontFamily:
          theme.displayFont,
        fontSize:
          typography.displayMedium,
        lineHeight: 1.04,
        fontWeight: 740,
        letterSpacing: -2.6,
        textAlign: align,
        maxWidth,
        overflowWrap: "break-word",
        ...style,
      },
    },
    children,
  );


export const BodyCopy:
React.FC<TextProps> = ({
  children,
  theme,
  align = "left",
  maxWidth = 1250,
  style,
}) =>
  React.createElement(
    "div",
    {
      style: {
        color:
          theme.foregroundMuted,
        fontFamily: theme.bodyFont,
        fontSize: typography.body,
        lineHeight: 1.42,
        fontWeight: 450,
        textAlign: align,
        maxWidth,
        ...style,
      },
    },
    children,
  );


type AutoFitTextProps = {
  text: string;
  theme: DynamicTheme;
  maximumFontSize?: number;
  minimumFontSize?: number;
  maximumCharactersAtFullSize?: number;
  align?: HorizontalAlignment;
  style?: React.CSSProperties;
};


export const AutoFitText:
React.FC<AutoFitTextProps> = ({
  text,
  theme,
  maximumFontSize =
    typography.displayMedium,
  minimumFontSize = 30,
  maximumCharactersAtFullSize = 46,
  align = "left",
  style,
}) => {
  const overflow = Math.max(
    0,
    text.length
      - maximumCharactersAtFullSize,
  );

  const reduction =
    Math.ceil(
      overflow / 12,
    ) * 4;

  const fontSize = Math.max(
    minimumFontSize,
    maximumFontSize
      - reduction,
  );

  return React.createElement(
    "div",
    {
      style: {
        color: theme.foreground,
        fontFamily:
          theme.displayFont,
        fontSize,
        lineHeight: 1.05,
        fontWeight: 740,
        letterSpacing: -2,
        textAlign: align,
        overflowWrap: "break-word",
        ...style,
      },
    },
    text,
  );
};


type MetricValueProps = {
  value: string;
  label?: string;
  theme: DynamicTheme;
  emphasis?:
    | "hero"
    | "primary"
    | "supporting";
  align?: HorizontalAlignment;
};


export const MetricValue:
React.FC<MetricValueProps> = ({
  value,
  label,
  theme,
  emphasis = "primary",
  align = "left",
}) => {
  const sizes = {
    hero: 104,
    primary: 72,
    supporting: 54,
  };

  return React.createElement(
    "div",
    {
      style: {
        display: "flex",
        flexDirection: "column",
        gap: spacing.sm,
        textAlign: align,
      },
    },
    React.createElement(
      "div",
      {
        style: {
          color: theme.accent,
          fontFamily:
            theme.displayFont,
          fontSize:
            sizes[emphasis],
          lineHeight: 0.95,
          fontWeight: 780,
          letterSpacing: -3,
        },
      },
      value,
    ),
    label
      ? React.createElement(
          "div",
          {
            style: {
              color:
                theme.foregroundMuted,
              fontFamily:
                theme.bodyFont,
              fontSize:
                typography.body,
              lineHeight: 1.3,
              maxWidth: 430,
            },
          },
          label,
        )
      : null,
  );
};


type MetricCardProps =
  MetricValueProps & {
    delayFrames?: number;
  };


export const MetricCard:
React.FC<MetricCardProps> = ({
  delayFrames = 0,
  theme,
  ...metricProps
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const progress = spring({
    frame: Math.max(
      0,
      frame - delayFrames,
    ),
    fps,
    config: {
      damping: 18,
      stiffness: 115,
      mass: 0.9,
    },
  });

  const opacity = interpolate(
    progress,
    [0, 1],
    [0, 1],
  );

  const translateY =
    interpolate(
      progress,
      [0, 1],
      [25, 0],
    );

  return React.createElement(
    "div",
    {
      style: {
        padding: "32px 34px",
        borderRadius: radius.large,
        background: theme.surface,
        border:
          "1px solid "
          + theme.border,
        boxShadow: shadows.medium,
        opacity,
        transform:
          "translateY("
          + translateY
          + "px)",
      },
    },
    React.createElement(
      MetricValue,
      {
        theme,
        ...metricProps,
      },
    ),
  );
};


type ApprovedAssetProps = {
  artifactId: string;
  manifest: ArtifactManifest;
  fit?: "cover" | "contain";
  style?: React.CSSProperties;
};


export const ApprovedAsset:
React.FC<ApprovedAssetProps> = ({
  artifactId,
  manifest,
  fit = "cover",
  style,
}) => {
  const artifact =
    getApprovedArtifact(
      manifest,
      artifactId,
    );

  return React.createElement(
    Img,
    {
      src: staticFile(
        artifact.rendererPath,
      ),
      alt: artifact.altText,
      style: {
        width: "100%",
        height: "100%",
        objectFit: fit,
        borderRadius: radius.large,
        ...style,
      },
    },
  );
};


type RevealProps = ChildrenProps & {
  delayFrames?: number;
  durationFrames?: number;
};


export const FadeReveal:
React.FC<RevealProps> = ({
  delayFrames = 0,
  durationFrames = 18,
  children,
}) => {
  const frame = useCurrentFrame();

  const opacity = interpolate(
    frame,
    [
      delayFrames,
      delayFrames
        + durationFrames,
    ],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  return React.createElement(
    "div",
    {
      style: {
        opacity,
      },
    },
    children,
  );
};


type SlideRevealProps =
  RevealProps & {
    direction?: RevealDirection;
    distance?: number;
  };


export const SlideReveal:
React.FC<SlideRevealProps> = ({
  delayFrames = 0,
  durationFrames = 20,
  direction = "up",
  distance = 36,
  children,
}) => {
  const frame = useCurrentFrame();

  const progress = interpolate(
    frame,
    [
      delayFrames,
      delayFrames
        + durationFrames,
    ],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  const x =
    direction === "left"
      ? distance * (1 - progress)
      : direction === "right"
        ? -distance
          * (1 - progress)
        : 0;

  const y =
    direction === "up"
      ? distance * (1 - progress)
      : direction === "down"
        ? -distance
          * (1 - progress)
        : 0;

  return React.createElement(
    "div",
    {
      style: {
        opacity: progress,
        transform:
          "translate("
          + x
          + "px, "
          + y
          + "px)",
      },
    },
    children,
  );
};


type StaggerGroupProps =
  ChildrenProps & {
    delayFrames?: number;
    staggerFrames?: number;
    direction?: RevealDirection;
  };


export const StaggerGroup:
React.FC<StaggerGroupProps> = ({
  delayFrames = 0,
  staggerFrames = 8,
  direction = "up",
  children,
}) => {
  const childArray =
    React.Children.toArray(
      children,
    );

  return React.createElement(
    React.Fragment,
    null,
    ...childArray.map(
      (child, index) =>
        React.createElement(
          SlideReveal,
          {
            key: index,
            delayFrames:
              delayFrames
              + index
              * staggerFrames,
            direction,
          },
          child,
        ),
    ),
  );
};


type ConfidentialityLabelProps = {
  text: string;
  theme: DynamicTheme;
};


export const ConfidentialityLabel:
React.FC<ConfidentialityLabelProps> = ({
  text,
  theme,
}) =>
  React.createElement(
    "div",
    {
      style: {
        position: "absolute",
        right: safeArea.horizontal,
        top: 31,
        zIndex: 50,
        padding: "8px 15px",
        border:
          "1px solid "
          + theme.border,
        borderRadius: radius.pill,
        color:
          theme.foregroundMuted,
        background:
          "rgba(255,255,255,0.48)",
        fontFamily: theme.bodyFont,
        fontSize:
          typography.caption,
        fontWeight: 650,
        letterSpacing: 1.4,
        textTransform: "uppercase",
      },
    },
    text,
  );


type OverflowBoundaryProps =
  ChildrenProps & {
    debug?: boolean;
  };


export const OverflowBoundary:
React.FC<OverflowBoundaryProps> = ({
  debug = false,
  children,
}) =>
  React.createElement(
    "div",
    {
      style: {
        position: "relative",
        width: "100%",
        height: "100%",
        overflow: "hidden",
        outline: debug
          ? "2px dashed #D64545"
          : "none",
      },
    },
    children,
  );
