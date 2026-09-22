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

export type RenderEvent = {
  event_id: string;
  event_type: string;
  start_frame: number;
  duration_frames: number;
  props: Record<string, unknown>;
};

export type RenderSceneProps = {
  purpose?: string;
  voiceover?: string;
  visual_elements?: VisualElement[];
  transition_in?: string;
  transition_out?: string;
  background_variant?: string;
  [key: string]: unknown;
};

export type RenderScene = {
  scene_id: string;
  component: string;
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
  font_family: string;
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
