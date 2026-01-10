# test

Motion Forge Gatewayのテストを実行するスキル。

## 実行方法

### 全テスト実行

```bash
PYTHONPATH=./app python -m unittest discover app/tests
```

### 特定のテストファイルを実行

```bash
PYTHONPATH=./app python -m unittest app/tests/test_convert.py
```

### 特定のテストメソッドを実行

```bash
PYTHONPATH=./app python -m unittest app/tests/test_convert.TestConversion.test_specific_method
```

## 要件

- Blenderの`bpy`モジュールが必要
- Dockerコンテナ内で実行することを推奨

## 注意事項

- テストはモックを使用してBlender操作をシミュレート
- Redis、ファイルI/Oも`unittest.mock`でモック化
- タイムアウトシナリオと一時ファイルクリーンアップを検証
