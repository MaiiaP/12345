from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import streamlit as st
from pdf2image import convert_from_path


BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR / "data" / "results"
PDF_DIR = BASE_DIR / "data" / "pdfs"

KEY_LABELS_RU = {
    "indications": "Показания",
    "dosage": "Схемы дозирования",
    "tags": "Теги",
    "indication": "Схема",
    "startDosage": "Начальная доза",
    "dose": "Доза",
    "unit": "Единица",
    "interval": "Интервал",
    "intervalUnit": "Единица интервала",
    "intakeCount": "Кратность приема",
    "daily_dose": "Суточная доза",
    "courseDurationMin": "Минимальная длительность курса",
    "courseDurationMax": "Максимальная длительность курса",
    "courseDuration": "Длительность курса",
    "loading_dose": "Нагрузочная доза",
    "courseMaxF": "Ограничение курса (формула)",
    "expr": "Формула",
    "vars": "Переменные",
    "schemaDescription": "Описание схемы",
    "step1": "Шаг 1",
    "step2": "Шаг 2",
    "step3": "Шаг 3",
    "specialPatientGroups": "Особые группы пациентов",
    "icd10_code": "Код МКБ-10",
    "disease": "Состояние/группа",
    "administration": "Способ применения",
    "time": "Время приема",
    "food": "Связь с приемом пищи",
    "form": "Лекарственная форма",
}


def humanize_iso_duration(value: str) -> str:
    m = re.fullmatch(r"P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)W)?(?:(\d+)D)?", value.strip())
    if not m:
        return value
    years = int(m.group(1) or 0)
    months = int(m.group(2) or 0)
    weeks = int(m.group(3) or 0)
    days = int(m.group(4) or 0)
    parts = []
    if years:
        parts.append(f"{years} г.")
    if months:
        parts.append(f"{months} мес.")
    if weeks:
        parts.append(f"{weeks} нед.")
    if days:
        parts.append(f"{days} дн.")
    return " ".join(parts) if parts else value


def humanize_value(key: str, value: Any) -> Any:
    if isinstance(value, str) and key in {"courseDurationMin", "courseDurationMax", "courseDuration"}:
        return humanize_iso_duration(value)
    if key == "intervalUnit":
        mapping = {"DAY": "день", "WEEK": "неделя", "MONTH": "месяц", "YEAR": "год"}
        return mapping.get(str(value), value)
    return value


@st.cache_data(show_spinner=False)
def list_result_files() -> list[str]:
    if not RESULTS_DIR.exists():
        return []
    files = sorted([p.name for p in RESULTS_DIR.glob("*.json") if not p.name.startswith("_")])
    filtered: list[str] = []
    prednisolone_kept = False
    for name in files:
        if "преднизолон" in name.lower():
            if prednisolone_kept:
                continue
            prednisolone_kept = True
        filtered.append(name)
    return filtered


@st.cache_data(show_spinner=False)
def load_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def label_ru(key: str) -> str:
    return KEY_LABELS_RU.get(key, key)


def render_scalar_line(key: str, value: Any) -> None:
    if value is None:
        return
    if isinstance(value, str) and not value.strip():
        return
    if key == "tags":
        render_tags(str(value))
        return
    value = humanize_value(key, value)
    value_class = "dense-value"
    if key == "schemaDescription":
        value_class = "dense-value-regular"
    st.markdown(
        (
            "<div class='dense-line'>"
            f"<span class='dense-key'>{label_ru(key)}:</span> <span class='{value_class}'>{value}</span>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_tags(raw_tags: str) -> None:
    parts = [p.strip() for p in raw_tags.split(";") if p.strip()]
    if not parts:
        return
    html_parts = []
    palette = ["#E3F2FD", "#E8F5E9", "#FFF3E0", "#F3E5F5", "#E0F7FA"]
    for idx, part in enumerate(parts):
        bg = palette[idx % len(palette)]
        html_parts.append(
            f"<span style='background:{bg}; color:#111111; padding:4px 8px; border-radius:6px; "
            f"margin-right:6px; display:inline-block; margin-bottom:6px;'>{part}</span>"
        )
    st.markdown(f"**{label_ru('tags')}:**  " + "".join(html_parts), unsafe_allow_html=True)


def open_block(title: str) -> None:
    st.markdown(
        (
            "<div style='border:1px solid #d9d9d9; border-radius:10px; "
            "padding:8px 10px; margin:6px 0; background:#fafafa;'>"
            f"<div style='font-weight:700; margin-bottom:4px; line-height:1.05; color:#111111;'>{title}</div>"
        ),
        unsafe_allow_html=True,
    )


def open_block_soft(title: str) -> None:
    st.markdown(
        (
            "<div style='border:1px solid #d9d9d9; border-radius:10px; "
            "padding:8px 10px; margin:6px 0; background:#f5f8ff;'>"
            f"<div style='font-weight:700; margin-bottom:4px; line-height:1.05; color:#111111;'>{title}</div>"
        ),
        unsafe_allow_html=True,
    )


def close_block() -> None:
    st.markdown("</div>", unsafe_allow_html=True)


def render_structured(data: Any, level: int = 0, parent_key: str = "") -> None:
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, dict):
                if key != "indication":
                    if key == "administration":
                        open_block_soft(label_ru(key))
                        render_structured(value, level + 1, key)
                        close_block()
                        continue
                    st.markdown(
                        f"<div class='dense-subtitle'>{label_ru(key)}</div>",
                        unsafe_allow_html=True,
                    )
                render_structured(value, level + 1, key)
            elif isinstance(value, list):
                if key == "dosage":
                    st.markdown(
                        "<hr style='border:none; border-top:1px solid #e5e7eb; margin:6px 0 8px 0;'>",
                        unsafe_allow_html=True,
                    )
                st.markdown(
                    f"<div class='dense-subtitle'>{label_ru(key)}</div>",
                    unsafe_allow_html=True,
                )
                if not value:
                    st.caption("Пусто")
                    continue
                for idx, item in enumerate(value, start=1):
                    if isinstance(item, (dict, list)):
                        open_block(f"Схема {idx}")
                        render_structured(item, level + 1, key)
                        close_block()
                    else:
                        st.markdown(f"- {item}")
            else:
                render_scalar_line(key, value)
    elif isinstance(data, list):
        for idx, item in enumerate(data, start=1):
            open_block(f"Схема {idx}")
            render_structured(item, level + 1, parent_key)
            close_block()
    else:
        st.write(data)


def resolve_bin(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    mac_path = Path("/opt/homebrew/bin") / name
    if mac_path.exists():
        return str(mac_path)
    return name


@st.cache_data(show_spinner=False)
def find_section_page(pdf_path: str, section: str = "4.1") -> int:
    marker = re.compile(r"\b4[.,]1\b", flags=re.IGNORECASE)
    try:
        proc = subprocess.run(
            [resolve_bin("pdftotext"), "-layout", pdf_path, "-"],
            capture_output=True,
            text=True,
            check=True,
        )
        pages = proc.stdout.split("\f")
        for idx, text in enumerate(pages, start=1):
            if marker.search(text):
                return idx
    except Exception:
        return 1
    return 1


@st.cache_data(show_spinner=False)
def render_pdf_page_as_image(pdf_path: str, page: int):
    images = convert_from_path(
        pdf_path,
        dpi=120,
        first_page=page,
        last_page=page,
        fmt="png",
    )
    return images[0] if images else None


@st.cache_data(show_spinner=False)
def get_pdf_page_count(pdf_path: str) -> int:
    try:
        proc = subprocess.run(
            [resolve_bin("pdfinfo"), pdf_path],
            capture_output=True,
            text=True,
            check=True,
        )
        for line in proc.stdout.splitlines():
            if line.lower().startswith("pages:"):
                return max(1, int(line.split(":", 1)[1].strip()))
    except Exception:
        return 1
    return 1


def render_page_control(total_pages: int, page_state_key: str, key_prefix: str, show_label: bool = True) -> None:
    page = int(st.session_state[page_state_key])
    if show_label:
        st.caption(f"Страница {page} из {total_pages}")
    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("← Назад", key=f"{key_prefix}_prev", use_container_width=True):
            page = max(1, page - 1)
    with c2:
        if st.button("Вперед →", key=f"{key_prefix}_next", use_container_width=True):
            page = min(total_pages, page + 1)

    st.session_state[page_state_key] = min(max(int(page), 1), total_pages)


def render_pdf(pdf_path: Path, state_key: str) -> None:
    if not pdf_path.exists():
        st.error(f"PDF не найден: `{pdf_path}`")
        return

    total_pages = get_pdf_page_count(str(pdf_path))
    start_page = find_section_page(str(pdf_path), "4.1")
    start_page = min(max(start_page, 1), total_pages)

    page_state_key = f"pdf_page_{state_key}"
    if page_state_key not in st.session_state:
        st.session_state[page_state_key] = start_page

    render_page_control(total_pages, page_state_key, f"top_{state_key}", show_label=True)

    current_page = int(st.session_state[page_state_key])
    try:
        img = render_pdf_page_as_image(str(pdf_path), current_page)
        if img is not None:
            st.image(
                img,
                use_container_width=True,
                caption=f"{pdf_path.name}, страница {current_page}/{total_pages}",
            )
            render_page_control(total_pages, page_state_key, f"bottom_{state_key}", show_label=False)
            return
    except Exception:
        pass

    st.warning("Не удалось отрендерить страницу PDF в приложении. Открываю fallback-ссылку.")
    st.markdown(f"[Открыть PDF-файл]({pdf_path.as_uri()})")


def main() -> None:
    st.set_page_config(
        page_title="Дозировки: просмотр",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(
        """
        <style>
        /* Hide/transparent Streamlit top chrome (Deploy header) */
        [data-testid="stHeader"] {
            background: transparent !important;
        }
        [data-testid="stToolbar"] {
            display: none !important;
        }
        #MainMenu {
            visibility: hidden;
        }
        section[data-testid="stSidebar"] {
            display: none !important;
        }
        [data-testid="collapsedControl"] {
            display: none !important;
        }
        [data-testid="stAppViewContainer"] .main .block-container {
            padding-top: 0 !important;
            padding-bottom: 0 !important;
        }
        [data-testid="stAppViewContainer"] .main {
            padding-top: 0 !important;
            padding-bottom: 0 !important;
        }
        [data-testid="stMainBlockContainer"] {
            padding-top: 0 !important;
            padding-bottom: 0 !important;
            margin-top: 0 !important;
            margin-bottom: 0 !important;
        }
        [data-testid="stAppViewContainer"] .main > div {
            padding-top: 0 !important;
            padding-bottom: 0 !important;
            margin-top: 0 !important;
            margin-bottom: 0 !important;
        }
        [data-testid="stVerticalBlock"] > div:first-child {
            margin-top: 0 !important;
            padding-top: 0 !important;
        }
        section[data-testid="stSidebar"][aria-expanded="true"] {
            width: 240px !important;
            min-width: 240px !important;
        }
        section[data-testid="stSidebar"] > div {
            padding-top: 0.3rem !important;
        }
        [data-testid="stAppViewContainer"] .main .block-container {
            max-width: 100% !important;
            padding-left: 0.6rem !important;
            padding-right: 0.6rem !important;
        }

        .dense-line {
            margin: 0.04rem 0;
            line-height: 1.0;
            font-size: 0.96rem;
            color: #111111;
        }
        .dense-key {
            font-weight: 400;
            color: #111111;
        }
        .dense-value {
            font-weight: 700;
            color: #111111;
        }
        .dense-value-regular {
            font-weight: 400;
            color: #111111;
        }
        .dense-subtitle {
            font-weight: 700;
            margin-top: 0.14rem;
            margin-bottom: 0.14rem;
            line-height: 1.05;
            color: #111111;
        }
        @media (prefers-color-scheme: dark) {
            .dense-line,
            .dense-key,
            .dense-value,
            .dense-value-regular,
            .dense-subtitle {
                color: #ffffff !important;
            }
        }
        /* Denser text layout for the left column (scheme) */
        div[data-testid="stVerticalBlock"] div:has(> #two-col-marker)
        + div[data-testid="stHorizontalBlock"]
        > div[data-testid="column"]:nth-child(1) p,
        div[data-testid="stVerticalBlock"] div:has(> #two-col-marker)
        + div[data-testid="stHorizontalBlock"]
        > div[data-testid="column"]:nth-child(1) li {
            line-height: 0.98;
            margin-top: 0.01rem;
            margin-bottom: 0.01rem;
        }
        div[data-testid="stVerticalBlock"] div:has(> #two-col-marker)
        + div[data-testid="stHorizontalBlock"]
        > div[data-testid="column"]:nth-child(1) ul {
            margin-top: 0.02rem;
            margin-bottom: 0.02rem;
            padding-left: 1rem;
        }
        div[data-testid="stVerticalBlock"] div:has(> #two-col-marker)
        + div[data-testid="stHorizontalBlock"]
        > div[data-testid="column"]:nth-child(1) ul li {
            line-height: 0.95;
            margin-top: 0;
            margin-bottom: 0;
            padding-top: 0;
            padding-bottom: 0;
        }
        div[data-testid="stVerticalBlock"] div:has(> #two-col-marker)
        + div[data-testid="stHorizontalBlock"]
        > div[data-testid="column"]:nth-child(1) h4,
        div[data-testid="stVerticalBlock"] div:has(> #two-col-marker)
        + div[data-testid="stHorizontalBlock"]
        > div[data-testid="column"]:nth-child(1) h5,
        div[data-testid="stVerticalBlock"] div:has(> #two-col-marker)
        + div[data-testid="stHorizontalBlock"]
        > div[data-testid="column"]:nth-child(1) h6 {
            line-height: 1.0;
            margin-top: 0.04rem;
            margin-bottom: 0.04rem;
        }
        div[data-testid="stVerticalBlock"] div:has(> #two-col-marker)
        + div[data-testid="stHorizontalBlock"]
        > div[data-testid="column"]:nth-child(1) div[data-testid="stMarkdownContainer"] {
            margin-bottom: 0.01rem;
        }
        div[data-testid="stVerticalBlock"] div:has(> #two-col-marker)
        + div[data-testid="stHorizontalBlock"]
        > div[data-testid="column"]:nth-child(1) div[data-testid="stDivider"] {
            margin-top: 0.04rem;
            margin-bottom: 0.04rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    files = list_result_files()
    if not files:
        st.error(f"В папке результатов нет JSON-файлов: `{RESULTS_DIR}`")
        return

    selected = st.selectbox("Препарат", files, key="top_drug_select")

    result_path = RESULTS_DIR / selected
    pdf_path = PDF_DIR / f"{Path(selected).stem}.pdf"

    st.markdown('<div id="two-col-marker" style="display:none;height:0;margin:0;padding:0;"></div>', unsafe_allow_html=True)
    left, middle, right = st.columns([0.78, 0.02, 1.2], gap="small")

    with left:
        st.subheader("Результат")
        left_panel = st.container(height=820, border=False)
        with left_panel:
            if result_path.exists():
                result_data = load_json(str(result_path))
                render_structured(result_data)
            else:
                st.error(f"Файл не найден: `{result_path}`")

    with middle:
        st.markdown(
            "<div style='height: 860px; width: 1px; background: #e5e7eb; margin: 0 auto;'></div>",
            unsafe_allow_html=True,
        )

    with right:
        st.subheader("Оригинал")
        right_panel = st.container(height=820, border=False)
        with right_panel:
            render_pdf(pdf_path, state_key=Path(selected).stem)


if __name__ == "__main__":
    main()
