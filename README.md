# Motion Forge Gateway

## プロジェクト概要
Blender を利用して 3D モデルを別形式へ変換する Flask ベースの API です。
Docker 環境で Blender を実行し、アップロードされたモデルを指定のフォーマットに変換して返却します。

## セットアップ方法

### Docker ビルドと起動
```bash
# イメージをビルド
docker compose build

# コンテナを起動
docker compose up
```
起動後は `http://localhost:5000/` で API が利用できます。

### 単体での Docker 実行例
```bash
docker build -t blender-converter .
docker run -p 5000:5000 blender-converter
```

## 設定と主要な環境変数
`app.config.settings.AppSettings` により環境変数から設定値を読み込みます。
`get_settings()` はプロセス内で一度だけ評価され、型付きで参照できます。

| 変数 | 説明 | デフォルト |
|------|------|------------|
| `REDIS_HOST` | Redis サーバーのホスト名 | `redis` |
| `REDIS_PORT` | Redis のポート番号 | `6379` |
| `MAX_FILE_SIZE` | アップロード可能な最大ファイルサイズ (バイト) | `52428800` |
| `RATE_LIMIT_REQUESTS` | 一定期間内に許可されるリクエスト数 | `10` |
| `RATE_LIMIT_WINDOW` | レートリミット対象の時間窓(秒) | `60` |
| `CONVERSION_TIMEOUT` | 変換処理のタイムアウト(秒) | `300` |
| `CACHE_DURATION` | 変換結果をキャッシュする時間(秒) | `3600` |
| `APP_ENV` | アプリケーションの環境種別 (`local` など) | `development` |
| `LOG_LEVEL` | ログ出力レベル | `INFO` |
| `LOG_FORMAT` | `plain` または `json` 形式のログフォーマット | `plain` |
| `LOG_FILE` | ログを出力するファイルパス(任意) | - |

`APP_ENV` が `local` の場合、`is_local_env()` ヘルパーは `True` を返します。
ローカル環境向けの条件分岐に利用できます。

### ログ出力設定
`LOG_LEVEL` と `LOG_FORMAT` を組み合わせることで、コンソールやファイルへ出力
するログの内容を調整できます。`LOG_FILE` を指定すると自動的にローテーションさ
れるファイルハンドラーが有効になります。

例:
```bash
LOG_LEVEL=DEBUG LOG_FORMAT=json LOG_FILE=/var/log/blender-api.log \
docker compose up
```

## 変換エンドポイントと使用例

### POST /convert

`POST` メソッドでファイルを送信し、変換後のファイルがレスポンスとして返されます。

**クエリパラメータ**

| パラメータ | 型 | 説明 | 必須 |
|---|---|---|---|
| `output_format` | string | 出力したいファイル形式 (例: `glb`, `fbx`, `obj`) | はい |

**リクエストボディ**

- `multipart/form-data`
- `file`: 変換したい 3D モデルファイル

**使用例**

`model.fbx` を `glb` 形式に変換する場合:

```bash
curl -F "file=@model.fbx" \
     "http://localhost:5000/convert?output_format=glb" \
     --output model.glb
```

## クイックスタート（開発者向け）
- 依存: Docker / Docker Compose、ポート `5000`、ローカルのディスク空き（キャッシュ用 `/tmp/convert_cache` 既定）
- 起動: `docker compose up --build`
- 動作確認: `curl -F "file=@example.fbx" "http://localhost:5000/convert?output_format=glb" -o example.glb`
- ドキュメント: `http://localhost:5000/apidocs`（Swagger UI）
- ヘルスチェック: `GET /health`（Redis疎通を含む）

## API 詳細（実装サマリ）
- エンドポイント: `POST /convert`
  - 入力: `multipart/form-data` の `file`。入力形式は拡張子で判定。
  - クエリ: `output_format`（`fbx|obj|gltf|glb|vrm|bvh`）
  - レスポンス: 変換済みファイル（Content-Type は出力形式に対応）
- レート制限: Redis ベース、`RATE_LIMIT_REQUESTS` 回 / `RATE_LIMIT_WINDOW` 秒（IPキー）
- キャッシュ: 入力ハッシュ + 出力形式をキーに Redis へ永続キャッシュパスを保存。変換結果は `/tmp/convert_cache`（環境変数 `CONVERSION_CACHE_DIR` で変更可）へコピーし再利用。
- 対応フォーマット補足:
  - BVH 出力はシーンにアニメーション（`bpy.data.actions`）が必要。無い場合は 500 を返す。
  - VRM は GLTF アドオンを先に有効化して VRM アドオンを登録してから処理。

## 運用ノート
- 依存サービス: Redis が必須（レート制限とキャッシュ）。未接続時はレート制限をスキップするが性能劣化に注意。
- タイムアウト: `CONVERSION_TIMEOUT` 秒で変換処理を打ち切り（スレッドタイムアウト方式、クロスプラットフォーム）。
- ログ: `LOG_LEVEL` / `LOG_FORMAT`（plain/json）/ `LOG_FILE` で制御。`LOG_FILE` を指定するとローテーション付きファイル出力。
- 永続キャッシュ: `/tmp/convert_cache` に変換結果をコピーしてパスを Redis に保存。ディスク容量とクリーンアップは運用で管理してください。
- 拡張: 環境変数は表の通り。`APP_ENV=local` でローカル向け挙動に切り替わり、テスト時はモックが利用されます。

## 制約 / FAQ
- Blender 依存: 変換は Blender のアドオン/オペレーターを使用。Blenderの対応フォーマット以外は非対応。
- 同期実行: `/convert` は同期で処理するため大きなファイルではリクエスト待ちが発生。ジョブキュー化は未実装。
- Windows: SIGALRM 非使用だが、Blender バイナリ依存のため Windows 動作は未検証。
- BVH の注意: アニメーションが無いとエクスポート失敗。VRM はアドオン必須。
- キャッシュ無効化: 今は未実装。手動で `/tmp/convert_cache` と Redis キー `conversion:*` を削除してください。

詳細な手順や[運用ガイド](docs/manual/manual.md)を参照してください。

## Swagger UI
flasgger により Swagger ドキュメントが自動生成されます。
コンテナ起動後は `http://localhost:5000/apidocs` で
API ドキュメントを閲覧できます。

## テストの実行方法
Blender 付属の `bpy` モジュールが必要です。Docker 環境上で次のコマンドを実行します。
```bash
PYTHONPATH=./app python -m unittest discover app/tests
```

ネットワーク制限で依存パッケージ（Flask 等）が取得できない環境では、一部テストが
自動的にスキップされます。

### Lint
`ruff` を導入しています。
```bash
PYTHONPATH=./app ruff check .
```

## 各ファイル形式の仕様リンク

以下の資料を参照することで、フォーマットの詳細構造を確認できます。
利用可能なパーサーがある場合は併せて記載します。

- **FBX**  
  - フォーマット: [Autodesk FBX SDK Documentation](https://help.autodesk.com/view/FBX/2019/ENU/)
  - パーサー: [FBX SDK](https://www.autodesk.com/developer-network/platform-technologies/fbx-sdk-2020-0)

- **OBJ**  
  - フォーマット: [Wavefront OBJ Format](https://en.wikipedia.org/wiki/Wavefront_.obj_file)
  - パーサー: [PyWavefront](https://github.com/pywavefront/PyWavefront)

- **glTF/GLB**  
  - フォーマット: [Khronos glTF 2.0 Specification](https://github.com/KhronosGroup/glTF)
  - パーサー: [pygltflib](https://github.com/kcoley/pygltflib)

- **VRM**  
  - フォーマット: [VRM Specification](https://vrm.dev/en/docs/vrm/vrm_spec/)
  - パーサー: [Blender VRM Addon](app/addons/vrm_addon.py)

- **BVH**  
  - フォーマット: [BVH File Format](https://research.cs.wisc.edu/graphics/Courses/cs-838-1999/Jeff/BVH.html)
  - パーサー: [bvh-python]
  - 資料: [東京都立大学 Mukai Laboratory の資料](https://mukai-lab.org/content/MotionCaptureDataFile.pdf)
---
## TODO リスト (将来実装予定)

### パフォーマンスの最適化
- [ ] 大きなファイルを処理する際のメモリ使用量監視機能
- [ ] ファイルサイズに基づく可変キャッシュ有効期限の設定
- [ ] 長時間の変換処理を非同期で実行する機能
- [ ] 複数のBlenderインスタンスを使用した並列処理
- [ ] メモリリークの検出と防止メカニズム

### エラーハンドリング
- [ ] より詳細なエラーメッセージとユーザーフレンドリーな表示
- [ ] 変換失敗時の自動リトライメカニズム
- [ ] 例外タイプに基づいた専用エラー処理
- [ ] エラーレポート自動生成・通知システム

### セキュリティ
- [ ] 入力ファイルの詳細な検証と潜在的な悪意のあるコンテンツの検出
- [ ] APIキーに基づくアクセス制御とレート制限
- [ ] 出力ファイルのサニタイズと整合性チェック
- [ ] 脆弱性スキャンの定期実行

### コード構造
- [ ] 機能ごとの個別モジュール分割
  - [ ] Blender操作用モジュール
  - [ ] ファイル処理用モジュール
  - [ ] APIルート定義
  - [ ] キャッシュ管理モジュール
- [ ] 設定の外部ファイル化
- [ ] 依存性注入パターンの導入
- [ ] ユニットテストと統合テストの追加

### その他の機能
- [x] JSON形式の構造化ログ出力
- [ ] 拡張されたヘルスチェックエンドポイント
- [x] Swagger/OpenAPIによるAPI自動ドキュメント生成
- [ ] 変換プロセスの進捗モニタリング機能
- [ ] メール通知機能
- [ ] バッチ処理機能
- [ ] テクスチャとマテリアルのより高度な処理
- [ ] 異なる変換オプションのサポート
- [ ] ユーザーごとのカスタム設定保存
- [ ] 変換履歴と統計情報の提供
