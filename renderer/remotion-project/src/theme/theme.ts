import type {CSSProperties} from "react";
import type {ThemeSettings} from "../types";

export const createTheme = (theme: ThemeSettings) => {
  return {
    primary: theme.primary_colour || "#111111",
    secondary: theme.secondary_colour || "#656565",
    background: theme.background_colour || "#F5F4F1",
    accent: theme.accent_colour || "#B79A5B",
    fontFamily:
      theme.font_family ||
      "Inter, Arial, Helvetica, sans-serif",
  };
};

export const fullFrameStyle: CSSProperties = {
  position: "absolute",
  inset: 0,
  overflow: "hidden",
};
