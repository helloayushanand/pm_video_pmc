import React from "react";

import {
  CalculateMetadataFunction,
  Composition,
} from "remotion";

import {CandidateVideo} from "./CandidateVideo";

import type {
  CandidateVideoProps,
} from "./types";

/**
 * Default props exist only for Remotion Studio preview
 * and composition metadata calculation.
 *
 * Production rendering supplies the actual renderSpec
 * through render-props.json.
 */
const defaultProps: CandidateVideoProps = {
  renderSpec: {
    schema_version: "2.0",

    render_id:
      "preview-render",

    candidate_name:
      "Candidate Name",

    video: {
      width: 1920,
      height: 1080,
      fps: 30,
      duration_frames: 300,
    },

    theme: {
      theme_id:
        "positive_moves_premium_v2",

      primary_colour:
        "#111318",

      secondary_colour:
        "#5F6872",

      background_colour:
        "#F5F4F1",

      accent_colour:
        "#B79A5B",

      accent_secondary_colour:
        "#315D78",

      accent_tertiary_colour:
        "#00A79D",

      surface_colour:
        "#FFFFFF",

      surface_secondary_colour:
        "#E9E4DA",

      font_family:
        "Inter, Arial, sans-serif",

      display_font_family:
        "Inter, Arial, sans-serif",

      confidential: true,

      confidentiality_text:
        "Private and Confidential",
    },

    audio: {
      source_path: "",

      duration_seconds: 10,

      start_frame: 0,

      volume: 1,
    },

    scenes: [
      {
        scene_id:
          "preview-scene",

        component:
          "CandidateIntro",

        renderer_strategy:
          "library_component",

        generated_component_key:
          null,

        variant:
          "default",

        start_frame: 0,

        duration_frames: 300,

        props: {
          /*
           * Explicit viewer-facing copy.
           */
          display: {
            eyebrow:
              "Executive Candidate Profile",

            headline:
              "Candidate Name",

            supporting_text:
              "Executive profile preview",
          },

          /*
           * Approved visual data.
           */
          visual_elements: [
            {
              element_id:
                "preview-title",

              element_type:
                "heading",

              content:
                "Candidate Name",

              label:
                "Candidate name",

              display_order: 1,
            },

            {
              element_id:
                "preview-role",

              element_type:
                "subheading",

              content:
                "Executive Role",

              label:
                "Current role",

              display_order: 2,
            },

            {
              element_id:
                "preview-location",

              element_type:
                "label",

              content:
                "Location",

              label:
                "Location",

              display_order: 3,
            },
          ],

          artifacts: [],

          /*
           * Renderer-only metadata.
           *
           * Nothing here may be displayed directly.
           */
          renderer_instructions: {
            scene_purpose:
              "Preview the executive candidate introduction composition.",

            visual_story:
              "Use a clean editorial executive-profile introduction.",

            layout_intent:
              "Asymmetric editorial introduction.",

            animation_intent:
              "Measured progressive reveal.",

            transition_in:
              "cut",

            transition_out:
              "cross_dissolve",

            background_variant:
              "dark_gradient",

            do_not_render_as_text:
              true,
          },

          /*
           * Legacy field intentionally blank.
           *
           * Renderer components must never use this
           * as viewer-facing copy.
           */
          purpose: "",

          voiceover: "",

          transition_in:
            "cut",

          transition_out:
            "cross_dissolve",

          background_variant:
            "dark_gradient",
        },

        events: [],
      },
    ],

    assets: [],

    output_path: "",

    metadata: {
      preview_mode: true,

      render_contract:
        "viewer_copy_separated_from_renderer_instructions_v2",
    },
  },
};

/**
 * Allow the production render specification
 * to determine composition dimensions and duration.
 */
const calculateMetadata: CalculateMetadataFunction<
  CandidateVideoProps
> = ({
  props,
}) => {
  const video =
    props.renderSpec.video;

  return {
    durationInFrames:
      Math.max(
        1,
        video.duration_frames,
      ),

    fps:
      video.fps,

    width:
      video.width,

    height:
      video.height,
  };
};

export const RemotionRoot: React.FC =
  () => {
    return (
      <Composition
        id="CandidateVideo"

        component={
          CandidateVideo
        }

        /*
         * These values are only initial
         * composition defaults.
         *
         * calculateMetadata replaces them
         * using the incoming render spec.
         */
        durationInFrames={
          300
        }

        fps={
          30
        }

        width={
          1920
        }

        height={
          1080
        }

        defaultProps={
          defaultProps
        }

        calculateMetadata={
          calculateMetadata
        }
      />
    );
  };