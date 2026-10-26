import type {ReactNode} from "react";

export type HorizontalAlignment =
  | "left"
  | "center"
  | "right";

export type VerticalAlignment =
  | "top"
  | "center"
  | "bottom";

export type RevealDirection =
  | "left"
  | "right"
  | "up"
  | "down";

export type AssetType =
  | "portrait"
  | "image"
  | "logo"
  | "chart"
  | "diagram"
  | "background"
  | "icon";

export type DynamicTheme = {
  themeId: string;
  background: string;
  surface: string;
  surfaceSecondary: string;
  foreground: string;
  foregroundMuted: string;
  accent: string;
  accentSecondary: string;
  border: string;
  displayFont: string;
  bodyFont: string;
  confidentialityText: string;
};

export type ApprovedArtifact = {
  artifactId: string;
  assetType: AssetType;
  rendererPath: string;
  approved: boolean;
  altText: string;
  width?: number;
  height?: number;
  sourceReference?: string;
};

export type ArtifactManifest = {
  artifacts: ApprovedArtifact[];
};

export type SceneContext = {
  sceneId: string;
  candidateName: string;
  durationInFrames: number;
  fps: number;
  theme: DynamicTheme;
  artifacts: ArtifactManifest;
};

export type GeneratedSceneProps = {
  context: SceneContext;
  content: Record<string, unknown>;
};

export type GeneratedComponentManifest = {
  sceneId: string;
  componentName: string;
  sourceFile: string;
  usedPrimitives: string[];
  usedArtifacts: string[];
  expectedPeakFramePercentage: number;
  fallbackComponent: string;
};

export type ChildrenProps = {
  children?: ReactNode;
};
