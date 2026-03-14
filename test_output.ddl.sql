-- ============================================================
-- 表单提交主记录（每次用户提交一份表单生成一条记录）
-- ============================================================
CREATE TABLE IF NOT EXISTS t_form_submission (
    id              BIGSERIAL PRIMARY KEY,
    template_id     VARCHAR(64)  NOT NULL,
    template_name   VARCHAR(200),
    submitted_by    VARCHAR(100),
    submitted_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    status          VARCHAR(20)  NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'submitted', 'approved', 'rejected'))
);

-- 封面信息
CREATE TABLE IF NOT EXISTS t_insp_cover_info (

    id              BIGSERIAL PRIMARY KEY,
    submission_id   BIGINT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    device_name                              VARCHAR(200),
    use_unit_name                            VARCHAR(200),
    inspection_date                          DATE,
    CONSTRAINT fk_t_insp_cover_info_submission
        FOREIGN KEY (submission_id)
        REFERENCES t_form_submission(id) ON DELETE CASCADE
);

-- 年度检查报告
CREATE TABLE IF NOT EXISTS t_insp_annual_inspection_report (

    id              BIGSERIAL PRIMARY KEY,
    submission_id   BIGINT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    use_unit_name                            VARCHAR(200),
    use_registration_cert_no                 VARCHAR(200),
    use_unit_address                         VARCHAR(200),
    unified_social_credit_code               VARCHAR(200),
    safety_manager                           VARCHAR(200),
    contact_phone                            VARCHAR(200),
    next_annual_inspection_date              DATE,
    description                              TEXT,
    CONSTRAINT fk_t_insp_annual_inspection_report_submission
        FOREIGN KEY (submission_id)
        REFERENCES t_form_submission(id) ON DELETE CASCADE
);

-- 年度检查结论报告附页
CREATE TABLE IF NOT EXISTS t_insp_conclusion_report_appendix (

    id              BIGSERIAL PRIMARY KEY,
    submission_id   BIGINT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    seq_no                                   NUMERIC(10,2),
    pipe_code                                VARCHAR(200),
    pipe_name                                VARCHAR(200),
    inspection_conclusion                    VARCHAR(50),
    pressure                                 NUMERIC(10,2),
    temperature                              NUMERIC(10,2),
    medium                                   VARCHAR(200),
    problems_and_handling                    TEXT,
    remark                                   TEXT,
    CONSTRAINT fk_t_insp_conclusion_report_appendix_submission
        FOREIGN KEY (submission_id)
        REFERENCES t_form_submission(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_t_insp_conclusion_report_appendix_submission_id
    ON t_insp_conclusion_report_appendix(submission_id);

-- 年度检查记录表
CREATE TABLE IF NOT EXISTS t_insp_inspection_checklist (

    id              BIGSERIAL PRIMARY KEY,
    submission_id   BIGINT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    seq_no                                   VARCHAR(200),
    inspection_item                          VARCHAR(200),
    inspection_sub_item                      VARCHAR(200),
    inspection_result                        TEXT,
    remark                                   TEXT,
    CONSTRAINT fk_t_insp_inspection_checklist_submission
        FOREIGN KEY (submission_id)
        REFERENCES t_form_submission(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_t_insp_inspection_checklist_submission_id
    ON t_insp_inspection_checklist(submission_id);

-- 设计安装信息
CREATE TABLE IF NOT EXISTS t_insp_design_installation_info (

    id              BIGSERIAL PRIMARY KEY,
    submission_id   BIGINT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    design_unit                              VARCHAR(200),
    design_date                              DATE,
    design_standard                          VARCHAR(200),
    installation_unit                        VARCHAR(200),
    installation_acceptance_standard         VARCHAR(200),
    operation_start_date                     DATE,
    laying_method                            VARCHAR(200),
    CONSTRAINT fk_t_insp_design_installation_info_submission
        FOREIGN KEY (submission_id)
        REFERENCES t_form_submission(id) ON DELETE CASCADE
);

-- 安全管理情况检查
CREATE TABLE IF NOT EXISTS t_insp_safety_management_check (

    id              BIGSERIAL PRIMARY KEY,
    submission_id   BIGINT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    safety_rules_complete                    VARCHAR(200),
    design_docs_complete                     VARCHAR(200),
    personnel_qualification                  VARCHAR(200),
    maintenance_records                      VARCHAR(200),
    inspection_reports_complete              VARCHAR(200),
    safety_accessories_records               VARCHAR(200),
    emergency_plan_records                   VARCHAR(200),
    rectification_completed                  VARCHAR(200),
    accident_records                         VARCHAR(200),
    CONSTRAINT fk_t_insp_safety_management_check_submission
        FOREIGN KEY (submission_id)
        REFERENCES t_form_submission(id) ON DELETE CASCADE
);

-- 管道基本信息
CREATE TABLE IF NOT EXISTS t_insp_pipeline_basic_info (

    id              BIGSERIAL PRIMARY KEY,
    submission_id   BIGINT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    serial_no                                NUMERIC(10,2),
    pipeline_name                            VARCHAR(200),
    pipeline_number                          VARCHAR(200),
    pipeline_level                           VARCHAR(200),
    material                                 VARCHAR(200),
    medium                                   VARCHAR(200),
    nominal_diameter                         NUMERIC(10,2),
    nominal_wall_thickness                   NUMERIC(10,2),
    pipeline_length                          NUMERIC(10,2),
    start_point                              VARCHAR(200),
    end_point                                VARCHAR(200),
    design_temperature                       NUMERIC(10,2),
    design_pressure                          NUMERIC(10,2),
    working_temperature                      NUMERIC(10,2),
    working_pressure                         NUMERIC(10,2),
    anticorrosion_material                   VARCHAR(200),
    insulation_material                      VARCHAR(200),
    insulation_thickness                     NUMERIC(10,2),
    CONSTRAINT fk_t_insp_pipeline_basic_info_submission
        FOREIGN KEY (submission_id)
        REFERENCES t_form_submission(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_t_insp_pipeline_basic_info_submission_id
    ON t_insp_pipeline_basic_info(submission_id);

-- 外观检验
CREATE TABLE IF NOT EXISTS t_insp_appearance_inspection (

    id              BIGSERIAL PRIMARY KEY,
    submission_id   BIGINT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    pipeline_number                          VARCHAR(200),
    paint_color_marking                      VARCHAR(100),
    components_welding_joints                VARCHAR(100),
    outer_surface                            VARCHAR(100),
    layout_check                             VARCHAR(100),
    insulation_layer                         VARCHAR(100),
    support_hanger                           VARCHAR(100),
    valve                                    VARCHAR(100),
    discharge_device                         VARCHAR(100),
    flange                                   VARCHAR(100),
    expansion_joint                          VARCHAR(100),
    anticorrosion_layer                      VARCHAR(100),
    cathodic_protection                      VARCHAR(100),
    buried_pipeline                          VARCHAR(100),
    apron_fueling_pipeline                   VARCHAR(100),
    other                                    TEXT,
    CONSTRAINT fk_t_insp_appearance_inspection_submission
        FOREIGN KEY (submission_id)
        REFERENCES t_form_submission(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_t_insp_appearance_inspection_submission_id
    ON t_insp_appearance_inspection(submission_id);

-- 安全附件检查
CREATE TABLE IF NOT EXISTS t_insp_safety_accessories_check (

    id              BIGSERIAL PRIMARY KEY,
    submission_id   BIGINT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sv_model_meets_design                    VARCHAR(200),
    sv_installation_position                 VARCHAR(200),
    sv_calibration_validity                  VARCHAR(200),
    sv_set_pressure                          NUMERIC(10,2),
    sv_seal_intact                           VARCHAR(200),
    sv_leakage                               VARCHAR(200),
    sv_shutoff_valve                         VARCHAR(200),
    sv_shutoff_valve_open_seal               VARCHAR(200),
    sv_vent_pipe                             VARCHAR(200),
    sv_rain_cap                              VARCHAR(200),
    sv_other_abnormality                     TEXT,
    rd_overdue                               VARCHAR(200),
    rd_installation_direction                VARCHAR(200),
    rd_temp_pressure_meets                   VARCHAR(200),
    rd_leakage                               VARCHAR(200),
    rd_burst_abnormality                     VARCHAR(200),
    rd_vent_pipe                             VARCHAR(200),
    rd_water_or_ice                          VARCHAR(200),
    rd_waterproof_cap                        VARCHAR(200),
    rd_shutoff_valve                         VARCHAR(200),
    rd_shutoff_valve_open_seal               VARCHAR(200),
    rd_series_with_sv                        VARCHAR(200),
    rd_other_abnormality                     TEXT,
    esv_nameplate                            VARCHAR(200),
    esv_overflow_protection                  VARCHAR(200),
    esv_leakage                              VARCHAR(200),
    esv_other_abnormality                    TEXT,
    fa_installation_direction                VARCHAR(200),
    fa_spec_meets_requirement                VARCHAR(200),
    fa_leakage                               VARCHAR(200),
    fa_other_abnormality                     TEXT,
    pg_selection_meets                       VARCHAR(200),
    pg_maintenance_system                    VARCHAR(200),
    pg_calibration_validity                  VARCHAR(200),
    pg_seal_intact                           VARCHAR(200),
    pg_three_way_valve                       VARCHAR(200),
    pg_appearance_accuracy                   VARCHAR(200),
    pg_readings_reasonable                   VARCHAR(200),
    mil_structure_intact                     VARCHAR(200),
    mil_function_meets                       VARCHAR(200),
    ti_calibration_maintenance               VARCHAR(200),
    ti_range_matching                        VARCHAR(200),
    ti_appearance_meets                      VARCHAR(200),
    mil2_structure_intact                    VARCHAR(200),
    mil2_function_meets                      VARCHAR(200),
    conclusion                               TEXT,
    CONSTRAINT fk_t_insp_safety_accessories_check_submission
        FOREIGN KEY (submission_id)
        REFERENCES t_form_submission(id) ON DELETE CASCADE
);

-- 电阻检测记录
CREATE TABLE IF NOT EXISTS t_insp_resistance_test (

    id              BIGSERIAL PRIMARY KEY,
    submission_id   BIGINT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    pipe_name                                VARCHAR(200),
    pipe_number                              VARCHAR(200),
    medium                                   VARCHAR(200),
    pipe_spec                                VARCHAR(200),
    flange_instrument_name                   VARCHAR(200),
    flange_instrument_model                  VARCHAR(200),
    flange_instrument_number                 VARCHAR(200),
    flange_instrument_accuracy               VARCHAR(200),
    ground_instrument_name                   VARCHAR(200),
    ground_instrument_model                  VARCHAR(200),
    ground_instrument_number                 VARCHAR(200),
    ground_instrument_accuracy               VARCHAR(200),
    remark                                   TEXT,
    CONSTRAINT fk_t_insp_resistance_test_submission
        FOREIGN KEY (submission_id)
        REFERENCES t_form_submission(id) ON DELETE CASCADE
);

-- 壁厚测量记录
CREATE TABLE IF NOT EXISTS t_insp_wall_thickness_measurement (

    id              BIGSERIAL PRIMARY KEY,
    submission_id   BIGINT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    pipe_name                                VARCHAR(200),
    pipe_number                              VARCHAR(200),
    instrument_number                        VARCHAR(200),
    instrument_accuracy                      NUMERIC(10,2),
    surface_condition                        VARCHAR(200),
    measurement_ratio                        VARCHAR(200),
    min_wall_thickness                       NUMERIC(10,2),
    measured_points_count                    NUMERIC(10,2),
    conclusion                               TEXT,
    CONSTRAINT fk_t_insp_wall_thickness_measurement_submission
        FOREIGN KEY (submission_id)
        REFERENCES t_form_submission(id) ON DELETE CASCADE
);

-- 壁厚测量记录（续页）
CREATE TABLE IF NOT EXISTS t_insp_wall_thickness_cont (

    id              BIGSERIAL PRIMARY KEY,
    submission_id   BIGINT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    seq                                      NUMERIC(10,2),
    location_number                          VARCHAR(200),
    point_1                                  NUMERIC(10,2),
    point_2                                  NUMERIC(10,2),
    point_3                                  NUMERIC(10,2),
    point_4                                  NUMERIC(10,2),
    point_5                                  NUMERIC(10,2),
    point_6                                  NUMERIC(10,2),
    point_7                                  NUMERIC(10,2),
    point_8                                  NUMERIC(10,2),
    point_9                                  NUMERIC(10,2),
    point_10                                 NUMERIC(10,2),
    point_11                                 NUMERIC(10,2),
    point_12                                 NUMERIC(10,2),
    point_13                                 NUMERIC(10,2),
    point_14                                 NUMERIC(10,2),
    point_15                                 NUMERIC(10,2),
    point_16                                 NUMERIC(10,2),
    conclusion                               TEXT,
    CONSTRAINT fk_t_insp_wall_thickness_cont_submission
        FOREIGN KEY (submission_id)
        REFERENCES t_form_submission(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_t_insp_wall_thickness_cont_submission_id
    ON t_insp_wall_thickness_cont(submission_id);

-- 耐压试验记录
CREATE TABLE IF NOT EXISTS t_insp_pressure_test (

    id              BIGSERIAL PRIMARY KEY,
    submission_id   BIGINT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    pipe_number_device                       VARCHAR(200),
    test_medium                              VARCHAR(200),
    test_pressure                            NUMERIC(10,2),
    medium_temperature                       NUMERIC(10,2),
    ambient_temperature                      NUMERIC(10,2),
    holding_time                             VARCHAR(200),
    test_standard                            VARCHAR(200),
    test_process                             TEXT,
    conclusion                               TEXT,
    CONSTRAINT fk_t_insp_pressure_test_submission
        FOREIGN KEY (submission_id)
        REFERENCES t_form_submission(id) ON DELETE CASCADE
);

-- 管道测厚测点布置图
CREATE TABLE IF NOT EXISTS t_insp_pipe_thickness_sketch (

    id              BIGSERIAL PRIMARY KEY,
    submission_id   BIGINT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    pipe_name                                VARCHAR(200),
    pipe_number                              VARCHAR(200),
    CONSTRAINT fk_t_insp_pipe_thickness_sketch_submission
        FOREIGN KEY (submission_id)
        REFERENCES t_form_submission(id) ON DELETE CASCADE
);
