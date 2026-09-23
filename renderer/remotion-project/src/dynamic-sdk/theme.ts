import type {DynamicTheme} from "./types";

export const defaultDynamicTheme: DynamicTheme = {
  themeId: "pm_premium_v1",
  background: "#F4F1EA",
  surface: "#FFFFFF",
  surfaceSecondary: "#E9E4DA",
  foreground: "#16212B",
  foregroundMuted: "#66717C",
  accent: "#B59252",
  accentSecondary: "#315D78",
  border: "rgba(22, 33, 43, 0.12)",
  displayFont:
    "Aptos Display, Inter, Arial, sans-serif",
  bodyFont:
    "Aptos, Inter, Arial, sans-serif",
  confidentialityText:
    "Private and Confidential",
};

export const spacing = {
  xxs: 8,
  xs: 12,
  sm: 16,
  md: 24,
  lg: 40,
  xl: 64,
  xxl: 96,
};

export const radius = {
  small: 12,
  medium: 20,
  large: 30,
  pill: 999,
};

export const safeArea = {
  horizontal: 88,
  vertical: 72,
};

export const typography = {
  displayLarge: 88,
  displayMedium: 70,
  displaySmall: 56,
  heading: 42,
  subheading: 31,
  bodyLarge: 29,
  body: 25,
  label: 18,
  caption: 16,
};

export const shadows = {
  subtle:
    "0 12px 36px rgba(22, 33, 43, 0.06)",
  medium:
    "0 20px 60px rgba(22, 33, 43, 0.10)",
  strong:
    "0 28px 90px rgba(22, 33, 43, 0.16)",
};
