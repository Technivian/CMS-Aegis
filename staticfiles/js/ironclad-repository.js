
/**
 * Ironclad-mode repository functionality
 */
class IroncladRepository {
    constructor() {
        this.selectedContracts = new Set();
        this.filters = {
            q: '',
            status: [],
            contract_type: [],
            sort: 'updated_desc',
            page: 1,
            page_size: 25
        };
        this.savedViews = this.loadSavedViews();
        this.currentUser = { role: 'admin' }; // Mock user
        
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.renderFilterChips();
        this.renderSavedViews();
        this.setupKeyboardShortcuts();
        this.loadFromURL();
    }
    
    setupEventListeners() {
        // Search input with debounce
        let searchTimeout;
        document.getElementById('search-input')?.addEventListener('input', (e) => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                this.filters.q = e.target.value;
                this.loadContracts();
                this.updateURL();
            }, 300);
        });
        
        // Sort change
        document.getElementById('sort-select')?.addEventListener('change', (e) => {
            this.filters.sort = e.target.value;
            this.loadContracts();
            this.updateURL();
        });
        
        // Select all checkbox
        document.getElementById('select-all')?.addEventListener('change', (e) => {
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
        
        // Individual checkboxes
        document.addEventListener('change', (e) => {
            if (e.target.classList.contains('contract-checkbox')) {
                if (e.target.checked) {
                    this.selectedContracts.add(e.target.value);
                } else {
                    this.selectedContracts.delete(e.target.value);
                }
                this.updateBulkActionBar();
            }
        });
        
        // Row click for drawer
        document.addEventListener('click', (e) => {
            const row = e.target.closest('tr[data-clickable="true"]');
            if (row && !e.target.classList.contains('contract-checkbox')) {
                const contractId = row.dataset.contractId;
                this.openDrawer(contractId);
            }
        });
        
        // Drawer close
        document.getElementById('close-drawer')?.addEventListener('click', () => {
            this.closeDrawer();
        });
        
        // Bulk actions
        document.getElementById('bulk-status-btn')?.addEventListener('click', () => {
            this.showBulkStatusModal();
        });
        
        document.getElementById('bulk-assign-btn')?.addEventListener('click', () => {
            this.bulkAssignToMe();
        });
        
        document.getElementById('bulk-export-btn')?.addEventListener('click', () => {
            this.exportSelected();
        });
        
        document.getElementById('clear-selection-btn')?.addEventListener('click', () => {
            this.clearSelection();
        });
        
        // Save view
        document.getElementById('save-view-btn')?.addEventListener('click', () => {
            this.showSaveViewModal();
        });
    }
    
    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Only handle shortcuts when not typing in an input
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
                if (e.key === 'Escape') {
                    e.target.blur();
                    this.closeDrawer();
                }
                return;
            }
            
            switch (e.key) {
                case '/':
                    e.preventDefault();
                    document.getElementById('search-input')?.focus();
                    break;
                case 'n':
                    if (!e.ctrlKey && !e.metaKey) {
                        e.preventDefault();
                        this.showNewContractWizard();
                    }
                    break;
                case 'Escape':
                    this.closeDrawer();
                    break;
                case 'a':
                    if (e.shiftKey) {
                        e.preventDefault();
                        this.selectAllOnPage();
                    }
                    break;
            }
        });
    }
    
    async loadContracts() {
        try {
            const params = new URLSearchParams();
            Object.entries(this.filters).forEach(([key, value]) => {
                if (value !== null && value !== '' && (!Array.isArray(value) || value.length > 0)) {
                    if (Array.isArray(value)) {
                        value.forEach(v => params.append(key, v));
                    } else {
                        params.append(key, value);
                    }
                }
            });
            
            const response = await fetch(`/contracts/api/contracts/?${params}`);
            const data = await response.json();
            
            if (data.success) {
                this.renderContracts(data.data.rows);
                this.updatePagination(data.data);
            } else {
                this.showToast('Error loading contracts: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Network error loading contracts', 'error');
            console.error('Error loading contracts:', error);
        }
    }
    
    renderContracts(contracts) {
        const tbody = document.getElementById('contracts-tbody');
        if (!tbody) return;
        
        tbody.innerHTML = contracts.map(contract => `
            <tr class="hover:bg-gray-50" data-contract-id="${contract.id}" data-clickable="true">
                <td class="px-6 py-4 whitespace-nowrap">
                    <input type="checkbox" class="contract-checkbox rounded border-gray-300" value="${contract.id}">
                </td>
                <td class="px-6 py-4 whitespace-nowrap">
                    <div>
                        <div class="text-sm font-medium text-gray-900">${contract.title}</div>
                        <div class="text-sm text-gray-500">${contract.hint || ''}</div>
                    </div>
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">${contract.counterparty || '—'}</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">${contract.contract_type || '—'}</td>
                <td class="px-6 py-4 whitespace-nowrap">
                    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${this.getStatusClass(contract.status)}">
                        ${contract.status}
                    </span>
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                    ${contract.value ? `$${parseFloat(contract.value).toFixed(2)}` : '—'}
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    ${new Date(contract.updated_at).toLocaleDateString()}
                </td>
            </tr>
        `).join('');
        
        // Clear selection after re-render
        this.selectedContracts.clear();
        this.updateBulkActionBar();
    }
    
    getStatusClass(status) {
        const classes = {
            'DRAFT': 'bg-gray-100 text-gray-800',
            'ACTIVE': 'bg-green-100 text-green-800',
            'INACTIVE': 'bg-red-100 text-red-800',
            'UNVERIFIED': 'bg-yellow-100 text-yellow-800'
        };
        return classes[status] || 'bg-gray-100 text-gray-800';
    }
    
    updateBulkActionBar() {
        const bar = document.getElementById('bulk-action-bar');
        const count = this.selectedContracts.size;
        
        if (count > 0) {
            bar.classList.remove('hidden');
            document.getElementById('selection-count').textContent = `${count} selected`;
        } else {
            bar.classList.add('hidden');
        }
    }
    
    async openDrawer(contractId) {
        try {
            const response = await fetch(`/contracts/api/contracts/${contractId}/`);
            const data = await response.json();
            
            if (data.success) {
                this.renderDrawerContent(data.data);
                this.showDrawer();
                this.updateURL({ contractId });
            } else {
                this.showToast('Error loading contract details', 'error');
            }
        } catch (error) {
            this.showToast('Network error loading contract', 'error');
        }
    }
    
    renderDrawerContent(contract) {
        const content = document.getElementById('drawer-content');
        content.innerHTML = `
            <div class="space-y-4">
                <div>
                    <h4 class="text-lg font-semibold text-gray-900">${contract.title}</h4>
                    <p class="text-sm text-gray-600">${contract.counterparty || 'No counterparty'}</p>
                </div>
                
                <div>
                    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${this.getStatusClass(contract.status)}">
                        ${contract.status}
                    </span>
                </div>
                
                <div class="space-y-2">
                    <div class="text-sm">
                        <span class="font-medium text-gray-700">Type:</span>
                        <span class="text-gray-900">${contract.contract_type || '—'}</span>
                    </div>
                    <div class="text-sm">
                        <span class="font-medium text-gray-700">Value:</span>
                        <span class="text-gray-900">${contract.value ? `$${parseFloat(contract.value).toFixed(2)}` : '—'}</span>
                    </div>
                    <div class="text-sm">
                        <span class="font-medium text-gray-700">Updated:</span>
                        <span class="text-gray-900">${new Date(contract.updated_at).toLocaleDateString()}</span>
                    </div>
                </div>
                
                <div class="pt-4 border-t border-gray-200">
                    <div class="flex space-x-2">
                        <a href="/contracts/${contract.id}/" class="btn-primary text-sm">View Details</a>
                        <a href="/contracts/${contract.id}/edit/" class="bg-gray-200 text-gray-800 px-3 py-1 rounded text-sm hover:bg-gray-300">Edit</a>
                    </div>
                </div>
            </div>
        `;
    }
    
    showDrawer() {
        const drawer = document.getElementById('details-drawer');
        drawer.classList.remove('translate-x-full');
    }
    
    closeDrawer() {
        const drawer = document.getElementById('details-drawer');
        drawer.classList.add('translate-x-full');
        this.updateURL({ contractId: null });
    }
    
    async bulkAssignToMe() {
        if (this.selectedContracts.size === 0) return;
        
        try {
            const response = await fetch('/contracts/api/contracts/bulk-update/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCsrfToken()
                },
                body: JSON.stringify({
                    ids: Array.from(this.selectedContracts),
                    patch: { assigned_to: 'current_user' }
                })
            });
            
            const data = await response.json();
            if (data.success) {
                this.showToast(data.message, 'success');
                this.loadContracts();
                this.clearSelection();
            } else {
                this.showToast('Error updating contracts: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Network error updating contracts', 'error');
        }
    }
    
    clearSelection() {
        this.selectedContracts.clear();
        document.querySelectorAll('.contract-checkbox').forEach(cb => cb.checked = false);
        document.getElementById('select-all').checked = false;
        this.updateBulkActionBar();
    }
    
    selectAllOnPage() {
        const checkboxes = document.querySelectorAll('.contract-checkbox');
        const allChecked = Array.from(checkboxes).every(cb => cb.checked);
        
        checkboxes.forEach(cb => {
            cb.checked = !allChecked;
            if (!allChecked) {
                this.selectedContracts.add(cb.value);
            } else {
                this.selectedContracts.delete(cb.value);
            }
        });
        
        document.getElementById('select-all').checked = !allChecked;
        this.updateBulkActionBar();
    }
    
    showNewContractWizard() {
        // For now, redirect to the create page
        window.location.href = '/contracts/new/';
    }
    
    exportSelected() {
        if (this.selectedContracts.size === 0) return;
        
        // Mock CSV export
        const csvContent = 'ID,Title,Status,Counterparty\n' + 
            Array.from(this.selectedContracts).map(id => `${id},Contract ${id},ACTIVE,Mock Corp`).join('\n');
        
        const blob = new Blob([csvContent], { type: 'text/csv' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'contracts.csv';
        a.click();
        window.URL.revokeObjectURL(url);
        
        this.showToast(`Exported ${this.selectedContracts.size} contracts`, 'success');
    }
    
    renderFilterChips() {
        // Implementation for filter chips
        const container = document.getElementById('filter-chips');
        if (!container) return;
        
        container.innerHTML = `
            <button class="chip chip-inactive text-sm" onclick="ironclad.toggleStatusFilter()">Status</button>
            <button class="chip chip-inactive text-sm" onclick="ironclad.toggleTypeFilter()">Type</button>
            <button class="chip chip-inactive text-sm" onclick="ironclad.togglePeopleFilter()">People</button>
        `;
    }
    
    renderSavedViews() {
        const container = document.getElementById('saved-views');
        if (!container) return;
        
        const viewsHtml = this.savedViews.map(view => 
            `<button class="chip chip-inactive text-sm" onclick="ironclad.loadSavedView('${view.id}')">${view.name}</button>`
        ).join('');
        
        container.innerHTML = `
            <span class="text-sm text-gray-600">Saved Views:</span>
            ${viewsHtml}
        `;
    }
    
    loadSavedViews() {
        try {
            return JSON.parse(localStorage.getItem('ironclad_saved_views') || '[]');
        } catch {
            return [];
        }
    }
    
    saveSavedViews() {
        localStorage.setItem('ironclad_saved_views', JSON.stringify(this.savedViews));
    }
    
    loadFromURL() {
        const params = new URLSearchParams(window.location.search);
        const contractId = params.get('contractId');
        
        if (contractId) {
            this.openDrawer(contractId);
        }
    }
    
    updateURL(updates = {}) {
        const params = new URLSearchParams(window.location.search);
        
        Object.entries(updates).forEach(([key, value]) => {
            if (value === null || value === '') {
                params.delete(key);
            } else {
                params.set(key, value);
            }
        });
        
        const url = window.location.pathname + '?' + params.toString();
        window.history.replaceState({}, '', url);
    }
    
    updatePagination(data) {
        // Update pagination controls if they exist
        // This is a simplified version
    }
    
    getCsrfToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
    }
    
    showToast(message, type = 'info') {
        // Simple toast implementation
        const toast = document.createElement('div');
        toast.className = `fixed top-4 right-4 px-6 py-3 rounded-lg text-white z-50 ${
            type === 'error' ? 'bg-red-600' : 
            type === 'success' ? 'bg-green-600' : 'bg-blue-600'
        }`;
        toast.textContent = message;
        document.body.appendChild(toast);
        
        setTimeout(() => {
            toast.remove();
        }, 3000);
    }
}

// Initialize when DOM is loaded and ironclad mode is enabled
document.addEventListener('DOMContentLoaded', () => {
    if (window.ironcladMode) {
        window.ironclad = new IroncladRepository();
    }
});
/**
 * Ironclad-mode repository functionality
 * This file is created to match the static file reference
 */
// Content is the same as the previous file
