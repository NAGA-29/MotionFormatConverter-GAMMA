# CLAUDE.md

Motion Forge Gatewayのコードベースに関するガイダンス。

## プロジェクト概要

Flask + BlenderによるヘッドレスAPIで、3Dモデルファイルのフォーマット変換を提供。
対応フォーマット: FBX, OBJ, glTF, GLB, VRM, BVH

## 言語設定

ユーザーとのコミュニケーションは日本語で行う。

## アーキテクチャ

### リクエストフロー

1. `POST /convert?output_format=<format>` でファイルアップロード
2. レート制限チェック（Redis、IPベース）
3. ファイル検証（形式、サイズ）
4. キャッシュ確認（Redis + `/tmp/convert_cache`）
5. キャッシュミス時: Blender変換実行（タイムアウト制御）
6. 結果をキャッシュして返却

### 主要コンポーネント

- `app/convert.py`: Flaskエントリポイント、ルート定義
- `app/services/conversion_service.py`: 変換ロジック、検証、キャッシング
- `app/blender/io.py`: Blenderインポート/エクスポート操作
- `app/config/settings.py`: 環境変数設定（`@dataclass` + `@lru_cache`）

### 重要な設計パターン

- **依存性注入**: テスタビリティのため、関数はBlender操作を引数で受け取る
- **タイムアウト**: `ThreadPoolExecutor` + `future.result(timeout)` でクロスプラットフォーム対応
- **VRM処理**: `io_scene_gltf2` アドオン有効化 → VRMアドオン登録 → インポート/エクスポート
- **BVH制約**: アニメーションデータ(`bpy.data.actions`)が必須、なければ500エラー

## 環境設定

設定は環境変数から `AppSettings.from_env()` で読み込み。`get_settings()` でキャッシュアクセス。

主要な環境変数:

- `MAX_FILE_SIZE`: 最大アップロードサイズ (デフォルト: 50MB)
- `RATE_LIMIT_REQUESTS` / `RATE_LIMIT_WINDOW`: レート制限設定
- `CONVERSION_TIMEOUT`: 変換タイムアウト (デフォルト: 300秒)
- `CACHE_DURATION`: キャッシュTTL (デフォルト: 3600秒)
- `CONVERSION_CACHE_DIR`: キャッシュディレクトリ (デフォルト: `/tmp/convert_cache`)

詳細は `app/config/settings.py` を参照。

## コーディング規約

### 必須事項

- PyDocで全関数・クラスを文書化
- TDD: 実装前にテスト作成
- DRY, SOLID, KISS, YAGNI原則に従う
- 純粋関数を優先
- マジックナンバー禁止（名前付き定数を使用）

### 禁止事項

- テストなしコミット
- シークレット情報のハードコーディング
- テスト更新なしの動作変更
- Linter警告の無視

### ドキュメント更新
コード変更時は `docs/sow/` の関連ドキュメントを必ず更新。

## テスト方針

- Blender操作(`bpy`)はモック化
- Redis、ファイルI/Oは`unittest.mock`使用
- 成功/エラーパス両方を検証
- タイムアウトシナリオをテスト
- 一時ファイルのクリーンアップを検証

## 既知の制限

- 同期処理のみ（ジョブキューなし）
- BVHエクスポートにはアニメーションデータが必須
- VRMはGLTFアドオン依存
- キャッシュ自動無効化なし（手動クリーンアップが必要）

## ディレクトリ構造

```plaintext
app/
├── blender/          # Blender操作
├── config/           # 設定管理
├── services/         # ビジネスロジック
├── utils/            # ユーティリティ
├── addons/           # VRMアドオン（Linter除外）
├── tests/            # テスト
└── convert.py        # Flaskエントリポイント
```
