import os
import io
import gc
import glob
import sys
import logging
import warnings

import numpy as np
import pandas as pd

_stderr = sys.stderr
sys.stderr = io.StringIO()
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["GLOG_minloglevel"] = "2"
os.environ["GRPC_VERBOSITY"] = "ERROR"

from lightgbm import LGBMRegressor, early_stopping
from xgboost import XGBRegressor
from sklearn.model_selection import GroupKFold
from sklearn.metrics import mean_squared_error
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

sys.stderr = _stderr
logging.getLogger("lightgbm").setLevel(logging.ERROR)
warnings.filterwarnings("ignore")


# ---------------- CONFIG ----------------
BASE = "/kaggle/input/competitions/rogii-wellbore-geology-prediction"
TRAIN_DIR = f"{BASE}/train"
TEST_DIR = f"{BASE}/test"
SAMPLE_SUB = f"{BASE}/sample_submission.csv"

RANDOM_STATE = 42
TVT_CLIP_MIN, TVT_CLIP_MAX = 9000, 14000
MEMORY_DIR = "/tmp/neraium_v34_safe_full"
os.makedirs(MEMORY_DIR, exist_ok=True)

TRAIN_HIDE_FRACS = [0.30, 0.40, 0.50]
BACKTEST_HIDE_FRACS = [0.30, 0.40, 0.50]
MIN_VALID_ROWS = 20
BACKTEST_MAX_WELLS = 10
META_NEAR_THRESHOLD = 90

USE_GPU = True
try:
    import tensorflow as tf  # noqa: F401
    gpus = tf.config.list_physical_devices("GPU")
    USE_GPU = len(gpus) > 0
except Exception:
    USE_GPU = False

lgbm_params = (
    {"device": "gpu", "gpu_platform_id": 0, "gpu_device_id": 0, "verbosity": -1}
    if USE_GPU else {}
)
xgb_params = (
    {"device": "cuda", "tree_method": "hist"}
    if USE_GPU else {"tree_method": "hist"}
)

np.random.seed(RANDOM_STATE)


# ---------------- HELPERS ----------------
def rmse(y_true, y_pred):
    return np.sqrt(mean_squared_error(y_true, y_pred))


def load_typewell(well, folder):
    path = f"{folder}/{well}__typewell.csv"
    if not os.path.exists(path):
        return None
    tw = pd.read_csv(path)
    if "TVT" not in tw.columns or "GR" not in tw.columns:
        return None
    tw = tw[["TVT", "GR"]].dropna().sort_values("TVT")
    return tw if len(tw) >= 10 else None


def safe_slope(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = ~np.isnan(x) & ~np.isnan(y)
    x, y = x[mask], y[mask]
    if len(x) < 5:
        return 0.0
    stdx = np.nanstd(x)
    if stdx == 0 or np.isnan(stdx):
        return 0.0
    try:
        slope = float(np.polyfit(x, y, 1)[0])
        return float(np.clip(slope, -5.0, 5.0))
    except Exception:
        return 0.0


def compute_global_shift(known_tvt, known_gr, tw_tvt, tw_gr, search_range=(-80, 80, 5)):
    known_tvt = np.asarray(known_tvt, dtype=float)
    known_gr = np.asarray(known_gr, dtype=float)
    tw_tvt = np.asarray(tw_tvt, dtype=float)
    tw_gr = np.asarray(tw_gr, dtype=float)

    if len(known_tvt) < 10 or len(tw_tvt) < 10:
        return 0.0, 0.0

    shifts = np.arange(search_range[0], search_range[1] + 1, search_range[2])
    best_corr = -1.0
    best_shift = 0.0

    for sh in shifts:
        interp_gr = np.interp(known_tvt + sh, tw_tvt, tw_gr)
        mask = np.isfinite(interp_gr) & np.isfinite(known_gr)
        if mask.sum() < 10:
            continue

        corr = np.corrcoef(known_gr[mask], interp_gr[mask])[0, 1]
        if np.isfinite(corr) and corr > best_corr:
            best_corr = float(corr)
            best_shift = float(sh)

    if not np.isfinite(best_corr) or best_corr < -0.99:
        best_corr = 0.0

    return best_shift, best_corr


def make_hidden_tail_scenario(df_raw, hide_frac):
    if "TVT" not in df_raw.columns:
        return None

    df = df_raw.copy().reset_index(drop=True)
    df = df.dropna(subset=["TVT"]).reset_index(drop=True)
    if len(df) < MIN_VALID_ROWS:
        return None

    n = len(df)
    keep_frac = 1.0 - hide_frac
    cutoff_pos = int(n * keep_frac)
    cutoff_pos = max(5, min(cutoff_pos, n - 3))

    df["TVT_input"] = df["TVT"]
    df.loc[cutoff_pos:, "TVT_input"] = np.nan

    hidden_mask = np.zeros(n, dtype=bool)
    hidden_mask[cutoff_pos:] = True

    if hidden_mask.sum() < 3:
        return None

    return df, hidden_mask, cutoff_pos


# ---------------- FEATURE ENGINEERING ----------------
def add_typewell_features_optimal(df, typewell, tvt_ref, global_shift, global_corr):
    tw_tvt = typewell["TVT"].values
    tw_gr = typewell["GR"].values

    aligned_tvt = np.asarray(tvt_ref, dtype=float) + float(global_shift)

    df["typewell_gr_at_est"] = np.interp(aligned_tvt, tw_tvt, tw_gr)
    tw_min, tw_max = np.nanmin(tw_tvt), np.nanmax(tw_tvt)
    df["typewell_out_of_range"] = (
        (aligned_tvt < tw_min - 100) | (aligned_tvt > tw_max + 100)
    ).astype(int)

    df["gr_minus_typewell"] = df["GR"] - df["typewell_gr_at_est"]
    df["typewell_alignment_error"] = df["gr_minus_typewell"].abs()

    offsets = [-100, -60, -30, -15, -8, -4, 0, 4, 8, 15, 30, 60, 100]
    for off in offsets:
        df[f"tw_gr_{off}"] = np.interp(aligned_tvt + off, tw_tvt, tw_gr)
        df[f"gr_diff_tw_{off}"] = df["GR"] - df[f"tw_gr_{off}"]

    for half_win in [15, 30, 60]:
        col_plus = f"tw_gr_{half_win}"
        col_minus = f"tw_gr_{-half_win}"
        if col_plus in df.columns and col_minus in df.columns:
            df[f"tw_slope_{2 * half_win}"] = (
                df[col_plus] - df[col_minus]
            ) / (2 * half_win)

    for w in [31, 121]:
        minp = max(5, w // 4)
        df[f"typewell_alignment_error_roll_{w}"] = (
            df["typewell_alignment_error"].rolling(w, min_periods=minp).mean()
        )

    df["typewell_confidence"] = 1.0 / (1.0 + df["typewell_alignment_error_roll_31"])
    df["best_shift"] = float(global_shift)
    df["best_shift_corr"] = float(global_corr)
    return df


def add_features_neraium_max(df, typewell=None, well_offsets=None):
    df = df.copy()

    for col in ["MD", "X", "Y", "Z", "GR"]:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = df[col].ffill().bfill().fillna(0)

    if "TVT_input" not in df.columns:
        df["TVT_input"] = np.nan

    df["row_idx"] = np.arange(len(df))
    df["md_delta"] = df["MD"].diff().fillna(0)
    df["z_delta"] = df["Z"].diff().fillna(0)
    df["gr_delta"] = df["GR"].diff().fillna(0)
    df["gr_abs_delta"] = df["gr_delta"].abs()
    df["gr_gradient"] = np.gradient(df["GR"].values)
    df["gr_gradient_abs"] = np.abs(df["gr_gradient"])
    df["gr_curvature"] = np.gradient(df["gr_gradient"])
    df["z_gradient"] = np.gradient(df["Z"].values)

    for step in [3, 5, 10, 20]:
        df[f"gr_velocity_{step}"] = df["GR"].diff(step).fillna(0)
        df[f"gr_acceleration_{step}"] = df[f"gr_velocity_{step}"].diff(step).fillna(0)

    df["z_velocity_5"] = df["Z"].diff(5).fillna(0)
    df["z_acceleration_5"] = df["z_velocity_5"].diff(5).fillna(0)

    for lag in [1, 2, 3, 5, 10, 20, 50]:
        df[f"GR_lag_{lag}"] = df["GR"].shift(lag).bfill().fillna(0)
        df[f"Z_lag_{lag}"] = df["Z"].shift(lag).bfill().fillna(0)
        df[f"GR_diff_lag_{lag}"] = df["GR"] - df[f"GR_lag_{lag}"]

    for w in [5, 15, 31, 61, 121]:
        minp = max(3, w // 3)
        rm = df["GR"].rolling(w, min_periods=minp)
        df[f"gr_roll_mean_{w}"] = rm.mean()
        df[f"gr_roll_std_{w}"] = rm.std()
        df[f"gr_roll_min_{w}"] = rm.min()
        df[f"gr_roll_max_{w}"] = rm.max()
        df[f"gr_roll_range_{w}"] = df[f"gr_roll_max_{w}"] - df[f"gr_roll_min_{w}"]

        zm = df["Z"].rolling(w, min_periods=minp)
        df[f"z_roll_mean_{w}"] = zm.mean()
        df[f"z_roll_std_{w}"] = zm.std()

        df[f"gr_abs_delta_roll_{w}"] = df["gr_abs_delta"].rolling(w, min_periods=minp).mean()

    df["gr_structural_shift_31_121"] = df["gr_roll_mean_31"] - df["gr_roll_mean_121"]
    df["z_structural_shift_31_121"] = df["z_roll_mean_31"] - df["z_roll_mean_121"]
    df["gr_volatility_shift_31_121"] = df["gr_roll_std_31"] - df["gr_roll_std_121"]

    df["gr_cumsum"] = df["GR"].cumsum()
    df["gr_cumsum_50"] = df["GR"].rolling(50, min_periods=5).sum()

    df["TVT_input_ffill"] = df["TVT_input"].ffill().bfill().fillna(0)
    df["TVT_input_bfill"] = df["TVT_input"].bfill().ffill().fillna(0)
    df["has_tvt_input"] = df["TVT_input"].notna().astype(int)

    known = np.where(df["TVT_input"].notna())[0]
    if len(known) > 0:
        last = known.max()
        df["last_known_tvt"] = df.loc[last, "TVT_input"]
        df["last_known_md"] = df.loc[last, "MD"]
        df["last_known_z"] = df.loc[last, "Z"]
        df["last_known_gr"] = df.loc[last, "GR"]
        df["rows_after_known_tvt"] = (df["row_idx"] - last).clip(lower=0)
        df["md_after_known"] = df["MD"] - df["last_known_md"]
        df["z_after_known"] = df["Z"] - df["last_known_z"]
        df["gr_after_known"] = df["GR"] - df["last_known_gr"]

        known_df = df.loc[known, ["Z", "TVT_input"]].dropna()
        slope = safe_slope(known_df["Z"], known_df["TVT_input"])
        df["known_tvt_slope"] = slope
        df["linear_tvt_est"] = df["last_known_tvt"] + df["z_after_known"] * slope
        df["linear_tvt_residual_proxy"] = df["TVT_input_ffill"] - df["linear_tvt_est"]

        base_gr = df.loc[known, "GR"].dropna()
        base_mean = base_gr.mean() if len(base_gr) else 0.0
        base_std = base_gr.std() if len(base_gr) else 1.0
        if np.isnan(base_std) or base_std < 1e-6:
            base_std = 1.0

        df["neraium_gr_z"] = (df["GR"] - base_mean) / base_std
        df["neraium_gr_drift_abs"] = df["neraium_gr_z"].abs()
        df["inv_dist_to_known"] = 1.0 / (1.0 + df["rows_after_known_tvt"])
    else:
        for c in [
            "last_known_tvt", "last_known_md", "last_known_z", "last_known_gr",
            "rows_after_known_tvt", "md_after_known", "z_after_known", "gr_after_known",
            "known_tvt_slope", "linear_tvt_est", "linear_tvt_residual_proxy",
            "neraium_gr_z", "neraium_gr_drift_abs", "inv_dist_to_known",
        ]:
            df[c] = 0.0
        df["linear_tvt_est"] = 0.0

    well = df["well"].iloc[0] if "well" in df.columns else "unknown"
    df["well_offset"] = well_offsets.get(well, 0.0) if well_offsets else 0.0

    if typewell is not None and len(known) > 0:
        known_tvt = df.loc[known, "TVT_input"].values
        known_gr = df.loc[known, "GR"].values
        global_shift, global_corr = compute_global_shift(
            known_tvt, known_gr, typewell["TVT"].values, typewell["GR"].values
        )
        tvt_ref = (
            df["linear_tvt_est"]
            .replace([np.inf, -np.inf], np.nan)
            .fillna(df["TVT_input_ffill"])
        )
        df = add_typewell_features_optimal(df, typewell, tvt_ref, global_shift, global_corr)
    else:
        for col in [
            "typewell_gr_at_est", "gr_minus_typewell", "typewell_alignment_error",
            "typewell_out_of_range", "typewell_confidence", "best_shift", "best_shift_corr",
            "typewell_alignment_error_roll_31", "typewell_alignment_error_roll_121",
        ]:
            df[col] = 0.0
        for off in [-100, -60, -30, -15, -8, -4, 0, 4, 8, 15, 30, 60, 100]:
            df[f"tw_gr_{off}"] = 0.0
            df[f"gr_diff_tw_{off}"] = 0.0
        for w in [30, 60, 120]:
            df[f"tw_slope_{w}"] = 0.0

    eps = 1e-6
    df["neraium_gr_drift_roll_31"] = df["neraium_gr_drift_abs"].rolling(31, min_periods=5).mean()
    df["neraium_gr_drift_roll_121"] = df["neraium_gr_drift_abs"].rolling(121, min_periods=10).mean()
    df["neraium_drift_persistence"] = (
        (df["neraium_gr_drift_abs"] > 1.5).astype(int).rolling(61, min_periods=5).mean()
    )
    df["neraium_drift_pressure"] = df["neraium_gr_drift_roll_31"] * np.log1p(
        df["rows_after_known_tvt"].clip(lower=0)
    )
    df["neraium_drift_velocity"] = df["neraium_gr_drift_roll_31"].diff(5).fillna(0)
    df["neraium_alignment_velocity"] = df["typewell_alignment_error_roll_31"].diff(5).fillna(0)
    df["neraium_alignment_breakdown"] = (
        df["typewell_alignment_error_roll_31"] * (1.0 + df["neraium_gr_drift_roll_31"].clip(lower=0))
    )
    df["neraium_alignment_breakdown_121"] = (
        df["typewell_alignment_error_roll_121"] * (1.0 + df["neraium_gr_drift_roll_121"].clip(lower=0))
    )
    df["neraium_transition_pressure"] = (
        df["neraium_drift_velocity"].abs()
        + df["neraium_alignment_velocity"].abs()
        + df["gr_volatility_shift_31_121"].abs()
    )
    df["neraium_state_pressure"] = (
        0.35 * df["neraium_drift_pressure"].abs()
        + 0.35 * df["neraium_alignment_breakdown"].abs()
        + 0.30 * df["neraium_transition_pressure"].abs()
    )

    pressure_roll = df["neraium_state_pressure"].rolling(121, min_periods=10).mean()
    pressure_scale = pressure_roll.abs().rolling(301, min_periods=10).median().replace(0, np.nan)
    if pressure_scale.isna().all():
        pressure_scale = pd.Series(np.ones(len(df)), index=df.index)
    else:
        pressure_scale = pressure_scale.fillna(pressure_scale.median())

    df["neraium_state_pressure_norm"] = df["neraium_state_pressure"] / (pressure_scale + eps)
    df["neraium_stable_confidence"] = 1.0 / (1.0 + df["neraium_state_pressure_norm"].abs())
    df["neraium_watch_pressure"] = (
        (df["neraium_state_pressure_norm"].abs() > 1.0).astype(int).rolling(61, min_periods=5).mean()
    )
    df["neraium_alert_pressure"] = (
        (df["neraium_state_pressure_norm"].abs() > 2.0).astype(int).rolling(121, min_periods=10).mean()
    )
    df["neraium_persistent_alignment_loss"] = (
        (df["neraium_gr_drift_roll_121"] > 1.0).astype(int).rolling(121, min_periods=10).mean()
    )
    df["neraium_system_instability"] = (
        0.40 * df["neraium_alert_pressure"]
        + 0.35 * df["neraium_watch_pressure"]
        + 0.25 * df["neraium_persistent_alignment_loss"]
    )

    return df.replace([np.inf, -np.inf], np.nan).fillna(0)


# ---------------- FEATURE LIST ----------------
feature_cols = [
    "MD", "X", "Y", "Z", "GR", "row_idx",
    "md_delta", "z_delta", "gr_delta", "gr_abs_delta",
    "gr_gradient", "gr_gradient_abs", "gr_curvature", "z_gradient",
    "gr_velocity_3", "gr_velocity_5", "gr_velocity_10", "gr_velocity_20",
    "gr_acceleration_3", "gr_acceleration_5", "gr_acceleration_10", "gr_acceleration_20",
    "z_velocity_5", "z_acceleration_5",
    "gr_cumsum", "gr_cumsum_50",
    "TVT_input_ffill", "TVT_input_bfill", "has_tvt_input",
    "last_known_tvt", "last_known_md", "last_known_z", "last_known_gr",
    "rows_after_known_tvt", "md_after_known", "z_after_known", "gr_after_known",
    "known_tvt_slope", "linear_tvt_est", "linear_tvt_residual_proxy",
    "gr_structural_shift_31_121", "z_structural_shift_31_121", "gr_volatility_shift_31_121",
    "best_shift", "best_shift_corr", "well_offset", "inv_dist_to_known",
    "typewell_gr_at_est", "gr_minus_typewell", "typewell_alignment_error",
    "typewell_out_of_range", "typewell_confidence",
    "typewell_alignment_error_roll_31", "typewell_alignment_error_roll_121",
    "neraium_gr_z", "neraium_gr_drift_abs", "neraium_gr_drift_roll_31",
    "neraium_gr_drift_roll_121", "neraium_drift_persistence",
    "neraium_drift_pressure", "neraium_drift_velocity", "neraium_alignment_velocity",
    "neraium_alignment_breakdown", "neraium_alignment_breakdown_121",
    "neraium_transition_pressure", "neraium_state_pressure",
    "neraium_state_pressure_norm", "neraium_stable_confidence",
    "neraium_watch_pressure", "neraium_alert_pressure",
    "neraium_persistent_alignment_loss", "neraium_system_instability",
]
for lag in [1, 2, 3, 5, 10, 20, 50]:
    feature_cols += [f"GR_lag_{lag}", f"Z_lag_{lag}", f"GR_diff_lag_{lag}"]
for w in [5, 15, 31, 61, 121]:
    feature_cols += [
        f"gr_roll_mean_{w}", f"gr_roll_std_{w}", f"gr_roll_min_{w}",
        f"gr_roll_max_{w}", f"gr_roll_range_{w}", f"z_roll_mean_{w}",
        f"z_roll_std_{w}", f"gr_abs_delta_roll_{w}",
    ]
for off in [-100, -60, -30, -15, -8, -4, 0, 4, 8, 15, 30, 60, 100]:
    feature_cols += [f"tw_gr_{off}", f"gr_diff_tw_{off}"]
for w in [30, 60, 120]:
    feature_cols += [f"tw_slope_{w}"]
feature_cols = list(dict.fromkeys(feature_cols))


# ---------------- WELL OFFSETS ----------------
print("Computing well offsets ...")
raw_train_files = sorted(glob.glob(f"{TRAIN_DIR}/*__horizontal_well.csv"))
well_offsets = {}
for fp in raw_train_files:
    well_name = os.path.basename(fp).split("__")[0]
    df_tmp = pd.read_csv(fp)
    if "TVT" in df_tmp.columns:
        valid = df_tmp["TVT"].dropna()
        if len(valid) > 0:
            well_offsets[well_name] = float(valid.mean() - 11502.884013)
    del df_tmp
    gc.collect()


# ---------------- TRAINING SCENARIOS ----------------
scenario_specs = []
total_rows = 0
print("Planning training scenarios ...")
for fp in raw_train_files:
    well = os.path.basename(fp).split("__")[0]
    try:
        df_raw = pd.read_csv(fp)
    except Exception as e:
        print(f"Failed to read {fp}: {e}")
        continue
    if "TVT" not in df_raw.columns:
        del df_raw
        continue

    for hide_frac in TRAIN_HIDE_FRACS:
        scenario = make_hidden_tail_scenario(df_raw, hide_frac)
        if scenario is None:
            continue
        _, hidden_mask, _ = scenario
        n_hidden = int(hidden_mask.sum())
        if n_hidden < 3:
            continue
        scenario_specs.append((fp, well, hide_frac, n_hidden))
        total_rows += n_hidden

    del df_raw
    gc.collect()

print(f"Total simulated hidden-tail rows: {total_rows}")
print(f"Scenario count: {len(scenario_specs)}")

if total_rows == 0:
    print("No training scenarios were created.")
    print(f"TRAIN_DIR: {TRAIN_DIR}")
    print(f"Found train files: {len(raw_train_files)}")
    for fp in raw_train_files[:5]:
        try:
            tmp = pd.read_csv(fp, nrows=5)
            print(f"{os.path.basename(fp)} -> columns: {list(tmp.columns)}")
        except Exception as e:
            print(f"{os.path.basename(fp)} -> read failed: {e}")
    raise RuntimeError(
        "total_rows == 0. No valid hidden-tail training scenarios were generated."
    )


# ---------------- MEMORY-MAPPED TRAIN MATRIX ----------------
X_mmap = np.memmap(
    os.path.join(MEMORY_DIR, "X.dat"),
    dtype=np.float32,
    mode="w+",
    shape=(total_rows, len(feature_cols)),
)
y_mmap = np.memmap(
    os.path.join(MEMORY_DIR, "y.dat"),
    dtype=np.float32,
    mode="w+",
    shape=(total_rows,),
)
lin_mmap = np.memmap(
    os.path.join(MEMORY_DIR, "linear.dat"),
    dtype=np.float32,
    mode="w+",
    shape=(total_rows,),
)
wt_mmap = np.memmap(
    os.path.join(MEMORY_DIR, "wt.dat"),
    dtype=np.float32,
    mode="w+",
    shape=(total_rows,),
)
rows_after_mmap = np.memmap(
    os.path.join(MEMORY_DIR, "rows_after.dat"),
    dtype=np.float32,
    mode="w+",
    shape=(total_rows,),
)

scenario_group_names = []
well_group_names = []

row_start = 0
print("Building train matrix ...")
for fp, well, hide_frac, _ in scenario_specs:
    df_raw = pd.read_csv(fp)
    scenario = make_hidden_tail_scenario(df_raw, hide_frac)
    if scenario is None:
        del df_raw
        continue

    df_s, hidden_mask, _ = scenario
    df_s["well"] = well
    tw = load_typewell(well, TRAIN_DIR)
    feat_df = add_features_neraium_max(df_s, tw, well_offsets)
    train_df = feat_df.loc[hidden_mask].copy()

    if len(train_df) == 0:
        del df_raw, df_s, feat_df, train_df
        gc.collect()
        continue

    for c in feature_cols:
        if c not in train_df.columns:
            train_df[c] = 0.0

    n = len(train_df)
    scenario_name = f"{well}__hide_{int(hide_frac * 100)}"

    X_mmap[row_start:row_start + n] = train_df[feature_cols].values.astype(np.float32)
    y_mmap[row_start:row_start + n] = (
        train_df["TVT"].values.astype(np.float32)
        - train_df["linear_tvt_est"].values.astype(np.float32)
    )
    lin_mmap[row_start:row_start + n] = train_df["linear_tvt_est"].values.astype(np.float32)
    rows_after_mmap[row_start:row_start + n] = train_df["rows_after_known_tvt"].values.astype(np.float32)

    tail_weight = 1.0 + 0.0032 * np.clip(train_df["rows_after_known_tvt"].values, 0, 600)
    stability = train_df["neraium_stable_confidence"].clip(0.25, 1.0).values
    state_pressure = 1.0 + 0.15 * np.clip(train_df["neraium_watch_pressure"].values, 0, 1)
    final_weight = 0.55 * tail_weight + 0.30 * stability + 0.15 * state_pressure
    wt_mmap[row_start:row_start + n] = final_weight.astype(np.float32)

    scenario_group_names.extend([scenario_name] * n)
    well_group_names.extend([well] * n)
    row_start += n

    del df_raw, df_s, feat_df, train_df
    gc.collect()

well_ids, _ = pd.factorize(well_group_names)
well_ids = np.asarray(well_ids, dtype=np.int32)
del scenario_group_names, well_group_names
gc.collect()


# ---------------- FEATURE SELECTION ----------------
sample_size = min(200_000, total_rows)
sample_idx = np.random.RandomState(RANDOM_STATE).choice(total_rows, size=sample_size, replace=False)

temp = LGBMRegressor(
    n_estimators=250,
    learning_rate=0.05,
    num_leaves=31,
    random_state=RANDOM_STATE,
    n_jobs=-1,
    force_col_wise=True,
    **lgbm_params,
)
temp.fit(X_mmap[sample_idx], y_mmap[sample_idx], sample_weight=wt_mmap[sample_idx])

imp = pd.Series(temp.feature_importances_, index=feature_cols).sort_values(ascending=False)
keep = imp.index[imp.cumsum() / max(imp.sum(), 1.0) <= 0.995].tolist()
for ess in [
    "MD", "Z", "GR", "linear_tvt_est", "best_shift", "best_shift_corr",
    "well_offset", "inv_dist_to_known", "rows_after_known_tvt", "known_tvt_slope"
]:
    if ess not in keep:
        keep.append(ess)
keep_idx = np.array([feature_cols.index(f) for f in keep], dtype=np.int32)
print(f"Selected {len(keep_idx)} features")


# ---------------- MODEL BUILDERS ----------------
def build_lgb1(seed):
    return LGBMRegressor(
        n_estimators=2900,
        learning_rate=0.0125,
        num_leaves=100,
        subsample=0.82,
        colsample_bytree=0.72,
        min_child_samples=40,
        lambda_l1=0.08,
        lambda_l2=0.25,
        random_state=seed,
        n_jobs=-1,
        force_col_wise=True,
        **lgbm_params,
    )


def build_lgb2(seed):
    return LGBMRegressor(
        n_estimators=3500,
        learning_rate=0.0100,
        num_leaves=132,
        subsample=0.87,
        colsample_bytree=0.66,
        min_child_samples=55,
        lambda_l1=0.04,
        lambda_l2=0.18,
        random_state=seed,
        n_jobs=-1,
        force_col_wise=True,
        **lgbm_params,
    )


def build_xgb1(seed):
    return XGBRegressor(
        n_estimators=2900,
        learning_rate=0.020,
        max_depth=5,
        subsample=0.82,
        colsample_bytree=0.76,
        reg_lambda=0.75,
        reg_alpha=0.04,
        random_state=seed,
        n_jobs=-1,
        verbosity=0,
        **xgb_params,
    )


def build_xgb2(seed):
    return XGBRegressor(
        n_estimators=3500,
        learning_rate=0.0170,
        max_depth=4,
        subsample=0.90,
        colsample_bytree=0.82,
        reg_lambda=0.45,
        reg_alpha=0.02,
        random_state=seed,
        n_jobs=-1,
        verbosity=0,
        **xgb_params,
    )


# ---------------- OOF BASE MODELS ----------------
n_folds = 3
gkf = GroupKFold(n_splits=n_folds)
oof_a = np.zeros(total_rows, dtype=np.float32)
oof_b = np.zeros(total_rows, dtype=np.float32)
oof_c = np.zeros(total_rows, dtype=np.float32)
oof_d = np.zeros(total_rows, dtype=np.float32)

print("Training OOF base models ...")
for fold, (tr_idx, va_idx) in enumerate(gkf.split(np.zeros(total_rows), y_mmap, groups=well_ids)):
    print(f"Fold {fold + 1}/{n_folds}")

    X_tr = X_mmap[tr_idx][:, keep_idx]
    X_va = X_mmap[va_idx][:, keep_idx]
    y_tr = y_mmap[tr_idx]
    y_va = y_mmap[va_idx]
    w_tr = wt_mmap[tr_idx]

    m_a = build_lgb1(RANDOM_STATE + fold)
    m_b = build_lgb2(RANDOM_STATE + 7 + fold)
    m_c = build_xgb1(RANDOM_STATE + 13 + fold)
    m_d = build_xgb2(RANDOM_STATE + 17 + fold)

    m_a.fit(
        X_tr, y_tr,
        sample_weight=w_tr,
        eval_set=[(X_va, y_va)],
        eval_metric="rmse",
        callbacks=[early_stopping(120, verbose=False)],
    )
    m_b.fit(
        X_tr, y_tr,
        sample_weight=w_tr,
        eval_set=[(X_va, y_va)],
        eval_metric="rmse",
        callbacks=[early_stopping(140, verbose=False)],
    )

    m_c.set_params(early_stopping_rounds=80)
    m_d.set_params(early_stopping_rounds=80)
    m_c.fit(X_tr, y_tr, sample_weight=w_tr, eval_set=[(X_va, y_va)], verbose=False)
    m_d.fit(X_tr, y_tr, sample_weight=w_tr, eval_set=[(X_va, y_va)], verbose=False)

    oof_a[va_idx] = m_a.predict(X_va).astype(np.float32)
    oof_b[va_idx] = m_b.predict(X_va).astype(np.float32)
    oof_c[va_idx] = m_c.predict(X_va).astype(np.float32)
    oof_d[va_idx] = m_d.predict(X_va).astype(np.float32)

    del X_tr, X_va, y_tr, y_va, w_tr, m_a, m_b, m_c, m_d
    gc.collect()


# ---------------- DUAL META ----------------
stacked = np.column_stack([oof_a, oof_b, oof_c, oof_d, lin_mmap]).astype(np.float32)
scaler = StandardScaler()
stacked_scaled = scaler.fit_transform(stacked)

near_mask = rows_after_mmap <= META_NEAR_THRESHOLD
far_mask = rows_after_mmap > META_NEAR_THRESHOLD

meta_near = Ridge(alpha=0.08)
meta_far = Ridge(alpha=0.12)

if near_mask.sum() > 100:
    meta_near.fit(stacked_scaled[near_mask], y_mmap[near_mask])
else:
    meta_near.fit(stacked_scaled, y_mmap)

if far_mask.sum() > 100:
    meta_far.fit(stacked_scaled[far_mask], y_mmap[far_mask])
else:
    meta_far.fit(stacked_scaled, y_mmap)

oof_meta = np.zeros(total_rows, dtype=np.float32)
oof_meta[near_mask] = meta_near.predict(stacked_scaled[near_mask]).astype(np.float32)
oof_meta[far_mask] = meta_far.predict(stacked_scaled[far_mask]).astype(np.float32)

base_rmse = rmse(lin_mmap + y_mmap, lin_mmap + oof_meta)
print(f"OOF RMSE with dual meta: {base_rmse:.4f}")


# ---------------- FINAL MODELS ----------------
print("Training final models ...")
X_full = X_mmap[:, keep_idx]
y_full = y_mmap
w_full = wt_mmap

model_a = build_lgb1(RANDOM_STATE)
model_b = build_lgb2(RANDOM_STATE + 7)
model_c = build_xgb1(RANDOM_STATE + 13)
model_d = build_xgb2(RANDOM_STATE + 17)

model_a.fit(X_full, y_full, sample_weight=w_full)
model_b.fit(X_full, y_full, sample_weight=w_full)
model_c.fit(X_full, y_full, sample_weight=w_full, verbose=False)
model_d.fit(X_full, y_full, sample_weight=w_full, verbose=False)

del X_full, y_full, w_full
gc.collect()


# ---------------- INFERENCE HELPERS ----------------
def estimate_recent_known_bias(feat_df, window=12):
    known = feat_df["TVT_input"].notna()
    if known.sum() < 3:
        return 0.0
    recent = feat_df.loc[known].tail(window)
    if len(recent) == 0:
        return 0.0
    bias = (recent["TVT_input"] - recent["linear_tvt_est"]).median()
    if not np.isfinite(bias):
        return 0.0
    return float(np.clip(bias, -250.0, 250.0))


def predict_dual_meta_residual(linear_est, rows_after, pa, pb, pc, pd_):
    stacked_block = np.column_stack([pa, pb, pc, pd_, linear_est]).astype(np.float32)
    stacked_block_scaled = scaler.transform(stacked_block)

    out = np.zeros(len(linear_est), dtype=np.float32)
    near = rows_after <= META_NEAR_THRESHOLD
    far = ~near

    if near.any():
        out[near] = meta_near.predict(stacked_block_scaled[near]).astype(np.float32)
    if far.any():
        out[far] = meta_far.predict(stacked_block_scaled[far]).astype(np.float32)
    return out


def predict_rollout_style(df_raw, tw, alpha, direct_blend, chunk_size, bias_scale):
    working = df_raw.copy()
    if "TVT_input" not in working.columns:
        working["TVT_input"] = np.nan

    pred_tvt = np.full(len(working), np.nan, dtype=np.float32)
    known_mask = working["TVT_input"].notna().values

    if known_mask.any():
        pred_tvt[known_mask] = working.loc[known_mask, "TVT_input"].values.astype(np.float32)
        start_idx = int(np.where(known_mask)[0].max()) + 1
    else:
        start_idx = 0

    unknown_idx = np.arange(start_idx, len(working), dtype=int)
    if len(unknown_idx) == 0:
        return pred_tvt

    prev_prop = 0.0
    for block_start in range(0, len(unknown_idx), chunk_size):
        block = unknown_idx[block_start:block_start + chunk_size]

        feat_df = add_features_neraium_max(working.copy(), tw, well_offsets)
        for c in feature_cols:
            if c not in feat_df.columns:
                feat_df[c] = 0.0

        local_bias = estimate_recent_known_bias(feat_df, window=12)
        X_block = feat_df.loc[block, feature_cols].values.astype(np.float32)
        linear_block = feat_df.loc[block, "linear_tvt_est"].values.astype(np.float32)
        rows_after = feat_df.loc[block, "rows_after_known_tvt"].values.astype(np.float32)

        pa = model_a.predict(X_block[:, keep_idx]).astype(np.float32)
        pb = model_b.predict(X_block[:, keep_idx]).astype(np.float32)
        pc = model_c.predict(X_block[:, keep_idx]).astype(np.float32)
        pd_ = model_d.predict(X_block[:, keep_idx]).astype(np.float32)
        direct_residual = predict_dual_meta_residual(linear_block, rows_after, pa, pb, pc, pd_)

        for j, row_idx in enumerate(block):
            prev_prop = alpha * direct_residual[j] + (1.0 - alpha) * prev_prop
            decay = np.exp(-rows_after[j] / 220.0)
            local_bias_term = bias_scale * local_bias * decay
            pred = linear_block[j] + ((1.0 - direct_blend) * prev_prop + direct_blend * direct_residual[j])
            pred = pred + local_bias_term
            pred = float(np.clip(pred, TVT_CLIP_MIN, TVT_CLIP_MAX))

            working.at[row_idx, "TVT_input"] = pred
            pred_tvt[row_idx] = pred

        del feat_df, X_block, linear_block, rows_after, pa, pb, pc, pd_, direct_residual
        gc.collect()

    return pred_tvt


def smooth_1d(x, window, mix):
    x = np.asarray(x, dtype=np.float32)
    if window <= 1 or mix <= 0:
        return x
    sm = pd.Series(x).rolling(window, min_periods=1, center=True).mean().values.astype(np.float32)
    return ((1.0 - mix) * x + mix * sm).astype(np.float32)


def run_backtest_case(df_raw, well, hide_frac, params):
    scenario = make_hidden_tail_scenario(df_raw, hide_frac)
    if scenario is None:
        return None
    df_bt, hidden_mask, _ = scenario
    df_bt["well"] = well
    tw = load_typewell(well, TRAIN_DIR)

    preds = predict_rollout_style(
        df_raw=df_bt,
        tw=tw,
        alpha=params["alpha"],
        direct_blend=params["direct_blend"],
        chunk_size=params["chunk_size"],
        bias_scale=params["bias_scale"],
    )

    true_vals = df_bt.loc[hidden_mask, "TVT"].values.astype(np.float32)
    pred_vals = preds[hidden_mask].astype(np.float32)
    pred_vals = smooth_1d(pred_vals, params["smooth_window"], params["smooth_mix"])
    pred_vals = np.clip(pred_vals, TVT_CLIP_MIN, TVT_CLIP_MAX)
    return rmse(true_vals, pred_vals)


# ---------------- BACKTEST TUNING ----------------
print("Preparing real backtest wells ...")
backtest_wells = []
for fp in raw_train_files:
    well = os.path.basename(fp).split("__")[0]
    df_raw = pd.read_csv(fp)
    if "TVT" not in df_raw.columns:
        continue
    valid = df_raw["TVT"].notna().sum()
    if valid >= 80:
        backtest_wells.append((well, fp, valid))

backtest_wells = sorted(backtest_wells, key=lambda x: -x[2])[:BACKTEST_MAX_WELLS]
print(f"Backtesting on {len(backtest_wells)} wells")

param_grid = []
for alpha in [0.55, 0.68, 0.80]:
    for direct_blend in [0.10, 0.20, 0.30]:
        for chunk_size in [12, 24, 36]:
            for bias_scale in [0.0, 0.15, 0.30]:
                for smooth_window in [7, 11, 21]:
                    for smooth_mix in [0.0, 0.15, 0.30]:
                        param_grid.append({
                            "alpha": alpha,
                            "direct_blend": direct_blend,
                            "chunk_size": chunk_size,
                            "bias_scale": bias_scale,
                            "smooth_window": smooth_window,
                            "smooth_mix": smooth_mix,
                        })

best_params = None
best_score = 1e18
print(f"Tuning {len(param_grid)} backtest configs ...")
for params in param_grid:
    scores = []
    for well, fp, _ in backtest_wells:
        df_raw = pd.read_csv(fp)
        for hide_frac in BACKTEST_HIDE_FRACS:
            score = run_backtest_case(df_raw, well, hide_frac, params)
            if score is not None and np.isfinite(score):
                scores.append(score)
        del df_raw
        gc.collect()

    if not scores:
        continue
    mean_score = float(np.mean(scores))
    if mean_score < best_score:
        best_score = mean_score
        best_params = params.copy()
        print(f"New best: {best_score:.4f} with {best_params}")

if best_params is None:
    best_params = {
        "alpha": 0.68,
        "direct_blend": 0.20,
        "chunk_size": 24,
        "bias_scale": 0.15,
        "smooth_window": 11,
        "smooth_mix": 0.15,
    }
    print("Backtest tuning found no valid scores; using fallback params.")

print(f"Best backtest score: {best_score:.4f}")
print(f"Best params: {best_params}")


# ---------------- TEST PREDICTION ----------------
sample = pd.read_csv(SAMPLE_SUB)
sample[["well", "row_index"]] = sample["id"].str.extract(r"^(.+)_([0-9]+)$")
sample["row_index"] = sample["row_index"].astype(int)

sub = sample[["id"]].copy()
sub["tvt"] = np.nan

test_files = {
    os.path.basename(p).split("__")[0]: p
    for p in glob.glob(f"{TEST_DIR}/*__horizontal_well.csv")
}
fallback = 11502.884013

print("Predicting test wells ...")
for well, grp in sample.groupby("well", sort=False):
    if well not in test_files:
        continue

    print(f"  {well}")
    df = pd.read_csv(test_files[well])
    df["well"] = well
    if "TVT_input" not in df.columns:
        df["TVT_input"] = np.nan
    tw = load_typewell(well, TEST_DIR)

    preds = predict_rollout_style(
        df_raw=df,
        tw=tw,
        alpha=best_params["alpha"],
        direct_blend=best_params["direct_blend"],
        chunk_size=best_params["chunk_size"],
        bias_scale=best_params["bias_scale"],
    )

    if np.isnan(preds).any():
        feat_df = add_features_neraium_max(df.copy(), tw, well_offsets)
        for c in feature_cols:
            if c not in feat_df.columns:
                feat_df[c] = 0.0

        local_bias = estimate_recent_known_bias(feat_df, window=12)
        X_test = feat_df[feature_cols].values.astype(np.float32)
        linear_est = feat_df["linear_tvt_est"].values.astype(np.float32)
        rows_after = feat_df["rows_after_known_tvt"].values.astype(np.float32)

        pa = model_a.predict(X_test[:, keep_idx]).astype(np.float32)
        pb = model_b.predict(X_test[:, keep_idx]).astype(np.float32)
        pc = model_c.predict(X_test[:, keep_idx]).astype(np.float32)
        pd_ = model_d.predict(X_test[:, keep_idx]).astype(np.float32)
        direct_res = predict_dual_meta_residual(linear_est, rows_after, pa, pb, pc, pd_)

        decay = np.exp(-rows_after / 220.0).astype(np.float32)
        direct_pred = linear_est + direct_res + best_params["bias_scale"] * local_bias * decay
        fill_mask = np.isnan(preds)
        preds[fill_mask] = direct_pred[fill_mask]

        del feat_df, X_test, linear_est, rows_after, pa, pb, pc, pd_, direct_res, decay, direct_pred
        gc.collect()

    sidx = grp.sort_values("row_index").index
    ridx = grp.loc[sidx, "row_index"].values
    safe = np.clip(ridx, 0, len(preds) - 1)
    raw = preds[safe].astype(np.float32)
    final = smooth_1d(raw, best_params["smooth_window"], best_params["smooth_mix"])
    final = np.clip(final, TVT_CLIP_MIN, TVT_CLIP_MAX)

    sub.loc[grp.index, "tvt"] = sub.loc[grp.index].index.map(dict(zip(sidx, final)))

sub["tvt"] = sub["tvt"].fillna(sub["tvt"].median() if sub["tvt"].notna().any() else fallback)
sub.to_csv("/kaggle/working/submission.csv", index=False)

print("Submission saved:", sub.shape)
print("Best params used:", best_params)
