# PEMFC CFD Controller

PyFluent 기반 PEMFC(고분자 전해질 연료전지) CFD 자동화 GUI

## 구성 파일

| 파일 | 설명 |
|---|---|
| `pemfc_gui.py` | PyQt5 메인 GUI |
| `pemfc_runner.py` | Fluent 제어 로직 (Case Reader / Run Calculator / Mesh Replacer) |

## 주요 기능

<img src="https://github.com/user-attachments/assets/f2897d54-af49-4b55-9a16-667a7145e832"  width="970" height="1061"/>

- **Case File Reader** — Case 파일 로드 → UDF unload/load → Excute on Demands → Case 파일 재로드 
- **Run Calculator (Single Run)** — 초기화 → Species Patch → 단순 유동 → Potential Patch → 전기화학 반응 → 저장
- **Run Calculator (Parameter Study)** — 원하는 voltage 구간 측정 (범위 / 직접 입력) 각 Voltage 별 저장
- **Mesh Replacer** — Mesh 교체 → membran nr211 재료 설정

## 요구 사항

```
pip install -r requirements.txt
```

## 실행

```bash
python pemfc_gui.py
```

## 참고

- Fluent는 이 GUI를 통해 실행(`launch_fluent`)해야 제어 가능
- GUI 종료 시 Fluent는 계속 실행됨 (`cleanup_on_exit=False`)
- 실행 설정(precision, processor count 등)은 `config.json`에 자동 저장
