# kis/ — 한국투자증권 KIS Open API 연결 (6편이 쓰는 부분만)

모든 모듈은 설정을 `config.load("paper"|"real")` 로 받은 `KisConfig` 하나로 동작한다(기본 모의). 비밀값은 출력하지 않는다.
`real` 은 이 공개판에서 **시세 조회에만** 쓴다. 주문은 모의 설정이 아니면 `order.check` 가 거절한다 — 실전 주문 경로는 없다.

출처: 설정 파일 위치·이름(`~/KIS/config/kis_devlp.yaml`)과 키 이름(`my_app`·`paper_app`·`prod`·`vps`…), TR 이름·요청/응답 필드 이름은
한국투자증권 공식 예제 저장소 github.com/koreainvestment/open-trading-api 를 따랐다. 이 폴더의 코드는 그 형식·이름에 맞춰
이 프로그램용으로 쓴 것이며, 공식 예제 코드를 그대로 옮겨 온 부분은 없다. 그 저장소에는 라이선스 표시가 없고(2026-11-19 확인), README 에 "참고용으로 제공" · 샘플 코드로 만든 프로그램의 손해는 책임지지 않는다는 안내가 있다.

## 파일

| 파일 | 주요 이름 | 하는 일 |
|---|---|---|
| `config.py` | `load(mode)`, `status()`, `mask_account()`, `KisConfig`(`summary()`·`is_paper`·`product_name`·`token_file`), `CONFIG_DIR` | 설정 파일 읽기(기본 `~/KIS/config/kis_devlp.yaml`, 환경변수 `KIS_CONFIG_DIR` 로 바꿈), 모의/실전 전환, 계좌 가림(끝 2자리). stdout UTF-8 고정 |
| `auth.py` | `get_token(cfg)` | 토큰 캐시(`tk_v.json`·`tk_p.json`, `{"tok","exp"}`, 설정 폴더) 재사용. **만료 시각이 지났을 때만** 발급, 캐시가 깨지면 멈춤 |
| `client.py` | `get()`, `post()`, `KisError` | REST 공통 헤더·`rt_cd` 확인. 오류엔 `msg_cd`·`msg1` 만 |
| `quote.py` | `current_price()`, `minute_bars_past()` | 시세 조회 |
| `order.py` | `limit_order()`, `check()`, `tick_size()`, `MAX_ORDER_WON`, `DUP_WINDOW_SEC` | 모의 지정가 주문 + 안전장치, 기록 `logs/orders.jsonl` |

## 쓰는 TR (검색용)

"실전·모의" 칸은 한국투자 공식 TR 목록 기준이고, "원본 작업 실측"은 이 프로그램을 만들 때 실제로 호출해 본 결과다.

| TR / 경로 | 이름 | 실전 | 모의 | 함수 |
|---|---|---|---|---|
| `POST /oauth2/tokenP` | 접근 토큰 | ○ | ○ | `auth._issue` |
| `FHKST01010100` | 주식현재가 시세 | ○ | ○ | `quote.current_price` |
| `FHKST03010100` | 국내주식기간별시세(일봉) | ○ | 실전·모의 같은 tr_id(원본 주석). 모의 지원 여부는 공식 목록에서 확인 | `strategy/data.py` `fetch_daily` |
| `FHKST03010200` | 주식당일분봉조회(한 번 30건) | ○ | ○ | `strategy/data.py` `fetch_minute_today` |
| `FHKST03010230` | 주식일별분봉조회(과거 분봉, 한 번 120건) | ○ | 문서상 미지원 · 원본 작업 실측은 응답 옴 | `quote.minute_bars_past` |
| `VTTC0012U` / `VTTC0011U` | 모의 현금 매수 / 매도 | — (이 공개판은 실전 주문 없음) | ○ | `order.limit_order` |

## 막히는 자리
- **토큰 발급 제한**: 한국투자 안내는 "1일 1회 발급 원칙, 유효기간(24시간) 안에 잦은 발급 시 이용 제한" → 캐시를 다시 쓴다(`auth.py`).
- **초당 호출 한도**: 너무 빠르면 `EGW00201` 오류 → `strategy/data.py` 의 `Pacer` 가 호출 사이 0.35초를 두고, 이 오류면 1초 쉬고 한 번 더.
- **모의투자에서 안 되는 조회**: 과거 분봉(FHKST03010230)은 공식 목록상 모의 미지원 → 시세 조회는 실전 키(조회만)가 기본.
- **현재가가 호가 단위 사이 값**으로 올 때가 있다(원본 작업 실측) → 주문 전에 호가 단위로 맞추고(`strategy/live.py` `round_tick`), `order.check` 가 한 번 더 검사.

## 안전장치 (`order.check`)
- 모의 설정(`paper`)이 아니면 거절(실전 주문 경로 없음). 설정의 `vps` 주소가 모의투자 서버(`openapivts.koreainvestment.com`)가 아니어도 거절 — 모드 이름만이 아니라 보내는 주소도 본다.
- 매수 1회 최대 100만 원(`MAX_ORDER_WON` — 매도에는 걸지 않는다. 산 뒤 값이 올라도 청산이 거절되지 않게), 같은 주문 60초 안 재요청 차단(보내기 전에 먼저 기록해, 응답을 못 받은 주문도 센다), 호가 단위 검사(2023-01-25 개편 기준 KRX 호가 단위).
- 아직 없음: 일 손실 한도, 비상 정지.
