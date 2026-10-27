import React from "react";
import type {DSLContext, LayoutSpec, ElementSpec} from "./types";
import {DSLElement} from "./DSLElement";
import {spacing, safeArea} from "../dynamic-sdk";

type Props = {
  spec: LayoutSpec;
  ctx: DSLContext;
};

const renderSlot = (elements: ElementSpec[], ctx: DSLContext, gap: number) =>
  React.createElement(
    "div",
    {
      style: {
        display: "flex",
        flexDirection: "column" as const,
        gap,
        justifyContent: "center",
        height: "100%",
      },
    },
    ...elements.map((el, i) =>
      React.createElement(DSLElement, {key: i, spec: el, ctx}),
    ),
  );

export const DSLLayout: React.FC<Props> = ({spec, ctx}) => {
  const safeStyle: React.CSSProperties = {
    position: "absolute",
    left: safeArea.horizontal,
    right: safeArea.horizontal,
    top: safeArea.vertical,
    bottom: safeArea.vertical,
    overflow: "hidden",
  };

  switch (spec.type) {
    case "stack": {
      const gap = spec.gap ?? spacing.md;
      const dir = spec.direction ?? "column";
      const alignItems =
        spec.align === "center" ? "center" :
        spec.align === "right" ? "flex-end" : "flex-start";
      const justifyContent =
        spec.justify === "center" ? "center" :
        spec.justify === "end" ? "flex-end" :
        spec.justify === "between" ? "space-between" : "flex-start";

      return React.createElement(
        "div",
        {style: safeStyle},
        React.createElement(
          "div",
          {
            style: {
              display: "flex",
              flexDirection: dir,
              gap,
              alignItems,
              justifyContent,
              width: "100%",
              height: "100%",
            },
          },
          ...spec.elements.map((el, i) =>
            React.createElement(DSLElement, {key: i, spec: el, ctx}),
          ),
        ),
      );
    }

    case "split": {
      const leftRatio = spec.leftRatio ?? 0.5;
      const gap = spec.gap ?? spacing.xl;

      return React.createElement(
        "div",
        {style: safeStyle},
        React.createElement(
          "div",
          {
            style: {
              display: "grid",
              gridTemplateColumns: `${leftRatio}fr ${1 - leftRatio}fr`,
              gap,
              width: "100%",
              height: "100%",
              alignItems: "stretch",
            },
          },
          renderSlot(spec.left, ctx, spacing.md),
          renderSlot(spec.right, ctx, spacing.md),
        ),
      );
    }

    case "grid": {
      const cols = spec.columns ?? 2;
      const gap = spec.gap ?? spacing.md;

      return React.createElement(
        "div",
        {style: safeStyle},
        React.createElement(
          "div",
          {
            style: {
              display: "grid",
              gridTemplateColumns: `repeat(${cols}, 1fr)`,
              gap,
              width: "100%",
              height: "100%",
              alignContent: "center",
            },
          },
          ...spec.elements.map((el, i) =>
            React.createElement(DSLElement, {key: i, spec: el, ctx}),
          ),
        ),
      );
    }

    default:
      return null;
  }
};
