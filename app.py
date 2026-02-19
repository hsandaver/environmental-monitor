import io
import json
import math
import os
import uuid
import urllib.parse
import urllib.request
from datetime import datetime, date
from typing import Optional

import pandas as pd
import streamlit as st
import altair as alt
from pandas.errors import EmptyDataError

try:
    import boto3
    from botocore.config import Config as BotoConfig
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    BotoConfig = None
    ClientError = Exception

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "measurements.csv")
SPACES_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "data", "spaces_config.json")
DEFAULT_SPACES_REGION = "nyc3"
DEFAULT_SPACES_OBJECT_KEY = "environmental-monitor/measurements.csv"

LOCATIONS = [
    "Special Collections Room",
    "Special Collections Storage",
    "Compactus",
    "Workroom",
]

GUIDELINES = {
    "temp": {"min": 15, "max": 25, "delta": 4},
    "rh": {"core": (45, 55), "outer": (40, 60), "delta": 5},
}

OUTSIDE_LOCATION = "East Melbourne, VIC"
OUTSIDE_LAT = -37.813
OUTSIDE_LON = 144.985
OUTSIDE_TZ = "Australia/Melbourne"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OUTSIDE_TEMP_DELTA_WARN = 6.0
OUTSIDE_RH_DELTA_WARN = 15.0


st.set_page_config(
    page_title="Special Collections Environmental Monitoring",
    page_icon="CL",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,300;9..144,500;9..144,700&family=Public+Sans:wght@300;400;500;600;700&family=Space+Mono:wght@400;700&display=swap');

        :root {
            --bg-cream: #f5efe3;
            --bg-sage: #dce8df;
            --ink: #102129;
            --muted: #455960;
            --line: rgba(16, 33, 41, 0.16);
            --surface: rgba(255, 255, 255, 0.78);
            --surface-strong: rgba(255, 255, 255, 0.92);
            --shadow: 0 22px 52px rgba(15, 23, 29, 0.14);
            --accent: #bb6437;
            --accent-soft: rgba(187, 100, 55, 0.18);
            --signal: #1d6f6f;
            --signal-soft: rgba(29, 111, 111, 0.17);
            --warning: #b05717;
            --warning-soft: rgba(176, 87, 23, 0.16);
            --danger: #822f33;
            --danger-soft: rgba(130, 47, 51, 0.17);
        }

        html, body, [class*="css"] {
            font-family: 'Public Sans', sans-serif;
            color: var(--ink);
        }

        body, .stApp, [data-testid="stAppViewContainer"] {
            background:
                radial-gradient(65rem 36rem at 4% -2%, rgba(255, 255, 255, 0.92) 0%, transparent 70%),
                radial-gradient(48rem 28rem at 98% 10%, rgba(68, 132, 119, 0.22) 0%, transparent 76%),
                linear-gradient(138deg, var(--bg-cream) 0%, var(--bg-sage) 52%, #f3efe6 100%);
            background-attachment: fixed;
        }

        .stApp {
            color: var(--ink);
        }

        [data-testid="stAppViewContainer"] > .main {
            background: transparent;
        }

        .block-container {
            max-width: min(1720px, 96vw);
            padding-top: 2.25rem;
            padding-bottom: 1.8rem;
        }

        div[data-testid="stVerticalBlock"] {
            gap: 0.78rem;
        }

        h1, h2, h3, .fraunces {
            font-family: 'Fraunces', serif;
            color: var(--ink);
        }

        h1 {
            margin-top: 0.2rem;
            margin-bottom: 0.4rem;
            font-size: clamp(1.8rem, 2.4vw, 2.8rem);
            line-height: 1.18;
            letter-spacing: -0.01em;
            padding-top: 0.06em;
            overflow: visible;
        }

        h2 {
            margin-top: 0.2rem;
            margin-bottom: 0.4rem;
        }

        p {
            color: var(--muted);
        }

        hr {
            border: none;
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(17, 33, 41, 0.25), transparent);
            margin: 1.1rem 0;
        }

        .eyebrow {
            text-transform: uppercase;
            letter-spacing: 0.26em;
            font-size: 0.7rem;
            color: var(--muted);
            margin-bottom: 0.28rem;
            font-weight: 600;
        }

        .hero-summary {
            font-size: 1rem;
            max-width: 64ch;
            margin: 0.3rem 0 0.8rem;
            color: #32444b;
        }

        .hero-card {
            background:
                linear-gradient(155deg, rgba(255, 255, 255, 0.96) 0%, rgba(248, 251, 249, 0.86) 100%);
            border: 1px solid var(--line);
            border-radius: 20px;
            padding: 1.15rem 1.25rem;
            box-shadow: var(--shadow);
            backdrop-filter: blur(5px);
            transition: transform 180ms ease, box-shadow 180ms ease;
        }

        .hero-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 26px 58px rgba(15, 23, 29, 0.16);
        }

        .hero-card .hero-card-title {
            font-family: 'Fraunces', serif;
            font-weight: 600;
            margin-bottom: 0.5rem;
            line-height: 1.28;
            padding-top: 0.18rem;
            overflow: visible;
        }

        .metric-label {
            font-size: 0.71rem;
            letter-spacing: 0.16em;
            text-transform: uppercase;
            color: var(--muted);
            margin-bottom: 0.18rem;
            font-weight: 600;
        }

        .metric-value {
            font-family: 'Space Mono', monospace;
            font-size: 1.08rem;
            margin: 0;
            color: #1a2c33;
        }

        .status-card {
            background: var(--surface-strong);
            border: 1px solid var(--line);
            border-left: 4px solid transparent;
            border-radius: 16px;
            padding: 0.9rem 0.95rem;
            box-shadow: 0 12px 24px rgba(16, 22, 26, 0.09);
            min-height: 170px;
        }

        .status-card.state-core { border-left-color: var(--signal); }
        .status-card.state-outer { border-left-color: var(--warning); }
        .status-card.state-out { border-left-color: var(--danger); }
        .status-card.state-awaiting { border-left-color: rgba(69, 89, 96, 0.45); }

        .status-card-title {
            font-weight: 600;
            font-size: 0.95rem;
            margin-bottom: 0.18rem;
        }

        .status-card-meta,
        .status-card-delta {
            color: var(--muted);
            font-size: 0.82rem;
        }

        .status-card-reading {
            color: #20343a;
            font-size: 0.9rem;
            margin: 0.2rem 0 0.35rem;
            font-family: 'Space Mono', monospace;
        }

        .status-flags {
            margin-top: 0.45rem;
        }

        .stat-card {
            background:
                linear-gradient(155deg, rgba(255, 255, 255, 0.95) 0%, rgba(244, 248, 246, 0.8) 100%);
            border: 1px solid var(--line);
            border-radius: 14px;
            padding: 0.82rem 1rem;
            box-shadow: 0 14px 28px rgba(16, 22, 26, 0.08);
            min-height: 98px;
        }

        .stat-label {
            font-size: 0.68rem;
            letter-spacing: 0.15em;
            text-transform: uppercase;
            color: var(--muted);
            margin-bottom: 0.25rem;
            font-weight: 700;
        }

        .stat-value {
            font-family: 'Space Mono', monospace;
            font-size: 1rem;
            line-height: 1.35;
        }

        .stat-helper {
            color: var(--muted);
            font-size: 0.78rem;
            margin-top: 0.2rem;
        }

        .chip {
            display: inline-flex;
            align-items: center;
            padding: 0.24rem 0.58rem;
            border-radius: 999px;
            font-size: 0.68rem;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            font-weight: 700;
            margin-top: 0.34rem;
        }

        .chip.core { background: var(--signal-soft); color: var(--signal); }
        .chip.outer { background: var(--warning-soft); color: var(--warning); }
        .chip.out { background: var(--danger-soft); color: var(--danger); }
        .chip.awaiting { background: rgba(69, 89, 96, 0.14); color: #445960; }

        .flag {
            display: inline-block;
            padding: 0.2rem 0.5rem;
            border-radius: 999px;
            font-size: 0.64rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin-right: 0.28rem;
            margin-bottom: 0.22rem;
            background: rgba(17, 33, 41, 0.09);
            color: #31464d;
            font-weight: 600;
        }

        .flag.warn { background: var(--warning-soft); color: var(--warning); }
        .flag.danger { background: var(--danger-soft); color: var(--danger); }

        .lens-card {
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: 16px;
            padding: 1rem 1rem 1.05rem;
            box-shadow: 0 12px 24px rgba(16, 22, 26, 0.08);
            height: 100%;
        }

        .lens-card-title {
            font-family: 'Fraunces', serif;
            font-size: 1.02rem;
            margin-bottom: 0.35rem;
        }

        .lens-card-copy {
            color: var(--muted);
            font-size: 0.88rem;
            line-height: 1.45;
        }

        div[data-testid="stExpander"] {
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: 16px;
        }

        div[data-testid="stExpander"] details summary p {
            font-weight: 600;
            color: #1e333a;
        }

        .stButton > button,
        .stDownloadButton > button {
            border-radius: 12px;
            border: 1px solid rgba(17, 33, 41, 0.24);
            background: linear-gradient(160deg, #fafcfa 0%, #ebf1ef 100%);
            color: #15272e;
            font-weight: 600;
            transition: transform 140ms ease, box-shadow 140ms ease, border-color 140ms ease;
        }

        .stButton > button:hover,
        .stDownloadButton > button:hover {
            transform: translateY(-1px);
            border-color: rgba(187, 100, 55, 0.7);
            box-shadow: 0 10px 18px rgba(16, 22, 26, 0.12);
            color: #1b3037;
        }

        .stButton > button:focus:not(:active),
        .stDownloadButton > button:focus:not(:active) {
            border-color: var(--accent);
            box-shadow: 0 0 0 0.14rem rgba(187, 100, 55, 0.28);
        }

        div[data-baseweb="input"] > div,
        div[data-baseweb="textarea"] > div,
        div[data-baseweb="select"] > div {
            background: rgba(255, 255, 255, 0.9);
            border: 1px solid rgba(16, 33, 41, 0.2);
            border-radius: 12px;
        }

        div[data-baseweb="input"] > div:focus-within,
        div[data-baseweb="textarea"] > div:focus-within,
        div[data-baseweb="select"] > div:focus-within {
            border-color: rgba(187, 100, 55, 0.7);
            box-shadow: 0 0 0 0.12rem rgba(187, 100, 55, 0.26);
        }

        div[data-testid="stTabs"] [data-baseweb="tab-list"] {
            gap: 0.4rem;
            border-bottom: none;
            background: rgba(255, 255, 255, 0.62);
            border: 1px solid var(--line);
            border-radius: 999px;
            padding: 0.3rem;
            width: fit-content;
            box-shadow: 0 8px 16px rgba(16, 22, 26, 0.08);
        }

        button[data-baseweb="tab"] {
            border-radius: 999px;
            border: 1px solid transparent;
            padding: 0.4rem 0.85rem;
            font-weight: 600;
            color: #31454c;
            background: transparent;
        }

        button[data-baseweb="tab"][aria-selected="true"] {
            background: linear-gradient(160deg, rgba(29, 111, 111, 0.2) 0%, rgba(72, 163, 166, 0.15) 100%);
            color: #1d3f46;
            border-color: rgba(29, 111, 111, 0.35);
        }

        div[data-testid="stDataFrame"] {
            border: 1px solid var(--line);
            border-radius: 14px;
            overflow: hidden;
            box-shadow: 0 12px 24px rgba(16, 22, 26, 0.08);
            background: rgba(255, 255, 255, 0.88);
        }

        @media (max-width: 1024px) {
            .block-container {
                max-width: 98vw;
                padding-top: 1.5rem;
            }

            .hero-card,
            .status-card,
            .stat-card {
                padding: 0.88rem;
            }

            .status-card {
                min-height: 0;
            }

            h1 {
                font-size: clamp(1.6rem, 4.5vw, 2.2rem);
            }
        }

        @media (max-width: 740px) {
            .eyebrow {
                letter-spacing: 0.18em;
            }

            .hero-summary {
                font-size: 0.95rem;
            }

            div[data-testid="stTabs"] [data-baseweb="tab-list"] {
                width: 100%;
            }

            button[data-baseweb="tab"] {
                flex: 1 1 auto;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def empty_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "id",
            "datetime",
            "location",
            "temp_c",
            "rh",
            "lux",
            "uv",
            "co2",
            "outside_time",
            "outside_temp_c",
            "outside_rh",
            "outside_dew_point_c",
            "notes",
        ]
    )


def ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    for col in empty_frame().columns:
        if col not in df.columns:
            df[col] = None
    return df


def default_spaces_config() -> dict[str, str]:
    return {
        "bucket": os.getenv("DO_SPACES_BUCKET", "").strip(),
        "region": os.getenv("DO_SPACES_REGION", DEFAULT_SPACES_REGION).strip() or DEFAULT_SPACES_REGION,
        "endpoint": os.getenv("DO_SPACES_ENDPOINT", "").strip(),
        "object_key": os.getenv("DO_SPACES_OBJECT_KEY", DEFAULT_SPACES_OBJECT_KEY).strip() or DEFAULT_SPACES_OBJECT_KEY,
        "access_key_id": os.getenv("DO_SPACES_ACCESS_KEY_ID", os.getenv("AWS_ACCESS_KEY_ID", "")).strip(),
        "secret_access_key": os.getenv(
            "DO_SPACES_SECRET_ACCESS_KEY", os.getenv("AWS_SECRET_ACCESS_KEY", "")
        ).strip(),
    }


def normalize_spaces_config(config: Optional[dict[str, str]] = None) -> dict[str, str]:
    config = config or {}
    return {
        "bucket": str(config.get("bucket", "")).strip(),
        "region": str(config.get("region", DEFAULT_SPACES_REGION)).strip() or DEFAULT_SPACES_REGION,
        "endpoint": str(config.get("endpoint", "")).strip(),
        "object_key": str(config.get("object_key", DEFAULT_SPACES_OBJECT_KEY)).strip() or DEFAULT_SPACES_OBJECT_KEY,
        "access_key_id": str(config.get("access_key_id", "")).strip(),
        "secret_access_key": str(config.get("secret_access_key", "")).strip(),
    }


def load_saved_spaces_config() -> dict[str, str]:
    if not os.path.exists(SPACES_CONFIG_PATH):
        return {}
    try:
        with open(SPACES_CONFIG_PATH, "r", encoding="utf-8") as file:
            data = json.load(file)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return normalize_spaces_config(data)


def save_saved_spaces_config(config: dict[str, str]) -> None:
    os.makedirs(os.path.dirname(SPACES_CONFIG_PATH), exist_ok=True)
    with open(SPACES_CONFIG_PATH, "w", encoding="utf-8") as file:
        json.dump(normalize_spaces_config(config), file)


def clear_saved_spaces_config() -> None:
    if os.path.exists(SPACES_CONFIG_PATH):
        os.remove(SPACES_CONFIG_PATH)


def get_spaces_config() -> dict[str, str]:
    if "spaces_config" not in st.session_state:
        config = default_spaces_config()
        saved_config = load_saved_spaces_config()
        if saved_config:
            config.update(saved_config)
        st.session_state["spaces_config"] = normalize_spaces_config(config)
    st.session_state["spaces_config"] = normalize_spaces_config(st.session_state["spaces_config"])
    return st.session_state["spaces_config"]


def spaces_enabled(config: Optional[dict[str, str]] = None) -> bool:
    active_config = normalize_spaces_config(config or get_spaces_config())
    return all(
        [
            active_config["bucket"],
            active_config["object_key"],
            active_config["access_key_id"],
            active_config["secret_access_key"],
        ]
    )


def spaces_endpoint(config: Optional[dict[str, str]] = None) -> str:
    active_config = normalize_spaces_config(config or get_spaces_config())
    endpoint = active_config["endpoint"]
    if endpoint:
        if "://" in endpoint:
            return endpoint
        return f"https://{endpoint}"
    return f"https://{active_config['region']}.digitaloceanspaces.com"


def spaces_client(config: Optional[dict[str, str]] = None):
    active_config = normalize_spaces_config(config or get_spaces_config())
    if boto3 is None or not spaces_enabled(active_config):
        return None
    client_kwargs = {
        "region_name": active_config["region"],
        "endpoint_url": spaces_endpoint(active_config),
        "aws_access_key_id": active_config["access_key_id"],
        "aws_secret_access_key": active_config["secret_access_key"],
    }
    if BotoConfig is not None:
        client_kwargs["config"] = BotoConfig(
            connect_timeout=3,
            read_timeout=5,
            retries={"max_attempts": 1, "mode": "standard"},
        )
    return boto3.client(
        "s3",
        **client_kwargs,
    )


def prepare_data_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return empty_frame().copy()
    df = ensure_columns(df)
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    numeric_cols = [
        "temp_c",
        "rh",
        "lux",
        "uv",
        "co2",
        "outside_temp_c",
        "outside_rh",
        "outside_dew_point_c",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def load_data_from_spaces(config: Optional[dict[str, str]] = None) -> tuple[Optional[pd.DataFrame], Optional[float]]:
    active_config = normalize_spaces_config(config or get_spaces_config())
    client = spaces_client(active_config)
    if client is None:
        return None, None
    try:
        response = client.get_object(Bucket=active_config["bucket"], Key=active_config["object_key"])
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code in {"404", "NoSuchKey", "NotFound"}:
            return None, None
        st.warning(f"Unable to load CSV from DigitalOcean Spaces: {error_code or 'unknown error'}")
        return None, None
    except Exception:
        st.warning("Unable to load CSV from DigitalOcean Spaces.")
        return None, None
    data = response.get("Body")
    last_modified = response.get("LastModified")
    last_modified_ts = last_modified.timestamp() if last_modified else None
    if data is None:
        return empty_frame().copy(), last_modified_ts
    csv_bytes = data.read()
    if not csv_bytes:
        return empty_frame().copy(), last_modified_ts
    try:
        return prepare_data_frame(pd.read_csv(io.BytesIO(csv_bytes))), last_modified_ts
    except EmptyDataError:
        return empty_frame().copy(), last_modified_ts
    except Exception:
        st.warning("Unable to parse CSV from DigitalOcean Spaces.")
        return None, last_modified_ts


def save_data_to_spaces(df: pd.DataFrame, config: Optional[dict[str, str]] = None) -> bool:
    active_config = normalize_spaces_config(config or get_spaces_config())
    client = spaces_client(active_config)
    if client is None:
        return False
    try:
        client.put_object(
            Bucket=active_config["bucket"],
            Key=active_config["object_key"],
            Body=df.to_csv(index=False).encode("utf-8"),
            ContentType="text/csv",
        )
        return True
    except Exception:
        st.warning("Saved locally, but failed to upload CSV to DigitalOcean Spaces.")
        return False


def load_data() -> pd.DataFrame:
    active_config = get_spaces_config()
    local_df = empty_frame().copy()
    local_modified = None
    if os.path.exists(DATA_PATH):
        try:
            local_df = prepare_data_frame(pd.read_csv(DATA_PATH))
        except EmptyDataError:
            local_df = empty_frame().copy()
            os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
            local_df.to_csv(DATA_PATH, index=False)
        except Exception:
            st.warning("Local CSV could not be read. Starting with an empty dataset.")
            local_df = empty_frame().copy()
        local_modified = os.path.getmtime(DATA_PATH)

    spaces_df, _ = load_data_from_spaces(active_config)

    if spaces_df is None:
        if local_modified is not None and spaces_enabled(active_config):
            save_data_to_spaces(local_df, active_config)
        return local_df

    if not spaces_df.empty:
        os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
        spaces_df.to_csv(DATA_PATH, index=False)
        return spaces_df

    if spaces_df.empty and not local_df.empty:
        save_data_to_spaces(local_df, active_config)
        return local_df

    return spaces_df


def save_data(df: pd.DataFrame) -> None:
    active_config = get_spaces_config()
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    df.to_csv(DATA_PATH, index=False)
    save_data_to_spaces(df, active_config)


def format_dt(value: datetime) -> str:
    return value.strftime("%b %d, %Y %I:%M %p")


def format_value(value: Optional[float], digits: int = 1) -> str:
    if value is None or pd.isna(value):
        return "--"
    return f"{value:.{digits}f}"


def format_outside_time(value: Optional[str]) -> str:
    if not value:
        return "--"
    try:
        return datetime.fromisoformat(value).strftime("%b %d, %Y %I:%M %p")
    except ValueError:
        return value


def calc_dew_point(temp_c: float, rh: float) -> Optional[float]:
    if pd.isna(temp_c) or pd.isna(rh) or rh <= 0:
        return None
    a, b = 17.27, 237.7
    alpha = (a * temp_c) / (b + temp_c) + math.log(rh / 100)
    return (b * alpha) / (a - alpha)


@st.cache_data(show_spinner=False, ttl=900)
def fetch_outside_conditions(lat: float, lon: float, timezone: str) -> Optional[dict]:
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,dew_point_2m",
        "timezone": timezone,
    }
    url = f"{OPEN_METEO_URL}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            if response.status != 200:
                return None
            data = json.load(response)
    except Exception:
        return None
    current = data.get("current")
    if not current:
        return None
    return {
        "time": current.get("time"),
        "temp_c": current.get("temperature_2m"),
        "rh": current.get("relative_humidity_2m"),
        "dew_point_c": current.get("dew_point_2m"),
    }


def evaluate_records(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df = df.sort_values(["location", "datetime"]).reset_index(drop=True)
    df["prev_temp"] = df.groupby("location")["temp_c"].shift(1)
    df["prev_rh"] = df.groupby("location")["rh"].shift(1)
    df["prev_time"] = df.groupby("location")["datetime"].shift(1)
    df["delta_hours"] = (df["datetime"] - df["prev_time"]).dt.total_seconds() / 3600

    def classify(row) -> tuple[str, list[str]]:
        flags: list[str] = []
        range_status = "core"

        if row["temp_c"] < GUIDELINES["temp"]["min"] or row["temp_c"] > GUIDELINES["temp"]["max"]:
            range_status = "out"
            flags.append("Temp out of range|danger")

        rh_core_min, rh_core_max = GUIDELINES["rh"]["core"]
        rh_outer_min, rh_outer_max = GUIDELINES["rh"]["outer"]

        if row["rh"] < rh_core_min or row["rh"] > rh_core_max:
            if rh_outer_min <= row["rh"] <= rh_outer_max:
                if range_status != "out":
                    range_status = "outer"
                flags.append("RH in outer band|warn")
            else:
                range_status = "out"
                flags.append("RH out of range|danger")

        if row["rh"] >= 70:
            flags.append("Mould risk|danger")

        if pd.notna(row.get("outside_temp_c")):
            delta_temp = row["temp_c"] - row["outside_temp_c"]
            if abs(delta_temp) > OUTSIDE_TEMP_DELTA_WARN:
                flags.append(f"Temp delta vs outside {delta_temp:+.1f} C|warn")

        if pd.notna(row.get("outside_rh")):
            delta_rh = row["rh"] - row["outside_rh"]
            if abs(delta_rh) > OUTSIDE_RH_DELTA_WARN:
                flags.append(f"RH delta vs outside {delta_rh:+.1f}%|warn")

        if pd.notna(row["delta_hours"]) and row["delta_hours"] <= 24:
            temp_delta = abs(row["temp_c"] - row["prev_temp"]) if pd.notna(row["prev_temp"]) else 0
            rh_delta = abs(row["rh"] - row["prev_rh"]) if pd.notna(row["prev_rh"]) else 0
            if temp_delta > GUIDELINES["temp"]["delta"]:
                flags.append(f"Temp drift {temp_delta:.1f} C/24h|warn")
            if rh_delta > GUIDELINES["rh"]["delta"]:
                flags.append(f"RH drift {rh_delta:.1f}%/24h|warn")

        return range_status, flags

    results = df.apply(classify, axis=1, result_type="expand")
    df["range_status"] = results[0]
    df["flags"] = results[1]
    return df


def flags_to_html(flags: list[str]) -> str:
    if not flags:
        return '<span class="flag">Stable</span>'
    parts = []
    for flag in flags:
        label, level = flag.split("|")
        parts.append(f'<span class="flag {level}">{label}</span>')
    return "".join(parts)


def status_chip(status: str) -> str:
    label_map = {"core": "Core", "outer": "Outer", "out": "Out"}
    label = label_map.get(status, "Core")
    return f'<span class="chip {status}">{label}</span>'


def stat_card_html(label: str, value: str, helper: Optional[str] = None) -> str:
    helper_html = f'<div class="stat-helper">{helper}</div>' if helper else ""
    return (
        '<div class="stat-card">'
        f'<div class="stat-label">{label}</div>'
        f'<div class="stat-value">{value}</div>'
        f"{helper_html}"
        "</div>"
    )


def render_spaces_settings() -> None:
    config = get_spaces_config()
    with st.expander("DigitalOcean Spaces Sync", expanded=False):
        if spaces_enabled(config):
            st.caption("Spaces sync status: configured.")
        else:
            st.caption("Spaces sync status: not configured.")
        st.caption(
            "This keeps the app public while letting you enter credentials at runtime. "
            "Anyone with app access can overwrite these settings."
        )
        with st.form("spaces_settings_form", clear_on_submit=False):
            bucket = st.text_input("Bucket", value=config["bucket"])
            region = st.text_input("Region", value=config["region"])
            endpoint = st.text_input(
                "Endpoint (optional)",
                value=config["endpoint"],
                placeholder="nyc3.digitaloceanspaces.com",
            )
            object_key = st.text_input("Object Key", value=config["object_key"])
            access_key_id = st.text_input(
                "Access Key ID",
                value="",
                type="password",
                help="Leave blank to keep the current value.",
            )
            secret_access_key = st.text_input(
                "Secret Access Key",
                value="",
                type="password",
                help="Leave blank to keep the current value.",
            )
            persist_to_server = st.checkbox(
                "Persist settings on this server",
                value=os.path.exists(SPACES_CONFIG_PATH),
            )
            submitted = st.form_submit_button("Save Spaces Settings")
        if submitted:
            updated = {
                "bucket": bucket,
                "region": region,
                "endpoint": endpoint,
                "object_key": object_key,
                "access_key_id": access_key_id.strip() or config["access_key_id"],
                "secret_access_key": secret_access_key.strip() or config["secret_access_key"],
            }
            updated_config = normalize_spaces_config(updated)
            st.session_state["spaces_config"] = updated_config
            if persist_to_server:
                save_saved_spaces_config(updated_config)
            else:
                clear_saved_spaces_config()
            st.success("Spaces settings saved.")
            st.rerun()
        if st.button("Import local CSV to Spaces now", width="stretch"):
            active_config = get_spaces_config()
            if not spaces_enabled(active_config):
                st.warning("Add Spaces credentials first, then save settings.")
            elif not os.path.exists(DATA_PATH):
                st.warning("No local CSV found to import yet.")
            else:
                try:
                    local_df = prepare_data_frame(pd.read_csv(DATA_PATH))
                except EmptyDataError:
                    local_df = empty_frame().copy()
                except Exception:
                    st.error("Could not read local CSV for import.")
                else:
                    if save_data_to_spaces(local_df, active_config):
                        st.success("Local CSV imported to DigitalOcean Spaces.")
        if st.button("Clear Spaces Settings", width="stretch"):
            st.session_state["spaces_config"] = normalize_spaces_config({})
            clear_saved_spaces_config()
            st.success("Spaces settings cleared.")
            st.rerun()


inject_styles()

with st.spinner("Loading environmental data..."):
    df = load_data()
    outside_data = fetch_outside_conditions(OUTSIDE_LAT, OUTSIDE_LON, OUTSIDE_TZ)

hero_left, hero_right = st.columns([2.3, 1.2])
with hero_left:
    st.markdown(
        """
        <div class="eyebrow">AICCM-ALIGNED ENVIRONMENTAL LOGBOOK</div>
        <h1>Special Collections Environmental Monitoring</h1>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <p class="hero-summary">
            Record temperature, relative humidity, light, and air quality across the Special Collections Room,
            Special Collections Storage, Compactus, and Workroom with scientific clarity.
        </p>
        """,
        unsafe_allow_html=True,
    )
    action_cols = st.columns([1.1, 1])
    with action_cols[0]:
        if not df.empty:
            st.download_button(
                "Download CSV",
                data=df.to_csv(index=False).encode("utf-8"),
                file_name=f"environmental-log-{date.today().isoformat()}.csv",
                mime="text/csv",
            )
        else:
            st.caption("No data to export yet.")
    with action_cols[1]:
        clear_confirm = st.checkbox("Confirm clear all data", key="clear_confirm")
        if st.button("Clear Data") and clear_confirm:
            save_data(empty_frame())
            df = empty_frame().copy()
            st.success("All measurements cleared.")
    render_spaces_settings()

    stats_cols = st.columns(3)
    total_readings = str(len(df))
    last_reading = "--"
    last_location = "--"
    if not df.empty:
        last = df.sort_values("datetime").iloc[-1]
        last_reading = format_dt(last["datetime"])
        last_location = last["location"]
    locations_covered = f"{df['location'].nunique() if not df.empty else 0}/{len(LOCATIONS)}"
    with stats_cols[0]:
        st.markdown(stat_card_html("Total Readings", total_readings), unsafe_allow_html=True)
    with stats_cols[1]:
        st.markdown(stat_card_html("Last Reading", last_reading, last_location), unsafe_allow_html=True)
    with stats_cols[2]:
        st.markdown(stat_card_html("Locations Covered", locations_covered), unsafe_allow_html=True)

with hero_right:
    st.markdown(
        """
        <div class="hero-card">
            <div class="hero-card-title">AICCM Interim Guidelines</div>
            <div class="metric-label">Core Temperature</div>
            <div class="metric-value">15-25 C</div>
            <div class="metric-label" style="margin-top: 0.7rem;">Core RH</div>
            <div class="metric-value">45-55%</div>
            <div class="metric-label" style="margin-top: 0.7rem;">Outer RH Band</div>
            <div class="metric-value">40-60%</div>
            <div style="margin-top: 0.8rem; color: #4c5b5f; font-size: 0.85rem;">
                Daily drift targets: <=4 C and <=5% RH per 24 hours. Seasonal RH drift allowed within outer band.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if outside_data:
        st.markdown(
            f"""
            <div class="hero-card" style="margin-top: 1rem;">
                <div class="hero-card-title">Outside Conditions</div>
                <div style="color:#4c5b5f; font-size: 0.85rem;">{OUTSIDE_LOCATION}</div>
                <div class="metric-label" style="margin-top: 0.6rem;">Temperature</div>
                <div class="metric-value">{format_value(outside_data.get("temp_c"))} C</div>
                <div class="metric-label" style="margin-top: 0.6rem;">Relative Humidity</div>
                <div class="metric-value">{format_value(outside_data.get("rh"))}%</div>
                <div class="metric-label" style="margin-top: 0.6rem;">Dew Point</div>
                <div class="metric-value">{format_value(outside_data.get("dew_point_c"))} C</div>
                <div style="margin-top: 0.8rem; color: #4c5b5f; font-size: 0.85rem;">
                    Updated {format_outside_time(outside_data.get("time"))}
                </div>
                <div style="margin-top: 0.3rem; color: #4c5b5f; font-size: 0.75rem;">
                    Source: Open-Meteo current model data
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div class="hero-card" style="margin-top: 1rem;">
                <div class="hero-card-title">Outside Conditions</div>
                <div style="color:#4c5b5f; font-size: 0.85rem;">{OUTSIDE_LOCATION}</div>
                <div style="margin-top: 0.8rem; color: #4c5b5f; font-size: 0.85rem;">
                    Outside data unavailable right now.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.divider()

with st.expander("Record Measurement", expanded=False):
    with st.form("entry_form", clear_on_submit=False):
        form_left, form_right = st.columns(2)
        with form_left:
            location = st.selectbox("Location", LOCATIONS)
            date_value = st.date_input("Date", value=date.today())
            time_value = st.time_input("Time", value=datetime.now().time().replace(second=0, microsecond=0))
            temp_c = st.number_input("Temperature (C)", min_value=-10.0, max_value=50.0, value=20.0, step=0.1)
            rh = st.number_input("Relative Humidity (%)", min_value=0.0, max_value=100.0, value=50.0, step=0.1)
        with form_right:
            lux = st.number_input("Light (lux, optional)", min_value=0.0, value=0.0, step=1.0)
            uv = st.number_input("UV (uW/lm, optional)", min_value=0.0, value=0.0, step=0.1)
            co2 = st.number_input("CO2 (ppm, optional)", min_value=0.0, value=0.0, step=1.0)
            notes = st.text_area("Notes", placeholder="Condition notes, equipment IDs, notable events", height=120)
        submitted = st.form_submit_button("Record Reading", width="stretch")

if submitted:
    outside_snapshot = fetch_outside_conditions(OUTSIDE_LAT, OUTSIDE_LON, OUTSIDE_TZ)
    new_row = {
        "id": str(uuid.uuid4()),
        "datetime": datetime.combine(date_value, time_value),
        "location": location,
        "temp_c": temp_c,
        "rh": rh,
        "lux": lux,
        "uv": uv,
        "co2": co2,
        "outside_time": outside_snapshot.get("time") if outside_snapshot else None,
        "outside_temp_c": outside_snapshot.get("temp_c") if outside_snapshot else None,
        "outside_rh": outside_snapshot.get("rh") if outside_snapshot else None,
        "outside_dew_point_c": outside_snapshot.get("dew_point_c") if outside_snapshot else None,
        "notes": notes.strip(),
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    save_data(df)
    st.success("Measurement recorded.")

df_eval = evaluate_records(df)

st.subheader("Current Status")
status_cols = st.columns(4)
for col, location in zip(status_cols, LOCATIONS):
    target = df_eval[df_eval["location"] == location]
    with col:
        if target.empty:
            st.markdown(
                f"""
                <div class="status-card state-awaiting">
                    <div class="status-card-title">{location}</div>
                    <div class="status-card-meta">No readings yet.</div>
                    <span class="chip awaiting">Awaiting</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            continue
        latest = target.sort_values("datetime").iloc[-1]
        flags_html = flags_to_html(latest["flags"])
        delta_line = ""
        if outside_data and outside_data.get("temp_c") is not None and outside_data.get("rh") is not None:
            delta_temp = latest["temp_c"] - outside_data["temp_c"]
            delta_rh = latest["rh"] - outside_data["rh"]
            delta_line = (
                f'<div class="status-card-delta">'
                f'Delta vs outside: {delta_temp:+.1f} C / {delta_rh:+.1f}% RH'
                f"</div>"
            )
        st.markdown(
            f"""
            <div class="status-card state-{latest["range_status"]}">
                <div class="status-card-title">{location}</div>
                <div class="status-card-meta">{format_dt(latest["datetime"])}</div>
                <div class="status-card-reading">{latest["temp_c"]:.1f} C  /  {latest["rh"]:.1f}% RH</div>
                {delta_line}
                {status_chip(latest["range_status"])}
                <div class="status-flags">{flags_html}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.divider()

trend_tab, table_tab = st.tabs(["Trend Analysis", "Recorded Measurements"])

with trend_tab:
    st.subheader("Trend Analysis")
    location_choice = st.selectbox("Location", LOCATIONS, key="trend_location")
    location_df = df_eval[df_eval["location"] == location_choice].sort_values("datetime")
    if location_df.shape[0] < 2:
        st.info("Add at least two readings to see a trend line.")
    else:
        chart_df = location_df.copy()
        chart_df["datetime"] = pd.to_datetime(chart_df["datetime"])

        temp_long = (
            chart_df.melt(
                id_vars=["datetime"],
                value_vars=["temp_c", "outside_temp_c"],
                var_name="series_key",
                value_name="value",
            )
            .dropna(subset=["value"])
        )
        temp_long["series"] = temp_long["series_key"].map(
            {"temp_c": "Indoor Temp", "outside_temp_c": "Outside Temp (dashed)"}
        )
        temp_long["source"] = temp_long["series_key"].map({"temp_c": "Indoor", "outside_temp_c": "Outside"})
        temp_long = temp_long[temp_long["series"].notna()][["datetime", "value", "series", "source"]]

        rh_long = (
            chart_df.melt(
                id_vars=["datetime"],
                value_vars=["rh", "outside_rh"],
                var_name="series_key",
                value_name="value",
            )
            .dropna(subset=["value"])
        )
        rh_long["series"] = rh_long["series_key"].map({"rh": "Indoor RH", "outside_rh": "Outside RH (dashed)"})
        rh_long["source"] = rh_long["series_key"].map({"rh": "Indoor", "outside_rh": "Outside"})
        rh_long = rh_long[rh_long["series"].notna()][["datetime", "value", "series", "source"]]

        preferred_order = ["Indoor Temp", "Outside Temp (dashed)", "Indoor RH", "Outside RH (dashed)"]
        palette = {
            "Indoor Temp": "#b5653a",
            "Outside Temp (dashed)": "#c8956f",
            "Indoor RH": "#48a3a6",
            "Outside RH (dashed)": "#7fbfc1",
        }
        present_series = (
            pd.concat([temp_long["series"], rh_long["series"]], ignore_index=True).dropna().unique().tolist()
        )
        series_domain = [series for series in preferred_order if series in present_series]
        series_range = [palette[series] for series in series_domain]

        if not series_domain:
            st.info("No trend values available for this location yet.")
        else:
            legend = alt.Legend(title="Key", orient="top", direction="horizontal", columns=2)
            dash_scale = alt.Scale(domain=["Indoor", "Outside"], range=[[8, 0], [6, 4]])
            shared_color = alt.Scale(domain=series_domain, range=series_range)
            time_axis = alt.Axis(
                title="Datetime",
                labelAngle=-20,
                labelPadding=10,
                labelLimit=140,
                format="%b %d %H:%M",
            )
            layers = []

            if not temp_long.empty:
                temp_chart = (
                    alt.Chart(temp_long)
                    .mark_line(strokeWidth=3, interpolate="monotone")
                    .encode(
                        x=alt.X("datetime:T", axis=time_axis),
                        y=alt.Y("value:Q", axis=alt.Axis(title="Temp (C)")),
                        color=alt.Color("series:N", scale=shared_color, legend=legend),
                        strokeDash=alt.StrokeDash("source:N", scale=dash_scale, legend=None),
                        tooltip=[
                            alt.Tooltip("datetime:T", title="Date/Time"),
                            alt.Tooltip("series:N", title="Series"),
                            alt.Tooltip("value:Q", title="Value", format=".1f"),
                        ],
                    )
                )
                layers.append(temp_chart)

            if not rh_long.empty:
                rh_chart = (
                    alt.Chart(rh_long)
                    .mark_line(strokeWidth=3, interpolate="monotone")
                    .encode(
                        x=alt.X("datetime:T", axis=time_axis),
                        y=alt.Y("value:Q", axis=alt.Axis(title="RH (%)", orient="right")),
                        color=alt.Color(
                            "series:N",
                            scale=shared_color,
                            legend=legend if temp_long.empty else None,
                        ),
                        strokeDash=alt.StrokeDash("source:N", scale=dash_scale, legend=None),
                        tooltip=[
                            alt.Tooltip("datetime:T", title="Date/Time"),
                            alt.Tooltip("series:N", title="Series"),
                            alt.Tooltip("value:Q", title="Value", format=".1f"),
                        ],
                    )
                )
                layers.append(rh_chart)

            if layers:
                layered = (
                    alt.layer(*layers)
                    .resolve_scale(y="independent")
                    .properties(
                        height=430,
                        width="container",
                        padding={"left": 10, "top": 8, "right": 40, "bottom": 58},
                    )
                    .configure_view(strokeOpacity=0)
                    .configure_axis(
                        gridColor="rgba(16, 33, 41, 0.15)",
                        domainColor="rgba(16, 33, 41, 0.35)",
                        tickColor="rgba(16, 33, 41, 0.35)",
                        labelColor="#33464d",
                        titleColor="#112129",
                        titleFont="Fraunces",
                        labelFont="Public Sans",
                    )
                    .configure_axisX(
                        labelFlush=False,
                        labelPadding=10,
                        titlePadding=16,
                    )
                    .configure_legend(
                        labelFont="Public Sans",
                        titleFont="Fraunces",
                        labelColor="#33464d",
                        titleColor="#112129",
                        symbolStrokeWidth=4,
                    )
                )
                st.altair_chart(layered)
            else:
                st.info("No trend values available for this location yet.")

with table_tab:
    st.subheader("Recorded Measurements")
    filter_loc = st.selectbox("Filter", ["All Locations"] + LOCATIONS, key="table_filter")
    table_df = df_eval.copy()
    if filter_loc != "All Locations":
        table_df = table_df[table_df["location"] == filter_loc]

    if table_df.empty:
        st.info("No measurements recorded yet.")
    else:
        table_df = table_df.sort_values("datetime", ascending=False)
        table_df["dew_point_c"] = table_df.apply(lambda r: calc_dew_point(r["temp_c"], r["rh"]), axis=1)
        table_df["status"] = table_df["range_status"].str.title()
        table_df["flags_text"] = table_df["flags"].apply(lambda f: ", ".join([x.split("|")[0] for x in f]) if f else "Stable")
        table_df["delta_temp_c"] = table_df["temp_c"] - table_df["outside_temp_c"]
        table_df["delta_rh"] = table_df["rh"] - table_df["outside_rh"]

        display_df = table_df[
            [
                "datetime",
                "location",
                "temp_c",
                "rh",
                "dew_point_c",
                "outside_temp_c",
                "outside_rh",
                "outside_dew_point_c",
                "delta_temp_c",
                "delta_rh",
                "status",
                "flags_text",
            ]
        ].copy()
        display_df.columns = [
            "Date",
            "Location",
            "Temp (C)",
            "RH (%)",
            "Dew Point (C)",
            "Outside Temp (C)",
            "Outside RH (%)",
            "Outside Dew Point (C)",
            "Delta Temp (C)",
            "Delta RH (%)",
            "Status",
            "Flags",
        ]
        numeric_columns = [
            "Temp (C)",
            "RH (%)",
            "Dew Point (C)",
            "Outside Temp (C)",
            "Outside RH (%)",
            "Outside Dew Point (C)",
            "Delta Temp (C)",
            "Delta RH (%)",
        ]
        display_df[numeric_columns] = display_df[numeric_columns].round(1)
        display_df["Date"] = display_df["Date"].dt.strftime("%b %d, %Y %I:%M %p")
        st.dataframe(display_df, width="stretch", hide_index=True)

st.divider()

st.subheader("AICCM Guideline Lens")
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(
        """
        <div class="lens-card">
            <div class="lens-card-title">Temperature</div>
            <div class="lens-card-copy">
                Core range <strong>15-25 C</strong>. Rapid drift should be minimized; day-to-day fluctuation goal
                <=4 C within 24 hours.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col2:
    st.markdown(
        """
        <div class="lens-card">
            <div class="lens-card-title">Relative Humidity</div>
            <div class="lens-card-copy">
                Core range <strong>45-55%</strong> with <=5% RH drift per 24 hours. Seasonal drift is tolerated in
                the outer band <strong>40-60%</strong>.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col3:
    st.markdown(
        """
        <div class="lens-card">
            <div class="lens-card-title">Collections Sensitivity</div>
            <div class="lens-card-copy">
                Some materials require tighter control or different targets. Light, airflow, and loan requirements
                should be set with professional conservation advice.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col4:
    st.markdown(
        """
        <div class="lens-card">
            <div class="lens-card-title">Mould Risk</div>
            <div class="lens-card-copy">
                Sustained RH above ~70% increases mould risk. Maintain clean, dry storage with good air circulation.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
