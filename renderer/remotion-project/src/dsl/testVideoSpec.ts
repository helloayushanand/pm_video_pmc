import type {VideoSpec} from "./types";

export const testVideoSpec: VideoSpec = {
  candidateName: "Rohit Mehta",
  confidentialityText: "Private and Confidential",
  scenes: [
    {
      sceneId: "intro",
      title: "Introduction",
      durationSeconds: 8,
      background: {
        type: "gradient",
        from: "#0B1D2E",
        to: "#1A3A54",
        angle: 145,
      },
      themeOverrides: {
        foreground: "#F7FBFF",
        foregroundMuted: "#A0B4C8",
        accent: "#D4A843",
        surface: "rgba(255,255,255,0.08)",
        border: "rgba(255,255,255,0.12)",
      },
      layout: {
        type: "split",
        leftRatio: 0.55,
        left: [
          {
            type: "text",
            content: "Executive Candidate Profile",
            role: "label",
            entrance: {type: "fade", delay: 0.2, duration: 0.5},
          },
          {
            type: "autofit_text",
            text: "Rohit Mehta",
            entrance: {type: "slide_up", delay: 0.4, duration: 0.7},
          },
          {
            type: "text",
            content: "VP of Product · 12 years building consumer platforms at scale",
            role: "body",
            entrance: {type: "fade", delay: 0.9, duration: 0.6},
          },
          {
            type: "badge_row",
            items: [
              {label: "Product Strategy", icon: "🎯"},
              {label: "Growth", icon: "🚀"},
              {label: "B2C Platforms", icon: "📱"},
            ],
            entrance: {type: "slide_up", delay: 1.4, duration: 0.5},
            stagger: 0.1,
          },
        ],
        right: [
          {
            type: "metric_row",
            items: [
              {value: "3x", label: "MAU Growth", emphasis: "hero"},
              {value: "$4.2M", label: "Revenue Impact", emphasis: "primary"},
            ],
            cardStyle: true,
            entrance: {type: "scale", delay: 1.0, duration: 0.6},
            stagger: 0.2,
          },
        ],
      },
      narration:
        "Meet Rohit Mehta. A veteran product leader with twelve years of experience building consumer platforms at scale. He's driven three-times user growth and four point two million dollars in direct revenue impact.",
    },
    {
      sceneId: "career_timeline",
      title: "Career Journey",
      durationSeconds: 9,
      background: {
        type: "radial",
        base: "#F4F1EA",
        highlight: "#B59252",
        position: "80% 20%",
      },
      layout: {
        type: "stack",
        direction: "column",
        gap: 40,
        align: "center",
        justify: "center",
        elements: [
          {
            type: "text",
            content: "Career Journey",
            role: "label",
            align: "center",
            entrance: {type: "fade", delay: 0.2, duration: 0.4},
          },
          {
            type: "text",
            content: "A track record of increasing scope and impact",
            role: "heading",
            align: "center",
            entrance: {type: "slide_up", delay: 0.4, duration: 0.6},
          },
          {
            type: "timeline",
            orientation: "horizontal",
            nodes: [
              {year: "2014", title: "Product Analyst", subtitle: "InMobi", accent: "#6B8DB5"},
              {year: "2017", title: "Senior PM", subtitle: "Flipkart", accent: "#F5A623"},
              {year: "2020", title: "Director, Product", subtitle: "Flipkart", accent: "#D4A843"},
              {year: "2023", title: "VP Product", subtitle: "NeoBank", accent: "#2ECC71"},
            ],
            connectorStyle: "dashed",
            entrance: {type: "slide_up", delay: 0.8, duration: 0.6},
            stagger: 0.25,
          },
        ],
      },
      narration:
        "Rohit's career spans four progressively senior roles. Starting as a product analyst at InMobi, he moved to Flipkart where he rose from Senior PM to Director, and now leads product as VP at NeoBank.",
    },
    {
      sceneId: "metrics",
      title: "Quantified Impact",
      durationSeconds: 8,
      background: {
        type: "gradient",
        from: "#091427",
        to: "#10233F",
        angle: 135,
      },
      themeOverrides: {
        foreground: "#F7FBFF",
        foregroundMuted: "#94A7BE",
        accent: "#F1B14A",
        surface: "rgba(255,255,255,0.06)",
        border: "rgba(255,255,255,0.10)",
      },
      layout: {
        type: "stack",
        direction: "column",
        gap: 48,
        justify: "center",
        elements: [
          {
            type: "text",
            content: "Quantified Impact",
            role: "label",
            entrance: {type: "fade", delay: 0.3, duration: 0.4},
          },
          {
            type: "text",
            content: "Numbers that tell the story",
            role: "heading",
            entrance: {type: "slide_up", delay: 0.5, duration: 0.6},
          },
          {
            type: "metric_row",
            items: [
              {value: "50M+", label: "Monthly Active Users", emphasis: "hero"},
              {value: "3x", label: "Conversion Uplift", emphasis: "primary"},
              {value: "120%", label: "Revenue Growth YoY", emphasis: "primary"},
            ],
            cardStyle: true,
            entrance: {type: "scale", delay: 0.9, duration: 0.7},
            stagger: 0.2,
          },
          {
            type: "progress_bar",
            value: 92,
            label: "Team Engagement Score",
            entrance: {type: "fade", delay: 2.0, duration: 0.5},
          },
        ],
      },
      narration:
        "The numbers speak clearly. Fifty million monthly active users, a three-times conversion uplift, and one hundred twenty percent year-over-year revenue growth. His team engagement score sits at ninety two percent.",
    },
    {
      sceneId: "leadership",
      title: "Leadership Scope",
      durationSeconds: 8,
      background: {
        type: "gradient",
        from: "#F4F1EA",
        to: "#E9E4DA",
        angle: 160,
      },
      layout: {
        type: "split",
        leftRatio: 0.45,
        left: [
          {
            type: "text",
            content: "Leadership Scope",
            role: "label",
            entrance: {type: "fade", delay: 0.2, duration: 0.4},
          },
          {
            type: "text",
            content: "Building and scaling high-impact teams",
            role: "heading",
            entrance: {type: "slide_up", delay: 0.4, duration: 0.6},
          },
          {
            type: "quote",
            text: "Great products are built by empowered teams, not process.",
            attribution: "Rohit Mehta",
            style: "editorial",
            entrance: {type: "fade", delay: 1.2, duration: 0.6},
          },
        ],
        right: [
          {
            type: "org_tree",
            centerNode: {label: "Rohit Mehta", sublabel: "VP Product"},
            children: [
              {label: "Consumer Growth", sublabel: "12 engineers"},
              {label: "Platform Core", sublabel: "8 engineers"},
              {label: "Data & Insights", sublabel: "6 analysts"},
              {label: "Design", sublabel: "4 designers"},
            ],
            style: "radial",
            entrance: {type: "scale", delay: 0.6, duration: 0.8},
          },
        ],
      },
      narration:
        "Rohit leads a thirty-person cross-functional organisation spanning consumer growth, platform core, data and insights, and design. He believes great products come from empowered teams, not process.",
    },
    {
      sceneId: "strengths",
      title: "Key Strengths",
      durationSeconds: 8,
      background: {
        type: "solid",
        color: "#F4F1EA",
      },
      layout: {
        type: "stack",
        direction: "column",
        gap: 36,
        justify: "center",
        elements: [
          {
            type: "text",
            content: "Key Strengths",
            role: "label",
            entrance: {type: "fade", delay: 0.2, duration: 0.4},
          },
          {
            type: "text",
            content: "What sets Rohit apart",
            role: "heading",
            entrance: {type: "slide_up", delay: 0.4, duration: 0.6},
          },
          {
            type: "bullet_list",
            items: [
              {text: "Zero-to-one product thinking", subtext: "Built three products from scratch to 10M+ users", icon: "💡"},
              {text: "Data-driven decision making", subtext: "Pioneered experimentation culture at Flipkart", icon: "📊"},
              {text: "Cross-functional leadership", subtext: "Managed product, engineering, design, and data teams", icon: "🤝"},
              {text: "Strategic storytelling", subtext: "Consistently secured C-suite buy-in for bold bets", icon: "🎯"},
            ],
            columns: 2,
            entrance: {type: "slide_left", delay: 0.8, duration: 0.6},
            stagger: 0.15,
          },
        ],
      },
      narration:
        "Rohit's standout strengths include zero-to-one product thinking, data-driven decision making, cross-functional leadership, and the ability to tell a compelling strategic story.",
    },
    {
      sceneId: "closing",
      title: "Closing",
      durationSeconds: 6,
      background: {
        type: "gradient",
        from: "#0B1D2E",
        to: "#1A3A54",
        angle: 145,
      },
      themeOverrides: {
        foreground: "#F7FBFF",
        foregroundMuted: "#A0B4C8",
        accent: "#D4A843",
      },
      layout: {
        type: "stack",
        direction: "column",
        gap: 28,
        align: "center",
        justify: "center",
        elements: [
          {
            type: "text",
            content: "Rohit Mehta",
            role: "display",
            align: "center",
            entrance: {type: "scale", delay: 0.3, duration: 0.8},
          },
          {
            type: "text",
            content: "VP of Product",
            role: "subheading",
            align: "center",
            entrance: {type: "fade", delay: 0.8, duration: 0.5},
          },
          {
            type: "divider",
            thickness: 2,
          },
          {
            type: "text",
            content: "Private and Confidential",
            role: "caption",
            align: "center",
            entrance: {type: "fade", delay: 1.5, duration: 0.5},
          },
        ],
      },
      narration: "Rohit Mehta. A proven product leader ready for his next chapter.",
    },
  ],
};
