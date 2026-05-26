"""
pemfc_runner.py
PEMFC Fluent 제어 로직 - GUI에서 호출하는 함수 모음
"""

ITER_SECOND = 10_000_000   # 전기화학 반응: 수렴 시 자동 종료


# ── Case File Reader ─────────────────────────────────────────────
def case_file_reader(solver, case_file: str):
    """Case 파일 로드 + UDF unload/load + rename_UDvars + 재로드"""
    solver.settings.file.read_case(file_name=case_file)
    solver.tui.define.user_defined.compiled_functions("unload", "libudf")
    solver.tui.define.user_defined.compiled_functions("load", "libudf")
    solver.tui.define.user_defined.execute_on_demand('"rename_UDvars::libudf"')
    solver.settings.file.read_case(file_name=case_file)


# ── Run Calculator (Single Run) ──────────────────────────────────
def run_calculator(solver, anode_Y_h2, anode_Y_h2o,
                   cathode_Y_o2, cathode_Y_h2o,
                   w_lam: float,
                   iter_init: int, oper_volt: float,
                   save_path: str = ""):
    """초기화 → Species Patch → 단순 유동 → Potential Patch → 전기화학 반응 → (저장)"""

    # 1. 초기화
    solver.settings.solution.initialization.standard_initialize()
    solver.settings.solution.initialization.hybrid_initialize()

    # 2. Species Patch
    _patch_species(solver, anode_Y_h2, anode_Y_h2o, cathode_Y_o2, cathode_Y_h2o,
                   w_lam)

    # 3. 단순 유동 (iter_init 회)
    solver.settings.solution.run_calculation.iter_count = iter_init
    solver.settings.solution.run_calculation.calculate()

    # 4. Potential Patch + 운전 전압 설정
    _patch_potential(solver, oper_volt)

    # 5. 전기화학 반응 (수렴 시 자동 종료)
    solver.settings.solution.run_calculation.iter_count = ITER_SECOND
    solver.settings.solution.run_calculation.calculate()

    # 6. 저장 (경로가 지정된 경우)
    if save_path:
        solver.file.write(file_type="case-data", file_name=save_path)


# ── Parameter Study ──────────────────────────────────────────────
def parameter_study(solver, anode_Y_h2, anode_Y_h2o,
                    cathode_Y_o2, cathode_Y_h2o,
                    w_lam: float,
                    iter_init: int,
                    voltage_list: list, save_base: str):
    """IV 커브 전압 스윕.
    첫 번째 전압: 초기화 + Species/Potential Patch + 단순유동 + 전기화학 + 저장
    이후 전압   : ca-tab 변경 + 전기화학 + 저장

    save_base : 저장 기본 경로 (확장자 제외, 예: C:/results/run01)
                → 실제 파일: run01_70V.cas.h5, run01_85V.cas.h5, ...
    """
    for i, v in enumerate(voltage_list):
        if i == 0:
            # ── 첫 번째 전압: 전체 초기화 + 단순유동 포함 ──
            # 1. 초기화
            solver.settings.solution.initialization.standard_initialize()
            solver.settings.solution.initialization.hybrid_initialize()

            # 2. Species Patch
            _patch_species(solver, anode_Y_h2, anode_Y_h2o,
                           cathode_Y_o2, cathode_Y_h2o, w_lam)

            # 3. 단순 유동 (iter_init 회)
            solver.settings.solution.run_calculation.iter_count = iter_init
            solver.settings.solution.run_calculation.calculate()

            # 4. Potential Patch + 첫 번째 전압 설정
            _patch_potential(solver, v)
        else:
            # ── 이후 전압: ca-tab 변경만 ──
            solver.settings.setup.boundary_conditions.wall = {
                "ca-tab": {"uds": {"uds": {"Solid potential": {"value": v}}}}
            }

        # 5. 전기화학 반응 (수렴 시 자동 종료)
        solver.settings.solution.run_calculation.iter_count = ITER_SECOND
        solver.settings.solution.run_calculation.calculate()

        # 6. 저장: {save_base}_{전압라벨}V.cas.h5
        v_label  = f"{int(round(v * 100))}V"
        out_path = f"{save_base}_{v_label}.cas.h5"
        solver.file.write(file_type="case-data", file_name=out_path)


# ── Mesh Replacer ────────────────────────────────────────────────
def mesh_replacer(solver, mesh_file: str, membrane_material: str = "nafion-nr211"):
    """Mesh 교체 + 막 재료 설정"""
    solver.file.replace_mesh(file_name=mesh_file)
    solver.mesh.size_info()
    solver.settings.setup.cell_zone_conditions.fluid = {
        "membrn": {"name": "membrn", "general": {"material": membrane_material}}
    }


# ── 내부 헬퍼 ────────────────────────────────────────────────────
def _patch_species(solver, anode_Y_h2, anode_Y_h2o, cathode_Y_o2, cathode_Y_h2o,
                   w_lam: float = 14):
    patch = solver.settings.solution.initialization.patch.calculate_patch

    patch(domain="mixture",
          cell_zones=["an-chn", "an-ctl", "an-gdl", "an-mpl"],
          variable="species-0", value=anode_Y_h2)

    patch(domain="mixture",
          cell_zones=["ca-chn", "ca-ctl", "ca-gdl", "ca-mpl", "membrn"],
          variable="species-1", value=cathode_Y_o2)

    patch(domain="mixture",
          cell_zones=["an-chn", "an-ctl", "an-gdl", "an-mpl"],
          variable="species-2", value=anode_Y_h2o)

    patch(domain="mixture",
          cell_zones=["ca-chn", "ca-ctl", "ca-gdl", "ca-mpl", "membrn"],
          variable="species-2", value=cathode_Y_h2o)

    patch(domain="mixture",
          cell_zones=["an-bpp", "an-chn", "an-ctl", "an-gdl", "an-mpl",
                      "ca-bpp", "ca-chn", "ca-ctl", "ca-gdl", "ca-mpl", "membrn"],
          variable="uds-3", value=w_lam)


def _patch_potential(solver, oper_volt: float):
    patch = solver.settings.solution.initialization.patch.calculate_patch

    patch(domain="mixture",
          cell_zones=["an-bpp", "an-chn", "an-ctl", "an-gdl", "an-mpl"],
          variable="uds-0", value=-0.03)

    patch(domain="mixture",
          cell_zones=["ca-bpp", "ca-chn", "ca-ctl", "ca-gdl", "ca-mpl", "membrn"],
          variable="uds-0", value=0.53)

    patch(domain="mixture",
          cell_zones=["ca-bpp", "ca-chn", "ca-ctl", "ca-gdl", "ca-mpl", "membrn"],
          variable="uds-1", value=-0.15)

    solver.settings.setup.boundary_conditions.wall = {
        "ca-tab": {"uds": {"uds": {"Solid potential": {"value": oper_volt}}}}
    }
