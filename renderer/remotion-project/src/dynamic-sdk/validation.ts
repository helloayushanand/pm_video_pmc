import type {
  ApprovedArtifact,
  ArtifactManifest,
} from "./types";

const FORBIDDEN_SOURCE_PATTERNS = [
  "process.env",
  "require(",
  "eval(",
  "new Function",
  "child_process",
  "node:fs",
  "node:net",
  "node:http",
  "node:https",
  "node:os",
  "XMLHttpRequest",
  "WebSocket(",
  "fetch(",
  "import(",
];

const ALLOWED_IMPORTS = [
  "react",
  "remotion",
];

const ALLOWED_IMPORT_PREFIXES = [
  "./dynamic-sdk",
  "../dynamic-sdk",
  "../../dynamic-sdk",
  "@/dynamic-sdk",
];

export type SourceValidationResult = {
  valid: boolean;
  errors: string[];
};

export const validateGeneratedSource = (
  source: string,
): SourceValidationResult => {
  const errors: string[] = [];

  for (
    const pattern
    of FORBIDDEN_SOURCE_PATTERNS
  ) {
    if (source.includes(pattern)) {
      errors.push(
        "Generated source contains forbidden pattern: "
          + pattern,
      );
    }
  }

  const importPattern =
    /from\s+[^"']+["']/g;

  let match: RegExpExecArray | null;

  while (
    (match = importPattern.exec(source))
      !== null
  ) {
    const importedModule = match[1];

    const directlyAllowed =
      ALLOWED_IMPORTS.includes(
        importedModule,
      );

    const prefixAllowed =
      ALLOWED_IMPORT_PREFIXES.some(
        (prefix) =>
          importedModule === prefix
          || importedModule.startsWith(
            prefix + "/",
          ),
      );

    if (
      !directlyAllowed
      && !prefixAllowed
    ) {
      errors.push(
        "Generated source imports "
          + "a non-approved module: "
          + importedModule,
      );
    }
  }

  if (
    !source.includes(
      "GeneratedSceneProps",
    )
  ) {
    errors.push(
      "Generated component must use "
        + "GeneratedSceneProps.",
    );
  }

  if (!source.includes("export")) {
    errors.push(
      "Generated component must export "
        + "a component.",
    );
  }

  return {
    valid: errors.length === 0,
    errors,
  };
};

export const getApprovedArtifact = (
  manifest: ArtifactManifest,
  artifactId: string,
): ApprovedArtifact => {
  const artifact =
    manifest.artifacts.find(
      (item) =>
        item.artifactId
          === artifactId,
    );

  if (!artifact) {
    throw new Error(
      "Artifact not found in approved "
        + "manifest: "
        + artifactId,
    );
  }

  if (!artifact.approved) {
    throw new Error(
      "Artifact is not approved: "
        + artifactId,
    );
  }

  return artifact;
};
