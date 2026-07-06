class YakError(Exception):
    """ユーザーに表示するエラー。CLI はこれを捕捉して stderr + exit 1 にする。"""
