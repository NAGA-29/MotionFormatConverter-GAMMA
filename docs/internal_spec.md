# Blender Converter 内部仕様（抜粋）

## 設定レイヤー
- `app.config.settings.AppSettings` が環境変数から設定値を収集する。
- `get_settings()` は LRU キャッシュで 1 プロセス 1 インスタンスを返す。
- `LOG_FORMAT` は `plain` / `json` のみを受け付け、それ以外は `plain` にフォールバック。
- 主要キー: `REDIS_HOST`, `REDIS_PORT`, `MAX_FILE_SIZE`, `RATE_LIMIT_REQUESTS`, `RATE_LIMIT_WINDOW`,
  `CONVERSION_TIMEOUT`, `CACHE_DURATION`, `APP_ENV`, `LOG_LEVEL`, `LOG_FORMAT`, `LOG_FILE`。

## 依存モジュールの扱い
- CI や制限環境で Flask/Redis が存在しない場合、`app/tests/test_convert.py` の多くのテストは
  スキップされる。Flask が利用できる環境ではこれらのテストが有効化される。
- `bpy` / `redis` はテスト時にモック登録しており、実機での変換は Docker イメージ内の
  正規モジュールを想定する。

## ロギング
- 既存の `AppLogger` を継続利用。`LOG_LEVEL` / `LOG_FORMAT` / `LOG_FILE` は
  `AppSettings` を通じて設定可能。

## コードスタイル
- `ruff` による lint を追加。設定は `pyproject.toml` で管理し、`app/addons` は除外。
