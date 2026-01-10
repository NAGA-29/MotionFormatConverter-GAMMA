# マルチアーキテクチャ対応（Compose）

## 目的

開発環境で ARM64 / x86_64 が混在するケースに備え、アーキテクチャ別の Compose 追加ファイルを用意する。

## 対応内容

- `docker-compose.yml` から `platform` 固定を外し、共通のベース定義にする。
- アーキ別の上書きファイルを追加する。
  - `docker-compose.amd64.yml`
  - `docker-compose.arm64.yml`
- Dockerfile は `linuxserver/blender` をベースにし、マルチアーキのイメージを利用する。
- アーキ別の上書きファイルでは `platform` を明示する。

## 使い方

```bash
# x86_64 (amd64)
docker compose -f docker-compose.yml -f docker-compose.amd64.yml up --build

# ARM64
docker compose -f docker-compose.yml -f docker-compose.arm64.yml up --build
```

## 補足

`platform` を指定しない場合は、ホストのアーキテクチャに従って Blender が選ばれる。
