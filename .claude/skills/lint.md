# lint

Ruffリンターを使用してコード品質をチェックするスキル。

## 実行方法

### リンティング実行

```bash
PYTHONPATH=./app ruff check .
```

### 自動修正

```bash
PYTHONPATH=./app ruff check --fix .
```

## Ruff設定（pyproject.toml）

- 行長: 120文字
- 除外: `app/addons` ディレクトリ
- ルール:
  - E: pycodestyle errors
  - F: pyflakes
  - B: flake8-bugbear
  - I: isort
  - UP: pyupgrade

## 注意事項

- Linter警告を無視しない（コーディング規約の禁止事項）
- 自動修正後は変更内容を必ず確認
