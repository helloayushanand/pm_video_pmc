import React from "react";
import {
  interpolate,
  useCurrentFrame,
} from "remotion";
import type {
  RenderScene,
  ThemeSettings,
} from "../types";
import {SceneFrame} from "../components/SceneFrame";
import {createTheme} from "../theme/theme";

type Props = {
  scene: RenderScene;
  theme: ThemeSettings;
  candidateName: string;
};

export const ClosingScene: React.FC<Props> = ({
  scene,
  theme,
  candidateName,
}) => {
  const frame = useCurrentFrame();
  const colours = createTheme(theme);

  const opacity = interpolate(
    frame,
    [0, 20],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  return (
    <SceneFrame theme={theme}>
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          textAlign: "center",
          opacity,
        }}
      >
        <div
          style={{
            color: colours.accent,
            fontSize: 25,
            fontWeight: 700,
            letterSpacing: 4,
            textTransform: "uppercase",
            marginBottom: 30,
          }}
        >
          Positive Moves
        </div>

        <h1
          style={{
            margin: 0,
            maxWidth: 1300,
            color: colours.primary,
            fontSize: 66,
            lineHeight: 1.12,
            letterSpacing: -2,
          }}
        >
          Full candidate dossier shared separately.
        </h1>

        <div
          style={{
            marginTop: 30,
            color: colours.secondary,
            fontSize: 29,
          }}
        >
          {candidateName}
        </div>
      </div>
    </SceneFrame>
  );
};
