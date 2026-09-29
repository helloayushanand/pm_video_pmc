import React from "react";

import {
  AbsoluteFill,
  Audio,
  Sequence,
  staticFile,
} from "remotion";

import {
  CandidateIntro,
} from "./scenes/CandidateIntro";

import {
  ClosingScene,
} from "./scenes/ClosingScene";

import {
  GenericScene,
} from "./scenes/GenericScene";

import {
  generatedSceneRegistry,
} from "./generated-current";

import {
  defaultDynamicTheme,
} from "./dynamic-sdk";

import type {
  GeneratedSceneProps,
  ApprovedArtifact,
  AssetType,
  DynamicTheme,
} from "./dynamic-sdk";

import type {
  CandidateVideoProps,
  RenderScene,
  SceneArtifact,
  ThemeSettings,
} from "./types";


/**
 * Convert the main renderer theme into the Dynamic SDK theme
 * expected by AI-generated scene components.
 */
const toDynamicTheme = (
  theme: ThemeSettings,
): DynamicTheme => {
  return {
    themeId:
      theme.theme_id ||
      defaultDynamicTheme.themeId,

    background:
      theme.background_colour ||
      defaultDynamicTheme.background,

    surface:
      theme.surface_colour ||
      defaultDynamicTheme.surface,

    surfaceSecondary:
      theme.surface_secondary_colour ||
      defaultDynamicTheme.surfaceSecondary,

    foreground:
      theme.primary_colour ||
      defaultDynamicTheme.foreground,

    foregroundMuted:
      theme.secondary_colour ||
      defaultDynamicTheme.foregroundMuted,

    accent:
      theme.accent_colour ||
      defaultDynamicTheme.accent,

    accentSecondary:
      theme.accent_secondary_colour ||
      defaultDynamicTheme.accentSecondary,

    border:
      defaultDynamicTheme.border,

    displayFont:
      theme.display_font_family ||
      theme.font_family ||
      defaultDynamicTheme.displayFont,

    bodyFont:
      theme.font_family ||
      defaultDynamicTheme.bodyFont,

    confidentialityText:
      theme.confidentiality_text ||
      defaultDynamicTheme.confidentialityText,
  };
};


/**
 * Convert artifact types from the master render contract into
 * the stricter Dynamic SDK artifact type.
 */
const toAssetType = (
  value?: string | null,
): AssetType => {
  switch (value) {
    case "portrait":
      return "portrait";

    case "logo":
      return "logo";

    case "chart":
      return "chart";

    case "diagram":
      return "diagram";

    case "background":
      return "background";

    case "icon":
      return "icon";

    case "image":
      return "image";

    default:
      return "image";
  }
};


/**
 * Convert a master-render artifact into the artifact contract
 * used by generated components.
 */
const toApprovedArtifact = (
  artifact: SceneArtifact,
): ApprovedArtifact | null => {
  if (
    !artifact.approved ||
    !artifact.renderer_path
  ) {
    return null;
  }

  return {
    artifactId:
      artifact.artifact_id,

    assetType:
      toAssetType(
        artifact.artifact_type,
      ),

    rendererPath:
      artifact.renderer_path,

    approved:
      true,

    altText:
      artifact.alt_text ||
      artifact.artifact_id,
  };
};


/**
 * Build GeneratedSceneProps from the master render scene.
 *
 * This is the bridge between:
 *
 * RenderSpecification
 *
 * and
 *
 * AI-generated Remotion components.
 */
const buildGeneratedSceneProps = (
  scene: RenderScene,
  props: CandidateVideoProps,
): GeneratedSceneProps => {
  const approvedArtifacts =
    (
      scene.props.artifacts || []
    )
      .map(
        toApprovedArtifact,
      )
      .filter(
        (
          artifact,
        ): artifact is ApprovedArtifact =>
          artifact !== null,
      );

  return {
    context: {
      sceneId:
        scene.scene_id,

      candidateName:
        props.renderSpec
          .candidate_name,

      durationInFrames:
        scene.duration_frames,

      fps:
        props.renderSpec
          .video
          .fps,

      theme:
        toDynamicTheme(
          props.renderSpec.theme,
        ),

      artifacts: {
        artifacts:
          approvedArtifacts,
      },
    },

    content: {
      /**
       * Only viewer-facing or approved factual content
       * is supplied here.
       *
       * renderer_instructions and purpose are
       * intentionally excluded.
       */

      display:
        scene.props.display || {},

      visualElements:
        scene.props
          .visual_elements || [],

      approvedFacts:
        scene.props[
          "approved_facts"
        ] || [],

      voiceover:
        scene.props.voiceover || "",
    },
  };
};


/**
 * Render a trusted library/fallback scene.
 */
const renderLibraryScene = (
  scene: RenderScene,
  props: CandidateVideoProps,
): React.ReactElement => {
  const sceneProps = {
    scene,

    theme:
      props.renderSpec.theme,

    candidateName:
      props.renderSpec
        .candidate_name,
  };

  if (
    scene.component ===
    "CandidateIntro"
  ) {
    return React.createElement(
      CandidateIntro,
      sceneProps,
    );
  }

  if (
    scene.component ===
    "ClosingScene"
  ) {
    return React.createElement(
      ClosingScene,
      sceneProps,
    );
  }

  /**
   * GenericScene is now the final library fallback.
   *
   * GenericScene understands semantic visual elements such as:
   *
   * timeline
   * metric
   * organisation_chart
   *
   * but generated components are preferred whenever available.
   */
  return React.createElement(
    GenericScene,
    sceneProps,
  );
};


/**
 * Resolve the best renderer for one scene.
 *
 * Priority:
 *
 * 1. Generated component
 * 2. Trusted library component
 * 3. Generic semantic fallback
 */
const renderScene = (
  scene: RenderScene,
  props: CandidateVideoProps,
): React.ReactElement => {
  const registryKey =
    scene.generated_component_key ||
    scene.scene_id;

  const GeneratedComponent =
    generatedSceneRegistry[
      registryKey
    ];

  const shouldUseGenerated =
    scene.renderer_strategy ===
      "generated_component" &&
    Boolean(
      GeneratedComponent,
    );

  if (
    shouldUseGenerated &&
    GeneratedComponent
  ) {
    const generatedProps =
      buildGeneratedSceneProps(
        scene,
        props,
      );

    return React.createElement(
      GeneratedComponent,
      generatedProps,
    );
  }

  /**
   * Generated component unavailable or the scene was explicitly
   * resolved as a library scene.
   *
   * Fall back deterministically without failing the entire video.
   */
  return renderLibraryScene(
    scene,
    props,
  );
};


export const CandidateVideo:
React.FC<CandidateVideoProps> = (
  props,
) => {
  const {
    renderSpec,
  } = props;

  const audioVolume =
    renderSpec.audio.volume ?? 1;

  const audioElement =
    React.createElement(
      Audio,
      {
        src:
          staticFile(
            "generated/voiceover.mp3",
          ),

        volume:
          audioVolume,

        startFrom:
          renderSpec.audio
            .start_frame || 0,
      },
    );

  const sceneElements =
    renderSpec.scenes.map(
      (
        scene,
      ) =>
        React.createElement(
          Sequence,
          {
            key:
              scene.scene_id,

            from:
              scene.start_frame,

            durationInFrames:
              scene.duration_frames,

            premountFor:
              30,
          },

          renderScene(
            scene,
            props,
          ),
        ),
    );

  return React.createElement(
    AbsoluteFill,
    {
      style: {
        backgroundColor:
          renderSpec
            .theme
            .background_colour ||
          "#F5F4F1",
      },
    },

    audioElement,

    ...sceneElements,
  );
};