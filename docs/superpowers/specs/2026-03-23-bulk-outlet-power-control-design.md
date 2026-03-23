# Bulk Outlet Power Control — Design Spec

## Overview

Add checkbox-based bulk ON/OFF power control to the Outlets table on the PDU detail page.
Users can select multiple outlets and apply Power ON or Power OFF to all selected outlets at once.

## Scope

- **In scope:** Bulk ON and Bulk OFF from the PDU detail page
- **Out of scope:** Bulk Power Cycle (use individual outlet page), bulk control from standalone outlet list page

## Components

### 1. `tables.py` — Add `"pk"` to `default_columns`

`PDUOutletTable.Meta.fields` already contains `"pk"`, but `default_columns` does not. NetBoxTable only shows columns listed in `default_columns` by default, so the checkbox will not appear without this change.

Add `"pk"` as the first entry in `default_columns`:

```python
default_columns = (
    "pk",  # add this line
    "managed_pdu",
    "outlet_number",
    "outlet_name",
    "connected_device",
    "status",
    "current_a",
    "power_w",
    "voltage_v",
    "power_factor",
    "last_updated_from_pdu",
    "actions",
)
```

### 2. `templates/netbox_pdu_plugin/managedpdu.html` — Bulk form outside the table

The Outlets table rendered by `{% render_table outlets_table %}` contains individual action buttons, each with its own `<form>` tag. Wrapping the whole table in another `<form>` would create nested forms (invalid HTML), breaking all individual buttons.

**Solution:** Keep the table unchanged. Add a **separate** `<form>` element in the card footer below the table. JavaScript copies the selected `pk` values as hidden inputs into that form before submission.

```html
<div class="card">
  <h5 class="card-header">Outlets</h5>
  <div class="table-responsive">
    {% render_table outlets_table %}
  </div>
  {% if perms.netbox_pdu_plugin.change_managedpdu %}
  <div class="card-footer d-flex align-items-center gap-2">
    <span class="text-muted small me-2" id="outlet-selected-count">0 selected</span>
    <form id="bulk-power-form" method="post"
          action="{% url 'plugins:netbox_pdu_plugin:pduoutlet_bulk_power' pk=object.pk %}">
      {% csrf_token %}
      <div id="bulk-pk-inputs"></div>
      <button type="submit" name="action" value="on"  class="btn btn-success btn-sm">Power ON</button>
      <button type="submit" name="action" value="off" class="btn btn-danger btn-sm">Power OFF</button>
    </form>
  </div>
  {% endif %}
</div>

<script>
(function () {
  function getChecked() {
    return [...document.querySelectorAll('input[name="pk"]:checked')].map(cb => cb.value);
  }

  function updateCount() {
    const n = getChecked().length;
    const el = document.getElementById('outlet-selected-count');
    if (el) el.textContent = n === 0 ? '0 selected' : n + ' selected';
  }

  document.addEventListener('change', function (e) {
    if (e.target && e.target.name === 'pk') updateCount();
  });

  const bulkForm = document.getElementById('bulk-power-form');
  if (bulkForm) {
    bulkForm.addEventListener('submit', function (e) {
      const pks = getChecked();
      if (pks.length === 0) {
        e.preventDefault();
        alert('Select at least one outlet.');
        return;
      }
      const container = document.getElementById('bulk-pk-inputs');
      // Remove existing hidden inputs using safe DOM removal (no innerHTML)
      while (container.firstChild) {
        container.removeChild(container.firstChild);
      }
      pks.forEach(function (pk) {
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = 'pk';
        input.value = pk;
        container.appendChild(input);
      });
    });
  }
})();
</script>
```

### 3. `views.py` — New `PDUOutletBulkPowerView`

```python
class PDUOutletBulkPowerView(View):
    def post(self, request, pk):
        managed_pdu = get_object_or_404(models.ManagedPDU, pk=pk)

        if not request.user.has_perm("netbox_pdu_plugin.change_managedpdu"):
            messages.error(request, "Permission denied.")
            return redirect(managed_pdu.get_absolute_url())

        action = request.POST.get("action")
        if action not in ("on", "off"):
            messages.error(request, "Invalid action.")
            return redirect(managed_pdu.get_absolute_url())

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
                # Optimistic status update for bulk operations (avoids N extra API round-trips).
                # Consistent with PDUOutletPowerView which also uses save() without update_fields.
                # Status may differ briefly from actual PDU state; use individual outlet sync to verify.
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

### 4. `urls.py` — New URL (add to Managed PDU section)

```python
# In the Managed PDU URL section (not the Outlet section):
path("managed-pdus/<int:pk>/bulk-power/", views.PDUOutletBulkPowerView.as_view(), name="pduoutlet_bulk_power"),
```

## Data Flow

1. User checks outlets on PDU detail page (checkboxes from `pk` column in `default_columns`)
2. Clicks "Power ON" or "Power OFF" in the card footer
3. JavaScript copies checked `pk` values (multiple) as hidden inputs into `#bulk-power-form`, then submits
4. POST to `/managed-pdus/<pk>/bulk-power/` with multiple `pk` values and `action`
5. View validates permission and action value
6. View fetches outlets filtered by `managed_pdu` (cross-PDU manipulation prevented)
7. Calls `client.set_outlet_power_state()` for each outlet sequentially
8. Optimistically updates `outlet.status` and `last_updated_from_pdu` in DB
9. Flash message with success/fail counts
10. Redirect back to PDU detail page

## Error Handling

- No outlets selected → JS alert (client-side), POST not sent
- Invalid action value → error message, redirect back
- No permission → error message, redirect back
- Individual outlet API failure → counted as failed, others continue
- All failures → error message shown

## Permissions

Uses existing `change_managedpdu` permission — no new permissions needed.

## Testing

- Unit test: POST with valid outlet PKs and `action=on` → `set_outlet_power_state` called for each, status set to ON
- Unit test: POST with valid outlet PKs and `action=off` → status set to OFF
- Unit test: POST with no PKs → warning message, no API calls
- Unit test: POST with invalid action (`action=cycle`) → error message, no API calls
- Unit test: POST with outlet PKs belonging to different PDU → ignored (filtered by `managed_pdu=managed_pdu`)
- Unit test: API error on one outlet → others still processed, failed count reported
- Unit test: user without `change_managedpdu` permission → error message, no API calls
