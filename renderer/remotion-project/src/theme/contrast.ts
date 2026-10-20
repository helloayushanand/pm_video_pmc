const parseHex = (value: string): [number, number, number] | null => {
  const normalized = value.trim().replace(/^#/, "");
  const expanded = normalized.length === 3
    ? normalized.split("").map((part) => part + part).join("")
    : normalized;

  if (!/^[\da-f]{6}$/i.test(expanded)) {
    return null;
  }

  return [
    Number.parseInt(expanded.slice(0, 2), 16),
    Number.parseInt(expanded.slice(2, 4), 16),
    Number.parseInt(expanded.slice(4, 6), 16),
  ];
};

const luminance = ([red, green, blue]: [number, number, number]): number => {
  const linear = [red, green, blue].map((channel) => {
    const value = channel / 255;
    return value <= 0.04045
      ? value / 12.92
      : ((value + 0.055) / 1.055) ** 2.4;
  });

  return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
};

const contrastRatio = (
  foreground: [number, number, number],
  background: [number, number, number],
): number => {
  const values = [luminance(foreground), luminance(background)].sort(
    (left, right) => right - left,
  );
  return (values[0] + 0.05) / (values[1] + 0.05);
};

export const ensureTextContrast = (
  foreground: string,
  background = "#FFFFFF",
  minimumRatio = 4.5,
): string => {
  const foregroundRgb = parseHex(foreground);
  const backgroundRgb = parseHex(background);
  if (!foregroundRgb || !backgroundRgb) {
    return "#263746";
  }

  if (contrastRatio(foregroundRgb, backgroundRgb) >= minimumRatio) {
    return foreground;
  }

  const endpoint: [number, number, number] =
    contrastRatio([0, 0, 0], backgroundRgb) >=
    contrastRatio([255, 255, 255], backgroundRgb)
      ? [0, 0, 0]
      : [255, 255, 255];

  for (let step = 1; step <= 100; step += 1) {
    const amount = step / 100;
    const adjusted: [number, number, number] = [
      Math.round(foregroundRgb[0] + (endpoint[0] - foregroundRgb[0]) * amount),
      Math.round(foregroundRgb[1] + (endpoint[1] - foregroundRgb[1]) * amount),
      Math.round(foregroundRgb[2] + (endpoint[2] - foregroundRgb[2]) * amount),
    ];

    if (contrastRatio(adjusted, backgroundRgb) >= minimumRatio) {
      return `#${adjusted.map((channel) => channel.toString(16).padStart(2, "0")).join("")}`;
    }
  }

  return endpoint[0] === 0 ? "#000000" : "#FFFFFF";
};
