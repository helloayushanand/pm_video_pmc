import React from "react";
import {interpolate, useCurrentFrame} from "remotion";
import type {RenderScene, ThemeSettings, VisualElement} from "../types";
import {SceneFrame} from "../components/SceneFrame";
import {createTheme} from "../theme/theme";

type Props = {
  scene: RenderScene;
  theme: ThemeSettings;
  candidateName: string;
};

const getText = (element?: VisualElement) =>
  element?.content || element?.value || element?.label || "";

const componentHeadline = (component: string): string => {
  const labels: Record<string, string> = {
    ExecutiveSummary: "Executive profile",
    CareerTimeline: "Career progression",
    CareerMilestone: "Career impact",
    MetricHighlights: "Selected outcomes",
    SingleHighlight: "Selected highlight",
    LeadershipScope: "Leadership at scale",
    OrganisationStructure: "Organisation structure",
    StrengthSummary: "Core strengths",
    ConfidentialDetails: "Availability",
  };
  return labels[component] || "Candidate snapshot";
};

const metadataValue = (element: VisualElement, key: string): string | null => {
  const item = (element.metadata || []).find((entry) => entry.key === key);
  return item?.value || null;
};

const panelStyle: React.CSSProperties = {
  borderRadius: 24,
  background: "rgba(255,255,255,0.82)",
  boxShadow: "0 16px 50px rgba(12,24,36,0.08)",
};

export const GenericScene: React.FC<Props> = ({scene, theme}) => {
  const frame = useCurrentFrame();
  const colours = createTheme(theme);
  const elements = [...(scene.props.visual_elements || [])].sort(
    (a, b) => (a.display_order || 0) - (b.display_order || 0),
  );

  const headings = elements.filter((e) =>
    ["heading", "subheading"].includes(e.element_type || ""),
  );
  const metrics = elements.filter((e) => e.element_type === "metric");
  const timeline = elements.find((e) => e.element_type === "timeline");
  const organisation = elements.find((e) =>
    ["organisation_chart", "organization_chart"].includes(e.element_type || ""),
  );
  const textItems = elements.filter((e) =>
    ["body_text", "label"].includes(e.element_type || ""),
  );

  // Critical rule: purpose is renderer metadata. Never display it.
  const headline = getText(headings[0]) || componentHeadline(scene.component);
  const eyebrow = scene.component.replace(/([a-z])([A-Z])/g, "$1 $2").toUpperCase();
  const reveal = interpolate(frame, [0, 18], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const renderTimeline = () => {
    if (!timeline) return null;
    const raw = metadataValue(timeline, "milestones") || getText(timeline);
    const milestones = raw.split(/;|→/).map((v) => v.trim()).filter(Boolean);
    return (
      <div style={{position: "relative", marginTop: 60, padding: "44px 24px 20px"}}>
        <div style={{position: "absolute", left: 65, right: 65, top: 71, height: 5, borderRadius: 5, background: `linear-gradient(90deg, ${colours.accent}, #315D78, #00A79D)`, transform: `scaleX(${reveal})`, transformOrigin: "left"}} />
        <div style={{display: "grid", gridTemplateColumns: `repeat(${Math.max(milestones.length, 1)}, 1fr)`, gap: 28}}>
          {milestones.map((item, index) => {
            const local = interpolate(frame, [10 + index * 10, 25 + index * 10], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp"});
            return (
              <div key={item} style={{textAlign: "center", opacity: local, transform: `translateY(${(1-local)*22}px)`}}>
                <div style={{position: "relative", zIndex: 2, margin: "0 auto 30px", width: 54, height: 54, borderRadius: "50%", background: index % 2 ? "#315D78" : colours.accent, border: "8px solid #fff", boxShadow: "0 8px 28px rgba(0,0,0,.12)"}} />
                <div style={{...panelStyle, padding: "24px 20px", color: colours.primary, fontSize: 28, fontWeight: 700, lineHeight: 1.2}}>{item}</div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  const renderMetrics = () => {
    if (!metrics.length) return null;
    const accents = [colours.accent, "#315D78", "#00A79D", "#C66A3D"];
    return (
      <div style={{display: "grid", gridTemplateColumns: metrics.length >= 3 ? "1.25fr 1fr 1fr" : `repeat(${metrics.length}, 1fr)`, gap: 24, marginTop: 48}}>
        {metrics.slice(0, 4).map((metric, index) => {
          const local = interpolate(frame, [8 + index*8, 26 + index*8], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp"});
          const accent = accents[index % accents.length];
          return (
            <div key={metric.element_id || index} style={{...panelStyle, minHeight: index === 0 ? 250 : 220, padding: "30px 34px", borderTop: `7px solid ${accent}`, opacity: local, transform: `translateY(${(1-local)*26}px)`}}>
              <div style={{fontSize: index === 0 ? 66 : 54, lineHeight: 1, fontWeight: 800, color: accent, letterSpacing: -2}}>{metric.value || metric.content}</div>
              <div style={{marginTop: 18, fontSize: 24, color: colours.secondary, lineHeight: 1.25}}>{metric.label}</div>
              <div style={{height: 7, borderRadius: 7, background: `${accent}22`, marginTop: 30, overflow: "hidden"}}>
                <div style={{height: "100%", width: `${Math.round(local * 100)}%`, background: accent}} />
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  const renderOrg = () => {
    if (!organisation) return null;
    const raw = getText(organisation).replace(/^.*?:/, "");
    const nodes = raw.split(/;|,/).map((v) => v.trim()).filter(Boolean).slice(0, 7);
    return (
      <div style={{position: "relative", height: 430, marginTop: 38}}>
        <div style={{position: "absolute", left: "50%", top: "50%", width: 210, height: 110, marginLeft: -105, marginTop: -55, borderRadius: 28, background: "#00A79D", color: "white", display: "flex", alignItems: "center", justifyContent: "center", textAlign: "center", fontWeight: 800, fontSize: 28, zIndex: 3, boxShadow: "0 14px 36px rgba(0,167,157,.25)"}}>Leadership</div>
        {nodes.map((node, index) => {
          const angle = (-Math.PI/2) + index * (Math.PI*2 / Math.max(nodes.length,1));
          const x = 50 + Math.cos(angle) * 34;
          const y = 50 + Math.sin(angle) * 37;
          const local = interpolate(frame, [10 + index*5, 26 + index*5], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp"});
          return <div key={node} style={{position: "absolute", left: `${x}%`, top: `${y}%`, transform: "translate(-50%,-50%)", opacity: local, ...panelStyle, padding: "16px 22px", minWidth: 180, textAlign: "center", color: colours.primary, fontSize: 21, fontWeight: 700, border: `2px solid ${index % 2 ? "#315D78" : colours.accent}`}}>{node}</div>;
        })}
      </div>
    );
  };

  const hasSemanticVisual = Boolean(timeline || organisation || metrics.length);

  return (
    <SceneFrame theme={theme} sceneLabel={scene.component}>
      <div style={{position: "absolute", inset: "130px 110px 100px", display: "flex", flexDirection: "column", justifyContent: "center"}}>
        <div style={{color: colours.accent, fontSize: 18, fontWeight: 800, letterSpacing: 2.4, textTransform: "uppercase", marginBottom: 18}}>{eyebrow}</div>
        <h1 style={{margin: 0, maxWidth: 1480, color: colours.primary, fontSize: hasSemanticVisual ? 56 : 66, lineHeight: 1.05, fontWeight: 760, letterSpacing: -2}}>{headline}</h1>
        {headings[1] ? <div style={{marginTop: 17, color: colours.secondary, fontSize: 27}}>{getText(headings[1])}</div> : null}
        {renderTimeline()}
        {renderOrg()}
        {!timeline && !organisation ? renderMetrics() : null}
        {!hasSemanticVisual && textItems.length ? (
          <div style={{display: "grid", gridTemplateColumns: textItems.length > 2 ? "repeat(2,minmax(0,1fr))" : "1fr", gap: 20, marginTop: 38}}>
            {textItems.slice(0, 6).map((item, index) => <div key={item.element_id || index} style={{...panelStyle, padding: "22px 26px", borderLeft: `5px solid ${index % 2 ? "#315D78" : colours.accent}`, color: colours.primary, fontSize: 25, lineHeight: 1.3}}>{getText(item)}</div>)}
          </div>
        ) : null}
      </div>
    </SceneFrame>
  );
};
