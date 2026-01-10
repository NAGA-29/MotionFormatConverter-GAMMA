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

### Blender イメージの差し替え
Blender は `linuxserver/blender` をベースにしています。必要に応じてビルド引数で変更できます。  
[linuxserver/blender](https://hub.docker.com/r/linuxserver/blender)

```bash
docker build --build-arg BLENDER_IMAGE=linuxserver/blender:latest -t blender-converter .
```

### アーキテクチャ別の起動
ARM64 / x86_64 混在環境向けに、Compose の上書きファイルを用意しています。

```bash
# x86_64 (amd64) で起動
docker compose -f docker-compose.yml -f docker-compose.amd64.yml up --build

# ARM64 で起動
docker compose -f docker-compose.yml -f docker-compose.arm64.yml up --build
```

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
| `BLENDER_FACTORY_RESET` | ファクトリーリセットを有効化する (`1/true/yes/on`) | `0` |

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

## 対応ファイル形式

このAPIは以下の3Dファイル形式に対応しています:

| 形式 | 拡張子 | 入力 | 出力 | 説明 |
|------|--------|------|------|------|
| **FBX** | `.fbx` | ✅ | ✅ | Autodesk FBX形式。アニメーション、マテリアル、リグを含む総合的な3Dフォーマット |
| **OBJ** | `.obj` | ✅ | ✅ | Wavefront OBJ形式。シンプルなジオメトリとマテリアルの定義 |
| **glTF** | `.gltf` | ✅ | ✅ | glTF 2.0 JSON形式。Web向けの効率的な3D転送フォーマット |
| **GLB** | `.glb` | ✅ | ✅ | glTF 2.0 Binary形式。glTFの単一バイナリ版 |
| **VRM** | `.vrm` | ✅ | ✅ | VRM形式。人型アバター向けのglTF拡張フォーマット |
| **BVH** | `.bvh` | ✅ | ✅ | BioVision Hierarchy形式。モーションキャプチャデータ用 |

### フォーマット別の注意事項

- **BVH出力**: シーン内にアニメーションデータ(`bpy.data.actions`)が必要です。アニメーションがない場合はエラー(500)が返されます。
- **VRM**: glTFアドオンとVRMアドオンの両方が有効化されている必要があります。
- **入力形式の自動判定**: アップロードされたファイルの拡張子から入力形式を自動判定します。

## 変換エンドポイントと使用例

### POST /convert

`POST` メソッドでファイルを送信し、変換後のファイルがレスポンスとして返されます。

**クエリパラメータ**

| パラメータ | 型 | 説明 | 必須 |
|---|---|---|---|
| `output_format` | string | 出力形式 (`fbx`, `obj`, `gltf`, `glb`, `vrm`, `bvh` のいずれか) | はい |

**リクエストボディ**

- `multipart/form-data`
- `file`: 変換したい 3D モデルファイル (対応形式: fbx, obj, gltf, glb, vrm, bvh)

**使用例**

`model.fbx` を `glb` 形式に変換する場合:

```bash
curl -F "file=@model.fbx" \
     "http://localhost:5000/convert?output_format=glb" \
     --output model.glb
```

その他の変換例:

```bash
# OBJ → FBX
curl -F "file=@model.obj" \
     "http://localhost:5000/convert?output_format=fbx" \
     --output model.fbx

# GLB → VRM (アバター変換)
curl -F "file=@avatar.glb" \
     "http://localhost:5000/convert?output_format=vrm" \
     --output avatar.vrm

# FBX → BVH (アニメーションデータが必要)
curl -F "file=@animation.fbx" \
     "http://localhost:5000/convert?output_format=bvh" \
     --output animation.bvh
```

## クイックスタート（開発者向け）
- 依存: Docker / Docker Compose、ポート `5000`、ローカルのディスク空き（キャッシュ用 `/tmp/convert_cache` 既定）
- 起動: `docker compose up --build`
- 動作確認: `curl -F "file=assets/@example.fbx" "http://localhost:5000/convert?output_format=glb" -o example.glb`
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

## トラブルシューティング

APIの使用中に問題が発生した場合は、[トラブルシューティングガイド](docs/troubleshooting.md)を参照してください。

よくある問題:
- [curl エラー26: ファイルパスの指定ミス](docs/troubleshooting.md#エラー26-failed-to-openread-local-data-from-fileapplication)
- [curl エラー52: サーバークラッシュ](docs/troubleshooting.md#エラー52-empty-reply-from-server)
- [400/413/429/500エラー](docs/troubleshooting.md#その他のよくあるエラー)
- [パフォーマンス問題](docs/troubleshooting.md#パフォーマンス問題)

## 制約 / FAQ
- Blender 依存: 変換は Blender のアドオン/オペレーターを使用。Blenderの対応フォーマット以外は非対応。
- 同期実行: `/convert` は同期で処理するため大きなファイルではリクエスト待ちが発生。ジョブキュー化は未実装。
- Windows: SIGALRM 非使用だが、Blender バイナリ依存のため Windows 動作は未検証。
- BVH の注意: アニメーションが無いとエクスポート失敗。VRM はアドオン必須。
- キャッシュ無効化: 今は未実装。手動で `/tmp/convert_cache` と Redis キー `conversion:*` を削除してください。
- Blenderのクラッシュ: 複雑または破損したFBXファイルでBlenderがクラッシュする場合があります。その場合は、より単純なモデルを使用するか、別のツールで事前に修復してください。

詳細な手順や[運用ガイド](docs/manual/manual.md)を参照してください。

## Swagger UI
flasgger により Swagger ドキュメントが自動生成されます。
コンテナ起動後は `http://localhost:5000/apidocs` で
API ドキュメントを閲覧できます。

## テストの実行方法
Blender 付属の `bpy` モジュールが必要です。Docker 環境上で次のコマンドを実行します。
```bash
docker compose exec api bash -lc '
APP_ROOT=/workspace/app
BLENDER_PYTHON="$(blender --background --python-expr "import sys; print(sys.executable)" | awk "/\\/python/ {print; exit}")"
PYTHONPATH="$APP_ROOT" "$BLENDER_PYTHON" -m unittest discover -s "$APP_ROOT/tests" -t "$APP_ROOT"
'
```

ネットワーク制限で依存パッケージ（Flask 等）が取得できない環境では、一部テストが
自動的にスキップされます。

### Lint
`ruff` を導入しています。
```bash
docker compose exec api bash -lc '
APP_ROOT=/workspace/app
PYTHONPATH="$APP_ROOT" ruff check "$APP_ROOT"
'
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

- **OpenUSD**  
  - フォーマット: [OpenUSD Documentation](https://openusd.org/)
  - パーサー: [usd-python](https://github.com/PixarAnimationStudios/USD)

---

## 開発ヒント
- [Blender Python API ドキュメント](https://docs.blender.org/api/current/index.html)
- [Blender の python向けライブラリ `bpy` リスト](https://download.blender.org/pypi/bpy/)

## 開発ロードマップ

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
