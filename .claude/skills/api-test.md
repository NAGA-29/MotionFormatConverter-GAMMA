# api-test

Motion Forge Gateway APIの動作をテストするスキル。

## 実行方法

### ヘルスチェック

```bash
curl http://localhost:5000/health
```

### ファイル変換テスト

```bash
# FBXからGLBへ変換
curl -F "file=@model.fbx" "http://localhost:5000/convert?output_format=glb" -o output.glb

# OBJからFBXへ変換
curl -F "file=@model.obj" "http://localhost:5000/convert?output_format=fbx" -o output.fbx

# GLTFからVRMへ変換
curl -F "file=@model.gltf" "http://localhost:5000/convert?output_format=vrm" -o output.vrm
```

### Swaggerドキュメント確認

```bash
# ブラウザで開く
open http://localhost:5000/apidocs

# curlで取得
curl http://localhost:5000/apidocs/
```

## 対応フォーマット

- FBX
- OBJ
- glTF
- GLB
- VRM
- BVH（アニメーションデータが必要）

## 注意事項

- APIサーバーが起動していることを確認（`/build`スキルで起動）
- ファイルサイズ制限: デフォルト50MB
- レート制限: デフォルト60秒間に10リクエスト
- VRM変換にはGLTFアドオンが必要
- BVH変換にはアニメーションデータが必須
