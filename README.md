🛍️ Coupang Review Pipeline · Crawling → Transform → Analysis
쿠팡 상품 리뷰를 수집·정제·분석하는 경량 데이터 파이프라인 MVP.

📈 유즈케이스
	•	신제품/경쟁상품 리뷰 감성 추세 비교
	•	상위 불만/칭찬 키워드로 개선 포인트 도출
	•	캠페인 전후 후기 품질 변화 모니터링

✨ 무엇을 하나요?
	•	Crawling: 상품 식별자/URL을 입력하면 리뷰 목록을 페이징으로 수집
	•	Transform: 이모지·URL·공백·HTML 제거, 간단 정규화 및 통계치 계산
	•	Analysis: 리뷰 감성(긍/부/중립) 집계, 키워드 빈도/공동출현 기반 토픽 힌트

  🔌 확장 포인트
	•	Crawler 연결: crawling_api/service.py에서 실제 HTTP 요청/파싱 로직 연결
(합법 범위의 공개 페이지만 대상, 과도한 트래픽/빈도 제한 준수)
	•	Storage: DB_URL로 RDB에 저장(SQLAlchemy); 인덱스는 (product_id, created_at) 권장
	•	분석 고도화: 형태소 분석(koNLPy/kiwi), 감성 사전/ML/LLM, 토픽 모델링/요약
	•	오케스트레이션: Airflow/Prefect 배치 파이프라인 및 재시도/로깅/모니터링

⚖️ 합법·윤리 가이드 (중요)
	•	웹사이트 이용약관·robots.txt를 준수하고, 과도한 요청을 피하세요.
	•	개인식별정보(PII) 저장 금지, 리뷰 본문은 연구·통계 목적 등 합법 범위에서만 사용.
	•	인증이 필요한 영역 접근, 보안·반(反)봇 체계 우회, 취약점 악용 등 금지.
	•	필요 시 공식 API/데이터 제공 채널 사용을 우선 고려하세요.
