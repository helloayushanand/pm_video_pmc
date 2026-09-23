import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import {
  SceneFrame,
  SafeArea,
  DisplayTitle,
  BodyCopy,
  FadeReveal,
  ConfidentialityLabel,
  OverflowBoundary,
  GeneratedSceneProps
} from "../../../dynamic-sdk";

export const IntroEditorialStack: React.FC<GeneratedSceneProps> = (props) => {
  const { context } = props;
  const { durationInFrames, fps, theme } = context;
  const frame = useCurrentFrame();
  const bgColors = [
    "#181b23", // dark bluish gray
    "#2e3044", // purple-gray midtone
    "#232445"  // deeper accent
  ];

  // Fade/dissolve staged reveals
  // Timing: total 8s, 4 elements, with staged delays
  const elementTimings = [
    0,
    Math.round(0.9 * fps), // 0.9s delay to 2nd line
    Math.round(1.8 * fps), // 1.8s delay to 3rd
    Math.round(2.7 * fps)  // 2.7s delay to 4th
  ];
  const revealDur = Math.round(0.7 * fps); // 0.7s fade per line

  // Text values—Defensive read
  const name = "Dushyanth Jayanty";
  const title = "Chief Marketing Officer";
  const employer = "Flipkart";
  const location = "Bangalore";

  // Color/typographic palette as per art direction
  const nameAccent = theme && theme.accent ? theme.accent : "#6c7aff";
  const supportTextColor = "#e7e8ea";
  const mutedTextColor = "#bfc2ce";
  const bgGradient = `linear-gradient(115deg, ${bgColors[0]} 0%, ${bgColors[1]} 68%, ${bgColors[2]} 100%)`;

  // Editorial text sizes
  const nameSize = 72;
  const supportSize = 28;
  const employerSize = 26;

  // Opacity calcs for each staggered fade
  function getOpacity(startFrame: number) {
    return interpolate(
      frame,
      [startFrame, startFrame + revealDur],
      [0, 1],
      { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );
  }

  // Fade out in last ~0.5s (18 frames at 36 fps)
  const outroDur = Math.round(0.5 * fps);
  const outroStart = durationInFrames - outroDur;
  const outroOpacity = interpolate(
    frame,
    [outroStart, durationInFrames],
    [1, 0.0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  return React.createElement(
    SceneFrame,
    {
      theme: theme,
      background: bgGradient
    },
    React.createElement(
      OverflowBoundary,
      null,
      React.createElement(
        SafeArea,
        {
          horizontal: 0.07,
          vertical: 0.13
        },
        React.createElement(
          "div",
          {
            style: {
              width: "100%",
              maxWidth: 780,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 38,
              opacity: outroOpacity,
              transition: "opacity 400ms",
              position: "relative",
              minHeight: "70vh"
            }
          },
          React.createElement(
            FadeReveal,
            {
              delayFrames: elementTimings[0],
              durationFrames: revealDur
            },
            React.createElement(
              DisplayTitle,
              {
                theme: theme,
                style: {
                  color: nameAccent,
                  fontSize: nameSize,
                  fontWeight: 600,
                  letterSpacing: -1,
                  lineHeight: 1.07,
                  textAlign: "center",
                  textShadow: "0px 2px 20px rgba(36,38,63,0.17)",
                  filter: "drop-shadow(0 2px 12px #01011455)"
                },
                role: "heading"
              },
              name
            )
          ),
          React.createElement(
            FadeReveal,
            {
              delayFrames: elementTimings[1],
              durationFrames: revealDur
            },
            React.createElement(
              BodyCopy,
              {
                theme: theme,
                style: {
                  color: supportTextColor,
                  fontSize: supportSize,
                  fontWeight: 400,
                  letterSpacing: 0.1,
                  lineHeight: 1.19,
                  textAlign: "center",
                  marginTop: 18,
                  marginBottom: 0
                }
              },
              title
            )
          ),
          React.createElement(
            FadeReveal,
            {
              delayFrames: elementTimings[2],
              durationFrames: revealDur
            },
            React.createElement(
              BodyCopy,
              {
                theme: theme,
                style: {
                  color: mutedTextColor,
                  fontSize: employerSize,
                  fontWeight: 400,
                  letterSpacing: 0.08,
                  lineHeight: 1.15,
                  textAlign: "center",
                  marginTop: 15,
                  marginBottom: 0,
                  textTransform: "none"
                }
              },
              employer
            )
          ),
          React.createElement(
            FadeReveal,
            {
              delayFrames: elementTimings[3],
              durationFrames: revealDur
            },
            React.createElement(
              BodyCopy,
              {
                theme: theme,
                style: {
                  color: mutedTextColor,
                  fontSize: employerSize,
                  opacity: 0.90,
                  fontWeight: 400,
                  letterSpacing: 0.06,
                  lineHeight: 1.13,
                  textAlign: "center",
                  marginTop: 10,
                  textTransform: "none"
                }
              },
              location
            )
          ),
          React.createElement(
            "div",
            {
              style: {
                position: "absolute",
                left: 0,
                right: 0,
                bottom: 24,
                width: "100%",
                display: "flex",
                justifyContent: "center",
                pointerEvents: "none"
              }
            },
            React.createElement(
              ConfidentialityLabel,
              {
                text: theme.confidentialityText,
                theme: theme
              }
            )
          )
        )
      )
    )
  );
};
