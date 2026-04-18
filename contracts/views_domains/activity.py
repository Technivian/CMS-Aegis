from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from contracts.middleware import log_action
from contracts.models import AuditLog, Notification
from contracts.view_support import TenantScopedQuerysetMixin


class AuditLogListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = AuditLog
    template_name = 'contracts/audit_log_list.html'
    context_object_name = 'logs'
    paginate_by = 50

    def get_queryset(self):
        queryset = AuditLog.objects.select_related('user')
        action = self.request.GET.get('action')
        model = self.request.GET.get('model')
        if action:
            queryset = queryset.filter(action=action)
        if model:
            queryset = queryset.filter(model_name=model)
        return queryset.order_by('-timestamp')


@login_required
def notification_list(request):
    all_notifications = Notification.objects.filter(recipient=request.user).order_by('-created_at')
    unread_count = all_notifications.filter(is_read=False).count()
    notifications = all_notifications[:50]
    return render(request, 'contracts/notification_list.html', {
        'notifications': notifications,
        'unread_count': unread_count,
    })


@login_required
@require_POST
def mark_notification_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
    notification.is_read = True
    notification.save()
    log_action(
        request.user,
        AuditLog.Action.UPDATE,
        'Notification',
        object_id=notification.id,
        object_repr=str(notification),
        changes={'event': 'mark_notification_read'},
        request=request,
    )
    if notification.link:
        return redirect(notification.link)
    return redirect('contracts:notification_list')


@login_required
@require_POST
def mark_all_notifications_read(request):
    unread_qs = Notification.objects.filter(recipient=request.user, is_read=False)
    updated_count = unread_qs.update(is_read=True)
    log_action(
        request.user,
        AuditLog.Action.UPDATE,
        'Notification',
        object_repr=f'{updated_count} notifications',
        changes={'event': 'mark_all_notifications_read', 'count': updated_count},
        request=request,
    )
    return redirect('contracts:notification_list')
