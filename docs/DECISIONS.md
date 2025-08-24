
# Design System Decisions

## Section 1: Visual & Design System

### Overview
Implementation of premium design system with clean, bold typography and minimal chrome, designed to exceed Ironclad and MochaDocs in visual quality and user experience.

### Design Tokens
- **Colors**: Custom palette with semantic naming
  - `bg`: #FFFFFF (background)
  - `ink`: #0B0B0C (primary text)
  - `muted`: #6B7280 (secondary text)
  - `stroke`: #E5E7EB (borders)
  - `accent`: #0E9F6E (primary actions)
  - `warn`: #F59E0B (warnings)
  - `danger`: #DC2626 (errors)
  - `card`: #FFFFFF (surface)

### Typography
- **Font Family**: Inter (premium, widely readable)
- **Scale**: 
  - Base: 14px/16px
  - H2: 24px/28px  
  - H1: 32px/36px
- **Weights**: 
  - Titles: 600 (bold, authoritative)
  - Labels: 500 (medium, readable)

### Spacing System
- 8px base scale for consistent rhythm
- Maximum content width: 1200px
- Responsive breakpoints following Tailwind standards

### Component Architecture
- **Approach**: shadcn/Radix-style components
- **Principles**: 
  - Composable and reusable
  - Accessibility-first (focus rings, ARIA attributes)
  - Consistent interaction patterns
  - Premium feel with subtle shadows and transitions

### Components Implemented
1. **Container**: Content width management
2. **PageHeader**: Standard page titles and descriptions
3. **Card**: Primary content container with header/body/footer
4. **Stat**: Dashboard metrics with trend indicators
5. **Button**: Four variants (primary, secondary, ghost, destructive)
6. **Badge**: Status indicators with semantic colors
7. **Input/Textarea/Select**: Form controls with focus states
8. **Table**: Data display with hover states
9. **Tabs**: Navigation within sections
10. **Modal/Drawer**: Overlay components
11. **Toast**: Notification system
12. **Progress**: Loading and completion indicators
13. **EmptyState**: Zero-data scenarios
14. **Skeleton**: Loading states
15. **Toolbar**: Action bars with left/right sections
16. **FilterChips**: Applied filters with removal
17. **Search**: Input with icon integration
18. **Stepper**: Multi-step process navigation

### Implementation Decisions

#### Feature Flag Strategy
- All new design system work is behind `FEATURE_REDESIGN=true`
- Existing functionality remains untouched
- Gradual rollout capability

#### CSS Architecture
- Tailwind CSS for utility-first development
- Custom component classes for complex patterns
- PostCSS build pipeline for optimization

#### Responsive Design
- Mobile-first approach
- Specific breakpoints for sidebar, toolbar, and table layouts
- Touch-friendly interaction areas

#### Accessibility
- WCAG 2.1 AA compliance
- Focus ring management
- Semantic HTML structure
- Screen reader friendly

#### Testing Strategy
- Unit tests for component rendering
- Integration tests for CSS compilation
- Accessibility tests for keyboard navigation
- Responsive design validation

### Performance Considerations
- CSS is compiled and minified
- Components use efficient selectors
- Minimal JavaScript for interactions
- Progressive enhancement approach

### Future Sections
This foundation enables:
- Section 2: Global Layout & Navigation
- Section 3: Dashboard redesign
- Section 4: Contracts table with advanced features
- Section 5: Contract creation workflow

### Maintenance
- Component documentation via demo page (/components-demo/)
- Test coverage for all major components
- Clear naming conventions for future developers
- Modular CSS architecture for easy updates
