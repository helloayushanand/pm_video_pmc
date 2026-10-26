import React from "react";
import type {BackgroundSpec} from "./types";

type Props = {
  spec: BackgroundSpec;
  children?: React.ReactNode;
};

const resolve = (spec: BackgroundSpec): string => {
  if (spec.type === "solid") return spec.color;
  if (spec.type === "gradient") {
    const angle = spec.angle ?? 135;
    return `linear-gradient(${angle}deg, ${spec.from} 0%, ${spec.to} 100%)`;
  }
  const pos = spec.position ?? "50% 30%";
  return (
    `radial-gradient(circle at ${pos}, ${spec.highlight}33 0%, transparent 40%), ` +
    `linear-gradient(160deg, ${spec.base} 0%, ${spec.base} 100%)`
  );
};

export const DSLBackground: React.FC<Props> = ({spec, children}) =>
  React.createElement(
    "div",
    {
      style: {
        position: "absolute",
        inset: 0,
        overflow: "hidden",
        background: resolve(spec),
      },
    },
    children,
  );
