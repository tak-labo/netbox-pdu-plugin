# Bulk Outlet Power Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PDU詳細ページのOutletsテーブルにチェックボックスを追加し、複数アウトレットの一括ON/OFFを可能にする。

**Architecture:** `PDUOutletTable.Meta.default_columns` に `"pk"` を追加してチェックボックスを表示。テーブル内の個別アクションボタンが各自 `<form>` を持つため、バルクフォームはテーブル外のカードフッターに別途配置し、JavaScriptで選択値をコピーして送信。新ビュー `PDUOutletBulkPowerView` がPOSTを受け取り、選択アウトレットを順次制御する。

**Tech Stack:** Django (View), django-tables2 (CheckBoxColumn), Vanilla JavaScript (DOM API), Bootstrap 5

---

## File Structure

| File | Change |
|------|--------|
| `netbox_pdu_plugin/tables.py` | `PDUOutletTable.Meta.default_columns` の先頭に `"pk"` を追加 |
| `netbox_pdu_plugin/views.py` | `PDUOutletBulkPowerView` クラスを追加（末尾の既存Outlet viewsグループ内） |
| `netbox_pdu_plugin/urls.py` | Managed PDUセクションに bulk-power URL を追加 |
| `netbox_pdu_plugin/templates/netbox_pdu_plugin/managedpdu.html` | Outletsカードにフッターとバルクフォーム+JSを追加 |
| `netbox_pdu_plugin/tests/test_views.py` | `PDUOutletBulkPowerViewTest` クラスを追加 |

---

## Task 1: Write failing tests for PDUOutletBulkPowerView

**Files:**
- Modify: `netbox_pdu_plugin/tests/test_views.py:345` (末尾に追記)

### Background: テスト実行コマンド

```bash
# Docker内で実行（全テスト）
DC="docker compose -f ../netbox-docker/docker-compose.yml -f ../netbox-docker/docker-compose.override.yml"
$DC exec netbox python manage.py test netbox_pdu_plugin.tests.test_views -v2

# このタスクのクラスだけ実行
$DC exec netbox python manage.py test netbox_pdu_plugin.tests.test_views.PDUOutletBulkPowerViewTest -v2
```

### Background: 既存の `PDUOutletPowerViewTest` パターンを参照

既存テスト（`test_views.py:165`）では以下のパターンを使う：
- `@patch("netbox_pdu_plugin.views.get_pdu_client")` でバックエンドをモック
- `self.add_permissions("netbox_pdu_plugin.change_managedpdu")` で権限付与
- `self.client.post(url, data)` で POST リクエストを送信
- `self.assertHttpStatus(response, 302)` でリダイレクトを確認

- [ ] **Step 1: `test_views.py` の末尾に `PDUOutletBulkPowerViewTest` クラスを追加**

`test_views.py` の末尾（345行目の後）に以下を追記する：

```python
class PDUOutletBulkPowerViewTest(PluginViewTestCase):
    """Tests for PDUOutletBulkPowerView (bulk ON/OFF)."""

    @classmethod
    def setUpTestData(cls):
        cls.pdu = create_test_pdu()
        cls.pdu2_device = create_test_device("PDU-BULK-2")
        cls.pdu2 = create_test_pdu(cls.pdu2_device)
        cls.outlet1 = PDUOutlet.objects.create(
            managed_pdu=cls.pdu,
            outlet_number=1,
            outlet_name="Outlet 1",
        )
        cls.outlet2 = PDUOutlet.objects.create(
            managed_pdu=cls.pdu,
            outlet_number=2,
            outlet_name="Outlet 2",
        )
        cls.outlet_other_pdu = PDUOutlet.objects.create(
            managed_pdu=cls.pdu2,
            outlet_number=1,
            outlet_name="Other PDU Outlet",
        )

    def _url(self):
        return reverse(
            "plugins:netbox_pdu_plugin:pduoutlet_bulk_power",
            kwargs={"pk": self.pdu.pk},
        )

    def test_bulk_power_without_permission_redirects(self):
        """POST without permission redirects, no API call."""
        response = self.client.post(self._url(), {"action": "on", "pk": [self.outlet1.pk]})
        self.assertHttpStatus(response, 302)

    def test_bulk_power_without_permission_does_not_call_backend(self):
        with patch("netbox_pdu_plugin.views.get_pdu_client") as mock_get_client:
            self.client.post(self._url(), {"action": "on", "pk": [self.outlet1.pk]})
            mock_get_client.assert_not_called()

    @patch("netbox_pdu_plugin.views.get_pdu_client")
    def test_bulk_power_on(self, mock_get_client):
        """Power ON sets status ON for all selected outlets."""
        self.add_permissions("netbox_pdu_plugin.change_managedpdu")
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        response = self.client.post(
            self._url(), {"action": "on", "pk": [self.outlet1.pk, self.outlet2.pk]}
        )

        self.assertHttpStatus(response, 302)
        mock_client.set_outlet_power_state.assert_any_call(0, "on")
        mock_client.set_outlet_power_state.assert_any_call(1, "on")
        self.assertEqual(mock_client.set_outlet_power_state.call_count, 2)
        self.outlet1.refresh_from_db()
        self.outlet2.refresh_from_db()
        self.assertEqual(self.outlet1.status, OutletStatusChoices.ON)
        self.assertEqual(self.outlet2.status, OutletStatusChoices.ON)

    @patch("netbox_pdu_plugin.views.get_pdu_client")
    def test_bulk_power_off(self, mock_get_client):
        """Power OFF sets status OFF for all selected outlets."""
        self.add_permissions("netbox_pdu_plugin.change_managedpdu")
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        response = self.client.post(
            self._url(), {"action": "off", "pk": [self.outlet1.pk, self.outlet2.pk]}
        )

        self.assertHttpStatus(response, 302)
        self.outlet1.refresh_from_db()
        self.outlet2.refresh_from_db()
        self.assertEqual(self.outlet1.status, OutletStatusChoices.OFF)
        self.assertEqual(self.outlet2.status, OutletStatusChoices.OFF)

    @patch("netbox_pdu_plugin.views.get_pdu_client")
    def test_bulk_power_no_pks_returns_warning(self, mock_get_client):
        """POST with no pk values shows warning, no API call."""
        self.add_permissions("netbox_pdu_plugin.change_managedpdu")
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        response = self.client.post(self._url(), {"action": "on"})

        self.assertHttpStatus(response, 302)
        mock_client.set_outlet_power_state.assert_not_called()

    @patch("netbox_pdu_plugin.views.get_pdu_client")
    def test_bulk_power_invalid_action_returns_error(self, mock_get_client):
        """POST with action=cycle is rejected, no API call."""
        self.add_permissions("netbox_pdu_plugin.change_managedpdu")
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        response = self.client.post(
            self._url(), {"action": "cycle", "pk": [self.outlet1.pk]}
        )

        self.assertHttpStatus(response, 302)
        mock_client.set_outlet_power_state.assert_not_called()

    @patch("netbox_pdu_plugin.views.get_pdu_client")
    def test_bulk_power_ignores_outlets_from_other_pdu(self, mock_get_client):
        """Outlets belonging to a different PDU are silently ignored."""
        self.add_permissions("netbox_pdu_plugin.change_managedpdu")
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        response = self.client.post(
            self._url(),
            {"action": "on", "pk": [self.outlet1.pk, self.outlet_other_pdu.pk]},
        )

        self.assertHttpStatus(response, 302)
        # Only outlet1 (belonging to cls.pdu) should be processed
        mock_client.set_outlet_power_state.assert_called_once_with(0, "on")

    @patch("netbox_pdu_plugin.views.get_pdu_client")
    def test_bulk_power_continues_after_api_error(self, mock_get_client):
        """If one outlet fails, others are still processed."""
        self.add_permissions("netbox_pdu_plugin.change_managedpdu")
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # First call raises error, second succeeds
        mock_client.set_outlet_power_state.side_effect = [
            PDUClientError("timeout"),
            None,
        ]

        response = self.client.post(
            self._url(), {"action": "on", "pk": [self.outlet1.pk, self.outlet2.pk]}
        )

        self.assertHttpStatus(response, 302)
        self.assertEqual(mock_client.set_outlet_power_state.call_count, 2)
        # outlet2 succeeded → status updated
        self.outlet2.refresh_from_db()
        self.assertEqual(self.outlet2.status, OutletStatusChoices.ON)
```

- [ ] **Step 2: コードをコンテナにコピーしてテストを実行（失敗することを確認）**

```bash
DC="docker compose -f ../netbox-docker/docker-compose.yml -f ../netbox-docker/docker-compose.override.yml"
docker cp netbox_pdu_plugin/tests/test_views.py \
  "$(eval $DC ps -q netbox)":/opt/netbox/venv/lib/python3.12/site-packages/netbox_pdu_plugin/tests/test_views.py
$DC exec netbox python manage.py test netbox_pdu_plugin.tests.test_views.PDUOutletBulkPowerViewTest -v2
```

Expected: `NoReverseMatch` または `404` エラー（URLがまだ存在しないため）

- [ ] **Step 3: コミット**

```bash
git add netbox_pdu_plugin/tests/test_views.py
git commit -m "test: PDUOutletBulkPowerViewのテストを追加（未実装）"
```

---

## Task 2: Implement URL and View

**Files:**
- Modify: `netbox_pdu_plugin/urls.py:24` (Managed PDUセクションの末尾に追加)
- Modify: `netbox_pdu_plugin/views.py:516` (PDUOutletPowerCycleView の直後に追加)

### Background: `views.py` の既存インポート確認

`views.py` の先頭には以下がすでにインポートされている：
- `from django.contrib import messages`
- `from django.shortcuts import get_object_or_404, redirect`
- `from django.utils import timezone`
- `from django.views import View`
- `from . import models`
- `from .backends import PDUClientError, get_pdu_client`
- `from .choices import OutletStatusChoices`

**追加インポートは不要。**

- [ ] **Step 1: `urls.py` に URL を追加**

`urls.py` の24行目（`managedpdu_get_metrics` の直後、25行目の `# PDU Outlet` コメントの**直前**）に追加：

```python
    path(
        "managed-pdus/<int:pk>/bulk-power/",
        views.PDUOutletBulkPowerView.as_view(),
        name="pduoutlet_bulk_power",
    ),
```

- [ ] **Step 2: `views.py` に `PDUOutletBulkPowerView` を追加**

`views.py` の `PDUOutletPowerCycleView` クラス（`power_state = "cycle"` の行）の直後に追加：

```python
class PDUOutletBulkPowerView(View):
    """Bulk power ON/OFF for multiple outlets of a single PDU."""

    def post(self, request, pk):
        managed_pdu = get_object_or_404(models.ManagedPDU, pk=pk)

        if not request.user.has_perm("netbox_pdu_plugin.change_managedpdu"):
            messages.error(request, _("You do not have permission to control outlets."))
            return redirect(managed_pdu.get_absolute_url())

        action = request.POST.get("action")
        if action not in ("on", "off"):
            messages.error(request, _("Invalid action."))
            return redirect(managed_pdu.get_absolute_url())

        outlet_pks = request.POST.getlist("pk")
        if not outlet_pks:
            messages.warning(request, _("No outlets selected."))
            return redirect(managed_pdu.get_absolute_url())

        outlets = models.PDUOutlet.objects.filter(pk__in=outlet_pks, managed_pdu=managed_pdu)
        client = get_pdu_client(managed_pdu)
        success, failed = 0, 0

        for outlet in outlets:
            try:
                client.set_outlet_power_state(outlet.outlet_number - 1, action)
                # Optimistic status update — avoids N extra API round-trips.
                # Use individual outlet sync to verify actual state if needed.
                outlet.status = OutletStatusChoices.ON if action == "on" else OutletStatusChoices.OFF
                outlet.last_updated_from_pdu = timezone.now()
                outlet.save()
                success += 1
            except PDUClientError as e:
                logger.error("Bulk power %s failed for outlet %s: %s", action, outlet, e)
                failed += 1

        if success:
            messages.success(request, f"{success} outlet(s) powered {action.upper()}.")
        if failed:
            messages.error(request, f"{failed} outlet(s) failed.")

        return redirect(managed_pdu.get_absolute_url())
```

> **注意:** `logger` は `views.py` 先頭で `logger = logging.getLogger(__name__)` として定義済み。`_()` は `from django.utils.translation import gettext_lazy as _` でインポート済み。

- [ ] **Step 3: コンテナにコピーしてテストを実行（通過することを確認）**

```bash
DC="docker compose -f ../netbox-docker/docker-compose.yml -f ../netbox-docker/docker-compose.override.yml"
docker cp netbox_pdu_plugin/views.py \
  "$(eval $DC ps -q netbox)":/opt/netbox/venv/lib/python3.12/site-packages/netbox_pdu_plugin/views.py
docker cp netbox_pdu_plugin/urls.py \
  "$(eval $DC ps -q netbox)":/opt/netbox/venv/lib/python3.12/site-packages/netbox_pdu_plugin/urls.py
eval $DC restart netbox netbox-worker
$DC exec netbox python manage.py test netbox_pdu_plugin.tests.test_views.PDUOutletBulkPowerViewTest -v2
```

Expected: 全テスト PASS

- [ ] **Step 4: コミット**

```bash
git add netbox_pdu_plugin/views.py netbox_pdu_plugin/urls.py
git commit -m "feat: PDUOutletBulkPowerViewを追加（一括ON/OFF）"
```

---

## Task 3: Add pk to PDUOutletTable default_columns

**Files:**
- Modify: `netbox_pdu_plugin/tables.py:143-155`

- [ ] **Step 1: `tables.py` の `PDUOutletTable.Meta.default_columns` を編集**

`tables.py` の143行目、`default_columns` タプルの先頭に `"pk"` を追加：

```python
        default_columns = (
            "pk",
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

- [ ] **Step 2: コンテナにコピーして全テストを実行**

```bash
DC="docker compose -f ../netbox-docker/docker-compose.yml -f ../netbox-docker/docker-compose.override.yml"
docker cp netbox_pdu_plugin/tables.py \
  "$(eval $DC ps -q netbox)":/opt/netbox/venv/lib/python3.12/site-packages/netbox_pdu_plugin/tables.py
$DC exec netbox python manage.py test netbox_pdu_plugin.tests -v2
```

Expected: 全テスト PASS

- [ ] **Step 3: コミット**

```bash
git add netbox_pdu_plugin/tables.py
git commit -m "feat: Outletsテーブルにpkチェックボックスをデフォルト表示"
```

---

## Task 4: Add bulk form to managedpdu.html

**Files:**
- Modify: `netbox_pdu_plugin/templates/netbox_pdu_plugin/managedpdu.html:240-249`

### Background: 現在の Outlets カード構造（228-237行目）

```html
  <div class="row">
    <div class="col col-md-12">
      <div class="card">
        <h5 class="card-header">Outlets</h5>
        <div class="table-responsive">
          {% render_table outlets_table %}
        </div>
      </div>
    </div>
  </div>
```

**`<div class="card">` の閉じタグ `</div>` の直前にフッターを追加する。**

- [ ] **Step 1: `managedpdu.html` の Outlets カードを編集**

現在の Outlets カードブロック（`<div class="card">` ～ `</div>` まで）を以下に置き換える：

```html
  <div class="row">
    <div class="col col-md-12">
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
    </div>
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

- [ ] **Step 2: コンテナにコピーしてブラウザで動作確認**

```bash
DC="docker compose -f ../netbox-docker/docker-compose.yml -f ../netbox-docker/docker-compose.override.yml"
docker cp netbox_pdu_plugin/templates/netbox_pdu_plugin/managedpdu.html \
  "$(eval $DC ps -q netbox)":/opt/netbox/venv/lib/python3.12/site-packages/netbox_pdu_plugin/templates/netbox_pdu_plugin/managedpdu.html
```

ブラウザで PDU 詳細ページを開き以下を確認：
- [ ] Outlets テーブルの左端にチェックボックスが表示される
- [ ] ヘッダー行の全選択チェックボックスが機能する
- [ ] チェックを入れると下部に「N selected」カウントが表示される
- [ ] Power ON ボタンで選択アウトレットが ON になる
- [ ] Power OFF ボタンで選択アウトレットが OFF になる
- [ ] 0件選択でボタンを押すとアラートが出る

- [ ] **Step 3: 全テストを実行して回帰なし確認**

```bash
$DC exec netbox python manage.py test netbox_pdu_plugin.tests -v2
```

Expected: 全テスト PASS

- [ ] **Step 4: コミット**

```bash
git add netbox_pdu_plugin/templates/netbox_pdu_plugin/managedpdu.html
git commit -m "feat: PDU詳細ページにバルク電源コントロールを追加"
```
