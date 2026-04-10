
"""
API views for Careon repository functionality.
"""
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q

from contracts.domain.contracts import CareCaseData, ListParams, ListResult
from contracts.models import CareCase
from contracts.tenancy import get_user_organization, scope_queryset_for_organization


def _build_case_data(case):
    return CareCaseData(
        id=str(case.id),
        title=case.title,
        status=case.status,
        preferred_provider=getattr(case, 'preferred_provider', ''),
        value=float(case.value) if hasattr(case, 'value') and case.value else None,
        start_date=case.start_date.isoformat() if hasattr(case, 'start_date') and case.start_date else None,
        end_date=case.end_date.isoformat() if hasattr(case, 'end_date') and case.end_date else None,
        owner=case.created_by.get_full_name() if case.created_by else 'System',
        updated_at=case.updated_at.isoformat() if hasattr(case, 'updated_at') and case.updated_at else None,
        created_at=case.created_at.isoformat() if case.created_at else None,
        content=case.content or "",
    )

@login_required
@require_http_methods(["GET"])
def contracts_api(request):
    """
    API endpoint for listing cases with filtering and pagination.
    Used by the Careon repository UI.
    """
    try:
        # Parse filters from request
        params = ListParams(
            q=request.GET.get('q', ''),
            status=[s for s in request.GET.getlist('status') if s],
            contract_type=[t for t in request.GET.getlist('contract_type') if t],
            sort=request.GET.get('sort', 'updated_desc'),
            page=int(request.GET.get('page', 1)),
            page_size=int(request.GET.get('page_size', 25))
        )

        organization = get_user_organization(request.user)
        queryset = scope_queryset_for_organization(CareCase.objects.all(), organization)

        if params.q:
            queryset = queryset.filter(
                Q(title__icontains=params.q)
                | Q(preferred_provider__icontains=params.q)
                | Q(content__icontains=params.q)
            )

        if params.status:
            queryset = queryset.filter(status__in=params.status)

        if params.sort == 'updated_asc':
            queryset = queryset.order_by('updated_at')
        elif params.sort == 'title':
            queryset = queryset.order_by('title')
        elif params.sort == 'status':
            queryset = queryset.order_by('status')
        else:
            queryset = queryset.order_by('-updated_at')

        paginator = Paginator(queryset, params.page_size)
        page_obj = paginator.get_page(params.page)

        result = ListResult(
            contracts=[_build_case_data(case) for case in page_obj],
            total_count=paginator.count,
            page=params.page,
            page_size=params.page_size,
            total_pages=paginator.num_pages,
        )
        
        return JsonResponse(result.to_dict())
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_http_methods(["GET"])
def case_detail_api(request, contract_id=None, case_id=None):
    """Get single case details."""
    try:
        record_id = case_id or contract_id
        organization = get_user_organization(request.user)
        queryset = scope_queryset_for_organization(CareCase.objects.all(), organization)

        try:
            case = queryset.get(id=record_id)
        except CareCase.DoesNotExist:
            case = None
        
        if not case:
            return JsonResponse({'error': 'Casus niet gevonden'}, status=404)
            
        return JsonResponse(_build_case_data(case).to_dict())
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@login_required
@require_http_methods(["POST"])
def cases_bulk_update_api(request):
    """Bulk update cases."""
    try:
        data = json.loads(request.body)
        case_ids = data.get('case_ids', data.get('contract_ids', []))
        updates = data.get('updates', {})

        organization = get_user_organization(request.user)
        queryset = scope_queryset_for_organization(
            CareCase.objects.filter(id__in=case_ids),
            organization,
        )
        result = queryset.update(**updates)
        
        return JsonResponse({'success': True, 'updated_count': result})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


contract_detail_api = case_detail_api
contracts_bulk_update_api = cases_bulk_update_api
