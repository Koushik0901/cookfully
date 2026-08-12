---
name: Cookfully
colors:
  surface: '#0f141b'
  surface-dim: '#0f141b'
  surface-bright: '#353941'
  surface-container-lowest: '#0a0e15'
  surface-container-low: '#171c23'
  surface-container: '#1b2027'
  surface-container-high: '#262a32'
  surface-container-highest: '#31353d'
  on-surface: '#dfe2ed'
  on-surface-variant: '#c0c7d6'
  inverse-surface: '#dfe2ed'
  inverse-on-surface: '#2c3138'
  outline: '#8a919f'
  outline-variant: '#404753'
  surface-tint: '#a6c8ff'
  primary: '#a6c8ff'
  on-primary: '#00315f'
  primary-container: '#2c91ff'
  on-primary-container: '#002a54'
  inverse-primary: '#005fb0'
  secondary: '#a9c8fc'
  on-secondary: '#09315c'
  secondary-container: '#294a76'
  on-secondary-container: '#9bbaed'
  tertiary: '#ffb68c'
  on-tertiary: '#532200'
  tertiary-container: '#e76e0a'
  on-tertiary-container: '#481d00'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#d5e3ff'
  primary-fixed-dim: '#a6c8ff'
  on-primary-fixed: '#001c3b'
  on-primary-fixed-variant: '#004787'
  secondary-fixed: '#d5e3ff'
  secondary-fixed-dim: '#a9c8fc'
  on-secondary-fixed: '#001c3b'
  on-secondary-fixed-variant: '#274773'
  tertiary-fixed: '#ffdbc9'
  tertiary-fixed-dim: '#ffb68c'
  on-tertiary-fixed: '#321200'
  on-tertiary-fixed-variant: '#753400'
  background: '#0f141b'
  on-background: '#dfe2ed'
  surface-variant: '#31353d'
typography:
  display-lg:
    fontFamily: Hanken Grotesk
    fontSize: 48px
    fontWeight: '800'
    lineHeight: 56px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Hanken Grotesk
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Hanken Grotesk
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  body-lg:
    fontFamily: Public Sans
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Public Sans
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  data-lg:
    fontFamily: JetBrains Mono
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.02em
  data-sm:
    fontFamily: JetBrains Mono
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 16px
  label-caps:
    fontFamily: Public Sans
    fontSize: 12px
    fontWeight: '700'
    lineHeight: 16px
    letterSpacing: 0.05em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 8px
  xs: 4px
  sm: 12px
  md: 24px
  lg: 48px
  xl: 64px
  gutter: 20px
  margin-mobile: 16px
  margin-desktop: 40px
---

## Brand & Style

The design system is engineered for the intersection of culinary artistry and nutritional precision. It speaks to users who view food as both fuel and craft—demanding the rigor of a data-driven fitness tracker with the sensory appeal of a premium cookbook.

The aesthetic follows a **Modern / Tech-Humanist** approach. It leans into "Dark Mode First" as the primary environment to minimize kitchen glare and maximize the punch of macro-specific data visualizations. The interface utilizes generous whitespace (or "dark space") to create a sense of calm, ensuring that complex nutritional data never feels overwhelming. Subtle tactile cues—soft shadows and layered surfaces—prevent the UI from feeling like a flat spreadsheet, instead offering a sophisticated, tool-like experience that feels authoritative yet inviting.

## Colors

The palette is anchored by a deep **Slate-toned Charcoal** foundation, providing a high-contrast backdrop for functional data. The **Primary Brand Accent (Electric Blue)** is used for high-intent actions and progress completion.

Nutritional data is strictly categorized by an "Inviolable Macro Palette" to build muscle memory:
- **Protein (Electric Blue):** Reliable, structural, and primary.
- **Carbs (Deep Amber):** Energetic and warm.
- **Fats (Steel Blue/Grey):** Rich and muted.

Neutral scales prioritize legibility, using cool-tinted greys to distinguish between background, container, and interactive states without introducing visual noise.

## Typography

This design system utilizes a dual-font strategy to separate narrative content from technical data.

- **Hanken Grotesk** is used for headlines and titles. It provides a sharp, contemporary edge that feels "fitness-forward" and confident.
- **Public Sans** handles all body copy and instructions. Its neutral, humanist qualities ensure long-form recipes remain highly readable and warm.
- **JetBrains Mono** is reserved exclusively for numerical data, weights, and macro counts. The monospaced nature ensures that numbers align perfectly in lists and dashboards, reinforcing the "data-forward" brand pillar.

For mobile, `display-lg` should scale down to 32px to ensure title visibility without excessive wrapping.

## Layout & Spacing

The layout employs a **Fluid Grid** system with fixed maximum widths for recipe content to prevent line lengths from becoming unreadable. 

- **Grid:** 12-column on desktop, 4-column on mobile.
- **Rhythm:** An 8px base unit drives all padding and margin decisions. 
- **Density:** High density for data tables and ingredient lists; low density (more whitespace) for recipe discovery and editorial content.

Components should utilize "Safe Areas" for mobile interaction, specifically ensuring horizontal scrolling elements (like Day Tabs) have 16px of bleed to indicate more content is available.

## Elevation & Depth

The design system uses **Tonal Layering** combined with **Ambient Shadows** to create a sense of hierarchy. 

- **Level 0 (Background):** Deepest charcoal slate tone.
- **Level 1 (Cards/Containers):** Slightly lighter surface with a 1px subtle border (#FFFFFF10) to define edges against the background.
- **Level 2 (Modals/Popovers):** Higher contrast with a soft, diffused 24px blur shadow (0% offset, 15% opacity black).

Glassmorphism is used exclusively for "Sticky" headers or bottom navigation bars, using a backdrop-filter (blur: 12px) to maintain context of the scroll position behind the navigation.

## Shapes

The shape language is "Soft-Modern." A standard radius of **12px to 16px** is applied to cards and large containers to evoke a friendly, approachable feel. 

- **Interactive Elements:** Buttons and Input fields use a 12px radius.
- **Data Tags:** Pills (full-round) are used for "Macro Badges" to distinguish them from interactive buttons.
- **Progress Bars:** Use fully rounded caps to feel fluid and organic.

## Components

### Macro Rings & Budget Bars
- **Macro Rings:** 8px stroke width. Background track should be a low-opacity version of the macro color (e.g., Protein track is Blue at 10% opacity).
- **Budget Bar:** A thick horizontal track (12px height). The "Consumed" portion glows slightly using a soft outer shadow of the same color.

### Recipe Cards
- Image-led with a 16:9 aspect ratio. 
- Macro Badges are overlaid in the top-right corner using a semi-transparent dark blur.
- Title uses `headline-sm`, and the footer contains "Total Time" and "Calorie Count" using `data-sm`.

### Day Tabs
- Horizontal scroller. Active state uses the Primary Brand Accent (Electric Blue) for the text and a small dot indicator below.
- Inactive days show the date and a "dimmed" ring representing the total calorie completion for that past/future day.

### Ingredient Row
- Features a custom checkbox that, when checked, strikes through the text and reduces its opacity to 40%.
- Quantities are right-aligned using `data-sm` for vertical alignment precision.

### Nutrition Panel
- Styled as a clean list with 1px dividers.
- "Estimated" badges use `label-caps` in a subtle ghost-pill format (low-opacity border, no fill) to indicate data confidence without drawing excessive attention.