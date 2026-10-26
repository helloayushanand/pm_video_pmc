/* ------------------------------------------------------------------ *
 *  Scene DSL type definitions                                         *
 *  The LLM outputs JSON conforming to these types.                    *
 *  The DSLScene renderer consumes them — no generated TSX needed.     *
 * ------------------------------------------------------------------ */

import type {ArtifactManifest, DynamicTheme} from "../dynamic-sdk";

// ── Backgrounds ──────────────────────────────────────────────────────

export type SolidBackground = {
  type: "solid";
  color: string;
};

export type GradientBackground = {
  type: "gradient";
  from: string;
  to: string;
  angle?: number;
};

export type RadialBackground = {
  type: "radial";
  base: string;
  highlight: string;
  position?: string;
};

export type BackgroundSpec =
  | SolidBackground
  | GradientBackground
  | RadialBackground;

// ── Theme overrides ──────────────────────────────────────────────────

export type ThemeOverrides = Partial<
  Pick<
    DynamicTheme,
    | "background"
    | "surface"
    | "surfaceSecondary"
    | "foreground"
    | "foregroundMuted"
    | "accent"
    | "accentSecondary"
    | "border"
  >
>;

// ── Entrance animations ──────────────────────────────────────────────

export type EntranceType =
  | "none"
  | "fade"
  | "slide_up"
  | "slide_down"
  | "slide_left"
  | "slide_right"
  | "scale";

export type EntranceSpec = {
  type: EntranceType;
  delay?: number;
  duration?: number;
};

// ── Element types ────────────────────────────────────────────────────

export type TextRole =
  | "display"
  | "heading"
  | "subheading"
  | "body"
  | "label"
  | "caption";

export type TextElement = {
  type: "text";
  content: string;
  role: TextRole;
  align?: "left" | "center" | "right";
  color?: string;
  maxWidth?: number;
  entrance?: EntranceSpec;
};

export type AutoFitTextElement = {
  type: "autofit_text";
  text: string;
  maxFontSize?: number;
  minFontSize?: number;
  align?: "left" | "center" | "right";
  entrance?: EntranceSpec;
};

export type MetricElement = {
  type: "metric";
  value: string;
  label?: string;
  emphasis?: "hero" | "primary" | "supporting";
  entrance?: EntranceSpec;
};

export type MetricRowItem = {
  value: string;
  label?: string;
  emphasis?: "hero" | "primary" | "supporting";
};

export type MetricRowElement = {
  type: "metric_row";
  items: MetricRowItem[];
  cardStyle?: boolean;
  entrance?: EntranceSpec;
  stagger?: number;
};

export type TimelineNode = {
  year: string;
  title: string;
  subtitle?: string;
  accent?: string;
};

export type TimelineElement = {
  type: "timeline";
  orientation?: "horizontal" | "vertical";
  nodes: TimelineNode[];
  connectorStyle?: "solid" | "dashed" | "dotted";
  entrance?: EntranceSpec;
  stagger?: number;
};

export type BulletItem = {
  text: string;
  icon?: string;
  subtext?: string;
};

export type BulletListElement = {
  type: "bullet_list";
  items: BulletItem[];
  columns?: 1 | 2;
  entrance?: EntranceSpec;
  stagger?: number;
};

export type PortraitElement = {
  type: "portrait";
  artifactId: string;
  borderColor?: string;
  borderRadius?: number;
  shadow?: boolean;
  entrance?: EntranceSpec;
};

export type ImageElement = {
  type: "image";
  artifactId: string;
  fit?: "cover" | "contain";
  borderRadius?: number;
  entrance?: EntranceSpec;
};

export type QuoteElement = {
  type: "quote";
  text: string;
  attribution?: string;
  style?: "editorial" | "callout" | "minimal";
  entrance?: EntranceSpec;
};

export type OrgNode = {
  label: string;
  sublabel?: string;
};

export type OrgTreeElement = {
  type: "org_tree";
  centerNode: OrgNode;
  children: OrgNode[];
  style?: "radial" | "top_down";
  entrance?: EntranceSpec;
};

export type BadgeItem = {
  label: string;
  icon?: string;
};

export type BadgeRowElement = {
  type: "badge_row";
  items: BadgeItem[];
  entrance?: EntranceSpec;
  stagger?: number;
};

export type DividerElement = {
  type: "divider";
  color?: string;
  thickness?: number;
};

export type SpacerElement = {
  type: "spacer";
  height: number;
};

export type ProgressBarElement = {
  type: "progress_bar";
  value: number;
  label?: string;
  color?: string;
  entrance?: EntranceSpec;
};

export type ElementSpec =
  | TextElement
  | AutoFitTextElement
  | MetricElement
  | MetricRowElement
  | TimelineElement
  | BulletListElement
  | PortraitElement
  | ImageElement
  | QuoteElement
  | OrgTreeElement
  | BadgeRowElement
  | DividerElement
  | SpacerElement
  | ProgressBarElement;

// ── Layouts ──────────────────────────────────────────────────────────

export type StackLayout = {
  type: "stack";
  direction?: "column" | "row";
  gap?: number;
  align?: "left" | "center" | "right";
  justify?: "start" | "center" | "end" | "between";
  elements: ElementSpec[];
};

export type SplitLayoutSpec = {
  type: "split";
  leftRatio?: number;
  gap?: number;
  left: ElementSpec[];
  right: ElementSpec[];
};

export type GridLayoutSpec = {
  type: "grid";
  columns: number;
  gap?: number;
  elements: ElementSpec[];
};

export type LayoutSpec =
  | StackLayout
  | SplitLayoutSpec
  | GridLayoutSpec;

// ── Scene spec ───────────────────────────────────────────────────────

export type SceneSpec = {
  sceneId: string;
  title: string;
  durationSeconds: number;
  background: BackgroundSpec;
  themeOverrides?: ThemeOverrides;
  layout: LayoutSpec;
  narration?: string;
};

// ── Video spec (all scenes) ──────────────────────────────────────────

export type VideoSpec = {
  candidateName: string;
  confidentialityText?: string;
  scenes: SceneSpec[];
  globalTheme?: ThemeOverrides;
};

// ── Runtime context passed to primitives ─────────────────────────────

export type DSLContext = {
  theme: DynamicTheme;
  fps: number;
  durationInFrames: number;
  artifacts: ArtifactManifest;
};
