# Bulk Outlet Power Control — Design Spec

## Overview

Add checkbox-based bulk ON/OFF power control to the Outlets table on the PDU detail page.
Users can select multiple outlets and apply Power ON or Power OFF to all selected outlets at once.

## Scope

- **In scope:** Bulk ON and Bulk OFF from the PDU detail page
- **Out of scope:** Bulk Power Cycle (use individual outlet page), bulk control from standalone outlet list page

## Components

### 1. `tables.py` — Add CheckBoxColumn

Add `CheckBoxColumn` as the first column of `PDUOutletTable`:

```python
from netbox.tables import columns

class PDUOutletTable(NetBoxTable):
    pk = columns.CheckBoxColumn(accessor="pk")
    ...
```

This renders a checkbox in each row's leftmost cell, and a "select all" checkbox in the header.

### 2. `templates/netbox_pdu_plugin/managedpdu.html` — Wrap table in form

Replace the bare `render_table` call for outlets with a `<form>` wrapper:

```html
<form method="post" action="{% url 'plugins:netbox_pdu_plugin:pduoutlet_bulk_power' pk=object.pk %}">
  {% csrf_token %}
  {% render_table outlets_table %}
  {% if perms.netbox_pdu_plugin.change_managedpdu %}
  <div class="card-footer d-flex align-items-center gap-2">
    <button name="action" value="on"  class="btn btn-success btn-sm">Power ON</button>
    <button name="action" value="off" class="btn btn-danger btn-sm">Power OFF</button>
  </div>
  {% endif %}
</form>
```

### 3. `views.py` — New `PDUOutletBulkPowerView`

```python
class PDUOutletBulkPowerView(View):
    def post(self, request, pk):
        managed_pdu = get_object_or_404(models.ManagedPDU, pk=pk)

        if not request.user.has_perm("netbox_pdu_plugin.change_managedpdu"):
            messages.error(request, "Permission denied.")
            return redirect(managed_pdu.get_absolute_url())

        action = request.POST.get("action")  # "on" or "off"
        outlet_pks = request.POST.getlist("pk")

        if not outlet_pks:
            messages.warning(request, "No outlets selected.")
            return redirect(managed_pdu.get_absolute_url())

        outlets = models.PDUOutlet.objects.filter(pk__in=outlet_pks, managed_pdu=managed_pdu)
        client = get_pdu_client(managed_pdu)
        success, failed = 0, 0

        for outlet in outlets:
            try:
                client.set_outlet_power_state(outlet.outlet_number - 1, action)
                outlet.status = OutletStatusChoices.ON if action == "on" else OutletStatusChoices.OFF
                outlet.last_updated_from_pdu = timezone.now()
                outlet.save()
                success += 1
            except PDUClientError:
                failed += 1

        if success:
            messages.success(request, f"{success} outlet(s) powered {action.upper()}.")
        if failed:
            messages.error(request, f"{failed} outlet(s) failed.")

        return redirect(managed_pdu.get_absolute_url())
```

### 4. `urls.py` — New URL

```python
path("managed-pdus/<int:pk>/bulk-power/", views.PDUOutletBulkPowerView.as_view(), name="pduoutlet_bulk_power"),
```

## Data Flow

1. User checks outlets on PDU detail page
2. Clicks "Power ON" or "Power OFF" button
3. POST to `/managed-pdus/<pk>/bulk-power/` with `pk[]` list and `action`
4. View validates permission, fetches outlets belonging to this PDU
5. Calls `client.set_outlet_power_state()` for each outlet sequentially
6. Updates `outlet.status` and `last_updated_from_pdu` in DB
7. Flash message with success/fail counts
8. Redirect back to PDU detail page

## Error Handling

- No outlets selected → warning message, redirect back
- No permission → error message, redirect back
- Individual outlet API failure → counted as failed, others continue
- All failures → error message shown

## Permissions

Uses existing `change_managedpdu` permission — no new permissions needed.

## Testing

- Unit test: POST with valid outlet PKs → `set_outlet_power_state` called for each, status updated
- Unit test: POST with no PKs → warning message, no API calls
- Unit test: POST with outlet PKs belonging to different PDU → ignored (filtered by `managed_pdu=managed_pdu`)
- Unit test: API error on one outlet → others still processed
