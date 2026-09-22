import React from "react";
import type {
  RenderScene,
  ThemeSettings,
  VisualElement,
} from "../types";
import {SceneFrame} from "../components/SceneFrame";
import {MetricCard} from "../components/MetricCard";
import {createTheme} from "../theme/theme";

type Props = {
  scene: RenderScene;
  theme: ThemeSettings;
  candidateName: string;
};

const getText = (element: VisualElement) => {
  return (
    element.content ||
    element.value ||
    element.label ||
    ""
  );
};

export const GenericScene: React.FC<Props> = ({
  scene,
  theme,
  candidateName,
}) => {
  const colours = createTheme(theme);

  const elements = [
    ...(scene.props.visual_elements || []),
  ].sort(
    (first, second) =>
      (first.display_order || 0) -
      (second.display_order || 0),
  );

  const headings = elements.filter(
    (element) =>
      element.element_type === "heading" ||
      element.element_type === "subheading",
  );

  const metrics = elements.filter(
    (element) => element.element_type === "metric",
  );

  const bodyItems = elements.filter(
    (element) =>
      ![
        "heading",
        "subheading",
        "metric",
        "image",
        "logo",
        "confidentiality_marker",
      ].includes(element.element_type || ""),
  );

  const primaryHeading =
    getText(headings[0] || {}) ||
    scene.props.purpose ||
    candidateName;

  const supportingHeading = headings[1]
    ? getText(headings[1])
    : null;

  return (
    <SceneFrame
      theme={theme}
      sceneLabel={scene.component}
    >
      <div
        style={{
          position: "absolute",
          left: 110,
          right: 110,
          top: 155,
          bottom: 110,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
        }}
      >
        <div
          style={{
            color: colours.accent,
            fontSize: 19,
            fontWeight: 700,
            letterSpacing: 2,
            textTransform: "uppercase",
            marginBottom: 20,
          }}
        >
          Candidate Snapshot
        </div>

        <h1
          style={{
            margin: 0,
            maxWidth: 1450,
            color: colours.primary,
            fontSize: metrics.length > 0 ? 60 : 72,
            lineHeight: 1.06,
            fontWeight: 720,
            letterSpacing: -2.4,
          }}
        >
          {primaryHeading}
        </h1>

        {supportingHeading ? (
          <div
            style={{
              marginTop: 20,
              color: colours.secondary,
              fontSize: 29,
              lineHeight: 1.35,
              maxWidth: 1350,
            }}
          >
            {supportingHeading}
          </div>
        ) : null}

        {metrics.length > 0 ? (
          <div
            style={{
              display: "flex",
              gap: 25,
              marginTop: 52,
              flexWrap: "wrap",
            }}
          >
            {metrics.slice(0, 4).map((metric, index) => (
              <MetricCard
                key={
                  metric.element_id ||
                  `metric-${index}`
                }
                value={
                  metric.value ||
                  metric.content ||
                  ""
                }
                label={metric.label}
                accentColour={colours.accent}
                delayFrames={index * 9}
              />
            ))}
          </div>
        ) : null}

        {bodyItems.length > 0 ? (
          <div
            style={{
              display: "grid",
              gridTemplateColumns:
                bodyItems.length > 2
                  ? "repeat(2, minmax(0, 1fr))"
                  : "1fr",
              gap: 22,
              marginTop: 44,
              maxWidth: 1450,
            }}
          >
            {bodyItems.slice(0, 6).map((item, index) => (
              <div
                key={
                  item.element_id ||
                  `body-${index}`
                }
                style={{
                  padding: "23px 27px",
                  borderLeft: `5px solid ${colours.accent}`,
                  borderRadius: 14,
                  background: "rgba(255,255,255,0.70)",
                  color: colours.primary,
                  fontSize: 27,
                  lineHeight: 1.35,
                  boxShadow:
                    "0 10px 32px rgba(20,20,20,0.05)",
                }}
              >
                {getText(item)}
              </div>
            ))}
          </div>
        ) : null}

        {elements.length === 0 ? (
          <div
            style={{
              marginTop: 34,
              maxWidth: 1420,
              color: colours.secondary,
              fontSize: 31,
              lineHeight: 1.5,
            }}
          >
            {scene.props.voiceover}
          </div>
        ) : null}
      </div>
    </SceneFrame>
  );
};
