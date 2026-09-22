---
name: Lavoro Esterno Core
colors:
  surface: '#faf8ff'
  surface-dim: '#d2d9f4'
  surface-bright: '#faf8ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f3ff'
  surface-container: '#eaedff'
  surface-container-high: '#e2e7ff'
  surface-container-highest: '#dae2fd'
  on-surface: '#131b2e'
  on-surface-variant: '#434655'
  inverse-surface: '#283044'
  inverse-on-surface: '#eef0ff'
  outline: '#737686'
  outline-variant: '#c3c6d7'
  surface-tint: '#0053db'
  primary: '#004ac6'
  on-primary: '#ffffff'
  primary-container: '#2563eb'
  on-primary-container: '#eeefff'
  inverse-primary: '#b4c5ff'
  secondary: '#515f74'
  on-secondary: '#ffffff'
  secondary-container: '#d5e3fc'
  on-secondary-container: '#57657a'
  tertiary: '#943700'
  on-tertiary: '#ffffff'
  tertiary-container: '#bc4800'
  on-tertiary-container: '#ffede6'
  error: '#ef4444'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dbe1ff'
  primary-fixed-dim: '#b4c5ff'
  on-primary-fixed: '#00174b'
  on-primary-fixed-variant: '#003ea8'
  secondary-fixed: '#d5e3fc'
  secondary-fixed-dim: '#b9c7df'
  on-secondary-fixed: '#0d1c2e'
  on-secondary-fixed-variant: '#3a485b'
  tertiary-fixed: '#ffdbcd'
  tertiary-fixed-dim: '#ffb596'
  on-tertiary-fixed: '#360f00'
  on-tertiary-fixed-variant: '#7d2d00'
  background: '#faf8ff'
  on-background: '#131b2e'
  surface-variant: '#dae2fd'
  success: '#10b981'
  info: '#0ea5e9'
  warning: '#f59e0b'
  muted: '#f1f5f9'
  border: '#e2e8f0'
typography:
  headline-lg:
    fontFamily: Inter
    fontSize: 30px
    fontWeight: '600'
    lineHeight: 36px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 28px
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.02em
  mono-data:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  base: 4px
  gutter: 16px
  margin-page: 24px
  sidebar-width: 260px
  sidebar-collapsed: 64px
  topbar-height: 56px
---

## Brand & Style

The design system is engineered for high-stakes operational environments where data density, clarity, and reliability are paramount. It follows a **Modern Corporate** aesthetic—heavily influenced by the functional minimalism of `shadcn/ui`—tailored for B2B internal tools.

The brand personality is professional, sober, and precise. It eschews decorative elements like gradients or glassmorphism in favor of a rigorous, utility-first visual language. The UI prioritizes the "operational long-haul," ensuring that users can interact with complex datasets for extended periods without visual fatigue.

**Key Stylistic Pillars:**
- **Functional Minimalism:** White space is used strategically to group related data points rather than purely for aesthetics.
- **Data Density:** High information density is maintained through compact component sizing and a focus on typographic hierarchy over large icons or imagery.
- **Operational Trust:** Every state change, audit trail, and automated insight (AI) is presented with structured clarity to build user confidence in the underlying data.

## Colors

The color strategy uses a restrained "Neutral-Plus" approach. A single primary accent (Blue 600) is used sparingly for primary actions and focus states, ensuring that it remains a strong signal in a sea of data.

**Color Usage:**
- **Primary:** Reserved for the main call-to-action, active navigation states, and primary buttons.
- **Neutrals:** A sophisticated Slate/Zinc scale (from `Slate-50` to `Slate-950`) handles backgrounds, borders, and text contrast.
- **Semantic Palette:** Success, Info, Warning, and Error colors are used for status badges and system health indicators. These must always be accompanied by a secondary signal (icon or label) to ensure accessibility.
- **Dark Mode:** The system supports a native dark mode using `Zinc-950` as the base surface color to reduce glare in low-light environments.

## Typography

The system uses **Inter** for all UI elements to ensure maximum legibility and a neutral, professional tone. Hierarchy is established primarily through font weight and subtle color shifts rather than drastic size changes.

**Guidelines:**
- **Headlines:** Used for page titles (`headline-lg`) and section headers.
- **Body:** The default interface size is `body-md` (14px). Use `body-lg` (16px) only for primary content areas or search inputs.
- **Labels & Metadata:** Use `label-sm` (12px) for table headers, form labels, and timestamps.
- **Monospaced Data:** For phone numbers, UUIDs, and technical logs, use a monospaced font at 13px to ensure character alignment and readability during manual comparison.

## Layout & Spacing

The layout follows a **Fixed-Fluid Hybrid** model. The sidebar remains fixed or collapsible, while the main content area utilizes a fluid 12-column grid to accommodate massive data tables.

**Structure:**
- **Sidebar:** Left-aligned, persistent. Houses main navigation and administration.
- **Top Bar:** Compact (56px) for breadcrumbs and global phone search.
- **Grid:** 12-column system with 16px gutters. In data-heavy views (e.g., Record Details), the grid may collapse to simple flex-columns to maximize density.
- **Spacing Scale:** Strictly follows a 4px (0.25rem) baseline. Use 8px for internal component padding and 16px–24px for section margins.

**Breakpoints:**
- **Desktop (1440px+):** Primary target. All sidebars and columns visible.
- **Laptop (1024px):** Sidebar may collapse to icons; table columns use truncation.
- **Tablet/Mobile:** Sidebars move to a drawer (Sheet) component. Tables transition to a vertical list-card format.

## Elevation & Depth

To maintain a clean B2B look, depth is communicated through **Tonal Layering** and **Low-Contrast Outlines** rather than heavy shadows.

**Layering Logic:**
- **Level 0 (Background):** `Slate-50` (Light) or `Zinc-950` (Dark).
- **Level 1 (Cards/Surface):** White background with a 1px border (`Slate-200`). This is the primary surface for data tables and metric cards.
- **Level 2 (Overlays):** Dialogs, Drawers, and Popovers. These use a slightly more pronounced shadow (4px blur, 0.1 opacity) to indicate they sit above the primary workflow.

**Shadows:**
- Shadow usage is restricted to functional elevation (e.g., indicating a dropdown is open) rather than decorative styling.

## Shapes

The design uses a **Soft (rounded-md)** shape language. This provides a modern touch without sacrificing the professional "tool-like" feel of the application.

**Rounding Rules:**
- **Standard (4px):** Checkboxes, small buttons, and input fields.
- **Large (8px):** Main content cards, dialogs, and navigation containers.
- **Pill (999px):** Status badges (e.g., "Active", "Success") to distinguish them from interactive buttons.

## Components

**Buttons:**
- **Primary:** Solid Blue 600.
- **Secondary/Ghost:** Bordered or transparent for low-priority actions.
- **Size:** Compact (32px height) for table actions; Standard (40px) for forms.

**Data Tables:**
- **Density:** 40px row height for standard; 32px for "compact" views.
- **Features:** Sticky headers, row hover highlighting, and checkbox selection.
- **Numbers:** Phone numbers must be displayed in a monospaced font for quick visual scanning.

**Status Badges:**
- Small, pill-shaped, using a light background tint with a dark foreground text (e.g., Light Green BG with Dark Green Text for "Success").

**Drawers & Dialogs:**
- Used for media details and AI summary regeneration. Drawers should slide from the right to maintain context of the underlying list or record.

**Metric Cards:**
- Flat borders (1px), headline-sm for values, and label-sm for titles. No background icons; use color-coded top-borders for status (e.g., red top-border for "Scraping Errors").

**AI Summary Section:**
- Distinct from standard record data. Use a subtle background tint (Slate-50) and clear section headers (Summary, Forum Info, Unverified) to differentiate generated content from scraped data.