import React from "react";
import {
  interpolate,
  useCurrentFrame,
} from "remotion";

import {SceneFrame} from "../components/SceneFrame";
import {createTheme} from "../theme/theme";

import type {
  RenderScene,
  ThemeSettings,
} from "../types";

type CandidateIntroProps = {
  scene: RenderScene;
  theme: ThemeSettings;
  candidateName: string;
};

export const CandidateIntro: React.FC<
  CandidateIntroProps
> = ({
  scene,
  theme,
  candidateName,
}) => {
  const frame = useCurrentFrame();
  const colours = createTheme(theme);

  const visualElements =
    scene.props.visual_elements || [];

  const titleElement = visualElements.find(
    (item) =>
      item.element_type === "subheading" ||
      item.element_type === "label" ||
      item.element_type === "body_text",
  );

  const title =
    titleElement?.content ||
    titleElement?.label ||
    scene.props.purpose ||
    "";

  const scale = interpolate(
    frame,
    [0, 28],
    [0.96, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  const initials = candidateName
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part.charAt(0))
    .join("")
    .toUpperCase();

  return (
    <SceneFrame
      theme={theme}
      sceneLabel="Profile"
    >
      <div
        style={{
          position: "absolute",
          left: 120,
          right: 120,
          top: 180,
          bottom: 140,
          display: "flex",
          alignItems: "center",
          gap: 80,
          transform: `scale(${scale})`,
        }}
      >
        <div
          style={{
            flex: 1,
          }}
        >
          <div
            style={{
              color: colours.accent,
              fontSize: 22,
              fontWeight: 720,
              letterSpacing: 3,
              textTransform: "uppercase",
              marginBottom: 24,
            }}
          >
            Executive Candidate Profile
          </div>

          <h1
            style={{
              margin: 0,
              color: colours.primary,
              fontSize: 88,
              lineHeight: 1,
              letterSpacing: -3.5,
              fontWeight: 740,
            }}
          >
            {candidateName}
          </h1>

          {title ? (
            <div
              style={{
                marginTop: 28,
                color: colours.secondary,
                fontSize: 34,
                lineHeight: 1.35,
                maxWidth: 1050,
              }}
            >
              {title}
            </div>
          ) : null}
        </div>

        <div
          style={{
            width: 340,
            height: 340,
            flexShrink: 0,
            borderRadius: "50%",
            background: `
              linear-gradient(
                135deg,
                ${colours.accent},
                ${colours.primary}
              )
            `,
            boxShadow:
              "0 28px 80px rgba(20,20,20,0.18)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#FFFFFF",
            fontSize: 112,
            fontWeight: 760,
          }}
        >
          {initials}
        </div>
      </div>
    </SceneFrame>
  );
};
