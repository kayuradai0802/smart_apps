# 生成サウンド (パチスロ風 効果音・BGM)

`scripts/generate_sounds.py` によって NumPy の波形合成で一から作られた
オリジナルの効果音・BGM です。実機のサウンドを録音・複製したものでは
なく、パチスロらしい雰囲気を再現するために合成したフリー素材（私用目的）
です。

## 効果音

| ファイル | 内容 |
| --- | --- |
| `coin_insert.mp3` | メダル投入音（1枚） |
| `coin_payout.mp3` | メダル払い出し音（連打） |
| `reel_spin_loop.mp3` | リール回転音（ループ用） |
| `reel_stop.mp3` | リール停止音 |
| `lever_click.mp3` | スタートレバー操作音 |
| `button_beep.mp3` | ボタン押下ビープ |
| `bonus_chance_jingle.mp3` | チャンス目/ボーナス告知風ジングル |
| `big_win_fanfare.mp3` | 大当り/ビッグボーナス風ファンファーレ |
| `reg_win_fanfare.mp3` | 小役/レギュラーボーナス風ファンファーレ |

## BGM（ループ）

| ファイル | 内容 |
| --- | --- |
| `bgm_normal_loop.mp3` | 通常時 BGM ループ（118 BPM） |
| `bgm_bonus_loop.mp3` | ボーナス中 BGM ループ（150 BPM） |

## 再生成

```bash
pip install numpy
sudo apt-get install ffmpeg   # ffmpeg が未インストールの場合
python3 scripts/generate_sounds.py
```

`scripts/generate_sounds.py` 内のパラメータ（音階・BPM・エンベロープなど）
を変更することで、音色やフレーズを自由にアレンジできます。
