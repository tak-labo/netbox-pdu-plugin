# NetBox PDU Plugin

NetBox plugin for PDU management.

![NetBox](https://img.shields.io/badge/NetBox-4.5-blue)
![Python](https://img.shields.io/badge/Python-3.12%2B-blue)
![PyPI](https://img.shields.io/pypi/v/netbox-pdu-plugin)
![License](https://img.shields.io/badge/License-Apache%202.0-green)

> **[日本語版は下にあります / Japanese version below](#netbox-pdu-プラグイン)**

---

## Supported Vendors

| Vendor | Product | Protocol | Authentication |
|--------|---------|----------|----------------|
| Raritan | Xerus series | JSON-RPC 2.0 over HTTPS | HTTP Basic Auth |
| Ubiquiti | USP-PDU-Pro | UniFi Network Controller REST API | API Key or Session |

---

## Tested Hardware

The following hardware has been confirmed to work with this plugin:

| Vendor | Model | Version | Notes |
|--------|-------|---------|-------|
| Raritan | PX3-5138JR | Firmware 4.3.x (Xerus) | Full support: outlets, inlets, power control, thresholds |
| Ubiquiti | USP-PDU-Pro | UniFi OS 5.0.16 / Network 10.1.89 | Outlet control/monitoring; inlet data via aggregate power; no thresholds |

Other Raritan PDUs running Xerus firmware (PX2, PX3, PX4, BCM families) should work, but have not been directly tested.

---

## Features

- **Sync** hardware info (model, serial, firmware, rated power/voltage/current), network settings (IP, MAC, NTP, DNS) from the PDU
- **Outlet monitoring** — voltage, current, active power, power factor, accumulated energy per outlet
- **Inlet monitoring** — total input current, voltage, power, apparent power, frequency
- **Power control** — ON / OFF / Power Cycle per outlet with one click
- **Name push** — write outlet/inlet names from NetBox back to the PDU; syncs `PowerOutlet.label` / `PowerPort.label` on the connected device automatically
- **Threshold display** — warning and critical thresholds per sensor (Raritan only)
- **Background jobs** — post-cycle status refresh via RQ worker
- **REST API & GraphQL** — full NetBox-native API for all models
- **Multi-vendor architecture** — add new vendors by implementing a single base class

---

## Install

### Standard (non-Docker)

**1. Install the package**

```bash
source /opt/netbox/venv/bin/activate
pip install netbox-pdu-plugin
```

**2. Enable the plugin**

Add to `/opt/netbox/netbox/netbox/configuration.py`:

```python
PLUGINS = ["netbox_pdu_plugin"]
```

**3. Run migrations and restart**

```bash
cd /opt/netbox/netbox
python manage.py migrate
sudo systemctl restart netbox netbox-rq
```

---

### Docker (netbox-docker)

See also: [Using NetBox Plugins](https://github.com/netbox-community/netbox-docker/wiki/Using-Netbox-Plugins)

**1. Create `plugin_requirements.txt`**

```
netbox-pdu-plugin
```

**2. Create `Dockerfile-Plugins`**

```dockerfile
FROM netboxcommunity/netbox:latest

COPY ./plugin_requirements.txt /opt/netbox/
RUN /usr/local/bin/uv pip install -r /opt/netbox/plugin_requirements.txt

COPY configuration/configuration.py /etc/netbox/config/configuration.py
COPY configuration/plugins.py /etc/netbox/config/plugins.py
RUN DEBUG="true" SECRET_KEY="dummydummydummydummydummydummydummydummydummydummy" \
    /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py collectstatic --no-input
```

**3. Configure `docker-compose.override.yml`**

```yaml
services:
  netbox:
    image: netbox:latest-plugins
    pull_policy: never
    ports:
      - 8000:8080
    build:
      context: .
      dockerfile: Dockerfile-Plugins
  netbox-worker:
    image: netbox:latest-plugins
    pull_policy: never
```

**4. Enable the plugin**

Add to `configuration/plugins.py`:

```python
PLUGINS = ["netbox_pdu_plugin"]
```

**5. Build, start, and migrate**

```bash
docker compose build --no-cache
docker compose up -d
docker compose exec netbox python manage.py migrate
```

---

## Configure

### Create a ManagedPDU

Go to **Plugins → PDU Management → Add** and fill in the connection details.

| Field | Description |
|-------|-------------|
| Device | NetBox Device record for this PDU |
| Vendor | `Raritan` or `Ubiquiti (USP-PDU-Pro)` |
| API URL | Base URL of the PDU or UniFi controller (e.g. `https://192.168.1.1`) |
| API Username | Username for authentication. Leave blank on Ubiquiti to use API key mode |
| API Password | Password or API key |
| Verify SSL | Uncheck if the PDU uses a self-signed certificate |

### Ubiquiti-specific options

- **API key mode**: leave `API Username` blank and set `API Password` to the API key — no session required
- **Controller type**: UDM/UCG and standalone controllers are auto-detected
- **Site**: append `/s/<site>` to the API URL to target a non-default site (e.g. `https://192.168.1.1/s/mysite`)

---

## Use

### Syncing a PDU

Open a ManagedPDU detail page and click **Sync**. The plugin fetches hardware info and updates all outlet and inlet records. Sync status and timestamp are displayed on the detail page.

### Power control

On an outlet detail page, use the **Actions** card to turn the outlet ON, OFF, or trigger a Power Cycle. After a cycle, the status is updated automatically by a background job.

### Pushing names to the PDU

On an outlet or inlet detail page, click **Push Name to PDU** to write the name stored in NetBox to the PDU. The corresponding `PowerOutlet.label` or `PowerPort.label` on the connected NetBox device is also updated.

---

## Versions

| Plugin version | NetBox version |
|---------------|----------------|
| 0.2.0 | 4.5.0 – 4.5.xx |

---

## Vendor notes

### Raritan

- Uses JSON-RPC 2.0, not standard REST — each resource path is a separate endpoint
- Outlet power control uses 0-based index (`/model/pdu/0/outlet/{N}`)
- Outlet/inlet data is accessed via opaque RIDs returned by `getOutlets` / `getInlets`

### Ubiquiti

- `outlet_overrides` requires all outlets in a single PUT — partial updates reset unspecified outlets
- Inlet API is not supported — `outlet_ac_power_consumption` is exposed as Inlet 1 instead
- Sensor thresholds are not available via the UniFi API

---

## Development

```bash
# Run the same checks as CI (lint + Docker integration tests)
make ci

# Lint only
make lint

# Run integration tests via Docker
docker compose exec netbox python manage.py test netbox_pdu_plugin.tests -v 2

# Restart after code changes
docker compose restart netbox netbox-worker

# Apply migrations
docker compose exec netbox python manage.py migrate

# Generate migrations (requires DEVELOPER=True)
docker compose exec -e DEVELOPER=True netbox python manage.py makemigrations netbox_pdu_plugin
```

A pre-push hook is installed automatically by pre-commit. It runs lint and Docker integration tests before every `git push`.

```bash
# Install the pre-push hook (run once after cloning)
uvx pre-commit install --hook-type pre-push
```

### Adding a new vendor

1. Create `netbox_pdu_plugin/backends/<vendor>.py` implementing `BasePDUClient`
2. Register it in `netbox_pdu_plugin/backends/__init__.py` under `_VENDOR_BACKENDS`
3. Add the choice to `VendorChoices` in `netbox_pdu_plugin/choices.py`
4. Generate and apply a migration

---
---

# NetBox PDU プラグイン

[NetBox](https://github.com/netbox-community/netbox) 用プラグイン。Managed PDUを NetBox の Device レコードに紐付け、Vendor API 経由でアウトレット・インレットの監視と電源制御を行います。

---

## 対応ベンダー

| ベンダー | 製品 | プロトコル | 認証方式 |
|---------|------|-----------|---------|
| Raritan | Xerus シリーズ | JSON-RPC 2.0 over HTTPS | HTTP Basic 認証 |
| Ubiquiti | USP-PDU-Pro | UniFi Network Controller REST API | API キーまたはセッション |

---

## テスト済みハードウェア

以下のハードウェアで動作確認済みです：

| ベンダー | モデル | バージョン | 備考 |
|---------|--------|-----------|------|
| Raritan | PX3-5138JR | ファームウェア 4.3.x（Xerus） | アウトレット・インレット・電源制御・しきい値すべて対応 |
| Ubiquiti | USP-PDU-Pro | UniFi OS 5.0.16 / Network 10.1.89 | アウトレット制御・監視に対応；インレットは合計消費電力で代替表示；しきい値は非対応 |

Xerus ファームウェアが動作する他の Raritan PDU（PX2、PX3、PX4、BCM 系）も動作すると考えられますが、直接のテストは行っていません。

---

## 機能

- **同期** — ハードウェア情報（型番・シリアル・ファームウェア・定格電力/電圧/電流）、ネットワーク設定（IP・MAC・NTP・DNS）を PDU から取得
- **アウトレット監視** — 各アウトレットの電圧・電流・有効電力・力率・累積電力量
- **インレット監視** — 入力全体の電流・電圧・電力・皮相電力・周波数
- **電源制御** — アウトレットごとに ON / OFF / Power Cycle をワンクリックで実行
- **名前プッシュ** — NetBox 上のアウトレット名・インレット名を PDU に書き込み、接続デバイスの `PowerOutlet.label` / `PowerPort.label` も自動更新
- **しきい値表示** — センサーごとの警告・クリティカルしきい値を表示（Raritan のみ）
- **バックグラウンドジョブ** — Power Cycle 後のステータス更新を RQ ワーカーで実行
- **REST API & GraphQL** — 全モデルに対応した NetBox ネイティブ API
- **マルチベンダー設計** — ベースクラスを実装するだけで新ベンダーを追加可能

---

## インストール

### 通常環境（非Docker）

**1. パッケージをインストール**

```bash
source /opt/netbox/venv/bin/activate
pip install netbox-pdu-plugin
```

**2. プラグインを有効化**

`/opt/netbox/netbox/netbox/configuration.py` に追加:

```python
PLUGINS = ["netbox_pdu_plugin"]
```

**3. マイグレーション実行と再起動**

```bash
cd /opt/netbox/netbox
python manage.py migrate
sudo systemctl restart netbox netbox-rq
```

---

### Docker 環境（netbox-docker）

参考: [Using NetBox Plugins](https://github.com/netbox-community/netbox-docker/wiki/Using-Netbox-Plugins)

**1. `plugin_requirements.txt` を作成**

```
netbox-pdu-plugin
```

**2. `Dockerfile-Plugins` を作成**

```dockerfile
FROM netboxcommunity/netbox:latest

COPY ./plugin_requirements.txt /opt/netbox/
RUN /usr/local/bin/uv pip install -r /opt/netbox/plugin_requirements.txt

COPY configuration/configuration.py /etc/netbox/config/configuration.py
COPY configuration/plugins.py /etc/netbox/config/plugins.py
RUN DEBUG="true" SECRET_KEY="dummydummydummydummydummydummydummydummydummydummy" \
    /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py collectstatic --no-input
```

**3. `docker-compose.override.yml` を設定**

```yaml
services:
  netbox:
    image: netbox:latest-plugins
    pull_policy: never
    ports:
      - 8000:8080
    build:
      context: .
      dockerfile: Dockerfile-Plugins
  netbox-worker:
    image: netbox:latest-plugins
    pull_policy: never
```

**4. プラグインを有効化**

`configuration/plugins.py` に追加:

```python
PLUGINS = ["netbox_pdu_plugin"]
```

**5. ビルド・起動・マイグレーション**

```bash
docker compose build --no-cache
docker compose up -d
docker compose exec netbox python manage.py migrate
```

---

## 設定

### ManagedPDU の作成

**Plugins → PDU Management → Add** から接続情報を入力します。

| フィールド | 説明 |
|-----------|------|
| Device | NetBox に登録済みの PDU デバイス |
| Vendor | `Raritan` または `Ubiquiti (USP-PDU-Pro)` |
| API URL | PDU または UniFi コントローラーの URL（例: `https://192.168.1.1`） |
| API Username | 認証ユーザー名。Ubiquiti で API キーモードを使う場合は空欄 |
| API Password | パスワードまたは API キー |
| Verify SSL | 自己署名証明書の場合はオフにする |

### Ubiquiti 固有の設定

- **API キーモード**: `API Username` を空欄にし、`API Password` に API キーを設定（セッション認証不要）
- **コントローラー種別**: UDM/UCG とスタンドアロンコントローラーを自動判別
- **サイト指定**: デフォルト以外のサイトを指定する場合は API URL に `/s/<site>` を付加（例: `https://192.168.1.1/s/mysite`）

---

## 使い方

### PDU の同期

ManagedPDU 詳細ページで **Sync** をクリックすると、ハードウェア情報を取得し、全アウトレット・インレットのレコードを更新します。同期状態とタイムスタンプが詳細ページに表示されます。

### 電源制御

アウトレット詳細ページの **Actions** カードから ON / OFF / Power Cycle を実行できます。Power Cycle 後はバックグラウンドジョブでステータスが自動更新されます。

### PDU への名前プッシュ

アウトレットまたはインレットの詳細ページで **Push Name to PDU** をクリックすると、NetBox に保存されている名前をPDUに書き込みます。接続先デバイスの `PowerOutlet.label` / `PowerPort.label` も同時に更新されます。

---

## バージョン対応表

| プラグインバージョン | NetBox バージョン |
|-------------------|-----------------|
| 0.1.0 | 4.5.0 – 4.5.xx |

---

## ベンダー別の注意事項

### Raritan

- JSON-RPC 2.0 を使用（標準 REST ではない）— リソースパスごとに個別のエンドポイント
- アウトレット電源制御は 0-based index（`/model/pdu/0/outlet/{N}`）
- アウトレット・インレットデータは `getOutlets` / `getInlets` が返す opaque RID 経由でアクセス

### Ubiquiti

- `outlet_overrides` は全アウトレット分をまとめて PUT する必要あり（一部のみ送ると未指定分がリセットされる）
- インレット API は非対応 — `outlet_ac_power_consumption`（合計消費電力）を Inlet 1 として代替表示
- センサーしきい値は UniFi API 非対応

---

## 開発

```bash
# CIと同じチェックを実行（lint + Docker統合テスト）
make ci

# lintのみ
make lint

# Docker経由で統合テストを実行
docker compose exec netbox python manage.py test netbox_pdu_plugin.tests -v 2

# コード変更後の再起動
docker compose restart netbox netbox-worker

# マイグレーション適用
docker compose exec netbox python manage.py migrate

# マイグレーション自動生成（DEVELOPER=True 必須）
docker compose exec -e DEVELOPER=True netbox python manage.py makemigrations netbox_pdu_plugin
```

pre-pushフックがpre-commitによって自動インストールされます。`git push` 前に自動でlintとDockerテストが実行されます。

```bash
# pre-pushフックのインストール（clone後に1度だけ実行）
uvx pre-commit install --hook-type pre-push
```

### 新ベンダーの追加方法

1. `netbox_pdu_plugin/backends/<vendor>.py` に `BasePDUClient` を実装
2. `netbox_pdu_plugin/backends/__init__.py` の `_VENDOR_BACKENDS` に登録
3. `netbox_pdu_plugin/choices.py` の `VendorChoices` に追加
4. マイグレーションを生成・適用
