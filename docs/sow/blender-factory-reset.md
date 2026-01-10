# Blender ファクトリーリセット制御

## 目的

Blender の `read_factory_settings` 実行時にクラッシュする環境があるため、
環境変数でファクトリーリセットの実行可否を制御できるようにする。

## 対応内容

- 環境変数 `BLENDER_FACTORY_RESET` を導入し、既定では無効化する。
- `clear_scene` / `initialize_blender` / `import_file` / 例外フックから
  ファクトリーリセットを呼ぶ際は環境変数を確認する。

## 使い方

```bash
# ファクトリーリセットを無効化（既定）
BLENDER_FACTORY_RESET=0

# 有効化する場合
BLENDER_FACTORY_RESET=1
```
