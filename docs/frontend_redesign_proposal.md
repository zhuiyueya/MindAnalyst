# Frontend Redesign Proposal: "Mind Analyst" - The Data Terminal

## 1. Design Philosophy
**Theme:** "Cognitive Brutalism" / "The Analyst's Terminal"
**Concept:** This tool is not a passive consumption device; it is a workspace for dissecting information. The interface should feel like a precision instrument—raw, responsive, and data-centric. We are moving away from the "soft SaaS" aesthetic (rounded corners, drop shadows, blues) to a "hard-edged" technical aesthetic.

## 2. Visual Identity

### Typography
*Avoid generic sans-serifs.*
*   **Headings**: **Space Grotesk** (Geometric, quirky, technical).
*   **Body / Data**: **IBM Plex Mono** (Monospaced, legible, distinct).
*   **Rationale**: The mix of geometric headers and monospaced body text emphasizes the "data analysis" nature of the tool.

### Color Palette (Dark Mode Default)
*   **Background**: `#09090b` (Void Black)
*   **Surface**: `#18181b` (Zinc 900)
*   **Border**: `#27272a` (Zinc 800) - *Visible structural lines*
*   **Text Primary**: `#e4e4e7` (Zinc 200)
*   **Text Secondary**: `#a1a1aa` (Zinc 400)
*   **Accent A (Primary)**: `#ccff00` (Acid Lime) - Used for primary actions, active states.
*   **Accent B (Secondary)**: `#ff3366` (Signal Red) - Used for alerts, delete actions.
*   **Accent C (Tertiary)**: `#00f0ff` (Cyan) - Used for information highlighting.

### Layout & Spacing
*   **Grid**: Visible, rigid grid lines separating content areas.
*   **Density**: High density for data views, dramatic whitespace for landing/intro areas.
*   **Borders**: 1px solid borders everywhere. No drop shadows. Depth is created by layering and borders.

### Motion
*   **Type**: Instant, mechanical.
*   **Transitions**: "Blink" transitions rather than "Fade".
*   **Hover**: Invert colors (Black text on Lime background) rather than dimming.

## 3. Implementation Plan

### Phase 1: Foundation
1.  **Tailwind Configuration**:
    *   Extend `tailwind.config.js` with the new color palette and font families.
    *   Import fonts in `index.html`.
2.  **Global CSS**:
    *   Reset styles to remove default browser "softness".
    *   Define CSS variables for theming.
    *   Apply a global "scanline" or "noise" texture (optional, subtle).

### Phase 2: Structural Overhaul (App.vue)
*   **Navigation**:
    *   Replace the top navbar with a **Sidebar "Command Rail"**.
    *   Links look like technical tabs or terminal commands (e.g., `> /DASHBOARD`, `> /INGEST`).
    *   Status indicators (API health, Queue status) displayed like system metrics.

### Phase 3: Component Redesign
*   **Dashboard**:
    *   Turn "cards" into "Data Modules".
    *   Use ASCII-art style headers or technical labels (e.g., `MODULE: AUTHOR_STATS [ACTIVE]`).
*   **Author/Video Lists**:
    *   Strict tabular layout with monospaced data.
    *   "Hover" effects that highlight the entire row with a crosshair cursor.
*   **Chat Interface**:
    *   Style it like a terminal log or a script dialogue.
    *   User input: A clear, high-contrast command line at the bottom.
    *   AI Response: Streamed text with a blinking cursor block.

## 4. "Before & After" Concept

| Feature | Current (Generic SaaS) | Proposed (Cognitive Brutalism) |
| :--- | :--- | :--- |
| **Font** | System Sans / Inter | Space Grotesk + IBM Plex Mono |
| **Container** | White card, shadow, rounded-lg | Black bg, 1px border, square corners |
| **Button** | Blue rounded, shadow | Lime outline, uppercase, square, hover-fill |
| **Bg** | Gray-100 | Black #09090b + faint grid lines |
| **Nav** | Top bar, white | Left vertical rail, technical icons |

## 5. Approval Request
Do you approve this direction? Once approved, I will begin by installing the fonts and configuring the design tokens in Tailwind.
