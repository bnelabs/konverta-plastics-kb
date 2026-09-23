# UI/UX Mobile-First Redesign Spec

## Goals
- Professional, easy to understand interface for field use
- Mobile-first, touch-friendly, accessible
- Make factual data entry with sources obvious and validated
- Keep safety notes and review status prominent

## Current Issues
- Desktop-first layout with sidebar that becomes horizontal scroll on mobile
- Search not sticky, tap targets ~37px
- Dialogs not optimized for small screens
- Form validation feedback minimal
- No bulk data collection workflow

## Mobile-First Principles
1. Single column layout first, expand to multi-column on larger screens
2. Bottom navigation for primary sections: Overview, Materials, Processes, Projects
3. Sticky search bar at top
4. 44px minimum tap targets
5. Safe area insets for iOS/Android
6. Progressive disclosure in detail views

## Navigation
- Mobile: bottom tab bar with icons + labels, active state highlighted
- Tablet+: collapsible sidebar, persistent on desktop
- Top bar: breadcrumb, version, refresh

## Material Cards
- Large code pill, toxicity handling badge
- Melting range prominent
- Review status badge: "Prototype data · verify" vs "Source checked"
- Tap to open detail dialog

## Detail View
- Hero with material name and review banner
- Source block always visible with link
- Process suitability list with safety precautions highlighted
- Related projects
- Edit button for authorized users

## Data Entry / Factual Collection
- Editor dialog with clear sections
- Required fields: code, name, source_title, source_url https
- Review status dropdown: draft / verified
- Inline validation with helpful messages
- Safety notes field with placeholder examples
- Ability to save as draft then verify later
- Bulk import helper: CSV template with columns code,name,common_uses,melt_temp_c,density_g_cm3,toxicity_level,recyclability,notes,source_title,source_url,review_status
- Import validates each row, reports errors, does not insert without source

## Accessibility
- Focus outlines, aria-labels, focus trap in dialogs
- Color contrast meets WCAG AA
- Keyboard navigation

## Implementation Notes
- Refactor CSS to mobile-first: base styles for mobile, media queries min-width
- Keep existing design tokens, adjust spacing
- No API changes needed, only UI
- Ensure unknown compatibility remains unknown, never auto-infer
