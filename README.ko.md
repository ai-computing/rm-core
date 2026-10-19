<div align="center">

<h1>rm-core</h1>

<h3>ai-rm 구성요소를 잇는 계약</h3>

<p>
  <a href="README.md">English</a> · <strong>한국어</strong>
</p>

<p>
  <a href="https://github.com/ai-computing/rm-core/actions/workflows/ci.yml"><img src="https://github.com/ai-computing/rm-core/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/ai-computing/ai-rm"><img src="https://img.shields.io/badge/ai--rm-contracts-7c5cff" alt="ai-rm 계약"></a>
  <a href="PROTOCOL.md"><img src="https://img.shields.io/badge/protocol-v0.1-7c5cff" alt="프로토콜 v0.1"></a>
  <a href="https://github.com/ai-computing/rm-core/tree/v0.1.1"><img src="https://img.shields.io/badge/rm--core-0.1.1-22d3ee" alt="rm-core 0.1.1"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.9%2B-3776ab?logo=python&amp;logoColor=white" alt="Python 3.9+"></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/dependencies-none-64748b" alt="런타임 의존성 없음"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-BSD--3--Clause-64748b" alt="라이선스: BSD-3-Clause"></a>
</p>

<p>
  <a href="#-빠른-시작"><b>빠른 시작</b></a> ·
  <a href="#-ai-rm-연동"><b>ai-rm 연동</b></a> ·
  <a href="#-구조"><b>구조</b></a> ·
  <a href="PROTOCOL.md"><b>프로토콜</b></a> ·
  <a href="#-로드맵"><b>로드맵</b></a>
</p>

</div>

---

**rm-core**는 [ai-rm](https://github.com/ai-computing/ai-rm)의 계약 패키지입니다. 가속기(L1), 메모리 계층과 KV
전송(L2), 워크로드와 배치(L3–L4), 공통 메트릭 스키마로 구성요소 사이의 약속을 정의하므로 구성요소끼리 서로
import하지 않습니다. 타입, 인터페이스, 참조 구현, 적합성(conformance) 검사만 담고 있으며 표준 라이브러리만 쓰고
(Python 3.9+) 런타임 의존성이 없습니다. 규범 명세는 [PROTOCOL.md](PROTOCOL.md)(v0.1, 영문)이고, 현재 릴리스는
0.1.1입니다.

## ✨ 주요 특징

<table>
<tr>
<td width="33%" valign="top">
<b>계층별 타입 계약</b><br>
<code>Accelerator</code> / <code>AcceleratorProvider</code>(L1), <code>MemoryTier</code> / <code>KVLayout</code> /
<code>KVTransport</code>(L2), <code>Workload</code> / <code>Placement</code>(L3–L4). 검증에 실패하면
<code>ContractError</code>를 냅니다.
</td>
<td width="33%" valign="top">
<b>이름으로 선택</b><br>
구성요소는 어댑터를 Python entry point로 등록하고, 런타임은 <code>rm_core.registry.load(group, name)</code>로
불러옵니다. 구현을 바꾸는 일은 코드가 아니라 설정 변경입니다.
</td>
<td width="33%" valign="top">
<b>적합성 검사</b><br>
<code>python -m rm_core.conformance</code>가 등록된 모든 구현에 계약 검사를 돌리고 PASS, SKIP(하드웨어 없음),
FAIL로 보고합니다.
</td>
</tr>
<tr>
<td width="33%" valign="top">
<b>하나의 메트릭 언어</b><br>
<code>rm_core.metrics.METRICS</code>가 이름, 단위, 태그(TTFT, TPOT, tok/s, 전력, MFU, KV 전송 …)를 고정합니다.
Prometheus 시계열 이름은 <code>airm_&lt;name&gt;</code>입니다.
</td>
<td width="33%" valign="top">
<b>Kubernetes 표현</b><br>
<code>AcceleratorProfile</code> CRD(<code>airm.ai-computing.io/v1alpha1</code>)와 노드 레이블.
<code>rm_core.k8s</code>가 만들고 다시 읽습니다.
</td>
<td width="33%" valign="top">
<b>참조 구현</b><br>
<code>sim</code>, <code>loopback</code>, <code>greedy</code>는 하드웨어 없이 동작합니다. 기대 동작을 정의하고, 실제
어댑터를 작성할 때 본뜰 형태가 됩니다.
</td>
</tr>
</table>

## 🚀 빠른 시작

```bash
pip install "rm-core @ git+https://github.com/ai-computing/rm-core@v0.1.1"
python -m rm_core.conformance            # 등록된 모든 구현 검사
```

rm-core만 설치한 상태에서는 참조 구현이 검사됩니다.

```text
PASS  airm.accelerator_providers:sim
PASS  airm.kv_transports:loopback
PASS  airm.placements:greedy
```

그룹 하나나 구현 하나만 검사하려면 `python -m rm_core.conformance <group> [name ...]`를 씁니다. 실패한 구현이
하나라도 있으면 0이 아닌 코드로 종료합니다.

## 🔌 ai-rm 연동

구성요소는 자기 저장소 안의 작은 어댑터 모듈에서 계약을 구현하고 entry-point 그룹에 등록합니다.

| Entry-point 그룹 | 계약 | 등록 주체 | 참조 구현 |
|---|---|:-:|---|
| `airm.accelerator_providers` | `AcceleratorProvider` | L1 (장치 탐지) | `sim` |
| `airm.kv_transports` | `KVTransport` | L2 (데이터 이동) | `loopback` |
| `airm.placements` | `Placement` | L4 (배치 정책) | `greedy` |
| `airm.workloads` | 워크로드 runner ([§5.3](PROTOCOL.md#53-workload-runners)) | L3 (서빙, 학습) | — |

### 계약 구현하기

```python
# your_pkg/airm.py
from rm_core import KVTransport, TransferPlan, TransferHandle, TransferResult, TransportError

class P2PTransport:
    name = "p2p"
    def supports(self, src, dst): ...
    def plan(self, request_id, src, dst, src_layout, dst_layout, tokens): ...
    def submit(self, plan): ...
    def wait(self, handle, timeout_s): ...
    def close(self): ...
```

```toml
# your pyproject.toml
[project.entry-points."airm.kv_transports"]
p2p = "your_pkg.airm:P2PTransport"
```

```bash
python -m rm_core.conformance airm.kv_transports p2p
```

런타임은 설정(`kvTransport: p2p`)에 있는 이름으로 구현을 고릅니다.

```python
from rm_core import registry
transport = registry.load("airm.kv_transports", "p2p")
```

본뜰 참조 구현은 `rm_core.reference`(`SimAcceleratorProvider`, `LoopbackTransport`, `GreedyPlacement`)에
있습니다. 구성요소는 rm-core를 호환 범위로 고정해 의존합니다. 예: `rm-core>=0.1,<0.2`
([§1](PROTOCOL.md#1-scope-and-versioning)).

<details>
<summary><b>프로토콜의 주요 규칙</b></summary>
<br>

- **가속기** — `id`는 `<node>/<vendor>:<index>`이며 재시작해도 바뀌지 않습니다. `peak_tflops`는 정밀도별 dense
  최대 성능이고 `peak_source`가 있어야 합니다. 모르는 값은 0이 아니라 생략합니다. 장치가 없으면 `discover()`는
  예외 대신 `[]`를 돌려줍니다.
- **KV 전송** — `plan()`은 입력을 검증하고 `TransportError`를 냅니다. `wait()`는 데이터가 목적지에서 보일 때만
  반환합니다. 전송은 다른 경로로 조용히 대체하지 않습니다. 실제 장치가 필요한 전송은 `conformance_case()`를
  구현하고, 장치가 없으면 `rm_core.conformance.NoHardware`를 내 SKIP으로 보고됩니다.
- **배치** — pool에 있는 id만 돌려주고, 결정적이며, 맞는 자리가 없으면 예외 대신 `reason`이 담긴 빈 결정을
  돌려줍니다.
- **메트릭** — `METRICS`에 있는 양은 정확히 그 이름과 단위로 보고합니다. 태그는 `TAG_KEYS`에서 고르며,
  `mfu_pct`에는 `peak_source`, `power_w`에는 `scope=card|node`가 붙습니다.
- **보안** — 계약, 프로파일, 메트릭, 로그에는 내부 주소, 자격 증명, 토큰, 키를 담지 않습니다. 사이트 값은 환경에서
  옵니다.

전문: [PROTOCOL.md](PROTOCOL.md).
</details>

<details>
<summary><b>공통 메트릭 (<code>rm_core.metrics.METRICS</code>)</b></summary>
<br>

| 이름 | 단위 | 의미 |
|---|---|---|
| `ttft_p50_ms` · `ttft_p90_ms` · `ttft_p99_ms` | ms | 첫 토큰까지 걸린 시간 |
| `tpot_p50_ms` · `tpot_p90_ms` · `tpot_p99_ms` | ms | 출력 토큰당 시간 |
| `e2e_p90_ms` | ms | 요청 종단 지연, p90 |
| `tok_s` | tokens/s | 초당 생성 토큰, 측정 대상 시스템 전체 |
| `req_s` | requests/s | 초당 완료 요청 |
| `power_w` | W | 측정 구간 평균 전력 (태그 `scope=card\|node`) |
| `energy_j` | J | 측정 구간 에너지 |
| `gflops_per_w` | GFLOPS/W | 전력 효율 |
| `mfu_pct` | % | 모델 FLOPs 활용률 (태그 `peak_source`) |
| `kv_transfer_ms` | ms | 요청당 KV 전달 시간 |
| `kv_transfer_gbps` | GB/s | KV 전송 대역폭 |
| `accuracy_pct` | % | 과제 정확도 (태그 `dataset`) |
| `slo_attainment_pct` | % | SLO를 만족한 요청 비율 |
| `accelerators` | count | 사용 중인 가속기 수 (태그 `vendor`/`model`) |

Prometheus 시계열: `airm_<name>` (`rm_core.metrics.prometheus_name`). 태그 키: `component`, `model`,
`accelerator`, `vendor`, `scope`, `peak_source`, `dataset`, `workload`, `kv_transport`, `run_id`, `commit`.
</details>

## 🏗 구조

```text
src/rm_core/
├── accelerator.py   # L1: Accelerator, AcceleratorProvider; 벤더·메모리·정밀도·인터커넥트 열거형
├── memory.py        # L2: MemoryTier, KVLayout, TransferPlan/Handle/Result, KVTransport
├── workload.py      # L3–L4: Workload, PlacementDecision, Placement; 워크로드 종류, SLO 키
├── metrics.py       # METRICS, TAG_KEYS, Measurement, prometheus_name
├── k8s.py           # AcceleratorProfile 객체와 노드 레이블; from_profile()
├── registry.py      # entry-point 그룹: available(), load(), groups()
├── reference.py     # sim / loopback / greedy (하드웨어 불필요)
├── conformance.py   # python -m rm_core.conformance
└── errors.py        # ContractError, TransportError, NoHardware
k8s/acceleratorprofile.crd.yaml   # AcceleratorProfile CRD (airm.ai-computing.io/v1alpha1)
```

노드 데몬은 장치마다 클러스터 범위 `AcceleratorProfile`을 게시하고, 요약 노드 레이블
`airm.ai-computing.io/<vendor>.<model>=<개수>`와 `airm.ai-computing.io/managed=true`를 답니다. `rm_core.k8s`가 둘 다
만들고 다시 읽습니다. 프로파일에는 주소나 자격 증명을 담지 않습니다.

## 🧪 개발

```bash
pip install -e .
python -m unittest discover -s tests -v
```

CI는 Python 3.9–3.12에서 테스트를 돌린 뒤 `python -m rm_core.conformance`와 `python tools/check_sensitive.py .`를
실행합니다([워크플로](.github/workflows/ci.yml)).

## 🗺 로드맵

- [x] 프로토콜 v0.1: 계약, `AcceleratorProfile` CRD, 참조 구현, 적합성 검사
- [x] 0.1.1: `AcceleratorProfile`이 `extra` 유지, `python -m` 실행 시 `NoHardware`를 SKIP으로 보고, 메트릭 이전 규칙
- [ ] 프로토콜 v0.2: 전송 계획에 `MemoryRegion`(owner, fd/offset, size)을 넣어, 장치 간 전송이 실제 버퍼를 묶고
      하드웨어 fixture로 적합성 검사를 통과할 수 있게 함
- [ ] 프로토콜 v0.2: 워크로드 runner 인터페이스(`airm.workloads`) 정식화

변경 이력: [PROTOCOL.md § Change log](PROTOCOL.md#change-log).

## 📚 문서

| | |
|---|---|
| **명세** | [PROTOCOL.md](PROTOCOL.md) · [AcceleratorProfile CRD](k8s/acceleratorprofile.crd.yaml) |
| **ai-rm** | [Umbrella](https://github.com/ai-computing/ai-rm) · [인터페이스](https://github.com/ai-computing/ai-rm/blob/master/docs/interfaces.md) · [통합 안내](https://github.com/ai-computing/ai-rm/blob/master/docs/integration-guide.md) |

## 📄 라이선스

[BSD-3-Clause](LICENSE).

<div align="center"><sub><a href="https://github.com/ai-computing/ai-rm">ai-rm</a> 구성요소 · ai-computing 팀 · ETRI</sub></div>
