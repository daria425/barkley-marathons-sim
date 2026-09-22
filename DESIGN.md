---
name: Barkley Sim
description: Live-race command center for an LLM agent running a Barkley-style ultra.
colors:
  background: "#000000"
  foreground: "#f4f5f6"
  card: "#131315"
  popover: "#1c1c1f"
  primary: "#00aec7"
  primary-foreground: "#00171c"
  secondary: "#38383a"
  secondary-foreground: "#f4f5f6"
  muted: "#1c1c1f"
  muted-foreground: "#9a9aa0"
  destructive: "#ef4b4b"
  destructive-foreground: "#fff5f5"
  border: "rgba(255, 255, 255, 0.08)"
  input: "rgba(255, 255, 255, 0.1)"
  ring: "rgba(0, 174, 199, 0.5)"
typography:
  title:
    fontFamily: "Ubuntu, system-ui, Segoe UI, Roboto, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 600
    lineHeight: "1.25"
    letterSpacing: "0.02em"
  body:
    fontFamily: "Ubuntu, system-ui, Segoe UI, Roboto, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: "1.6"
    letterSpacing: "normal"
  label:
    fontFamily: "Ubuntu, system-ui, Segoe UI, Roboto, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 500
    lineHeight: "1.2"
    letterSpacing: "0.02em"
  readout:
    fontFamily: "Ubuntu Mono, ui-monospace, Consolas, monospace"
    fontSize: "1.25rem"
    fontWeight: 400
    lineHeight: "1"
    letterSpacing: "normal"
rounded:
  sm: "6px"
  md: "8px"
  lg: "10px"
  xl: "14px"
  full: "9999px"
spacing:
  xs: "8px"
  sm: "12px"
  md: "16px"
  lg: "20px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-foreground}"
    rounded: "{rounded.md}"
    padding: "8px 16px"
  button-primary-hover:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-foreground}"
  panel:
    backgroundColor: "{colors.card}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.xl}"
  badge-outline:
    backgroundColor: "transparent"
    textColor: "{colors.muted-foreground}"
    rounded: "{rounded.full}"
    padding: "2px 8px"
---

# Design System: Barkley Sim

## Overview

**Creative North Star: "The Broadcast Command Center"**

Barkley Sim's live-race dashboard reads like a race-control monitor bolted together for one purpose: make an LLM agent's real position, believed position, vitals, and reasoning legible to someone with zero trail-running context, at a glance, while sim time runs underneath it. It is a pure-black instrument panel, not a card grid — one instrument (the map, carrying the true-vs-believed position gap) leads, vitals and monologue are side instruments, and time/speed/connection are a persistent bottom rail, never a modal. Every surface sits at the same restrained elevation off a near-black ground; nothing shouts over anything else.

The palette is almost monochrome on purpose: near-black ground, off-white text, one warm-neutral secondary gray, and exactly one saturated color — a cyan — spent only on things that mean "this is the signal to watch" (the believed-position marker, active/primary actions, live-connection state, key readouts like HR). Ubuntu carries every weight of text in the system, including numeric readouts in its Mono cut; there is no separate display/editorial face anywhere in the build; there is also no large hero/display type tier at all — the interface never needs to shout a headline, only report numbers.

**Key Characteristics:**
- Near-black ground, off-white text, single cyan accent — no secondary hue anywhere in the shipped build
- One shadow language (`--shadow-panel`) shared by every panel; no per-panel elevation variation
- Ubuntu (sans) for prose and labels, Ubuntu Mono for every numeric readout and timestamp
- Inline SVG dotted-gradient backdrop, never a raster background asset
- Real position stays neutral (white/black); belief/estimate is the only thing drawn in the accent color

## Colors

A near-monochrome instrument palette: black ground, one warm gray for secondary surfaces, one cyan reserved for signal.

### Primary
- **Command Cyan** (`#00aec7`): the system's sole accent. Used for the believed-position map marker and its connecting line to true position, the primary button, active/live-connection state, key numeric readouts worth calling out (HR value), focus rings (`rgba(0, 174, 199, 0.5)`), and text selection tint.

### Neutral
- **Void Black** (`#000000`): page background, beneath the dotted texture.
- **Panel Charcoal** (`#131315`): card/panel background (`--card`) — every Panel, the map frame, the bottom rail.
- **Popover Charcoal** (`#1c1c1f`): dropdown/select surface (`--popover`), one step lighter than panel charcoal for stacking order.
- **Off-White** (`#f4f5f6`): primary text/foreground, and the true-position map marker fill.
- **Instrument Gray** (`#38383a`): secondary surface color (`--secondary`) — scrollbar thumb, secondary buttons/badges.
- **Muted Gray** (`#9a9aa0`): secondary/label text (`--muted-foreground`) — stat labels, timestamps' prose companions, idle-state copy.
- **Hairline White** (`rgba(255, 255, 255, 0.08)`): panel borders (`--border`) and input borders, always a low-opacity white over dark, never a flat gray hex.
- **Alert Red** (`#ef4b4b`): destructive state (`--destructive`) — defined in tokens for future destructive actions (e.g. quit), not yet consumed by any shipped component; see Do's and Don'ts.

### Named Rules
**The One Signal Rule.** Cyan is the only saturated color in the system. It marks exactly one thing per context — the belief marker on the map, the live dot in the connection badge, the primary action — never decoration. If a second accent hue is needed, that's a sign the interface has stopped being an instrument panel.

## Typography

**Body/UI Font:** Ubuntu (weights 400/500/700), self-hosted woff2, falling back to `system-ui, "Segoe UI", Roboto, sans-serif`
**Label/Mono Font:** Ubuntu Mono (weights 400/700), self-hosted woff2, falling back to `ui-monospace, Consolas, monospace`

**Character:** Ubuntu carries every weight in the system — there is no separate display face and no large hero type tier; the dashboard reports, it doesn't headline. Ubuntu Mono is reserved for anything that is a number or a live value, giving numeric readouts a tabular, watch-face precision against the sans prose around them.

### Hierarchy
- **Title** (600, 0.875rem/14px, tight line-height, 0.02em tracking): panel headings ("Monologue"), persona name in the watch card.
- **Body** (400, 0.875rem/14px, 1.6 line-height): monologue entries, idle-state copy.
- **Label** (500, 0.6875rem/11px, uppercase, 0.02em tracking, muted-foreground): stat labels in the watch card ("ELAPSED", "HR", "GLYCOGEN") — a functional data-label convention drawn directly from Garmin-style watch faces (PRODUCT.md), not an editorial kicker/eyebrow; it never sits above a headline, only above a numeric readout.
- **Readout** (400, mono, 1.25rem/20px, tabular-nums, 1 line-height): the numeric value under every stat label, and every clock/timestamp in the UI (bottom-rail clock, monologue entry timestamps).

### Named Rules
**The No-Display-Tier Rule.** This system has no display/hero typography role. Every screen in the shipped build is instrumentation, not editorial; don't introduce a large display size without a concrete need for one.

## Layout

A two-region body over a persistent bottom rail, all inside a padded viewport frame (`p-4` / 16px, `lg:p-6` / 24px). On large screens (`lg:` and up) the body is a single row: the map takes the remaining flex space (~60% in practice) on the left, and a right rail fixed at `basis-40%` stacks the watch-face card above the monologue feed card, sharing a `gap-5` (20px) rhythm; below `lg`, the layout stacks vertically (map fixed at `45vh`, then the aside, then controls), with `gap-4` (16px). The bottom rail (`Controls`) is always full-width, wraps its own contents on narrow viewports, and is never a modal or overlay — it's part of the persistent frame.

Spacing rhythm observed in components: 16px (`p-4`) internal panel padding as the base unit, 12px (`gap-3`) between a panel's sub-elements, 8px (`gap-2`) for tight label/value pairs. Panels never touch — the 16–20px outer gap is constant across breakpoints.

## Elevation & Depth

One shared elevation language, applied identically to every panel (map frame, watch-face card, monologue card, bottom rail) via a single `--shadow-panel` custom property — never a per-component shadow. Depth is ambient and structural (lifts each panel a consistent amount off the black/dotted ground) rather than expressive; no panel is ever "louder" than another, and there is no hover-elevation or interactive shadow growth anywhere in the build.

### Shadow Vocabulary
- **Panel** (`box-shadow: 0 1px 2px rgba(0,0,0,0.4), 0 12px 32px -8px rgba(0,0,0,0.65), 0 0 0 1px rgba(255,255,255,0.04)`): the only shadow value in the system. Applied to every Panel-based surface and to the map frame directly.

### Named Rules
**The One Shadow Rule.** All elevated surfaces share exactly one shadow token. Don't invent a second, "bigger" shadow for a surface meant to feel more important — importance is expressed through position and content, not elevation.

## Shapes

Two radius steps in practice: **14px** (`rounded-xl`, `--radius-xl`) for every panel-level container (cards, the map frame), and **8px** (`rounded-md`, `--radius-md`) for interactive controls (buttons, selects, inputs). Fully round (`rounded-full`) appears only for pill-shaped elements: badges, the connection-status dot, and the scrollbar thumb. Borders are uniformly hairline, low-opacity white over dark (`rgba(255,255,255,0.06–0.08)`), never a flat gray stroke — this is what reads as "structure" against the black ground in place of heavier framing.

## Components

### Buttons
- **Shape:** 8px radius (`rounded-md`).
- **Primary:** cyan background (`#00aec7`) with near-black text (`#00171c`), `h-9 px-4 py-2` at default size, `h-8 px-3` at `sm` (used in Controls' Start button).
- **Hover / Focus:** primary darkens via `hover:bg-primary/90`; focus shows a 3px cyan ring at 50% opacity plus a ring-colored border, never a shadow change.
- **Secondary / Outline / Ghost:** present in the shadcn primitive (`secondary`, `outline`, `ghost`, `link`, `destructive` variants) but only `default` and implicitly `outline` (via Badge) are exercised in the shipped screens; the `destructive` variant exists in tokens but is not consumed by any shipped control (see Do's and Don'ts).

### Badge
- **Style:** pill (`rounded-full`), `outline` variant used for the bib-number badge — transparent background, hairline `border-white/10`, muted-foreground text.

### Cards / Containers — Panel (signature component)
- **Corner Style:** 14px (`rounded-xl`).
- **Background:** `#131315` (panel charcoal).
- **Shadow Strategy:** the single `--shadow-panel` value (see Elevation & Depth) — no exceptions observed.
- **Border:** hairline `border-white/[0.06]`.
- **Internal Padding:** 16px (`p-4`) standard; the bottom rail uses `px-5 py-3`.
- Every surface in the dashboard (map frame, `WatchFace`, `MonologueFeed`, `Controls`, the idle-state card) is a `Panel` instance or shares its exact treatment — this is the one true container primitive of the system.

### Watch-Face Stat (signature component)
A label/value pair used for every physiology readout: an 11px uppercase muted `Label` above a mono `Readout` value, optionally tinted cyan (`accent` prop) for the single most important reading in context (HR). Laid out in a 2-column grid (`grid-cols-2 gap-x-4 gap-y-3`) inside the WatchFace panel.

### Inputs / Fields — Select
- **Style:** transparent/dark background, `border-input` (10% white) hairline border, `rounded-md`, `shadow-xs`.
- **Focus:** border shifts to the ring color plus a 3px cyan focus ring, same treatment as buttons.
- Used for the 1x/60x/600x speed control in the bottom rail, values rendered in mono.

### Navigation
No traditional nav exists; the bottom rail (`Controls`) functions as the system's persistent chrome: brand wordmark ("Barkley" in off-white + "Sim" in cyan, uppercase, `tracking-[0.08em]`, bold), live sim clock and weather (mono), connection-status dot + label, speed `Select`, and the Start button — always visible, never collapsed behind a menu.

### Map (signature component)
Dark MapLibre basemap (`streets-v2-dark`) framed as a Panel. True position renders as a solid off-white dot (`#f4f5f6`) with a black stroke — deliberately quiet. Believed position renders larger and in the sole accent color (`#00aec7`, translucent stroke halo) since it's the product's "comedy engine" and the thing meant to draw the eye. A dashed cyan line connects the two. The static course trail is a dashed neutral gray (`#6b6f76`); book markers use a one-off warm gold (`#e8b339`) reserved for this single purpose (not a system-wide token — see Colors).

## Do's and Don'ts

### Do:
- **Do** spend the cyan accent (`#00aec7`) on exactly one signal per context — belief marker, live state, primary action — per the One Signal Rule.
- **Do** apply the single `--shadow-panel` shadow to any new elevated surface; don't create a second shadow token.
- **Do** render numeric/time values in Ubuntu Mono with `tabular-nums`; reserve Ubuntu (sans) for prose and labels.
- **Do** keep true-position markers neutral (off-white/black) and reserve the accent color for believed/estimated state, anywhere position or estimation is shown again.
- **Do** self-host font files (`/public/fonts`); never load fonts from a CDN `<link>`.

### Don't:
- **Don't** add a second saturated accent hue; the system's identity depends on cyan being the only one.
- **Don't** introduce hard-offset or "neobrutalist" shadows — the one shadow token is soft and ambient by design.
- **Don't** turn the watch-face stat label (uppercase, 11px, muted) into a decorative section kicker/eyebrow elsewhere — it's a functional data-label paired with a readout, not a headline device, and should not be promoted to a general heading style.
- **Don't** treat the raster look as acceptable for the background texture — the dotted gradient is inline SVG (`<pattern>` + mask), never a bitmap asset.
