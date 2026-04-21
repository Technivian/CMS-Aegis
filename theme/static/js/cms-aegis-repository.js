
/**
 * CMS Aegis-mode repository functionality
 * Provides advanced filtering, bulk selection, and details drawer
 */
class CMSAegisRepository {
    constructor() {
        this.selectedContracts = new Set();
        this.viewStorageKey = 'cms-aegis-saved-views';
        this.contractCache = new Map();
        this.filters = {
            q: '',
            status: [],
            contract_type: [],
            sort: 'updated_desc',
            page: 1,
            page_size: 25
        };
        this.savedViews = this.loadSavedViews();
        this.activeSavedViewName = '';
        this.currentUser = { role: 'admin' };
        
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.renderSavedViews();
        this.setupKeyboardShortcuts();
        this.loadFromURL();
        this.syncControlsToFilters();
        this.renderFilterChips();
        this.updateQuickFilterState();
        this.loadContracts();
    }
    
    setupEventListeners() {
        // Search input with debounce
        let searchTimeout;
        const searchInput = document.getElementById('search-input');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                clearTimeout(searchTimeout);
                searchTimeout = setTimeout(() => {
                    this.filters.q = e.target.value;
                    this.filters.page = 1;
                    this.renderFilterChips();
                    this.loadContracts();
                    this.updateURL();
                }, 300);
            });
        }
        
        // Sort change
        const sortSelect = document.getElementById('sort-select');
        if (sortSelect) {
            sortSelect.addEventListener('change', (e) => {
                this.filters.sort = e.target.value;
                this.filters.page = 1;
                this.renderFilterChips();
                this.updateQuickFilterState();
                this.loadContracts();
                this.updateURL();
            });
        }

        document.querySelectorAll('[data-status-filter]').forEach((button) => {
            button.addEventListener('click', () => this.applyStatusFilter(button.dataset.statusFilter || ''));
        });
        
        // Select all checkbox
        const selectAllCheckbox = document.getElementById('select-all');
        if (selectAllCheckbox) {
            selectAllCheckbox.addEventListener('change', (e) => {
                const checkboxes = document.querySelectorAll('.contract-checkbox');
                checkboxes.forEach(cb => {
                    cb.checked = e.target.checked;
                    if (e.target.checked) {
                        this.selectedContracts.add(cb.value);
                    } else {
                        this.selectedContracts.delete(cb.value);
                    }
                });
                this.updateBulkActionBar();
            });
        }

        const bulkStatusButton = document.getElementById('repo-bulk-status');
        if (bulkStatusButton) {
            bulkStatusButton.addEventListener('click', () => this.bulkChangeStatus());
        }

        const bulkAssignButton = document.getElementById('repo-bulk-assign');
        if (bulkAssignButton) {
            bulkAssignButton.addEventListener('click', () => {
                window.alert('Bulk assignment will follow the status update path.');
            });
        }

        const bulkExportButton = document.getElementById('repo-bulk-export');
        if (bulkExportButton) {
            bulkExportButton.addEventListener('click', () => this.exportSelectedContracts());
        }
    }
    
    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            if (e.key === '/' && !e.ctrlKey && !e.metaKey) {
                e.preventDefault();
                const searchInput = document.getElementById('search-input');
                if (searchInput) searchInput.focus();
            }
            
            if (e.key === 'Escape') {
                this.closeDetailsDrawer();
            }
            
            if (e.key === 'n' && !e.ctrlKey && !e.metaKey) {
                e.preventDefault();
                window.location.href = '/contracts/create/';
            }
        });
    }
    
    loadFromURL() {
        const params = new URLSearchParams(window.location.search);
        
        // Load filters from URL
        if (params.get('q')) this.filters.q = params.get('q');
        if (params.getAll('status').length) this.filters.status = params.getAll('status');
        if (params.get('sort')) this.filters.sort = params.get('sort');
        if (params.get('page')) this.filters.page = parseInt(params.get('page'));
        
        // Load contract detail if specified
        const contractId = params.get('contractId');
        if (contractId) {
            this.openDetailsDrawer(contractId);
        }
    }

    syncControlsToFilters() {
        const searchInput = document.getElementById('search-input');
        if (searchInput) {
            searchInput.value = this.filters.q || '';
        }

        const sortSelect = document.getElementById('sort-select');
        if (sortSelect) {
            sortSelect.value = this.filters.sort;
        }
    }

    applyStatusFilter(status) {
        this.filters.status = status ? [status] : [];
        this.filters.page = 1;
        this.renderFilterChips();
        this.updateQuickFilterState();
        this.updateURL();
        this.loadContracts();
    }

    updateQuickFilterState() {
        const activeStatus = this.filters.status.length === 1 ? this.filters.status[0] : '';
        document.querySelectorAll('[data-status-filter]').forEach((button) => {
            const isActive = (button.dataset.statusFilter || '') === activeStatus;
            button.classList.toggle('chip-active', isActive);
        });
    }
    
    updateURL() {
        const params = new URLSearchParams();
        
        if (this.filters.q) params.set('q', this.filters.q);
        this.filters.status.forEach(s => params.append('status', s));
        if (this.filters.sort !== 'updated_desc') params.set('sort', this.filters.sort);
        if (this.filters.page !== 1) params.set('page', this.filters.page.toString());
        
        const newURL = window.location.pathname + '?' + params.toString();
        window.history.replaceState({}, '', newURL);
    }
    
    async loadContracts() {
        this.showLoading();
        
        try {
            const params = new URLSearchParams();
            if (this.filters.q) params.set('q', this.filters.q);
            this.filters.status.forEach(s => params.append('status', s));
            this.filters.contract_type.forEach(t => params.append('contract_type', t));
            params.set('sort', this.filters.sort);
            params.set('page', this.filters.page.toString());
            params.set('page_size', this.filters.page_size.toString());
            
            const response = await fetch(`/contracts/api/contracts/?${params.toString()}`);
            const result = await response.json();
            
            if (response.ok) {
                (result.contracts || []).forEach((contract) => {
                    this.contractCache.set(String(contract.id), contract);
                });
                this.renderContracts(result);
                this.updatePagination(result);
            } else {
                this.showError(result.error || 'Failed to load contracts');
            }
        } catch (error) {
            this.showError('Network error: ' + error.message);
        } finally {
            this.hideLoading();
        }
    }
    
    renderContracts(result) {
        const tbody = document.getElementById('contracts-tbody');
        if (!tbody) return;
        
        if (result.contracts.length === 0) {
            tbody.innerHTML = `
                <tr><td colspan="6" class="text-center py-8 text-muted">
                    No contracts found. <a href="/contracts/create/" class="link">Create your first contract</a>
                </td></tr>
            `;
            return;
        }
        
        tbody.innerHTML = result.contracts.map(contract => `
            <tr class="contract-row hover:bg-hover cursor-pointer" data-contract-id="${contract.id}">
                <td class="px-3 py-2">
                    <input type="checkbox" class="contract-checkbox" value="${contract.id}">
                </td>
                <td class="px-3 py-2">
                    <div class="font-medium">${contract.title}</div>
                    <div class="text-sm text-muted">${contract.counterparty || 'No counterparty'}</div>
                </td>
                <td class="px-3 py-2">
                    <span class="status-badge status-${contract.status.toLowerCase()}">
                        ${contract.status}
                    </span>
                </td>
                <td class="px-3 py-2 text-muted">
                    ${contract.value ? '$' + contract.value.toLocaleString() : '-'}
                </td>
                <td class="px-3 py-2 text-muted">
                    ${contract.owner}
                </td>
                <td class="px-3 py-2 text-muted">
                    ${contract.updated_at ? new Date(contract.updated_at).toLocaleDateString() : '-'}
                </td>
            </tr>
        `).join('');
        
        // Add click handlers
        tbody.querySelectorAll('.contract-row').forEach(row => {
            row.addEventListener('click', (e) => {
                if (!e.target.matches('input[type="checkbox"]')) {
                    const contractId = row.dataset.contractId;
                    this.openDetailsDrawer(contractId);
                }
            });
        });
        
        // Add checkbox handlers
        tbody.querySelectorAll('.contract-checkbox').forEach(cb => {
            cb.addEventListener('change', (e) => {
                if (e.target.checked) {
                    this.selectedContracts.add(e.target.value);
                } else {
                    this.selectedContracts.delete(e.target.value);
                }
                this.updateBulkActionBar();
            });
        });
    }
    
    updateBulkActionBar() {
        const count = this.selectedContracts.size;
        const bulkBar = document.getElementById('bulk-action-bar');
        
        if (count > 0) {
            if (bulkBar) {
                bulkBar.style.display = 'flex';
                bulkBar.querySelector('#selected-count').textContent = `${count} selected`;
            }
        } else {
            if (bulkBar) bulkBar.style.display = 'none';
        }
    }

    clearSelection() {
        this.selectedContracts.clear();

        const selectAllCheckbox = document.getElementById('select-all');
        if (selectAllCheckbox) {
            selectAllCheckbox.checked = false;
        }

        document.querySelectorAll('.contract-checkbox').forEach(cb => {
            cb.checked = false;
        });

        this.updateBulkActionBar();
    }

    updatePagination(result) {
        const container = document.getElementById('pagination-container');
        if (!container) return;

        const currentPage = Number(result?.page || 1);
        const totalPages = Number(result?.total_pages || 1);
        const totalCount = Number(result?.total_count || 0);

        if (totalPages <= 1) {
            container.innerHTML = `
                <div class="text-sm" style="color:var(--text-muted)">
                    ${totalCount} result${totalCount === 1 ? '' : 's'}
                </div>
            `;
            return;
        }

        const prevDisabled = currentPage <= 1;
        const nextDisabled = currentPage >= totalPages;

        container.innerHTML = `
            <div class="flex items-center justify-between gap-3 flex-wrap">
                <div class="text-sm" style="color:var(--text-muted)">
                    ${totalCount} result${totalCount === 1 ? '' : 's'} · Page ${currentPage} of ${totalPages}
                </div>
                <div class="flex items-center gap-2">
                    <button id="repo-page-prev" class="repo-mini-btn" ${prevDisabled ? 'disabled' : ''}>Previous</button>
                    <button id="repo-page-next" class="repo-mini-btn" ${nextDisabled ? 'disabled' : ''}>Next</button>
                </div>
            </div>
        `;

        const prevBtn = document.getElementById('repo-page-prev');
        const nextBtn = document.getElementById('repo-page-next');

        if (prevBtn) {
            prevBtn.addEventListener('click', () => {
                if (this.filters.page <= 1) return;
                this.filters.page -= 1;
                this.updateURL();
                this.loadContracts();
            });
        }

        if (nextBtn) {
            nextBtn.addEventListener('click', () => {
                if (this.filters.page >= totalPages) return;
                this.filters.page += 1;
                this.updateURL();
                this.loadContracts();
            });
        }
    }
    
    async openDetailsDrawer(contractId) {
        const drawer = document.getElementById('details-drawer');
        if (!drawer) return;
        
        // Update URL
        const params = new URLSearchParams(window.location.search);
        params.set('contractId', contractId);
        window.history.replaceState({}, '', '?' + params.toString());
        
        // Show loading state
        drawer.innerHTML = '<div class="p-6">Loading...</div>';
        drawer.classList.add('active');
        
        try {
            const response = await fetch(`/contracts/api/contracts/${contractId}/`);
            const contract = await response.json();
            
            if (response.ok) {
                this.renderContractDetails(contract, drawer);
            } else {
                drawer.innerHTML = '<div class="p-6 text-danger">Failed to load contract details</div>';
            }
        } catch (error) {
            drawer.innerHTML = '<div class="p-6 text-danger">Network error</div>';
        }
    }
    
    renderContractDetails(contract, drawer) {
        drawer.innerHTML = `
            <div class="p-6">
                <div class="flex items-center justify-between mb-4">
                    <h2 class="text-xl font-semibold">${contract.title}</h2>
                    <button onclick="window.cmsAegisRepository.closeDetailsDrawer()" class="btn-ghost">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                        </svg>
                    </button>
                </div>
                
                <div class="space-y-4">
                    <div>
                        <label class="text-sm text-muted">Status</label>
                        <div><span class="status-badge status-${contract.status.toLowerCase()}">${contract.status}</span></div>
                    </div>
                    
                    <div>
                        <label class="text-sm text-muted">Counterparty</label>
                        <div>${contract.counterparty || '-'}</div>
                    </div>
                    
                    <div>
                        <label class="text-sm text-muted">Value</label>
                        <div>${contract.value ? '$' + contract.value.toLocaleString() : '-'}</div>
                    </div>
                    
                    <div>
                        <label class="text-sm text-muted">Owner</label>
                        <div>${contract.owner}</div>
                    </div>
                    
                    <div>
                        <label class="text-sm text-muted">Content</label>
                        <div class="mt-1 p-3 bg-hover rounded text-sm">${contract.content || 'No content'}</div>
                    </div>
                </div>
                
                <div class="mt-6 pt-4 border-t flex space-x-2">
                    <a href="/contracts/${contract.id}/" class="btn-primary">Edit Contract</a>
                    <button onclick="window.cmsAegisRepository.duplicateContract('${contract.id}')" class="btn-outline">Duplicate</button>
                </div>
            </div>
        `;
    }
    
    closeDetailsDrawer() {
        const drawer = document.getElementById('details-drawer');
        if (drawer) drawer.classList.remove('active');
        
        // Remove contractId from URL
        const params = new URLSearchParams(window.location.search);
        params.delete('contractId');
        window.history.replaceState({}, '', '?' + params.toString());
    }
    
    renderFilterChips() {
        const container = document.getElementById('filter-chips');
        if (!container) return;

        const chips = [];
        if (this.filters.q) {
            chips.push({
                label: `Search: ${this.filters.q}`,
                onClick: () => {
                    this.filters.q = '';
                    this.filters.page = 1;
                    this.syncControlsToFilters();
                    this.renderFilterChips();
                    this.updateQuickFilterState();
                    this.updateURL();
                    this.loadContracts();
                }
            });
        }

        this.filters.status.forEach((status) => {
            chips.push({
                label: `Status: ${status}`,
                onClick: () => {
                    this.filters.status = this.filters.status.filter((value) => value !== status);
                    this.filters.page = 1;
                    this.renderFilterChips();
                    this.updateQuickFilterState();
                    this.updateURL();
                    this.loadContracts();
                }
            });
        });

        if (this.filters.sort && this.filters.sort !== 'updated_desc') {
            chips.push({
                label: `Sort: ${this.filters.sort}`,
                onClick: () => {
                    this.filters.sort = 'updated_desc';
                    this.filters.page = 1;
                    this.syncControlsToFilters();
                    this.renderFilterChips();
                    this.updateQuickFilterState();
                    this.updateURL();
                    this.loadContracts();
                }
            });
        }

        this.filters.contract_type.forEach((contractType) => {
            chips.push({
                label: `Type: ${contractType}`,
                onClick: () => {
                    this.filters.contract_type = this.filters.contract_type.filter((value) => value !== contractType);
                    this.filters.page = 1;
                    this.renderFilterChips();
                    this.updateURL();
                    this.loadContracts();
                }
            });
        });

        if (chips.length === 0) {
            container.innerHTML = '';
            return;
        }

        container.innerHTML = `
            <div class="flex items-center gap-2 flex-wrap">
                ${chips.map((chip) => `
                    <button type="button" class="repo-filter-chip" data-chip-label="${chip.label}">
                        ${chip.label}
                        <span aria-hidden="true">×</span>
                    </button>
                `).join('')}
            </div>
        `;

        container.querySelectorAll('[data-chip-label]').forEach((button) => {
            const chip = chips.find((entry) => entry.label === button.dataset.chipLabel);
            if (chip) {
                button.addEventListener('click', chip.onClick);
            }
        });
    }
    
    renderSavedViews() {
        const container = document.getElementById('saved-views');
        if (!container) return;

        if (!this.savedViews.length) {
            container.innerHTML = `
                <div class="text-sm" style="color:var(--text-muted)">
                    No saved views yet.
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <div class="flex items-center gap-2 flex-wrap">
                ${this.savedViews.map((view, index) => `
                    <span class="repo-saved-view-wrap">
                        <button type="button" class="repo-saved-view ${this.activeSavedViewName === view.name ? 'chip-active' : ''}" data-saved-view-index="${index}">
                            ${view.name}
                        </button>
                        <button type="button" class="repo-saved-view-delete" data-saved-view-delete-index="${index}" aria-label="Delete saved view ${view.name}">
                            ×
                        </button>
                    </span>
                `).join('')}
            </div>
        `;

        container.querySelectorAll('[data-saved-view-index]').forEach((button) => {
            const index = Number(button.dataset.savedViewIndex);
            button.addEventListener('click', () => this.applySavedView(index));
        });

        container.querySelectorAll('[data-saved-view-delete-index]').forEach((button) => {
            const index = Number(button.dataset.savedViewDeleteIndex);
            button.addEventListener('click', (event) => {
                event.stopPropagation();
                this.deleteSavedView(index);
            });
        });
    }
    
    loadSavedViews() {
        try {
            const parsed = JSON.parse(localStorage.getItem(this.viewStorageKey) || '[]');
            return Array.isArray(parsed) ? parsed : [];
        } catch {
            return [];
        }
    }

    persistSavedViews() {
        localStorage.setItem(this.viewStorageKey, JSON.stringify(this.savedViews));
        this.renderSavedViews();
    }

    saveCurrentView() {
        const name = window.prompt('Name this saved view', this.filters.q ? `Search: ${this.filters.q}` : 'Saved view');
        if (!name) return;

        const trimmedName = name.trim();
        if (!trimmedName) return;

        this.savedViews = [
            {
                name: trimmedName,
                filters: JSON.parse(JSON.stringify(this.filters)),
                created_at: new Date().toISOString(),
            },
            ...this.savedViews.filter((view) => view.name !== trimmedName),
        ];
        this.persistSavedViews();
    }

    applySavedView(index) {
        const savedView = this.savedViews[index];
        if (!savedView) return;

        this.filters = {
            q: savedView.filters.q || '',
            status: Array.isArray(savedView.filters.status) ? [...savedView.filters.status] : [],
            contract_type: Array.isArray(savedView.filters.contract_type) ? [...savedView.filters.contract_type] : [],
            sort: savedView.filters.sort || 'updated_desc',
            page: 1,
            page_size: savedView.filters.page_size || 25,
        };

        this.syncControlsToFilters();
        this.renderFilterChips();
        this.updateURL();
        this.loadContracts();
        this.activeSavedViewName = savedView.name;
        this.renderSavedViews();
    }

    deleteSavedView(index) {
        this.savedViews = this.savedViews.filter((_, savedViewIndex) => savedViewIndex !== index);
        this.persistSavedViews();
    }
    
    showLoading() {
        const table = document.getElementById('contracts-table');
        if (table) table.classList.add('loading');
    }
    
    hideLoading() {
        const table = document.getElementById('contracts-table');
        if (table) table.classList.remove('loading');
    }
    
    showError(message) {
        console.error('Repository error:', message);
        // Could show toast notification here
    }
    
    async duplicateContract(contractId) {
        // Placeholder for contract duplication
        alert('Contract duplication feature coming soon');
    }

    async bulkChangeStatus() {
        if (!this.selectedContracts.size) {
            window.alert('Select one or more contracts first.');
            return;
        }

        const nextStatus = window.prompt(
            'Enter the new status (DRAFT, PENDING, IN_REVIEW, APPROVED, ACTIVE, EXPIRED, TERMINATED, COMPLETED, CANCELLED)',
            'ACTIVE'
        );
        if (!nextStatus) return;

        const normalizedStatus = nextStatus.trim().toUpperCase();
        const allowedStatuses = new Set(['DRAFT', 'PENDING', 'IN_REVIEW', 'APPROVED', 'ACTIVE', 'EXPIRED', 'TERMINATED', 'COMPLETED', 'CANCELLED']);
        if (!allowedStatuses.has(normalizedStatus)) {
            window.alert('That is not a valid contract status.');
            return;
        }

        const response = await fetch('/contracts/api/contracts/bulk-update/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCsrfToken(),
            },
            body: JSON.stringify({
                contract_ids: Array.from(this.selectedContracts),
                updates: { status: normalizedStatus },
            }),
        });

        const payload = await response.json();
        if (!response.ok) {
            window.alert(payload.error || 'Bulk status update failed.');
            return;
        }

        this.loadContracts();
    }

    exportSelectedContracts() {
        if (!this.selectedContracts.size) {
            window.alert('Select one or more contracts first.');
            return;
        }

        const rows = Array.from(this.selectedContracts)
            .map((contractId) => this.contractCache.get(String(contractId)))
            .filter(Boolean);

        if (!rows.length) {
            window.alert('Selected contracts are not loaded in the current view.');
            return;
        }

        const header = ['id', 'title', 'status', 'counterparty', 'value', 'owner', 'updated_at'];
        const csvLines = [
            header.join(','),
            ...rows.map((contract) => [
                contract.id,
                this.csvEscape(contract.title),
                this.csvEscape(contract.status),
                this.csvEscape(contract.counterparty || ''),
                contract.value ?? '',
                this.csvEscape(contract.owner || ''),
                this.csvEscape(contract.updated_at || ''),
            ].join(',')),
        ];

        const blob = new Blob([csvLines.join('\n')], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = 'repository-contracts.csv';
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
    }

    csvEscape(value) {
        const text = String(value ?? '');
        if (text.includes(',') || text.includes('"') || text.includes('\n')) {
            return `"${text.replaceAll('"', '""')}"`;
        }
        return text;
    }

    getCsrfToken() {
        const cookieName = 'csrftoken';
        return document.cookie
            .split('; ')
            .find((row) => row.startsWith(`${cookieName}=`))
            ?.split('=')[1] || '';
    }
}

// Initialize when DOM is loaded and CMS Aegis mode is enabled
document.addEventListener('DOMContentLoaded', () => {
    if (window.location.pathname.includes('/repository')) {
        window.cmsAegisRepository = new CMSAegisRepository();
    }
});
