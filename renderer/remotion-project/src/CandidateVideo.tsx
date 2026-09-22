import React from "react";
import {
  AbsoluteFill,
  Audio,
  Sequence,
  staticFile,
} from "remotion";

import {CandidateIntro} from "./scenes/CandidateIntro";
import {ClosingScene} from "./scenes/ClosingScene";
import {GenericScene} from "./scenes/GenericScene";

import type {
  CandidateVideoProps,
  RenderScene,
} from "./types";

const renderScene = (
  scene: RenderScene,
  props: CandidateVideoProps,
): React.ReactElement => {
  const sceneProps = {
    scene,
    theme: props.renderSpec.theme,
    candidateName: props.renderSpec.candidate_name,
  };

  if (scene.component === "CandidateIntro") {
    return React.createElement(CandidateIntro, sceneProps);
  }

  if (scene.component === "ClosingScene") {
    return React.createElement(ClosingScene, sceneProps);
  }

  return React.createElement(GenericScene, sceneProps);
};

export const CandidateVideo: React.FC<CandidateVideoProps> = (props) => {
  const {renderSpec} = props;
  const audioVolume = renderSpec.audio.volume ?? 1;

  const audioElement = React.createElement(Audio, {
    src: staticFile("generated/voiceover.mp3"),
    volume: audioVolume,
    startFrom: 0,
  });

  const sceneElements = renderSpec.scenes.map((scene) =>
    React.createElement(
      Sequence,
      {
        key: scene.scene_id,
        from: scene.start_frame,
        durationInFrames: scene.duration_frames,
        premountFor: 30,
      },
      renderScene(scene, props),
    ),
  );

  return React.createElement(
    AbsoluteFill,
    {
      style: {
        backgroundColor:
          renderSpec.theme.background_colour || "#F5F4F1",
      },
    },
    audioElement,
    ...sceneElements,
  );
};
