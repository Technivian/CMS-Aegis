# Design System Pattern Reference

This document maps legacy pattern classes to standardized design system components.

## Pattern Consolidation Map

### Detail Pages Layout

| Legacy | New | Usage | Notes |
|--------|-----|-------|-------|
| `page-wrap page-stack` | `ds-detail-shell` | Main container | Full width detail page layout |
| `provider-identity-card` | `ds-detail-card ds-detail-head` | Top identity section | Header with title, badges, meta, actions |
| `provider-identity-wrap` | Flex layout | Internal structure | Flexbox for title/meta and action buttons |
| `provider-identity-main` | Flex column | Left side | Title, badges, metadata grid |
| `provider-identity-actions` | Flex row gap | Right side | Primary + secondary actions |
| `provider-capacity-strip` | `ds-summary-strip` | Status bar | Horizontal summary items (availability, wait time, etc) |
| `matching-summary-strip` | `ds-summary-strip` | Status bar | Same as above |
| `provider-grid` | `grid grid-cols-1 xl:grid-cols-12` | Main layout | Two-column: main (8 cols) + sidebar (4 cols) |

### Content Cards

| Legacy | New | Usage | Notes |
|--------|-----|-------|-------|
| `provider-panel` | `ds-card` | General card | For sections like profile summary, constraints, track record |
| `ds-card` | `ds-card` | General card | Already standardized |
| `side-card` | `ds-sidebar-card` | Sidebar card | In right rail, slightly different styling |
| `side-card-primary` | `ds-sidebar-card ds-sidebar-card--primary` | Primary sidebar card | Call-to-action card |

### Content Organization

| Legacy | New | Usage | Notes |
|--------|-----|-------|-------|
| `field-rows` | `ds-field-list` | Definition list | Alternating field labels + values |
| `field-row` | `ds-field-item` | Individual field | Single label/value pair |
| `panel-title` | `ds-card-title` | Card heading | h2/h3 for card sections |
| `rail-title` | `ds-sidebar-title` | Sidebar heading | Smaller title in sidebar |
| `signal-list` | `ds-signal-list` | Bullet list | Green check signals, "why passing", constraints |
| `mini-list` | `ds-mini-list` | Compact list | Smaller bullet list for sidebar summaries |
| `contact-list` | `ds-contact-list` | Contact info | Stack of contact details |

### Track Record & Stats

| Legacy | New | Usage | Notes |
|--------|-----|-------|-------|
| `track-grid` | `ds-metric-grid` | 3-column metric | Active cases, open cases, configurations |
| `track-card` | `ds-metric-card` | Individual metric | Label + large value |
| `track-label` | `ds-metric-label` | Metric label | Smaller text above value |
| `track-value` | `ds-metric-value` | Metric value | Large bold number |

### Tab & List Content

| Legacy | New | Usage | Notes |
|--------|-----|-------|-------|
| `provider-detail-tabs` | `ds-tabs-container` | Tab section wrapper | Contains tab nav + content |
| `tab-row` | `ds-tabs-nav` | Tab navigation | Horizontal pill/chip tabs |
| `tab-chip` | `ds-tab-item` | Individual tab | Clickable tab |
| `tab-chip-active` | `ds-tab-item--active` | Active tab | Currently selected tab |
| `tab-content-list` | `ds-list-container` | List content | For document lists, placement lists |
| `list-row` | `ds-list-row` | List item row | Clickable row with title, meta, action |
| `compact-row` | `ds-list-row--compact` | Compact list row | Smaller padding/spacing |
| `empty-state` | `ds-empty-state` | No results | Message when list is empty |

### History & Status Cards

| Legacy | New | Usage | Notes |
|--------|-----|-------|-------|
| `history-grid` | `ds-info-grid` | 3-column info | Timeline/history info (created, updated, count) |
| `history-card` | `ds-info-card` | Individual info | Label + value pair |
| `history-label` | `ds-info-label` | Info label | Smaller text |

### Metadata & Info

| Legacy | New | Usage | Notes |
|--------|-----|-------|-------|
| `provider-meta-grid` | `ds-meta-grid` | 3-column metadata | Top section: specialization, region, type |
| `meta-label` | `ds-meta-label` | Meta label | Uppercase small label |
| `meta-value` | `ds-meta-value` | Meta value | Value text |
| `provider-title` | `ds-page-title` | Main heading | Page h1 |
| `page-title` | `ds-page-title` | Main heading | Page h1 |
| `row-title` | `ds-row-title` | Row heading | For list rows |
| `row-meta` | `ds-row-meta` | Row metadata | Secondary text in rows |

### Status & Sizing

| Legacy | New | Usage | Notes |
|--------|-----|-------|-------|
| `provider-main-col` | `xl:col-span-8` | Main column | 8/12 width |
| `provider-side-col` | `xl:col-span-4` | Sidebar column | 4/12 width |
| `summary-item` | `ds-summary-item` | Summary bar item | Flex item in strip |
| `summary-label` | `ds-summary-label` | Summary label | Label text |
| `summary-value` | `ds-summary-value` | Summary value | Value text |
| `summary-risk` | `ds-summary-item--risk` | Risk item | Highlighted summary item |
| `text-muted` | `text-gray-500` | Muted text | Low contrast text |
| `side-note` | `ds-note-text` | Side note | Smaller descriptive text |

## Implementation Strategy

### Phase 1: Provider Detail (DONE)
- ✅ Refactored `provider_detail.html`
- ✅ Created CSS migration layer (aliases)
- ✅ Verified layout and styling

### Phase 2: Other Detail Pages (IN PROGRESS)
Priority order:
1. `intake_detail.html` - High impact, client-facing
2. `client_detail.html` - Medium impact, used in workflows  
3. `placement_detail.html` - Critical for placement workflow
4. `case_detail.html` - Core workflow page
5. Other detail pages - Lower impact

### Phase 3: Analytics Pages
- `reports_dashboard.html` - Uses own analytics styling

### Phase 4: Cleanup
- Remove unused CSS classes
- Consolidate SCSS structure
- Performance validation

## Testing Checklist

- [ ] Detail page layouts render correctly
- [ ] Sidebar cards align properly
- [ ] Tab navigation works  
- [ ] List rows display consistently
- [ ] Summary strips remain aligned
- [ ] Mobile responsive behavior preserved
- [ ] No console errors
- [ ] CSS specificity reviewed
- [ ] Print styles verified
- [ ] Accessibility (ARIA labels, focus) maintained
