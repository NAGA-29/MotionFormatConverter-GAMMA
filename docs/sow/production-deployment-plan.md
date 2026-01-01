# 本番環境設定実装プラン

## 概要

Flask開発サーバーの警告を解決するため、本番環境用にGunicorn + Nginx構成を追加します。
開発環境と本番環境を切り替え可能にし、それぞれ適切なサーバー構成で動作させます。

## アーキテクチャ

### 開発環境
```
Client → Flask Dev Server (port 5000) → Blender → Redis
```

### 本番環境
```
Client → Nginx (port 80) → Gunicorn (internal:5000) → Blender → Redis
```

## 実装ステップ

### Step 1: Gunicorn統合

#### 1.1 requirements.txtの更新
**ファイル**: `requirements.txt`

追加:
```
gunicorn==21.2.0
```

#### 1.2 WSGIエントリーポイントの作成
**ファイル**: `app/wsgi.py` (新規作成)

Gunicorn用のエントリーポイント。Blender初期化処理を含む。
`convert.py`の初期化ロジックを再利用しつつ、Gunicornの起動フローに対応。

重要ポイント:
- `if __name__ == "__main__"` ブロックはGunicornでは実行されない
- モジュールimport時にBlender初期化を実行
- appオブジェクトをexportして `gunicorn app.wsgi:app` で起動

#### 1.3 Gunicorn設定ファイルの作成
**ファイル**: `gunicorn.conf.py` (新規作成)

設定内容:
- workers: 2（Blenderの重さを考慮して控えめ）
- timeout: 600秒（大きなファイル変換に対応）
- bind: 0.0.0.0:5000
- worker_class: sync（Blenderは非同期非対応）
- max_requests: 1000（メモリリーク対策）
- ログ設定: stdout/stderrに出力

### Step 2: Nginx設定

#### 2.1 Nginx設定ファイルの作成
**ファイル**: `nginx/nginx.conf` (新規作成)

設定内容:
- upstream: api:5000へプロキシ
- client_max_body_size: 100MB
- proxy_timeout: 600秒（Gunicornと統一）
- セキュリティヘッダー: X-Frame-Options, X-Content-Type-Options, X-XSS-Protection
- gzip圧縮有効化
- ヘルスチェックエンドポイント: /health

### Step 3: Docker設定の分離

#### 3.1 Dockerfileのマルチステージビルド化
**ファイル**: `Dockerfile` (修正)

3つのステージに分離:
1. **base**: 共通の依存関係（Blender, Python packages）
2. **development**: Flask開発サーバー起動
3. **production**: Gunicorn起動

変更箇所:
- `FROM ubuntu:22.04 AS base` でベースステージ開始
- `FROM base AS development` で開発ステージ
- `FROM base AS production` で本番ステージ
- productionステージでcurlをインストール（ヘルスチェック用）
- CMD: 本番では `/usr/local/blender/blender --background --factory-startup --python-use-system-env --python-exec "/usr/local/blender/5.0/python/bin/python3.11 -m gunicorn -c /workspace/gunicorn.conf.py app.wsgi:app"`

#### 3.2 docker-compose.ymlの明確化
**ファイル**: `docker-compose.yml` (修正)

開発環境用として明確化:
- build.target: development
- APP_ENV=development
- volumes: ホットリロード用に./app:/workspace/appマウント
- command: Flask開発サーバー起動
- ports: 5000を直接公開

#### 3.3 本番環境用docker-compose作成
**ファイル**: `docker-compose.prod.yml` (新規作成)

本番環境の構成:
1. **nginxサービス**:
   - image: nginx:1.25-alpine
   - ports: 80:80
   - volumes: nginx.confをマウント
   - healthcheck: wget http://localhost/health

2. **apiサービス**:
   - build.target: production
   - expose: 5000（外部公開せず）
   - APP_ENV=production
   - LOG_FORMAT=json
   - LOG_FILE=/var/log/blender/app.log
   - GUNICORN_WORKERS=2
   - volumesからappディレクトリのマウントを削除（本番ではイメージに焼く）
   - healthcheck: curl http://localhost:5000/health

3. **redisサービス**:
   - expose: 6379（外部公開せず）
   - maxmemory: 512mb
   - maxmemory-policy: allkeys-lru
   - healthcheck追加

全サービス:
- restart: always
- healthcheck設定

### Step 4: 運用スクリプト

#### 4.1 開発環境起動スクリプト
**ファイル**: `scripts/dev.sh` (新規作成)

```bash
#!/bin/bash
docker-compose up --build
```

#### 4.2 本番環境起動スクリプト
**ファイル**: `scripts/prod.sh` (新規作成)

```bash
#!/bin/bash
docker-compose -f docker-compose.prod.yml up -d --build
```

#### 4.3 本番環境停止スクリプト
**ファイル**: `scripts/stop-prod.sh` (新規作成)

```bash
#!/bin/bash
docker-compose -f docker-compose.prod.yml down
```

実行権限を付与: `chmod +x scripts/*.sh`

### Step 5: .gitignoreの更新

**ファイル**: `.gitignore` (修正)

追加:
```
.env.production
nginx/logs/
```

### Step 6: ドキュメント更新

#### 6.1 README.mdの更新
**ファイル**: `README.md` (修正)

追加セクション:
- 環境別起動方法
- アーキテクチャ図
- 環境変数一覧
- ヘルスチェック方法

## 重要なファイルリスト

### 新規作成
1. `app/wsgi.py` - Gunicorn用WSGIエントリーポイント
2. `gunicorn.conf.py` - Gunicorn設定
3. `nginx/nginx.conf` - Nginx設定
4. `docker-compose.prod.yml` - 本番環境用Compose設定
5. `scripts/dev.sh` - 開発環境起動スクリプト
6. `scripts/prod.sh` - 本番環境起動スクリプト
7. `scripts/stop-prod.sh` - 本番環境停止スクリプト

### 修正
1. `requirements.txt` - gunicorn追加
2. `Dockerfile` - マルチステージビルド化
3. `docker-compose.yml` - 開発環境として明確化
4. `.gitignore` - 本番用ファイルを除外
5. `README.md` - ドキュメント更新

## テスト手順

### 開発環境
```bash
# 起動
docker-compose up --build

# ヘルスチェック
curl http://localhost:5000/health

# ログ確認
docker-compose logs api
```

### 本番環境
```bash
# 起動
docker-compose -f docker-compose.prod.yml up -d --build

# ヘルスチェック（Nginx経由）
curl http://localhost/health

# コンテナ状態確認
docker-compose -f docker-compose.prod.yml ps

# ログ確認
docker-compose -f docker-compose.prod.yml logs nginx
docker-compose -f docker-compose.prod.yml logs api

# 停止
docker-compose -f docker-compose.prod.yml down
```

## 注意事項

1. **Dockerfileの--python-execオプション**
   - Blenderで外部Pythonコマンドを実行するため、`--python-exec`を使用
   - Gunicornはコマンド文字列として渡す

2. **ワーカー数**
   - Blenderのメモリ消費が大きいため、ワーカー数は2を推奨
   - サーバースペックに応じて環境変数`GUNICORN_WORKERS`で調整可能

3. **タイムアウト設定**
   - Gunicorn: 600秒
   - Nginx: 600秒
   - 環境変数`CONVERSION_TIMEOUT`: 600秒
   - 3つを統一することが重要

4. **ログ出力**
   - 開発環境: plain形式、stdout
   - 本番環境: JSON形式、ファイル出力（/var/log/blender/app.log）
   - 既存のstructlog設定が活用される

5. **セキュリティ**
   - 本番環境ではAPIとRedisを外部公開しない（exposeのみ）
   - Nginxでセキュリティヘッダーを設定
   - ファイルサイズ制限: 100MB

## 実装順序

1. requirements.txt更新
2. app/wsgi.py作成
3. gunicorn.conf.py作成
4. nginx/nginx.conf作成
5. Dockerfile修正
6. docker-compose.yml修正
7. docker-compose.prod.yml作成
8. scriptsディレクトリ作成とスクリプト追加
9. .gitignore更新
10. README.md更新
11. テストと検証
