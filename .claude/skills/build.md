# build

Motion Forge GatewayのDockerイメージをビルドして起動するスキル。

## 実行方法

### Docker Composeでビルド・起動

```bash
# ビルド
docker compose build

# コンテナ起動（Flask API + Redis）
docker compose up

# バックグラウンド起動
docker compose up -d
```

### 単一コンテナでビルド・実行

```bash
# イメージビルド
docker build -t blender-converter .

# コンテナ実行
docker run -p 5000:5000 blender-converter
```

## 構成

- Flask API: ポート5000
- Redis: ポート6379（Docker Compose使用時）
- Blender: 5.0.1（ヘッドレスモード）

## 確認方法

```bash
# ヘルスチェック
curl http://localhost:5000/health
```
