# パチスロ収支管理

パチスロの収支を記録するスマホ向け Web アプリ（React + TypeScript + Vite）。

## 機能

- カレンダーで日付をタップすると、その日の入力画面へ遷移
- 1日に複数回の記録が可能（ホールをはしごした日、複数台打った日など）
- 入力項目：ホール名・機種名（入力済みの候補からプルダウン選択可）、投資額、回収額、開始時間・終了時間（稼働時間は自動計算）
- カレンダー上部に年間トータル収支と月間トータル収支を並べて表示
- カレンダーの各日に、その日の収支を表示
- データは端末の localStorage に保存

## 開発

```bash
npm install
npm run dev
```

## ビルド

```bash
npm run build
```

## スマホへのインストール（PWA）

このアプリは PWA（Progressive Web App）対応済みです。GitHub Pages にデプロイ後、スマホのブラウザでアクセスし「ホーム画面に追加」するとアプリのように起動できます。

### 1. GitHub Pages を有効化（初回のみ）

このリポジトリの Settings → Pages → Build and deployment → Source で **GitHub Actions** を選択してください。

### 2. デプロイ

`main` ブランチに `pachislot-tracker/` の変更が push されると、`.github/workflows/deploy-pachislot-tracker.yml` が自動でビルドして GitHub Pages に公開します（Actions タブから手動実行も可能）。

公開URL: `https://<GitHubユーザー名>.github.io/smart_apps/`

### 3. ホーム画面に追加

- **iPhone (Safari)**: 上記URLを開く → 共有ボタン → 「ホーム画面に追加」
- **Android (Chrome)**: 上記URLを開く → メニュー → 「アプリをインストール」または「ホーム画面に追加」

## パチスロ風サウンド生成（私用素材）

`scripts/generate_sounds.py` は、実機音源を複製するのではなく NumPy の波形合成
と FluidSynth(+ General MIDI サウンドフォント) で一からパチスロ風の効果音・
BGM を作り、`public/sounds/generated/` に MP3 として書き出すスクリプトです。
詳細は [`public/sounds/generated/README.md`](public/sounds/generated/README.md) を参照してください。

```bash
pip install numpy
sudo apt-get install ffmpeg fluidsynth fluid-soundfont-gm musescore-general-soundfont
python3 scripts/generate_sounds.py
```
