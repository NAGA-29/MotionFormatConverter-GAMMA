# トラブルシューティング

このドキュメントでは、Motion Forge Gateway APIを使用する際によく発生する問題とその解決方法について説明します。

## 目次

- [curl エラーの対処](#curl-エラーの対処)
  - [エラー26: Failed to open/read local data from file/application](#エラー26-failed-to-openread-local-data-from-fileapplication)
  - [エラー52: Empty reply from server](#エラー52-empty-reply-from-server)
- [その他のよくあるエラー](#その他のよくあるエラー)
- [パフォーマンス問題](#パフォーマンス問題)
- [ログの確認方法](#ログの確認方法)

---

## curl エラーの対処

### エラー26: "Failed to open/read local data from file/application"

**原因**: ファイルパスの指定が誤っています。

#### ❌ 誤った例

```bash
# 先頭の / はシステムのルートディレクトリを意味します
curl -F "file=@/assets/model.fbx" \
     "http://localhost:5000/convert?output_format=glb" \
     --output model.glb
```

#### ✅ 正しい例

```bash
# プロジェクトルートからの相対パス
curl -F "file=@assets/model.fbx" \
     "http://localhost:5000/convert?output_format=glb" \
     --output model.glb

# 明示的な相対パス
curl -F "file=@./assets/model.fbx" \
     "http://localhost:5000/convert?output_format=glb" \
     --output model.glb

# 絶対パスを使う場合
curl -F "file=@$PWD/assets/model.fbx" \
     "http://localhost:5000/convert?output_format=glb" \
     --output model.glb
```

**チェックポイント**:
- ファイルが実際に存在するか確認: `ls -lh assets/model.fbx`
- カレントディレクトリを確認: `pwd`
- ファイルの読み取り権限を確認: `ls -l assets/model.fbx`

---

### エラー52: "Empty reply from server"

**原因**: サーバーが変換処理中にクラッシュしています。これはBlenderが予期しないエラーに遭遇した場合に発生します。

**最もよくある原因**: Blenderのバージョン不具合またはFBXインポーターのバグ

#### 対処法

##### 0. **Blenderバージョンの問題（最優先）**

Blender 5.0系には FBX インポート時のクラッシュが報告されています。**安定版の Blender 4.2 LTS** を使用することを強く推奨します。

**修正方法**:

Dockerfile は `linuxserver/blender` をベースにしています。バージョンを変える場合は
ビルド引数 `BLENDER_IMAGE` を差し替えます。

```bash
docker build --build-arg BLENDER_IMAGE=linuxserver/blender:latest -t blender-converter .
```

変更後、イメージを再ビルド:

```bash
docker compose down
docker compose build --no-cache
docker compose up
```

##### 1. サーバーログを確認する

```bash
# 最新100行のログを表示
docker compose logs api --tail=100

# リアルタイムでログを監視
docker compose logs -f api
```

**注目すべきログメッセージ**:
- `Writing: /tmp/blender.crash.txt` - Blenderがクラッシュした証拠
- `ERROR` レベルのメッセージ
- Python のトレースバック

##### 1.1 ファクトリーリセットの無効化を試す

`bpy.ops.wm.read_factory_settings` 実行時にクラッシュする場合があります。必要に応じて
環境変数で無効化してください（既定は無効です）。

```bash
BLENDER_FACTORY_RESET=0 docker compose up --build
```

##### 2. Blenderのクラッシュログを確認する

```bash
docker compose exec api cat /tmp/blender.crash.txt
```

このファイルには、Blenderがクラッシュした際の詳細なスタックトレースが含まれています。

##### 3. ファイルの妥当性を確認する

**破損ファイルのチェック**:
- 別の3Dソフトウェア（Blender GUI、Maya、3ds Maxなど）でファイルを開けるか試す
- ファイルサイズが異常に大きくないか確認: `ls -lh your_file.fbx`
- より単純なモデル（プリミティブ形状など）で試す

**テスト用の単純なモデルを作成**:
1. Blender GUIで新規プロジェクトを作成
2. デフォルトのCube（立方体）のみを残す
3. FBX形式でエクスポート
4. そのファイルで変換をテスト

##### 4. メモリ制限を増やす

大きなモデルや複雑なシーンの場合、メモリ不足でクラッシュする可能性があります。

`docker-compose.yml`を編集:

```yaml
services:
  api:
    deploy:
      resources:
        limits:
          memory: 16G  # デフォルトは8G
        reservations:
          memory: 8G   # デフォルトは4G
```

変更後、コンテナを再起動:

```bash
docker compose down
docker compose up --build
```

##### 5. タイムアウトを延長する

非常に複雑なモデルの場合、変換に時間がかかることがあります。

`docker-compose.yml`に環境変数を追加:

```yaml
services:
  api:
    environment:
      - CONVERSION_TIMEOUT=600  # デフォルトは300秒
```

---

## その他のよくあるエラー

### 400 Bad Request

**原因と対処法**:

| エラーメッセージ | 原因 | 解決方法 |
|----------------|------|---------|
| `No file provided` | ファイルがアップロードされていない | `-F "file=@ファイル名"` を確認 |
| `No file selected` | ファイル名が空 | 正しいファイルパスを指定 |
| `File has no extension` | ファイルに拡張子がない | `.fbx`, `.obj` などの拡張子を付ける |
| `Unsupported input format: xxx` | 非対応の形式 | 対応形式を確認（fbx, obj, gltf, glb, vrm, bvh） |
| `output_format query parameter is required` | output_formatパラメータがない | `?output_format=glb` を追加 |

**例**:
```bash
# ❌ 誤り: ファイルパラメータ名が間違っている
curl -F "model=@assets/model.fbx" ...

# ✅ 正解: パラメータ名は "file"
curl -F "file=@assets/model.fbx" ...
```

---

### 413 Payload Too Large

**原因**: ファイルサイズがデフォルトの上限（50MB）を超えています。

**対処法**:

環境変数でファイルサイズ上限を変更します。

```bash
# 一時的に変更（100MB）
MAX_FILE_SIZE=104857600 docker compose up

# または docker-compose.yml に追加
services:
  api:
    environment:
      - MAX_FILE_SIZE=104857600  # 100MB in bytes
```

**推奨設定**:
- 小〜中規模モデル: 50MB（デフォルト）
- 大規模モデル: 100-200MB
- 非常に大きなモデル: 500MB（メモリも増やす必要があります）

---

### 429 Too Many Requests

**原因**: レート制限に達しました（デフォルト: 60秒間に10リクエスト）。

**対処法**:

1. **待機する**: 60秒待ってから再試行
2. **レート制限を緩和する**: 

```bash
# docker-compose.yml に追加
services:
  api:
    environment:
      - RATE_LIMIT_REQUESTS=50  # デフォルトは10
      - RATE_LIMIT_WINDOW=60    # 秒
```

**注意**: 本番環境ではセキュリティのため、レート制限を緩和しすぎないでください。

---

### 500 Internal Server Error

**原因**: サーバー内部でエラーが発生しました。

**よくある原因**:
1. **BVH出力時にアニメーションデータがない**
   ```json
   {"error": "No animation data found in the scene"}
   ```
   対処: アニメーションを含むFBXファイルを使用する

2. **VRMアドオンが正しく読み込まれていない**
   - ログを確認: `docker compose logs api | grep VRM`
   - コンテナを再起動: `docker compose restart api`

3. **ファイルの破損**
   - 別のツールでファイルを開いて再エクスポート

**ログの確認**:
```bash
docker compose logs api --tail=50 | grep ERROR
```

---

## パフォーマンス問題

### 変換が非常に遅い

**原因と対処法**:

1. **モデルの複雑さ**
   - 頂点数、ポリゴン数を確認
   - LOD（Level of Detail）を使用してモデルを簡略化

2. **キャッシュが機能していない**
   - Redisが正しく接続されているか確認:
   ```bash
   curl http://localhost:5000/health
   # "redis": "connected" を確認
   ```

3. **ログレベルが DEBUG になっている**
   - `LOG_LEVEL=INFO` に変更（docker-compose.yml）

4. **ディスク I/O が遅い**
   - SSDを使用する
   - Dockerのボリュームキャッシュを確認

---

## ログの確認方法

### 基本的なログコマンド

```bash
# 全ログを表示
docker compose logs api

# 最新100行を表示
docker compose logs api --tail=100

# リアルタイムで監視
docker compose logs -f api

# タイムスタンプ付きで表示
docker compose logs -t api

# 特定の時間以降のログ
docker compose logs api --since 2026-01-10T10:00:00

# エラーのみを抽出
docker compose logs api | grep ERROR

# 特定の変換処理を追跡
docker compose logs api | grep "Starting conversion request"
```

### ログレベルの変更

`docker-compose.yml`:

```yaml
services:
  api:
    environment:
      - LOG_LEVEL=DEBUG  # DEBUG, INFO, WARNING, ERROR
      - LOG_FORMAT=json  # json または plain
```

### JSON形式のログを見やすく表示

```bash
docker compose logs api --tail=50 | grep "^api-1" | sed 's/^api-1  | //' | jq '.'
```

---

## Redis接続の問題

### Redisに接続できない

**症状**:
```bash
curl http://localhost:5000/health
# {"redis": "disconnected", ...}
```

**対処法**:

1. **Redisコンテナが起動しているか確認**:
   ```bash
   docker compose ps redis
   ```

2. **Redisコンテナのログを確認**:
   ```bash
   docker compose logs redis
   ```

3. **ネットワーク接続を確認**:
   ```bash
   docker compose exec api ping redis
   ```

4. **Redisを再起動**:
   ```bash
   docker compose restart redis
   ```

---

## Docker関連の問題

### コンテナが起動しない

```bash
# コンテナの状態を確認
docker compose ps

# 詳細なエラーを確認
docker compose up

# イメージを再ビルド
docker compose build --no-cache

# 古いコンテナとボリュームを削除してクリーンスタート
docker compose down -v
docker compose up --build
```

### ディスク容量不足

```bash
# Dockerのディスク使用量を確認
docker system df

# 未使用のイメージ・コンテナ・ボリュームを削除
docker system prune -a

# キャッシュディレクトリを確認（ホスト側）
du -sh /tmp/convert_cache
```

---

## よくある質問 (FAQ)

### Q: Windows で動作しますか？

A: 理論上は可能ですが、現時点では未検証です。Docker Desktop for Windows を使用すれば動作する可能性がありますが、パフォーマンスが低下する場合があります。

### Q: 複数のファイルを一括変換できますか？

A: 現時点ではバッチ処理機能は未実装です。シェルスクリプトでループ処理することで対応可能です：

```bash
for file in assets/*.fbx; do
  filename=$(basename "$file" .fbx)
  curl -F "file=@$file" \
       "http://localhost:5000/convert?output_format=glb" \
       --output "output/${filename}.glb"
  sleep 2  # レート制限を回避
done
```

### Q: 変換結果のキャッシュを削除するには？

A: 以下のコマンドでキャッシュをクリアできます：

```bash
# Redisのキャッシュをクリア
docker compose exec redis redis-cli FLUSHALL

# ディスクキャッシュを削除（コンテナ内）
docker compose exec api rm -rf /tmp/convert_cache/*
```

### Q: HTTPS で使用できますか？

A: 現在はHTTPのみです。本番環境では、Nginx や Caddy などのリバースプロキシを前段に配置してHTTPSを終端することを推奨します。

---

## さらにサポートが必要な場合

1. **GitHubのIssueを確認**: 同様の問題が報告されていないか確認
2. **新しいIssueを作成**: 問題を報告する際は以下の情報を含めてください
   - エラーメッセージ全文
   - 使用したコマンド
   - サーバーログ（`docker compose logs api --tail=100`）
   - 環境情報（OS、Dockerバージョン）
   - 可能であれば問題を再現できる最小限のサンプルファイル

3. **運用ガイドを参照**: [運用ガイド](manual/manual.md) により詳細な情報があります

---

## 関連ドキュメント

- [README.md](../README.md) - プロジェクト概要とセットアップ
- [運用ガイド](manual/manual.md) - 本番運用時の詳細情報
- [内部仕様](internal_spec.md) - システムアーキテクチャと実装詳細
