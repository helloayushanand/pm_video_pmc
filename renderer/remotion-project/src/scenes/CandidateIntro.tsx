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
  VisualElement,
} from "../types";

type CandidateIntroProps = {
  scene: RenderScene;
  theme: ThemeSettings;
  candidateName: string;
};

/**
 * Return visible text from an approved visual element.
 *
 * Renderer metadata such as scene purpose is deliberately
 * excluded from this function.
 */
const getText = (
  element?: VisualElement,
): string => {
  if (!element) {
    return "";
  }

  return (
    element.content ||
    element.value ||
    element.label ||
    ""
  );
};

export const CandidateIntro: React.FC<
  CandidateIntroProps
> = ({
  scene,
  theme,
  candidateName,
}) => {
  const frame = useCurrentFrame();

  const colours = createTheme(
    theme,
  );

  const visualElements =
    scene.props.visual_elements || [];

  /*
   * Viewer-facing content hierarchy:
   *
   * 1. scene.props.display
   * 2. approved visual elements
   * 3. candidateName
   *
   * scene.props.purpose is NEVER rendered.
   */

  const headingElement =
    visualElements.find(
      (item) =>
        item.element_type ===
        "heading",
    );

  const subheadingElement =
    visualElements.find(
      (item) =>
        item.element_type ===
          "subheading" ||
        item.element_type ===
          "body_text",
    );

  const labelElements =
    visualElements.filter(
      (item) =>
        item.element_type ===
        "label",
    );

  const display =
    scene.props.display;

  const eyebrow =
    display?.eyebrow ||
    "Executive Candidate Profile";

  const headline =
    display?.headline ||
    getText(
      headingElement,
    ) ||
    candidateName;

  const supportingText =
    display?.supporting_text ||
    getText(
      subheadingElement,
    );

  /*
   * Optional short factual label such
   * as location.
   */
  const secondaryLabel =
    getText(
      labelElements[0],
    );

  /*
   * Intro motion.
   */

  const entrance =
    interpolate(
      frame,
      [0, 26],
      [0, 1],
      {
        extrapolateLeft:
          "clamp",
        extrapolateRight:
          "clamp",
      },
    );

  const scale =
    interpolate(
      entrance,
      [0, 1],
      [0.965, 1],
    );

  const translateY =
    interpolate(
      entrance,
      [0, 1],
      [24, 0],
    );

  const textOpacity =
    interpolate(
      frame,
      [4, 22],
      [0, 1],
      {
        extrapolateLeft:
          "clamp",
        extrapolateRight:
          "clamp",
      },
    );

  const supportingOpacity =
    interpolate(
      frame,
      [14, 32],
      [0, 1],
      {
        extrapolateLeft:
          "clamp",
        extrapolateRight:
          "clamp",
      },
    );

  /*
   * Use initials only as the deterministic
   * fallback visual.
   *
   * When an approved portrait is connected
   * later, the asset renderer can replace
   * this block.
   */

  const initials =
    candidateName
      .split(" ")
      .filter(Boolean)
      .slice(0, 2)
      .map(
        (part) =>
          part.charAt(0),
      )
      .join("")
      .toUpperCase();

  return (
    <SceneFrame
      theme={theme}
      sceneLabel="Profile"
    >
      <div
        style={{
          position:
            "absolute",

          left: 120,
          right: 120,
          top: 160,
          bottom: 130,

          display: "grid",

          gridTemplateColumns:
            "minmax(0, 1.45fr) minmax(300px, 0.55fr)",

          alignItems:
            "center",

          gap: 90,

          transform:
            `translateY(${translateY}px) scale(${scale})`,

          opacity:
            entrance,
        }}
      >
        <div
          style={{
            minWidth: 0,
          }}
        >
          <div
            style={{
              color:
                colours.accent,

              fontSize: 20,

              fontWeight: 760,

              letterSpacing: 3,

              textTransform:
                "uppercase",

              marginBottom: 28,

              opacity:
                textOpacity,
            }}
          >
            {eyebrow}
          </div>

          <h1
            style={{
              margin: 0,

              maxWidth: 1100,

              color:
                colours.primary,

              fontSize: 82,

              lineHeight: 1.02,

              letterSpacing:
                -3.2,

              fontWeight: 760,

              opacity:
                textOpacity,
            }}
          >
            {headline}
          </h1>

          {supportingText ? (
            <div
              style={{
                marginTop: 28,

                maxWidth: 1000,

                color:
                  colours.secondary,

                fontSize: 33,

                lineHeight: 1.32,

                fontWeight: 500,

                opacity:
                  supportingOpacity,
              }}
            >
              {supportingText}
            </div>
          ) : null}

          {secondaryLabel ? (
            <div
              style={{
                display:
                  "inline-flex",

                alignItems:
                  "center",

                marginTop: 30,

                padding:
                  "10px 16px",

                borderRadius:
                  999,

                color:
                  colours.primary,

                background:
                  "rgba(255,255,255,0.66)",

                border:
                  `1px solid ${colours.accent}`,

                fontSize: 19,

                fontWeight: 650,

                letterSpacing:
                  0.3,

                opacity:
                  supportingOpacity,
              }}
            >
              {secondaryLabel}
            </div>
          ) : null}
        </div>

        <div
          style={{
            position:
              "relative",

            width: 350,
            height: 350,

            justifySelf:
              "end",

            flexShrink: 0,

            borderRadius:
              "50%",

            background: `
              linear-gradient(
                145deg,
                ${colours.accent},
                #315D78 54%,
                ${colours.primary}
              )
            `,

            boxShadow:
              "0 28px 80px rgba(20,20,20,0.18)",

            display: "flex",

            alignItems:
              "center",

            justifyContent:
              "center",

            color:
              "#FFFFFF",

            fontSize: 108,

            fontWeight: 760,

            letterSpacing: -4,

            overflow:
              "hidden",
          }}
        >
          <div
            style={{
              position:
                "absolute",

              inset: 18,

              border:
                "1px solid rgba(255,255,255,0.30)",

              borderRadius:
                "50%",
            }}
          />

          <div
            style={{
              position:
                "absolute",

              width: 115,
              height: 115,

              right: -20,
              top: 18,

              borderRadius:
                "50%",

              background:
                "rgba(255,255,255,0.10)",
            }}
          />

          <span
            style={{
              position:
                "relative",

              zIndex: 2,
            }}
          >
            {initials}
          </span>
        </div>
      </div>
    </SceneFrame>
  );
};