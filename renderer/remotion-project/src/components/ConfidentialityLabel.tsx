import React from "react";

type Props = {
  text: string;
  colour: string;
};

export const ConfidentialityLabel: React.FC<Props> = ({
  text,
  colour,
}) => {
  return (
    <div
      style={{
        position: "absolute",
        right: 46,
        top: 34,
        padding: "9px 16px",
        border: `1px solid ${colour}55`,
        borderRadius: 999,
        color: colour,
        fontSize: 18,
        fontWeight: 600,
        letterSpacing: 1.5,
        textTransform: "uppercase",
        opacity: 0.78,
      }}
    >
      {text}
    </div>
  );
};
