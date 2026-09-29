export type VisualMetadataItem = {
  key: string;
  value: string;
};

export type VisualElement = {
  element_id?: string;
  element_type?: string;

  content?: string | null;
  value?: string | null;
  label?: string | null;

  asset_id?: string | null;

  animation?: string | null;
  display_order?: number;

  metadata?: VisualMetadataItem[];
};

/**
 * Text explicitly intended to appear in the final video.
 */
export type SceneDisplay = {
  eyebrow?: string | null;
  headline?: string | null;
  supporting_text?: string | null;
};

/**
 * Creative and rendering instructions.
 *
 * IMPORTANT:
 * Nothing in this object should ever be rendered
 * directly as viewer-facing text.
 */
export type RendererInstructions = {
  scene_purpose?: string | null;

  visual_story?: string | null;
  layout_intent?: string | null;
  animation_intent?: string | null;

  transition_in?: string | null;
  transition_out?: string | null;

  background_variant?: string | null;

  do_not_render_as_text?: boolean;

  [key: string]: unknown;
};

/**
 * Renderer-ready artifact available to a scene.
 */
export type SceneArtifact = {
  artifact_id: string;

  artifact_type?: string | null;

  renderer_path?: string | null;

  alt_text?: string | null;

  approved?: boolean;

  source_strategy?: string | null;
};

/**
 * Props supplied to an individual scene.
 *
 * VIEWER-VISIBLE CONTENT:
 *
 * display
 * visual_elements
 *
 * NON-DISPLAY CONTROL DATA:
 *
 * renderer_instructions
 */
export type RenderSceneProps = {
  display?: SceneDisplay;

  visual_elements?: VisualElement[];

  artifacts?: SceneArtifact[];

  renderer_instructions?: RendererInstructions;

  voiceover?: string;

  /**
   * Legacy field retained during migration.
   *
   * Never render this value directly.
   */
  purpose?: string;

  transition_in?: string;

  transition_out?: string;

  background_variant?: string;

  [key: string]: unknown;
};

export type RenderEvent = {
  event_id: string;
  event_type: string;

  start_frame: number;
  duration_frames: number;

  props: Record<string, unknown>;
};

export type RenderScene = {
  scene_id: string;

  /**
   * Renderer/component requested for this scene.
   */
  component: string;

  /**
   * Determines how CandidateVideo should resolve
   * the scene.
   */
  renderer_strategy?:
    | "generated_component"
    | "library_component"
    | "generic_fallback";

  /**
   * Key used to find an AI-generated component
   * in the generated component registry.
   */
  generated_component_key?: string | null;

  variant: string;

  start_frame: number;
  duration_frames: number;

  props: RenderSceneProps;

  events?: RenderEvent[];
};

export type RenderVideoSettings = {
  width: number;
  height: number;

  fps: number;
  duration_frames: number;

  output_format?: string;
  codec?: string;
  pixel_format?: string;
};

export type ThemeSettings = {
  theme_id: string;

  primary_colour: string;
  secondary_colour: string;

  background_colour: string;
  accent_colour: string;

  /**
   * Additional accents available to charts   * diagrams and generated scenes.
   */
  accent_secondary_colour?: string;
  accent_tertiary_colour?: string;

  surface_colour?: string;
  surface_secondary_colour?: string;

  font_family: string;

  display_font_family?: string;

  logo_asset_path?: string | null;

  confidential: boolean;

  confidentiality_text: string;
};

export type AudioTrack = {
  source_path: string;

  duration_seconds: number;

  start_frame: number;

  volume: number;
};

export type ResolvedAsset = {
  asset_id: string;

  asset_type: string;

  source_path: string;

  renderer_path?: string | null;

  required: boolean;

  approved?: boolean;

  alt_text?: string | null;
};

export type RenderSpecification = {
  schema_version: string;

  render_id: string;

  candidate_name: string;

  video: RenderVideoSettings;

  theme: ThemeSettings;

  audio: AudioTrack;

  scenes: RenderScene[];

  assets: ResolvedAsset[];

  output_path: string;

  metadata: Record<string, unknown>;
};

export type CandidateVideoProps = {
  renderSpec: RenderSpecification;
};