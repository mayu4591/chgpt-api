# ChatGPT Selenium API - 入力処理最適化仕様書

## 概要
本仕様書は、ChatGPT Selenium APIにおける入力処理最適化機能の技術仕様を定義します。

## 問題解決対象
1. **起動時謎な入力問題**: ブラウザ起動時にChatGPTテキストエリアに「Pl」等の不正な文字が入力される
2. **段階的送信問題**: 短いメッセージが複数回に分割され、応答を待たずに連続送信される

## アーキテクチャ設計

### 1. 入力処理フローの最適化
```
メッセージ受信 → 入力フィールド検索 → クリーンアップ処理 → 文字数判定 → 送信戦略選択
```

### 2. 3段階クリーンアップ戦略
- **段階1**: 標準clear() + 適度待機(0.8秒)
- **段階2**: 残存データ検出 + 追加クリーンアップ（必要時のみ）
- **段階3**: キーボードコンビネーション(Ctrl+A, Delete)による確実削除

### 3. 科学的根拠に基づく送信戦略
| メッセージ長 | 戦略 | 根拠 |
|-------------|------|------|
| ≤150文字 | 必ず単一送信 | 平均質問文長+安全マージン |
| 151-4000文字 | 単一送信試行→フォールバック | ChatGPT推奨範囲 |
| >4000文字 | スマート分割送信 | ブラウザ処理限界考慮 |

## データ構造設計

### 1. 設定データ構造
```python
class InputOptimizationSettings:
    input_cleanup_delay: float = 0.8      # クリーンアップ待機時間
    safe_send_limit: int = 150            # 安全送信文字数上限
    init_timeout: int = 15                # 初期化タイムアウト
    residual_cleanup: bool = True         # 残存データクリーンアップ
```

### 2. 処理状態管理
```python
class InputProcessingState:
    cleanup_required: bool = False        # クリーンアップ必要フラグ
    residual_detected: str = ""          # 検出された残存データ
    send_strategy: str = "single"        # 選択された送信戦略
    performance_metrics: dict = {}       # パフォーマンス指標
```

## アルゴリズム設計

### 1. 段階的クリーンアップアルゴリズム
```python
def enhanced_cleanup_algorithm(input_element):
    # 段階1: 標準クリーンアップ
    input_element.clear()
    sleep(settings.input_cleanup_delay)

    # 段階2: 残存データ検出
    residual = get_residual_data(input_element)
    if residual:
        # 段階3: 強制クリーンアップ
        force_clear_with_keyboard(input_element)
        sleep(0.3)

    return residual
```

### 2. 送信戦略選択アルゴリズム
```python
def select_send_strategy(message_length):
    if message_length <= settings.safe_send_limit:
        return "safe_single"
    elif message_length <= 4000:
        return "try_single_fallback_chunk"
    else:
        return "smart_chunking"
```

## インターフェース設計

### 1. 公開API
```python
class ChatGPTDriver:
    def send_message_optimized(self, message: str) -> str:
        """最適化された入力処理でメッセージを送信"""
        pass

    def configure_input_optimization(self, settings: dict) -> bool:
        """入力処理最適化設定の変更"""
        pass

    def get_input_performance_metrics(self) -> dict:
        """入力処理パフォーマンス指標の取得"""
        pass
```

### 2. 設定インターフェース
```python
# .env設定例
INPUT_CLEANUP_DELAY=0.8
SAFE_SEND_LIMIT=150
INIT_TIMEOUT=15
RESIDUAL_CLEANUP=true
```

## エラーハンドリング設計

### 1. 段階的エラー回復
```python
class InputProcessingError(Exception):
    """入力処理エラーの基底クラス"""
    pass

class ResidualDataError(InputProcessingError):
    """残存データ処理エラー"""
    pass

class SendStrategyError(InputProcessingError):
    """送信戦略エラー"""
    pass
```

### 2. 回復戦略
- **レベル1**: 追加クリーンアップで回復試行
- **レベル2**: 別の送信戦略で再試行
- **レベル3**: ページリロード + 再初期化

## ログ出力設計

### 1. 構造化ログ
```python
# 入力処理開始
logger.info("Starting optimized input processing", extra={
    "message_length": len(message),
    "cleanup_delay": settings.input_cleanup_delay,
    "send_strategy": strategy
})

# 残存データ検出
logger.warning("Residual data detected", extra={
    "residual_content": residual_data,
    "cleanup_action": "force_keyboard_clear"
})

# パフォーマンス測定
logger.info("Input processing completed", extra={
    "total_time": elapsed_time,
    "cleanup_time": cleanup_time,
    "send_time": send_time
})
```

## パフォーマンス最適化

### 1. 計測指標
- **処理時間**: メッセージ送信完了までの総時間
- **クリーンアップ時間**: 入力フィールドクリーンアップ所要時間
- **残存データ発生率**: 残存データが検出される頻度
- **送信成功率**: 単一送信戦略の成功率

### 2. 最適化目標
- 平均処理時間: <2秒/メッセージ
- 残存データ発生率: <1%
- 送信成功率: >99%
- 分割送信回避率: >90%（150文字以下）

## セキュリティ設計

### 1. 入力データ検証
```python
def validate_input_message(message: str) -> bool:
    # 最大長制限
    if len(message) > 32000:
        raise ValueError("Message too long")

    # 不正文字検出
    if contains_malicious_content(message):
        raise SecurityError("Malicious content detected")

    return True
```

### 2. 残存データ保護
- 残存データのログ出力時はマスキング処理
- 機密情報の誤送信防止機構

## メンテナンス性設計

### 1. 設定の外部化
- 全ての待機時間、閾値は設定ファイルで管理
- 環境別設定（開発、テスト、本番）サポート

### 2. デバッグサポート
```python
# デバッグモード
DEBUG_INPUT_PROCESSING=true  # 詳細ログ出力
PERFORMANCE_PROFILING=true   # パフォーマンス計測
```

## 信頼性設計

### 1. フェイルセーフ機構
- クリーンアップ失敗時の自動回復
- 送信戦略の段階的フォールバック
- 無限ループ防止（最大リトライ回数制限）

### 2. 状態一貫性保証
- 処理途中での中断からの回復
- トランザクション的な処理保証

## 拡張性設計

### 1. プラグイン機構
```python
class InputProcessingPlugin:
    def pre_cleanup(self, element): pass
    def post_cleanup(self, element): pass
    def custom_send_strategy(self, message): pass
```

### 2. 機械学習対応
- 最適な待機時間の自動学習
- ユーザーパターンに基づく戦略選択

## 互換性設計

### 1. ブラウザ互換性
- Chrome: 完全サポート
- Firefox: 基本サポート
- Edge: 基本サポート

### 2. バージョン互換性
- 既存API完全互換
- 設定の後方互換性保証

## テスト戦略

### 1. テストレベル
- **単体テスト**: 各アルゴリズムの独立テスト
- **統合テスト**: 実ブラウザでの総合動作テスト
- **パフォーマンステスト**: 負荷・応答時間測定
- **回帰テスト**: 既存機能の非破壊性確認

### 2. テストカバレッジ
- コードカバレッジ: >90%
- 機能カバレッジ: 100%（全ての送信戦略パターン）
- エラーパスカバレッジ: >80%

## デプロイメント

### 1. 段階的ロールアウト
1. **開発環境**: 機能テスト完了
2. **ステージング環境**: 負荷テスト完了
3. **本番環境**: カナリアリリース → 全面展開

### 2. 監視指標
- 入力処理成功率
- 平均応答時間
- エラー発生率
- リソース使用量

---

本仕様書は、入力処理最適化機能の完全な技術仕様を定義し、実装、テスト、運用の指針となります。
