# Design System Decisions

## Section #1: Brand System (Bolton Style)

### Typography Choice
- **Decision**: Use Inter font family as the primary typeface
- **Rationale**: Inter is highly legible, modern, and works well in digital interfaces. It's also web-safe and performs well across different screen sizes.

### Color Palette
- **Decision**: Implement the exact colors specified in the blueprint
- **Rationale**: These colors provide good contrast ratios and align with professional SaaS applications. The accent color (#0E9F6E) provides a distinct brand identity.

### Component Architecture
- **Decision**: Use CSS classes with Tailwind utilities rather than CSS-in-JS
- **Rationale**: Maintains consistency with the existing Django/Tailwind setup and allows for easier theming and maintenance.

### Spacing Scale
- **Decision**: Use 8px base spacing scale (0.5, 1, 1.5, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24)
- **Rationale**: 8px scale is a common design system practice that ensures consistent spacing and makes components align properly.

### Feature Flag Implementation
- **Decision**: Use environment variables with Django settings fallback
- **Rationale**: Allows for easy toggling in different environments without code changes.

### Demo Page Structure
- **Decision**: Create a comprehensive demo page showing all components
- **Rationale**: Makes it easy to visually verify components work correctly and provides documentation for developers.

## Design System Implementation

- **Color Tokens**: Used CSS custom properties for consistent theming across components
- **Component Architecture**: Built reusable components with Tailwind utility classes
- **Testing Strategy**: Created both unit tests for components and visual regression tests
- **Documentation**: Added components demo page for design system showcase

## Global Layout & Navigation

- **Sidebar Approach**: Implemented collapsible sidebar (280px expanded, 64px collapsed) for better space utilization
- **Top Navigation**: Sticky header with logo, global search, and user actions for consistent access
- **Feature Flag Integration**: Used base_redesign.html template with conditional rendering based on FEATURE_REDESIGN flag
- **Keyboard Shortcuts**: Implemented standard shortcuts (/ for search, N for new contract, G+key for navigation)
- **Search Design**: Centered global search with placeholder text and visual search icon
- **Content Layout**: Max-width 1200px container with responsive margins for optimal reading width
- **Sidebar Sections**: Organized into "My Views", "Quick Actions", and "Filters" for logical grouping