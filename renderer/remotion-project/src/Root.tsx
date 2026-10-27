import React from "react";

import {
  CalculateMetadataFunction,
  Composition,
} from "remotion";

import {DSLVideo, getTotalDuration} from "./dsl";
import {testVideoSpec} from "./dsl/testVideoSpec";

const DSL_FPS = 30;

const DSLTestVideo: React.FC = () => (
  <DSLVideo videoSpec={testVideoSpec} fps={DSL_FPS} />
);

type DSLRenderProps = {
  videoSpec: import("./dsl/types").VideoSpec;
  artifacts?: import("./dynamic-sdk").ArtifactManifest;
  sceneAudio?: Record<string, string>;
};

const DSLRenderVideo: React.FC<DSLRenderProps> = ({videoSpec, artifacts, sceneAudio}) => (
  <DSLVideo videoSpec={videoSpec} fps={DSL_FPS} artifacts={artifacts} sceneAudio={sceneAudio} />
);

const calculateDSLMetadata: CalculateMetadataFunction<DSLRenderProps> = ({
  props,
}) => ({
  durationInFrames: getTotalDuration(props.videoSpec, DSL_FPS),
  fps: DSL_FPS,
  width: 1920,
  height: 1080,
});

const defaultDSLProps: DSLRenderProps = {
  videoSpec: testVideoSpec,
};

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="DSLTest"
        component={DSLTestVideo}
        durationInFrames={getTotalDuration(testVideoSpec, DSL_FPS)}
        fps={DSL_FPS}
        width={1920}
        height={1080}
      />
      <Composition
        id="DSLRender"
        component={DSLRenderVideo}
        durationInFrames={getTotalDuration(testVideoSpec, DSL_FPS)}
        fps={DSL_FPS}
        width={1920}
        height={1080}
        defaultProps={defaultDSLProps}
        calculateMetadata={calculateDSLMetadata}
      />
    </>
  );
};
