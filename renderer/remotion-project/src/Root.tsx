import React from "react";
import {
  CalculateMetadataFunction,
  Composition,
} from "remotion";
import {CandidateVideo} from "./CandidateVideo";
import type {CandidateVideoProps} from "./types";

const defaultProps: CandidateVideoProps = {
  renderSpec: {
    schema_version: "1.0",
    render_id: "preview-render",
    candidate_name: "Candidate Name",
    video: {
      width: 1920,
      height: 1080,
      fps: 30,
      duration_frames: 300,
    },
    theme: {
      theme_id: "positive_moves_premium_v1",
      primary_colour: "#111111",
      secondary_colour: "#656565",
      background_colour: "#F5F4F1",
      accent_colour: "#B79A5B",
      font_family: "Inter",
      confidential: true,
      confidentiality_text: "Private and Confidential",
    },
    audio: {
      source_path: "",
      duration_seconds: 10,
      start_frame: 0,
      volume: 1,
    },
    scenes: [
      {
        scene_id: "preview-scene",
        component: "CandidateIntro",
        variant: "default",
        start_frame: 0,
        duration_frames: 300,
        props: {
          purpose: "Executive candidate profile",
          visual_elements: [],
        },
        events: [],
      },
    ],
    assets: [],
    output_path: "",
    metadata: {},
  },
};

const calculateMetadata: CalculateMetadataFunction<
  CandidateVideoProps
> = ({props}) => {
  const video = props.renderSpec.video;

  return {
    durationInFrames: Math.max(
      1,
      video.duration_frames,
    ),
    fps: video.fps,
    width: video.width,
    height: video.height,
  };
};

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="CandidateVideo"
      component={CandidateVideo}
      durationInFrames={300}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={defaultProps}
      calculateMetadata={calculateMetadata}
    />
  );
};
