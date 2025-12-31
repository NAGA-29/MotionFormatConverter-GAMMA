# Blender Converter 開発/運用マニュアル

本プロジェクトで利用する API と周辺設定の詳細ガイドです。README のサマリを補足し、開発者がすぐに着手・運用できるようにまとめています。

## 1. クイックスタート手順
- 前提: Docker / Docker Compose インストール済み、ポート `5000` 利用可、Redis は Compose 内で起動。
- ビルド & 起動:
  ```bash
  docker compose up --build
  ```
- 動作確認:
  ```bash
  curl -F "file=@example.fbx" "http://localhost:5000/convert?output_format=glb" -o example.glb
  ```
- ドキュメント: `http://localhost:5000/apidocs`
- ヘルスチェック: `GET /health`（Redis 疎通を含む）

## 2. API 詳細
- エンドポイント: `POST /convert`
  - 入力: `multipart/form-data` の `file`。拡張子で入力形式を自動判定。
  - クエリ: `output_format`（`fbx|obj|gltf|glb|vrm|bvh`）
  - 出力: 変換済みファイル（Content-Type は出力形式に対応）
- レート制限: Redis の ZSET で IP ベース、`RATE_LIMIT_REQUESTS` 回 / `RATE_LIMIT_WINDOW` 秒。
- キャッシュ: 入力ハッシュ + 出力形式をキーに Redis へキャッシュパスを保存。ファイルは `/tmp/convert_cache`（`CONVERSION_CACHE_DIR` 変更可）へコピーして再利用。
- 制約/挙動:
  - BVH 出力はシーンにアニメーション（`bpy.data.actions`）が必須。無い場合は 500 を返す。
  - VRM は GLTF アドオンを有効化後に VRM アドオンを登録して処理。
  - タイムアウト: `CONVERSION_TIMEOUT` 秒で変換スレッドを打ち切り（クロスプラットフォーム）。

## 3. 環境変数と推奨値
| 変数 | 説明 | デフォルト | 備考 |
| --- | --- | --- | --- |
| `REDIS_HOST` | Redis ホスト | `redis` | Compose のサービス名 |
| `REDIS_PORT` | Redis ポート | `6379` | - |
| `MAX_FILE_SIZE` | アップロード上限 (byte) | `52428800` | 50MB。大きい場合はリバースプロキシ設定も考慮 |
| `RATE_LIMIT_REQUESTS` | レート上限 | `10` | - |
| `RATE_LIMIT_WINDOW` | レート窓 (秒) | `60` | - |
| `CONVERSION_TIMEOUT` | 変換タイムアウト (秒) | `300` | 大きな FBX/VRM で調整 |
| `CACHE_DURATION` | キャッシュTTL (秒) | `3600` | - |
| `CONVERSION_CACHE_DIR` | 変換キャッシュ保存先 | `/tmp/convert_cache` | 永続ボリューム推奨 |
| `APP_ENV` | 環境種別 | `development` | `local` でローカル挙動 |
| `LOG_LEVEL` | ログレベル | `INFO` | - |
| `LOG_FORMAT` | ログ形式 | `plain` | `json` も可 |
| `LOG_FILE` | ログ出力ファイル | - | 指定時はローテーション付 |

## 4. 運用ノート
- 依存サービス: Redis が必須。未接続時はレート制限がスキップされるため注意。
- キャッシュ運用: 変換結果は `CONVERSION_CACHE_DIR` にコピーし、パスを Redis に保存。容量監視と定期クリーンアップを運用で行う。
- 非同期/負荷対策: 現状は同期 API。大きな変換が多い場合はジョブキューや複数ワーカーの検討を推奨。
- ログ/監視: `LOG_FORMAT=json` で集約基盤に送りやすくなる。`/health` は Redis の疎通のみを確認。
- Windows: SIGALRM 非使用だが、Blender バイナリの対応は未検証。Linux コンテナでの運用を推奨。

## 5. 制約とFAQ
- Q. BVHが出力できない  
  A. シーンにアクションが無いとエクスポート失敗します。入力にアニメーションを含めるか、リターゲット済みのアクションを用意してください。
- Q. キャッシュを無効化したい  
  A. 未実装です。`CONVERSION_CACHE_DIR` と Redis の `conversion:*` キーを手動で削除してください。
- Q. レート制限を調整したい  
  A. `RATE_LIMIT_REQUESTS` と `RATE_LIMIT_WINDOW` を設定してください。プロキシ側での制限追加も推奨です。
- Q. どのフォーマットがサポートされる？  
  A. `fbx, obj, gltf, glb, vrm, bvh`。Blenderの対応範囲に準拠します。

## 6. 開発時のTips
- テスト: Docker 内で `PYTHONPATH=./app python -m unittest discover app/tests`。Flask/Redis がない環境では一部スキップ。
- Lint: `PYTHONPATH=./app ruff check .`
- コード構造: API (`app/convert.py`)、変換サービス (`app/services/`)、Blender I/O (`app/blender/`) に分離済み。モックはテストで定義済み。
- VRM/BVH の動作確認は Blender 付きコンテナで行うこと。
