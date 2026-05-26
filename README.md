# PEMFC CFD Controller

PyFluent 기반 PEMFC(고분자 전해질 연료전지) CFD 자동화 GUI

## 구성 파일

| 파일 | 설명 |
|---|---|
| `pemfc_gui.py` | PyQt5 메인 GUI |
| `pemfc_runner.py` | Fluent 제어 로직 (Case Reader / Run Calculator / Mesh Replacer) |

## 주요 기능

- **Case File Reader** — Case 파일 로드 + UDF unload/load + rename_UDvars 자동 실행
- **Run Calculator (Single Run)** — 초기화 → Species/Potential Patch → 단순 유동 → 전기화학 반응
- **Run Calculator (Parameter Study)** — IV 커브 전압 스윕 자동화 (범위 / 직접 입력)
- **Mesh Replacer** — Mesh 교체 + 막 재료 설정

## 요구 사항

```
ansys-fluent-core
PyQt5
```

## 실행

```bash
python pemfc_gui.py
```

## 참고

- Fluent는 이 GUI를 통해 실행(`launch_fluent`)해야 제어 가능
- GUI 종료 시 Fluent는 계속 실행됨 (`cleanup_on_exit=False`)
- 실행 설정(precision, processor count 등)은 `config.json`에 자동 저장
