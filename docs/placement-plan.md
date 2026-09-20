# taskbarの予約領域とwindowの配置維持

2026-09-20。taskbar対応は承認済み。windowの増減時を含めた配置維持を追加依頼として扱う。
runtimeから利用上限の残量は確認できない。

## 変更方針

- `SPI_GETWORKAREA`を基準に、primary monitorのtaskbarが占める辺を確保する。
  `SHAppBarMessage(ABM_GETTASKBARPOS)`で辺を取得し、taskbarの`GetWindowRect`で
  配置処理と同じDPI座標系の厚みを測る。auto-hideで画面外へ動いていても厚みを予約する。
  既存のwork areaと境界を比較し、二重に差し引かない。取得失敗時は既存のwork areaを使う。
- 前回のsnapshotの`arranged`は配置順に保存されている。この順序とwindow handleを使い、
  同じwindow集合ならそのまま枠を再利用する。
- window数が変わったら、残っているwindowの前回中心位置と新しい枠の中心の距離を使い、
  移動距離の二乗和が最小になる割り当てを求める。新規windowは残りの枠へ割り当てる。
  同点の場合は前回順、初回は読む順とhandleで決定する。
- RustとPython oracleへ同じ変更を入れる。snapshot schema、toggle/restore、
  layoutの枠の形、3周配置、DPI manifest、2 bin構成、summaryの契約を維持する。
- 同じwindowの識別は既存のwindow handleの生存期間内。閉じて開き直したアプリを
  titleや作業内容から識別する仕組みは追加しない。

## 調査根拠

- `src/app.rs`と`align_terminals.pyw`は毎回外枠を`(top, left, width, height)`でsortする。
  snapshotの前回順は割り当てに使っていない。
- `DPI-verification.md`にはauto-hide環境でwork areaがmonitor全体になる実測がある。
- 当初の実行環境では既存の描画probeが0 windowで、sandbox外でも同じだった。
  後述のinput desktopへの接続で解消した。実測とテスト用Windows応答による検証は区別する。
- [ABM_GETTASKBARPOS](https://learn.microsoft.com/en-us/windows/win32/shell/abm-gettaskbarpos)
  はtaskbarの矩形を取得する。
- [GetWindowRect](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getwindowrect)
  はDPI virtualization対象。shellからの矩形と倍率が同じだと仮定しない。

## 検証と配備

1. Python oracleの`main()`を使った再現testを先に実行する。
2. taskbarの四辺、auto-hide、二重控除、取得失敗を検証する。
3. 同じwindowの再整列、復元後の再整列、追加・削除、同点の決定性を検証する。
4. Python fixtureを再生成して`cargo test`でRustと照合する。
5. `cargo build --release`と`tools/deploy.ps1`でrepo rootの2 exeを更新する。
6. 実desktopにアクセスできる場合、描画下端・隙間・混在DPI・restoreを確認する。
   できない場合は実機検証未完了として明示する。

判定: 適正。相場: OSのwork area取得と保存済みIDによる配置維持。
簡素化: snapshotを再利用し、追加設定・新規crate・常駐processを増やさない。

## 検証結果

- 修正前の実際のPython entry pointにテスト用Win32応答を与え、2件のFAILを再現した。
  taskbar予約後の下端1032に対して1080へ配置し、外枠の上辺が1px違う2 windowは
  2回目の整列で左右を入れ替えた。
- 修正後、Pythonの14 testがPASS。追加・削除・復元後の席維持、最小化、1枚のみ、
  taskbar四辺と二重控除を含む。距離最小化は小さい例の全順列探索とも照合した。
- `cargo test --offline`は6 testがPASS。fixtureは既存layout 245件、
  追加の配置維持186件、taskbar予約120件。既存layout fixtureは再生成して差分なし。
- 当初は診断processが別desktopに接続されており、taskbar未取得・Terminal 0枚で
  `UNVERIFIED`だった。継続調査で`OpenInputDesktop`の読み取りに成功し、診断threadだけを
  `SetThreadDesktop`で接続すると6枚を取得できた。画面のdesktop切替は行っていない。
- 子processは診断threadの接続先を自動継承しなかったため、実機試験用の起動では
  `CreateProcessW`の`STARTUPINFO.lpDesktop`を明示した。本番exeの実装・manifestは変更していない。
- 実機ではtaskbar全厚48、表示時の矩形`(0, 1032, 1920, 48)`を測定した。
  Rust/Pythonとも6 of 6で整列し、全描画下端が1032以下、隣接windowの隙間は0pxだった。
- 再整列3回でwindowごとの実測矩形とsnapshotの`previous`を維持した。
  Rust/Pythonのstdoutはbyte一致、描画と外枠のgeometryも一致。
  両方向のsnapshot復元は6 of 6。復元後の再整列も同じ席へ戻った。
- 1枚の一時非表示・再表示で6枚→5枚→6枚を実機検証し、それぞれ再整列しても位置を維持した。
  windowを閉じたりsessionの内容を変更したりしていない。
- primary 192 DPIとsecondary 144 DPI間を移動してから整列し、6 of 6、隙間0pxを確認した。
  手動移動相当のnudge後の`--restore`は、何も動かさず拒否した。
- 別アプリを前面のz-orderに置いて3回整列し、毎回全Terminalがその前へ出て、TOPMOSTは残らなかった。
  Windowsが別アプリへのfocus移動を拒否したため、keyboard focus強制切替は検証条件に含めていない。
  windowed exeでもconsole exeとstdout・geometryが一致した。
- 検証用snapshotは`target/`配下へ隔離した。本番の復元fileは変更なし。
  終了時には6枚とも検証前の位置へ完全一致で戻し、taskbar表示試験で動かしたmouseも戻した。
- 読み取りprobeへ`--input-desktop`を追加し、隔離されたdesktopからも再測定できるようにした。
- `tools/deploy.ps1`でrelease buildとrepo rootの2 exe更新を完了した。
  配備先とbuild成果物のSHA-256は一致。旧exeは`target/placement-backup/`へ保存した。
  2 binの起動・stdout capture・CRLF・help出力のbyte一致を確認した。
  PowerShellのscript実行制限はこの配備processだけで解除し、永続設定は変更していない。
- `cargo fmt --check`と`git diff --check`もPASS。
- 2026-09-20、ユーザーによる実機確認も完了し、closeoutとcommit/pushの依頼を受けた。
