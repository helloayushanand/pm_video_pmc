import React from "react";
import {
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

type Props = {
  value: string;
  label?: string | null;
  accentColour: string;
  delayFrames?: number;
};

export const MetricCard: React.FC<Props> = ({
  value,
  label,
  accentColour,
  delayFrames = 0,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const progress = spring({
    frame: Math.max(0, frame - delayFrames),
    fps,
    config: {
      damping: 18,
      stiffness: 120,
      mass: 0.9,
    },
  });

  const opacity = interpolate(
    progress,
    [0, 1],
    [0, 1],
  );

  const scale = interpolate(
    progress,
    [0, 1],
    [0.92, 1],
  );

  return (
    <div
      style={{
        flex: 1,
        minWidth: 260,
        minHeight: 245,
        padding: "34px 32px",
        borderRadius: 28,
        background: "rgba(255,255,255,0.80)",
        border: "1px solid rgba(20,20,20,0.08)",
        boxShadow: "0 18px 55px rgba(20,20,20,0.08)",
        opacity,
        transform: `scale(${scale})`,
      }}
    >
      <div
        style={{
          color: accentColour,
          fontSize: 60,
          lineHeight: 1,
          fontWeight: 760,
          letterSpacing: -2,
        }}
      >
        {value}
      </div>

      {label ? (
        <div
          style={{
            marginTop: 24,
            color: "#444444",
            fontSize: 25,
            lineHeight: 1.3,
            fontWeight: 520,
          }}
        >
          {label}
        </div>
      ) : null}
    </div>
  );
};
