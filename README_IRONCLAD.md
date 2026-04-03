
# Ironclad Mode Features

This document describes the Ironclad-like features that can be enabled in the contract management system.

## Feature Flag

The Ironclad mode is controlled by the `IRONCLAD_MODE` setting in Django:

```python
# In settings.py
IRONCLAD_MODE = True  # Enable Ironclad features
```

Or via environment variable:
```bash
export IRONCLAD_MODE=true
```

## Features

When `IRONCLAD_MODE=True`, the following features are enabled:

### 1. Filter Chips and Saved Views
- Multi-select filter chips for Status, Type, Counterparty, People, Date
- Save custom views with filters
- Persistent saved views in localStorage
- Quick access to common filter combinations

### 2. Bulk Selection and Operations
- Checkbox selection on each contract row
- "Select all on page" functionality  
- Bulk action bar appears when contracts are selected
- Available bulk operations:
  - Change status
  - Assign to current user
  - Export to CSV

### 3. Details Drawer
- Click any row to open details drawer from the right
- Non-blocking - can browse contracts while drawer is open
- Deep-linking via URL parameters (`?contractId=123`)
- Keyboard shortcuts (Esc to close)

### 4. Enhanced Search and Sort
- Debounced search with 300ms delay
- Sort by Updated (Recent/Oldest), Title, Status
- Page size controls (25/50/100 per page)

### 5. Keyboard Shortcuts
- `/` - Focus search input
- `n` - New contract wizard
- `Esc` - Close drawer
- `Shift+A` - Select all contracts on current page

### 6. Permissions (Stubbed)
- Role-based access control stub
- Different bulk actions available based on user role
- Currently supports: viewer, editor, admin roles

## Services Architecture

### Repository Service Interface
The system uses a service layer to abstract data operations:

```python
from contracts.services.repository import get_repository_service

# Get service instance
service = get_repository_service(user, use_mock=False)

# List contracts with filters
params = ListParams(q="search", status=[ContractStatus.ACTIVE])
result = service.list(params)

# Bulk operations
service.bulk_update(["1", "2"], {"status": "ACTIVE"})
```

### Implementations
- **DjangoRepositoryService**: Production implementation using Django ORM
- **MockRepositoryService**: Testing implementation with simulated data and latency

## API Endpoints

When Ironclad mode is enabled, additional API endpoints are available:

- `GET /contracts/api/contracts/` - List contracts with filtering
- `GET /contracts/api/contracts/{id}/` - Get contract details  
- `POST /contracts/api/contracts/bulk-update/` - Bulk update contracts

## Testing

Run the Ironclad feature tests:

```bash
python manage.py test tests.test_ironclad_features
```

The tests cover:
- API endpoint functionality
- Repository service implementations
- Filtering and search
- Bulk operations
- Template rendering with/without Ironclad mode

## Automated Contract Reminder Scheduling

Renewal and expiration reminders can run automatically via in-repo management commands:

```bash
# one-off execution
python manage.py send_contract_reminders

# scheduler loop (runs hourly by default)
python manage.py run_reminder_scheduler

# custom interval in minutes
python manage.py run_reminder_scheduler --interval-minutes 15

# run scheduler logic once and exit
python manage.py run_reminder_scheduler --once
```

Recommended production setup:
- Run `run_reminder_scheduler` as a dedicated background process.
- Keep the web server and scheduler as separate processes for reliability.

## Switching to Real API

To switch from the current Django backend to a real API:

1. Update `get_repository_service()` in `contracts/services/repository.py`
2. Implement `ApiRepositoryService` class with HTTP calls
3. Update the factory function to return the new service
4. All components will automatically use the new service

## Backward Compatibility

- With `IRONCLAD_MODE=False`: App behaves exactly as before
- All existing routes, exports, and functionality remain unchanged
- Bolton theme and styling are preserved
- No breaking changes to existing code

## Browser Compatibility

- Modern browsers supporting ES6+ features
- Uses native fetch API for HTTP requests
- CSS Grid and Flexbox for layouts
- No external JavaScript dependencies
