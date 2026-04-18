from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q, Sum
from django.http import HttpResponseForbidden
from django.urls import reverse, reverse_lazy
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from contracts.forms import ClientForm, DocumentForm, DocumentOCRReviewForm, MatterForm
from contracts.middleware import log_action
from contracts.models import Client, Document, DocumentOCRReview, Matter
from contracts.permissions import ContractAction, can_access_contract_action
from contracts.tenancy import get_user_organization, scope_queryset_for_organization, set_organization_on_instance
from contracts.view_support import TenantAssignCreateMixin, TenantScopedQuerysetMixin
from contracts.services.document_versions import compare_document_versions
from contracts.services.document_ocr import queue_document_ocr_review


class ClientListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = Client
    template_name = 'contracts/client_list.html'
    context_object_name = 'clients'
    paginate_by = 25

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        qs = scope_queryset_for_organization(Client.objects.all(), org)
        q = self.request.GET.get('q')
        status = self.request.GET.get('status')
        client_type = self.request.GET.get('type')
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(email__icontains=q) | Q(industry__icontains=q))
        if status:
            qs = qs.filter(status=status)
        if client_type:
            qs = qs.filter(client_type=client_type)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = get_user_organization(self.request.user)
        tenant_clients = scope_queryset_for_organization(Client.objects.all(), org)
        client_stats = tenant_clients.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(status='ACTIVE')),
        )
        ctx['total_clients'] = client_stats['total']
        ctx['active_clients'] = client_stats['active']
        ctx['search_query'] = self.request.GET.get('q', '')
        return ctx


class ClientDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = Client
    template_name = 'contracts/client_detail.html'
    context_object_name = 'client'

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        return scope_queryset_for_organization(Client.objects.all(), org)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['matters'] = self.object.matters.all()[:10]
        ctx['contracts'] = self.object.contracts.all()[:10]
        ctx['invoices'] = self.object.invoices.all()[:10]
        ctx['documents'] = self.object.documents.all()[:10]
        return ctx


class ClientCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = Client
    form_class = ClientForm
    template_name = 'contracts/client_form.html'
    success_url = reverse_lazy('contracts:client_list')

    def form_valid(self, form):
        set_organization_on_instance(form.instance, get_user_organization(self.request.user))
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_action(self.request.user, 'CREATE', 'Client', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, f'Client "{self.object.name}" created successfully.')
        return response


class ClientUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = Client
    form_class = ClientForm
    template_name = 'contracts/client_form.html'
    success_url = reverse_lazy('contracts:client_list')

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        return scope_queryset_for_organization(Client.objects.all(), org)

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(self.request.user, 'UPDATE', 'Client', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, f'Client "{self.object.name}" updated successfully.')
        return response


class MatterListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = Matter
    template_name = 'contracts/matter_list.html'
    context_object_name = 'matters'
    paginate_by = 25

    def get_queryset(self):
        org = self.get_organization()
        qs = scope_queryset_for_organization(Matter.objects.select_related('client', 'responsible_attorney'), org)
        q = self.request.GET.get('q')
        status = self.request.GET.get('status')
        practice_area = self.request.GET.get('practice_area')
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(matter_number__icontains=q) | Q(client__name__icontains=q))
        if status:
            qs = qs.filter(status=status)
        if practice_area:
            qs = qs.filter(practice_area=practice_area)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.get_organization()
        tenant_matters = scope_queryset_for_organization(Matter.objects.all(), org)
        matter_stats = tenant_matters.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(status='ACTIVE')),
        )
        ctx['total_matters'] = matter_stats['total']
        ctx['active_matters'] = matter_stats['active']
        ctx['search_query'] = self.request.GET.get('q', '')
        return ctx


class MatterDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = Matter
    template_name = 'contracts/matter_detail.html'
    context_object_name = 'matter'

    def get_queryset(self):
        org = self.get_organization()
        return scope_queryset_for_organization(Matter.objects.all(), org)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['contracts'] = self.object.contracts.all()
        ctx['documents'] = self.object.documents.all()[:10]
        ctx['time_entries'] = self.object.time_entries.all()[:10]
        ctx['tasks'] = self.object.tasks.all()[:10]
        ctx['deadlines'] = self.object.deadlines.filter(is_completed=False)[:10]
        ctx['risks'] = self.object.risks.all()[:10]
        return ctx


class MatterCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = Matter
    form_class = MatterForm
    template_name = 'contracts/matter_form.html'

    def get_success_url(self):
        return reverse('contracts:matter_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        set_organization_on_instance(form.instance, get_user_organization(self.request.user))
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_action(self.request.user, 'CREATE', 'Matter', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, f'Matter "{self.object.title}" created.')
        return response


class MatterUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = Matter
    form_class = MatterForm
    template_name = 'contracts/matter_form.html'

    def get_success_url(self):
        return reverse('contracts:matter_detail', kwargs={'pk': self.object.pk})

    def get_queryset(self):
        org = self.get_organization()
        return scope_queryset_for_organization(Matter.objects.all(), org)

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(self.request.user, 'UPDATE', 'Matter', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, f'Matter "{self.object.title}" updated.')
        return response


class DocumentListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = Document
    template_name = 'contracts/document_list.html'
    context_object_name = 'documents'
    paginate_by = 25

    def get_queryset(self):
        org = self.get_organization()
        qs = scope_queryset_for_organization(
            Document.objects.select_related('contract', 'matter', 'client', 'uploaded_by'),
            org,
        )
        q = self.request.GET.get('q')
        doc_type = self.request.GET.get('type')
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(tags__icontains=q))
        if doc_type:
            qs = qs.filter(document_type=doc_type)
        return qs.order_by('-created_at')


class DocumentDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = Document
    template_name = 'contracts/document_detail.html'
    context_object_name = 'document'

    def get_queryset(self):
        org = self.get_organization()
        return scope_queryset_for_organization(Document.objects.all(), org)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ancestor_chain = []
        current_document = self.object
        while current_document.parent_document_id:
            current_document = current_document.parent_document
            ancestor_chain.append(current_document)
        ctx['version_chain'] = list(reversed(ancestor_chain))
        ctx['versions'] = Document.objects.filter(parent_document=self.object).order_by('-version')
        return ctx


class DocumentCompareView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = Document
    template_name = 'contracts/document_compare.html'
    context_object_name = 'document'

    def get_queryset(self):
        org = self.get_organization()
        return scope_queryset_for_organization(Document.objects.all(), org)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        other_document = get_object_or_404(
            scope_queryset_for_organization(Document.objects.all(), self.get_organization()),
            pk=self.kwargs['other_pk'],
        )
        context['other_document'] = other_document
        context['comparison'] = compare_document_versions(self.object, other_document)
        return context


class DocumentCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = Document
    form_class = DocumentForm
    template_name = 'contracts/document_form.html'
    success_url = reverse_lazy('contracts:document_list')

    def form_valid(self, form):
        set_organization_on_instance(form.instance, get_user_organization(self.request.user))
        if form.instance.contract and not can_access_contract_action(self.request.user, form.instance.contract, ContractAction.EDIT):
            return HttpResponseForbidden('You do not have permission to upload documents for this contract.')
        form.instance.uploaded_by = self.request.user
        response = super().form_valid(form)
        queue_document_ocr_review(self.object)
        log_action(
            self.request.user,
            'CREATE',
            'Document',
            self.object.id,
            str(self.object),
            changes={
                'event': 'document_uploaded',
                'version': self.object.version,
                'file_hash': self.object.file_hash,
            },
            request=self.request,
        )
        messages.success(self.request, f'Document "{self.object.title}" uploaded.')
        return response


class DocumentUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = Document
    form_class = DocumentForm
    template_name = 'contracts/document_form.html'
    success_url = reverse_lazy('contracts:document_list')

    def get_queryset(self):
        org = self.get_organization()
        return scope_queryset_for_organization(Document.objects.all(), org)

    def dispatch(self, request, *args, **kwargs):
        document = self.get_object()
        self.original_document = document
        if document.contract and not can_access_contract_action(request.user, document.contract, ContractAction.EDIT):
            return HttpResponseForbidden('You do not have permission to edit documents for this contract.')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        original_document = getattr(self, 'original_document', None) or self.get_object()
        staged_document = form.save(commit=False)
        self.object = Document(
            organization=original_document.organization,
            title=staged_document.title,
            document_type=staged_document.document_type,
            status=staged_document.status,
            description=staged_document.description,
            file=staged_document.file,
            contract=staged_document.contract,
            matter=staged_document.matter,
            client=staged_document.client,
            uploaded_by=self.request.user,
            tags=staged_document.tags,
            is_privileged=staged_document.is_privileged,
            is_confidential=staged_document.is_confidential,
            version=(original_document.version or 1) + 1,
            parent_document=original_document,
        )
        self.object.save()
        queue_document_ocr_review(self.object)
        log_action(
            self.request.user,
            'CREATE',
            'Document',
            self.object.id,
            str(self.object),
            changes={
                'event': 'document_version_created',
                'parent_document_id': original_document.id,
                'version': self.object.version,
                'file_hash': self.object.file_hash,
            },
            request=self.request,
        )
        messages.success(self.request, f'Document "{self.object.title}" updated as version {self.object.version}.')
        return redirect('contracts:document_detail', pk=self.object.pk)


class DocumentOCRQueueView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = DocumentOCRReview
    template_name = 'contracts/document_ocr_queue.html'
    context_object_name = 'reviews'
    paginate_by = 25

    def get_queryset(self):
        org = self.get_organization()
        qs = scope_queryset_for_organization(
            DocumentOCRReview.objects.select_related('document', 'reviewed_by'),
            org,
        )
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs.order_by('-created_at')


class DocumentOCRReviewUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = DocumentOCRReview
    form_class = DocumentOCRReviewForm
    template_name = 'contracts/document_ocr_review.html'

    def get_queryset(self):
        org = self.get_organization()
        return scope_queryset_for_organization(
            DocumentOCRReview.objects.select_related('document', 'reviewed_by'),
            org,
        )

    def form_valid(self, form):
        review = form.save(commit=False)
        review.organization = self.get_organization()
        review.reviewed_by = self.request.user
        review.reviewed_at = timezone.now()
        if review.status == DocumentOCRReview.Status.VERIFIED:
            review.mark_verified(self.request.user)
        elif review.status == DocumentOCRReview.Status.REJECTED:
            review.mark_rejected(self.request.user)
        review.save()
        messages.success(self.request, f'OCR review for "{review.document.title}" updated.')
        return redirect('contracts:document_ocr_queue')
