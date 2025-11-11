import hashlib
import json

def review_hash(source: str | None, product_url: str | None,
                body: str | None, review_date: str | None) -> str:
    """
    리뷰 중복 방지용 해시 (채널+상품URL+본문+작성일 기준)
    """
    payload = json.dumps([
        source or "", product_url or "", body or "", review_date or ""
    ], ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()