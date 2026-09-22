import React from "react";
import {
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type {ThemeSettings} from "../types";
import {createTheme} from "../theme/theme";
import {ConfidentialityLabel} from "./ConfidentialityLabel";

type Props = {
  theme: ThemeSettings;
  children: React.ReactNode;
  sceneLabel?: string;
};

export const SceneFrame: React.FC<Props> = ({
  theme,
  children,
  sceneLabel,
}) => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  const colours = createTheme(theme);

  const opacity = interpolate(
    frame,
    [
      0,
      14,
      Math.max(15, durationInFrames - 14),
      durationInFrames,
    ],
    [0, 1, 1, 0],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  const translateY = interpolate(
    frame,
    [0, 18],
    [26, 0],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        background: `
          radial-gradient(
            circle at 84% 15%,
            ${colours.accent}22 0%,
            transparent 30%
          ),
          linear-gradient(
            135deg,
            ${colours.background} 0%,
            #FFFFFF 52%,
            ${colours.background} 100%
          )
        `,
        color: colours.primary,
        fontFamily: colours.fontFamily,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          position: "absolute",
          left: 46,
          top: 39,
          color: colours.accent,
          fontSize: 17,
          fontWeight: 700,
          letterSpacing: 2.5,
          textTransform: "uppercase",
        }}
      >
        Positive Moves
      </div>

      {sceneLabel ? (
        <div
          style={{
            position: "absolute",
            left: 84,
            bottom: 46,
            color: colours.secondary,
            fontSize: 18,
            letterSpacing: 1,
            opacity: 0.72,
          }}
        >
          {sceneLabel}
        </div>
      ) : null}

      {theme.confidential ? (
        <ConfidentialityLabel
          text={
            theme.confidentiality_text ||
            "Private and Confidential"
          }
          colour={colours.secondary}
        />
      ) : null}

      <div
        style={{
          position: "absolute",
          left: 0,
          bottom: 0,
          width: "100%",
          height: 9,
          background: colours.accent,
        }}
      />

      <div
        style={{
          position: "absolute",
          inset: 0,
          opacity,
          transform: `translateY(${translateY}px)`,
        }}
      >
        {children}
      </div>
    </div>
  );
};
